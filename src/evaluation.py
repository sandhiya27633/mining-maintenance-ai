"""
evaluation.py — Evaluation Engine
===================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All metrics computed here are based on SYNTHETIC data only.
They do NOT represent real vehicle failure rates or field performance.

This module computes the full evaluation suite from Phase 1 design Section 10:

  PRIMARY METRICS (FR-10)
  ------------------------
  - Total breakdowns: prototype vs baseline
  - Breakdowns avoided (baseline - prototype)
  - Breakdown reduction %  (target: >= 20%)
  - Maintenance frequency (service actions / fleet-days)
  - Maintenance efficiency (breakdowns avoided / additional interventions)

  ERROR ANALYSIS (Section 10.3)
  --------------------------------
  - True Positives  : High/Critical flags followed by breakdown within 7 days
  - False Positives : High/Critical flags NOT followed by breakdown within 7 days
  - False Negatives : Low/Normal flags followed by breakdown within 7 days
  - Missed Breakdowns: breakdown with no High/Critical flag in preceding 7 days
  - Average warning lead time: mean days from first High flag to breakdown

  SCENARIO ANALYSIS (Section 10.2)
  -----------------------------------
  - NORMAL scenario (days 1-300) vs DISRUPTION scenario (days 301-330)
  - Both models compared per scenario

  SENSITIVITY ANALYSIS (Section 8.6)
  -------------------------------------
  - Three weight configs: Default, Fault-Heavy, Load-Heavy
  - Each produces its own DCSS distribution and breakdown count

All results are returned as a structured EvaluationReport dataclass,
persisted to data/processed/evaluation_results.json and to SQLite.

Usage:
    from evaluation import run_evaluation
    report = run_evaluation()

Standalone:
    python src/evaluation.py
"""

from __future__ import annotations

import json
import sys
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg
from feature_engineering import run_feature_engineering
from duty_cycle_model import run_duty_cycle_model, compute_dcss_dataframe
from maintenance_engine import apply_recommendations
from baseline import apply_baseline
from failure_simulator import simulate_breakdowns, build_initial_service_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("evaluation")

# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class ScenarioMetrics:
    """Metrics broken down by scenario tag (NORMAL / DISRUPTION / ALL)."""
    scenario: str
    total_records: int
    prototype_breakdowns: int
    baseline_breakdowns: int
    breakdowns_avoided: int
    reduction_pct: float
    prototype_prevented: int
    baseline_prevented: int
    avg_prototype_dcss: float
    avg_baseline_interval: float
    avg_prototype_interval: float


@dataclass
class ErrorAnalysis:
    """Precision / recall style error analysis for the prototype model."""
    true_positives: int       # HIGH/CRITICAL flag -> breakdown within window
    false_positives: int      # HIGH/CRITICAL flag -> NO breakdown within window
    false_negatives: int      # LOW/NORMAL flag  -> breakdown within window
    true_negatives: int       # LOW/NORMAL flag  -> NO breakdown within window
    missed_breakdowns: int    # breakdown with NO high flag in preceding window
    precision: float          # TP / (TP + FP)
    recall: float             # TP / (TP + FN)
    f1_score: float           # harmonic mean of precision and recall
    avg_warning_lead_days: float  # mean days: first HIGH flag -> breakdown
    warning_window_days: int  # BREAKDOWN_WARNING_WINDOW_DAYS from config


@dataclass
class SensitivityResult:
    """Result for one weight configuration in sensitivity analysis."""
    config_name: str
    weights: Dict[str, float]
    avg_dcss: float
    prototype_breakdowns: int
    breakdowns_avoided: int
    reduction_pct: float
    risk_distribution: Dict[str, int]
    avg_recommended_interval: float


@dataclass
class EvaluationReport:
    """Master evaluation report. All values are SYNTHETIC."""
    # ---- Identity ----
    synthetic_data: bool = True
    model_version: str = cfg.MODEL_VERSION
    num_vehicles: int = cfg.NUM_VEHICLES
    simulation_days: int = cfg.SIMULATION_DAYS
    total_vehicle_days: int = cfg.NUM_VEHICLES * cfg.SIMULATION_DAYS
    random_seed: int = cfg.RANDOM_SEED

    # ---- Primary metrics (default weight config) ----
    prototype_breakdowns: int = 0
    baseline_breakdowns: int = 0
    breakdowns_avoided: int = 0
    reduction_pct: float = 0.0
    target_reduction_pct: float = cfg.BREAKDOWN_REDUCTION_TARGET_PCT
    target_met: bool = False
    prototype_prevented: int = 0
    baseline_prevented: int = 0

    # ---- Maintenance frequency ----
    prototype_maintenance_freq: float = 0.0   # events / vehicle / day
    baseline_maintenance_freq: float = 0.0
    avg_prototype_interval_days: float = 0.0
    avg_baseline_interval_days: float = float(cfg.BASELINE_INTERVAL_DAYS)

    # ---- Maintenance efficiency ----
    # Additional interventions = extra service events prototype triggers vs baseline
    additional_interventions: int = 0
    maintenance_efficiency: float = 0.0  # breakdowns_avoided / additional_interventions

    # ---- Scenario analysis ----
    scenario_results: List[ScenarioMetrics] = field(default_factory=list)

    # ---- Error analysis ----
    error_analysis: Optional[ErrorAnalysis] = None

    # ---- Sensitivity analysis ----
    sensitivity_results: List[SensitivityResult] = field(default_factory=list)

    # ---- Honest reporting notes ----
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Primary metrics computation
# ---------------------------------------------------------------------------

def _get_prevented_column(df: pd.DataFrame) -> str:
    """Return the simulator's prevented-breakdown column name."""
    if "sim_breakdown_prevented" in df.columns:
        return "sim_breakdown_prevented"
    if "breakdown_prevented" in df.columns:
        return "breakdown_prevented"
    raise KeyError(
        "Prevented-breakdown column not found. Expected "
        "'sim_breakdown_prevented' or 'breakdown_prevented'."
    )


def _sum_prevented(df: pd.DataFrame) -> int:
    """Safely count prevented breakdowns from simulator output."""
    return int(df[_get_prevented_column(df)].sum())


def compute_primary_metrics(
    proto_sim: pd.DataFrame,
    baseline_sim: pd.DataFrame,
) -> dict:
    """
    Compute the primary evaluation metrics from the two simulation outputs.

    Parameters
    ----------
    proto_sim : pd.DataFrame    output of simulate_breakdowns(..., model_label='prototype')
    baseline_sim : pd.DataFrame output of simulate_breakdowns(..., model_label='baseline')

    Returns
    -------
    dict with all primary metric keys
    """
    proto_bd    = int(proto_sim["sim_breakdown"].sum())
    base_bd     = int(baseline_sim["sim_breakdown"].sum())
    proto_prev  = _sum_prevented(proto_sim)
    base_prev   = _sum_prevented(baseline_sim)
    avoided     = base_bd - proto_bd
    reduction   = round(100 * avoided / base_bd, 4) if base_bd > 0 else 0.0

    # Maintenance frequency: service events / vehicle-days
    # A service event is triggered at each interval. Approximate from recommended intervals.
    if "recommended_interval_days" in proto_sim.columns:
        avg_proto_iv = float(proto_sim["recommended_interval_days"].mean())
    else:
        avg_proto_iv = float(cfg.STANDARD_INTERVAL_DAYS)

    total_vd = cfg.NUM_VEHICLES * cfg.SIMULATION_DAYS
    proto_services = total_vd / max(avg_proto_iv, 1)
    base_services  = total_vd / cfg.BASELINE_INTERVAL_DAYS
    proto_freq     = round(proto_services / total_vd, 6)
    base_freq      = round(base_services  / total_vd, 6)

    additional_interventions = max(0, int(proto_services - base_services))
    if additional_interventions > 0:
        efficiency = round(avoided / additional_interventions, 4)
    elif avoided > 0:
        efficiency = float("inf")   # breakdowns avoided at no extra cost
    else:
        efficiency = 0.0

    return {
        "prototype_breakdowns":      proto_bd,
        "baseline_breakdowns":       base_bd,
        "breakdowns_avoided":        avoided,
        "reduction_pct":             reduction,
        "prototype_prevented":       proto_prev,
        "baseline_prevented":        base_prev,
        "avg_prototype_interval":    round(avg_proto_iv, 2),
        "avg_baseline_interval":     float(cfg.BASELINE_INTERVAL_DAYS),
        "prototype_maintenance_freq": proto_freq,
        "baseline_maintenance_freq":  base_freq,
        "additional_interventions":  additional_interventions,
        "maintenance_efficiency":    efficiency,
        "target_met":                reduction >= cfg.BREAKDOWN_REDUCTION_TARGET_PCT,
    }


# ---------------------------------------------------------------------------
# Scenario analysis
# ---------------------------------------------------------------------------

def compute_scenario_metrics(
    proto_sim: pd.DataFrame,
    baseline_sim: pd.DataFrame,
) -> List[ScenarioMetrics]:
    """
    Compute breakdown metrics broken down by scenario tag.

    Scenarios: NORMAL, DISRUPTION, ALL (full dataset).
    """
    results = []
    for tag in ["NORMAL", "DISRUPTION", "ALL"]:
        if tag == "ALL":
            p_sub = proto_sim
            b_sub = baseline_sim
        else:
            p_sub = (
                proto_sim[proto_sim["scenario_tag"] == tag]
                if "scenario_tag" in proto_sim.columns
                else proto_sim.iloc[0:0].copy()
            )
            b_sub = (
                baseline_sim[baseline_sim["scenario_tag"] == tag]
                if "scenario_tag" in baseline_sim.columns
                else baseline_sim.iloc[0:0].copy()
            )

        p_bd    = int(p_sub["sim_breakdown"].sum())
        b_bd    = int(b_sub["sim_breakdown"].sum())
        avoided = b_bd - p_bd
        red     = round(100 * avoided / b_bd, 2) if b_bd > 0 else 0.0

        avg_dcss = float(p_sub["dcss"].mean()) if "dcss" in p_sub.columns else 0.0
        avg_proto_iv = float(p_sub["recommended_interval_days"].mean()) \
            if "recommended_interval_days" in p_sub.columns else float(cfg.STANDARD_INTERVAL_DAYS)

        results.append(ScenarioMetrics(
            scenario=tag,
            total_records=len(p_sub),
            prototype_breakdowns=p_bd,
            baseline_breakdowns=b_bd,
            breakdowns_avoided=avoided,
            reduction_pct=red,
            prototype_prevented=_sum_prevented(p_sub),
            baseline_prevented=_sum_prevented(b_sub),
            avg_prototype_dcss=round(avg_dcss, 2),
            avg_baseline_interval=float(cfg.BASELINE_INTERVAL_DAYS),
            avg_prototype_interval=round(avg_proto_iv, 2),
        ))

    logger.info(
        "Scenario analysis: NORMAL=%d bd / DISRUPTION=%d bd / ALL=%d bd (prototype).",
        results[0].prototype_breakdowns,
        results[1].prototype_breakdowns,
        results[2].prototype_breakdowns,
    )
    return results


# ---------------------------------------------------------------------------
# Error analysis — FP / FN / missed breakdowns / lead time
# ---------------------------------------------------------------------------

def compute_error_analysis(
    proto_sim: pd.DataFrame,
    window: int = cfg.BREAKDOWN_WARNING_WINDOW_DAYS,
) -> ErrorAnalysis:
    """
    Compute precision/recall-style error analysis for the prototype model.

    Definitions:
      HIGH_FLAG  = risk_level in {HIGH, CRITICAL}
      BREAKDOWN  = sim_breakdown == 1 within the next `window` days

      TP: HIGH_FLAG and breakdown within window
      FP: HIGH_FLAG and NO breakdown within window
      FN: NOT HIGH_FLAG and breakdown within window
      TN: NOT HIGH_FLAG and NO breakdown within window
      Missed: breakdown with no HIGH_FLAG in preceding window days

    Note: because both models use the same random seed, breakdown events
    are driven by actual failure probability. High-risk flags that precede
    a breakdown represent genuine predictive signal.

    Parameters
    ----------
    proto_sim : pd.DataFrame  — must have risk_level, sim_breakdown, vehicle_id, date
    window : int              — days to look ahead/behind for breakdown

    Returns
    -------
    ErrorAnalysis
    """
    logger.info("Computing error analysis (window=%d days)...", window)

    df = proto_sim[["vehicle_id","date","risk_level","sim_breakdown"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["high_flag"] = df["risk_level"].isin(["HIGH","CRITICAL"]).astype(int)
    df = df.sort_values(["vehicle_id","date"]).reset_index(drop=True)

    # For each record, check whether a breakdown occurs within the next `window` days
    # for the SAME vehicle
    tp = fp = fn = tn = missed = 0
    lead_times: List[float] = []

    for vid, vdf in df.groupby("vehicle_id"):
        vdf = vdf.reset_index(drop=True)
        dates = vdf["date"].values
        breakdowns = vdf["sim_breakdown"].values
        high_flags = vdf["high_flag"].values
        n = len(vdf)

        for i in range(n):
            # Look ahead: any breakdown in next `window` days?
            future_bd = 0
            for j in range(i+1, n):
                day_diff = (dates[j] - dates[i]) / np.timedelta64(1, "D")
                if day_diff > window:
                    break
                if breakdowns[j] == 1:
                    future_bd = 1
                    break

            # Look behind: any HIGH flag in preceding `window` days before a breakdown?
            if breakdowns[i] == 1:
                preceding_high = 0
                first_high_days_ago = None
                for j in range(i-1, -1, -1):
                    day_diff = (dates[i] - dates[j]) / np.timedelta64(1, "D")
                    if day_diff > window:
                        break
                    if high_flags[j] == 1:
                        preceding_high = 1
                        first_high_days_ago = float(day_diff)
                if preceding_high == 0:
                    missed += 1
                else:
                    lead_times.append(first_high_days_ago)

            if high_flags[i] == 1:
                if future_bd == 1:
                    tp += 1
                else:
                    fp += 1
            else:
                if future_bd == 1:
                    fn += 1
                else:
                    tn += 1

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall    = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1        = round(2 * precision * recall / (precision + recall), 4) \
        if (precision + recall) > 0 else 0.0
    avg_lead  = round(float(np.mean(lead_times)), 2) if lead_times else 0.0

    logger.info(
        "Error analysis: TP=%d, FP=%d, FN=%d, TN=%d, Missed=%d, "
        "Precision=%.3f, Recall=%.3f, F1=%.3f, AvgLead=%.2f days",
        tp, fp, fn, tn, missed, precision, recall, f1, avg_lead,
    )

    return ErrorAnalysis(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        missed_breakdowns=missed,
        precision=precision,
        recall=recall,
        f1_score=f1,
        avg_warning_lead_days=avg_lead,
        warning_window_days=window,
    )


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------

def compute_sensitivity_analysis(
    features_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
) -> List[SensitivityResult]:
    """
    Run the full prototype pipeline (DCSS -> recommendations -> simulation)
    for each weight configuration in DCSS_WEIGHT_CONFIGS.

    Returns
    -------
    List[SensitivityResult]  one entry per weight config
    """
    logger.info("Running sensitivity analysis over %d weight configs...",
                len(cfg.DCSS_WEIGHT_CONFIGS))
    results: List[SensitivityResult] = []

    for config_name, weights in cfg.DCSS_WEIGHT_CONFIGS.items():
        logger.info("  Sensitivity: config='%s'", config_name)

        # DCSS with this weight config
        dcss_df = compute_dcss_dataframe(
            features_df, weights=weights, weight_config_name=config_name
        )

        # Recommendations (interval mapping depends on risk_level which uses DCSS with these weights)
        recs_df = apply_recommendations(dcss_df)

        # Simulation
        # Fresh independent service states for every simulation.
        # This prevents one sensitivity configuration from contaminating
        # the next configuration and keeps Baseline independent of Prototype.
        proto_state = build_initial_service_state(clean_df, vehicles_df)
        baseline_state = build_initial_service_state(clean_df, vehicles_df)

        proto_sim = simulate_breakdowns(
            recs_df, proto_state,
            interval_col="recommended_interval_days",
            model_label=f"prototype_{config_name}",
            rng=np.random.default_rng(cfg.RANDOM_SEED),
        )

        # Baseline is intentionally re-simulated with a fresh state and the
        # same seed (common-random-number style comparison).
        base_sim = simulate_breakdowns(
            apply_baseline(features_df), baseline_state,
            interval_col="baseline_interval_days",
            model_label="baseline",
            rng=np.random.default_rng(cfg.RANDOM_SEED),
        )

        proto_bd = int(proto_sim["sim_breakdown"].sum())
        base_bd  = int(base_sim["sim_breakdown"].sum())
        avoided  = base_bd - proto_bd
        red      = round(100 * avoided / base_bd, 2) if base_bd > 0 else 0.0
        risk_dist = dcss_df["risk_level"].value_counts().to_dict()
        avg_iv    = float(recs_df["recommended_interval_days"].mean())

        results.append(SensitivityResult(
            config_name=config_name,
            weights=weights,
            avg_dcss=round(float(dcss_df["dcss"].mean()), 2),
            prototype_breakdowns=proto_bd,
            breakdowns_avoided=avoided,
            reduction_pct=red,
            risk_distribution=risk_dist,
            avg_recommended_interval=round(avg_iv, 2),
        ))
        logger.info(
            "    %s: avg_dcss=%.2f, breakdowns=%d, avoided=%d, reduction=%.2f%%",
            config_name, results[-1].avg_dcss, proto_bd, avoided, red,
        )

    return results


# ---------------------------------------------------------------------------
# Honest reporting notes
# ---------------------------------------------------------------------------

def _build_notes(report: EvaluationReport) -> List[str]:
    """
    Generate honest, data-driven notes about the evaluation results.
    FR-10 / Section 10.4: if target not met, report it clearly.
    """
    notes = [
        "IMPORTANT: All metrics are based on SYNTHETIC data. No real-world validity claims.",
        f"Simulation: {report.num_vehicles} vehicles x {report.simulation_days} days = "
        f"{report.total_vehicle_days} vehicle-days.",
        f"Random seed: {report.random_seed} (fixed for reproducibility).",
    ]

    if not report.target_met:
        if report.baseline_breakdowns == 0:
            notes.append(
                "TARGET NOT MET: Baseline produced zero simulated breakdowns, so a percentage "
                "reduction is not statistically meaningful in this run. Prototype and Baseline "
                "were evaluated with independent fresh service states and the same random seed."
            )
        else:
            notes.append(
                f"TARGET NOT MET: Prototype achieved {report.reduction_pct:.2f}% breakdown reduction "
                f"vs target of {report.target_reduction_pct:.0f}%. "
                "The result is based on the synthetic simulator and should not be interpreted as "
                "real-world vehicle performance."
            )
    else:
        notes.append(
            f"TARGET MET: {report.reduction_pct:.2f}% breakdown reduction "
            f"(target: {report.target_reduction_pct:.0f}%)."
        )

    if report.error_analysis:
        ea = report.error_analysis
        notes.append(
            f"Error analysis (window={ea.warning_window_days}d): "
            f"Precision={ea.precision:.3f}, Recall={ea.recall:.3f}, F1={ea.f1_score:.3f}. "
            f"Missed breakdowns={ea.missed_breakdowns}, AvgLeadTime={ea.avg_warning_lead_days:.1f}d."
        )

    notes.append(
        "Maintenance efficiency: prototype shortens intervals for HIGH/CRITICAL vehicles "
        "and extends them for LOW vehicles — net effect is condition-appropriate service timing."
    )
    return notes


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_evaluation_results(
    report: EvaluationReport,
    project_root: Path,
) -> None:
    """Save evaluation report to JSON and summary CSV."""
    out_dir = project_root / cfg.PROCESSED_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON report
    report_dict = asdict(report)
    json_path = out_dir / "evaluation_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    logger.info("Saved evaluation report to: %s", json_path)

    # Scenario CSV
    if report.scenario_results:
        scen_rows = [asdict(s) for s in report.scenario_results]
        pd.DataFrame(scen_rows).to_csv(out_dir / "scenario_comparison.csv", index=False)
        logger.info("Saved scenario comparison to: scenario_comparison.csv")

    # Sensitivity CSV
    if report.sensitivity_results:
        sens_rows = []
        for sr in report.sensitivity_results:
            row = {
                "config_name": sr.config_name,
                "avg_dcss": sr.avg_dcss,
                "prototype_breakdowns": sr.prototype_breakdowns,
                "breakdowns_avoided": sr.breakdowns_avoided,
                "reduction_pct": sr.reduction_pct,
                "avg_recommended_interval": sr.avg_recommended_interval,
            }
            row.update({f"weight_{k}": v for k, v in sr.weights.items()})
            row.update({f"risk_{k}": v for k, v in sr.risk_distribution.items()})
            sens_rows.append(row)
        pd.DataFrame(sens_rows).to_csv(out_dir / "sensitivity_analysis.csv", index=False)
        logger.info("Saved sensitivity analysis to: sensitivity_analysis.csv")


# ---------------------------------------------------------------------------
# Master evaluation runner
# ---------------------------------------------------------------------------

def run_evaluation(
    features_df: Optional[pd.DataFrame] = None,
    proto_sim: Optional[pd.DataFrame] = None,
    baseline_sim: Optional[pd.DataFrame] = None,
    project_root: Optional[Path] = None,
) -> EvaluationReport:
    """
    Run the full evaluation pipeline.

    Parameters
    ----------
    features_df : pd.DataFrame | None  — pre-computed features; if None, recomputed
    proto_sim   : pd.DataFrame | None  — pre-computed prototype simulation
    baseline_sim: pd.DataFrame | None  — pre-computed baseline simulation
    project_root: Path | None

    Returns
    -------
    EvaluationReport  with all metrics populated
    """
    if project_root is None:
        project_root = PROJECT_ROOT

    logger.info("=== EVALUATION ENGINE START ===")
    logger.info("IMPORTANT: All data is SYNTHETIC.")

    # ---- Load dependencies ----
    clean_df    = pd.read_csv(project_root / cfg.OPERATIONAL_DATA_CLEAN_FILE)
    vehicles_df = pd.read_csv(project_root / cfg.VEHICLES_META_FILE)

    if features_df is None:
        features_df = run_feature_engineering(project_root=project_root)

    # ---- Run simulations if not pre-supplied ----
    if proto_sim is None or baseline_sim is None:
        logger.info("Running DCSS + recommendations + simulation from scratch...")
        dcss_df     = run_duty_cycle_model(features_df=features_df)
        recs_df     = apply_recommendations(dcss_df)
        baseline_df = apply_baseline(features_df)
        # IMPORTANT: simulate_breakdowns may mutate the service state.
        # Give Prototype and Baseline independent fresh states so the
        # Prototype run cannot affect the Baseline result.
        proto_state = build_initial_service_state(clean_df, vehicles_df)
        baseline_state = build_initial_service_state(clean_df, vehicles_df)

        proto_sim = simulate_breakdowns(
            recs_df, proto_state,
            interval_col="recommended_interval_days",
            model_label="prototype",
            rng=np.random.default_rng(cfg.RANDOM_SEED),
        )
        baseline_sim = simulate_breakdowns(
            baseline_df, baseline_state,
            interval_col="baseline_interval_days",
            model_label="baseline",
            rng=np.random.default_rng(cfg.RANDOM_SEED),
        )

    # ---- Primary metrics ----
    logger.info("Computing primary metrics...")
    primary = compute_primary_metrics(proto_sim, baseline_sim)

    report = EvaluationReport(
        prototype_breakdowns       = primary["prototype_breakdowns"],
        baseline_breakdowns        = primary["baseline_breakdowns"],
        breakdowns_avoided         = primary["breakdowns_avoided"],
        reduction_pct              = primary["reduction_pct"],
        target_met                 = primary["target_met"],
        prototype_prevented        = primary["prototype_prevented"],
        baseline_prevented         = primary["baseline_prevented"],
        prototype_maintenance_freq = primary["prototype_maintenance_freq"],
        baseline_maintenance_freq  = primary["baseline_maintenance_freq"],
        avg_prototype_interval_days= primary["avg_prototype_interval"],
        additional_interventions   = primary["additional_interventions"],
        maintenance_efficiency     = primary["maintenance_efficiency"],
    )

    # ---- Scenario analysis ----
    logger.info("Computing scenario analysis...")
    report.scenario_results = compute_scenario_metrics(proto_sim, baseline_sim)

    # ---- Error analysis ----
    logger.info("Computing error analysis...")
    report.error_analysis = compute_error_analysis(proto_sim)

    # ---- Sensitivity analysis ----
    logger.info("Computing sensitivity analysis (3 weight configs)...")
    report.sensitivity_results = compute_sensitivity_analysis(
        features_df, clean_df, vehicles_df
    )

    # ---- Notes ----
    report.notes = _build_notes(report)

    # ---- Save ----
    save_evaluation_results(report, project_root)

    logger.info("=== EVALUATION ENGINE COMPLETE ===")
    return report


# ---------------------------------------------------------------------------
# Pretty-print summary
# ---------------------------------------------------------------------------

def print_evaluation_summary(report: EvaluationReport) -> None:
    """Print a formatted evaluation summary to stdout."""
    sep = "=" * 65
    print(f"\n{sep}")
    print("  EVALUATION REPORT  (SYNTHETIC DATA ONLY)")
    print(sep)

    print(f"\n  Vehicles: {report.num_vehicles}  |  Days: {report.simulation_days}  "
          f"|  Vehicle-days: {report.total_vehicle_days}")
    print(f"  Model version: {report.model_version}  |  Seed: {report.random_seed}")

    print(f"\n  PRIMARY METRICS")
    print(f"  {'Metric':<40} {'Prototype':>12} {'Baseline':>12}")
    print(f"  {'-'*64}")
    print(f"  {'Simulated Breakdowns':<40} {report.prototype_breakdowns:>12} {report.baseline_breakdowns:>12}")
    print(f"  {'Breakdowns Prevented':<40} {report.prototype_prevented:>12} {report.baseline_prevented:>12}")
    print(f"  {'Breakdowns Avoided (baseline-proto)':<40} {report.breakdowns_avoided:>12}")
    print(f"  {'Reduction %':<40} {report.reduction_pct:>11.2f}%")
    print(f"  {'Target (>= {:.0f}%)':<40} {report.target_reduction_pct:>11.0f}%  {'MET' if report.target_met else 'NOT MET'}".format(report.target_reduction_pct))
    print(f"  {'Avg Recommended Interval (days)':<40} {report.avg_prototype_interval_days:>12.1f} {report.avg_baseline_interval_days:>12.0f}")
    print(f"  {'Maintenance Efficiency':<40} {report.maintenance_efficiency:>12.4f}")

    print(f"\n  SCENARIO BREAKDOWN")
    print(f"  {'Scenario':<14} {'Records':>8} {'Proto BD':>10} {'Base BD':>10} {'Avoided':>8} {'Reduction':>10} {'Proto DCSS':>11}")
    print(f"  {'-'*73}")
    for s in report.scenario_results:
        print(f"  {s.scenario:<14} {s.total_records:>8} {s.prototype_breakdowns:>10} "
              f"{s.baseline_breakdowns:>10} {s.breakdowns_avoided:>8} "
              f"{s.reduction_pct:>9.2f}% {s.avg_prototype_dcss:>11.2f}")

    if report.error_analysis:
        ea = report.error_analysis
        print(f"\n  ERROR ANALYSIS  (window = {ea.warning_window_days} days)")
        print(f"  TP={ea.true_positives}  FP={ea.false_positives}  FN={ea.false_negatives}  TN={ea.true_negatives}")
        print(f"  Missed breakdowns:    {ea.missed_breakdowns}")
        print(f"  Precision:            {ea.precision:.4f}")
        print(f"  Recall:               {ea.recall:.4f}")
        print(f"  F1 Score:             {ea.f1_score:.4f}")
        print(f"  Avg warning lead:     {ea.avg_warning_lead_days:.2f} days")

    print(f"\n  SENSITIVITY ANALYSIS")
    print(f"  {'Config':<16} {'Avg DCSS':>9} {'Proto BD':>9} {'Avoided':>8} {'Reduction':>10} {'Avg IV':>8}")
    print(f"  {'-'*62}")
    for sr in report.sensitivity_results:
        print(f"  {sr.config_name:<16} {sr.avg_dcss:>9.2f} {sr.prototype_breakdowns:>9} "
              f"{sr.breakdowns_avoided:>8} {sr.reduction_pct:>9.2f}% {sr.avg_recommended_interval:>8.1f}d")

    print(f"\n  NOTES:")
    for note in report.notes:
        # wrap at 60 chars
        words = note.split()
        line = "    "
        for w in words:
            if len(line) + len(w) > 64:
                print(line)
                line = "    " + w + " "
            else:
                line += w + " "
        if line.strip():
            print(line)

    print(f"\n{sep}")
    print("  NOTE: All figures are SYNTHETIC. Not real vehicle performance.")
    print(sep + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    report = run_evaluation(project_root=PROJECT_ROOT)
    print_evaluation_summary(report)
    sys.exit(0)
