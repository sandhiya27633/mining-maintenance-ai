"""
failure_simulator.py — Condition-Driven Breakdown Simulator
============================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC. Failure probabilities and
assumptions are engineering approximations for prototype purposes only.
They do NOT represent real vehicle failure rates.

Failure probability is computed via a sigmoid function of operational sub-scores:

  P(breakdown) = sigmoid(
      alpha_fault      * fault_score_norm
    + alpha_route      * route_severity_score_norm
    + alpha_load       * load_score_norm
    + alpha_engine     * engine_hour_score_norm
    + alpha_mileage    * mileage_score_norm
    + alpha_days_since * days_since_service_norm
    - beta_intercept
  )

All coefficients come from config.py. The sigmoid intercept (beta) is tuned to
produce a realistic baseline daily failure rate of ~3–8% under normal conditions.

Service effect:
  If a vehicle was serviced in the preceding interval, the breakdown is
  marked as PREVENTED (not OCCURRED). This is how the two models are compared:
  - Baseline: prevented if serviced in last BASELINE_INTERVAL_DAYS.
  - Prototype: prevented if serviced in last recommended_interval_days.

Three failure modes (ENGINE / DRIVETRAIN / BRAKE) are sampled from the
configured type probability distribution once a breakdown is confirmed.

Random draws use a seeded numpy Generator derived from RANDOM_SEED to ensure
full reproducibility across runs.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("failure_simulator")


# ---------------------------------------------------------------------------
# Sigmoid helper
# ---------------------------------------------------------------------------

def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    """Numerically stable sigmoid: handles both scalars and arrays."""
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))


# ---------------------------------------------------------------------------
# Failure probability (vectorised)
# ---------------------------------------------------------------------------

def compute_failure_probability(df: pd.DataFrame) -> pd.Series:
    """
    Compute daily breakdown probability for each record using the sigmoid function.

    All sub-scores are normalised to [0, 1] (divide by 100) before applying
    the sigmoid coefficients.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: fault_score, route_severity_score_n, load_score,
        engine_hour_score, mileage_score, service_wear_score.

    Returns
    -------
    pd.Series  float [0, 1], one probability per row.
    """
    logit = (
        cfg.FAILURE_ALPHA_FAULT        * (df["fault_score"]           / 100.0)
        + cfg.FAILURE_ALPHA_ROUTE      * (df["route_severity_score_n"] / 100.0)
        + cfg.FAILURE_ALPHA_LOAD       * (df["load_score"]             / 100.0)
        + cfg.FAILURE_ALPHA_ENGINE     * (df["engine_hour_score"]      / 100.0)
        + cfg.FAILURE_ALPHA_MILEAGE    * (df["mileage_score"]          / 100.0)
        + cfg.FAILURE_ALPHA_DAYS_SINCE * (df["service_wear_score"]     / 100.0)
        - cfg.FAILURE_BETA_INTERCEPT
    )
    return pd.Series(_sigmoid(logit.values), index=df.index)


# ---------------------------------------------------------------------------
# Failure type sampler
# ---------------------------------------------------------------------------

def _sample_failure_types(rng: np.random.Generator, n: int) -> np.ndarray:
    """
    Sample `n` failure type strings from the configured probability distribution.
    Returns an array of strings ('ENGINE', 'DRIVETRAIN', 'BRAKE').
    """
    types = list(cfg.FAILURE_TYPE_PROBS.keys())
    probs = list(cfg.FAILURE_TYPE_PROBS.values())
    return rng.choice(types, size=n, p=probs)


# ---------------------------------------------------------------------------
# Core simulation: apply to a fleet DataFrame
# ---------------------------------------------------------------------------

def simulate_breakdowns(
    df: pd.DataFrame,
    last_service_dates: dict[str, str],
    interval_col: str = "recommended_interval_days",
    model_label: str = "prototype",
    rng: Optional[np.random.Generator] = None,
) -> pd.DataFrame:
    """
    Simulate breakdowns for each vehicle-day and determine whether each
    potential failure is prevented by a recent service.

    Algorithm (per vehicle, chronological order):
    -----------------------------------------------
    1. Compute failure probability from sub-scores.
    2. Draw a random boolean (seeded) against the probability.
    3. Determine the active maintenance interval for this model:
       - baseline: always BASELINE_INTERVAL_DAYS
       - prototype: use the row's recommended_interval_days
    4. If the vehicle was serviced within the active interval → breakdown PREVENTED.
    5. If breakdown occurs and NOT prevented → record as breakdown.
    6. Track when each simulated service occurs (at the end of the interval).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain sub-scores + 'date' + 'vehicle_id' + interval_col.
    last_service_dates : dict[str, str]
        vehicle_id → last service date string (ISO 8601) at simulation start.
    interval_col : str
        Column name containing the maintenance interval in days.
        For baseline this should be a constant column set to BASELINE_INTERVAL_DAYS.
    model_label : str
        'prototype' or 'baseline' — stored in output for comparison.
    rng : np.random.Generator | None
        Seeded RNG. If None, creates one from cfg.RANDOM_SEED.

    Returns
    -------
    pd.DataFrame  — with added columns:
        failure_prob, sim_breakdown, sim_breakdown_prevented,
        sim_breakdown_type, sim_last_service_date, model_label
    """
    if rng is None:
        rng = np.random.default_rng(cfg.RANDOM_SEED)

    df = df.sort_values(["vehicle_id", "date"]).copy()
    df["failure_prob"] = compute_failure_probability(df).round(6)

    # Random breakdown draws (seeded, vectorised)
    draws = rng.random(len(df))
    df["_breakdown_draw"] = draws
    df["_raw_breakdown"] = (df["_breakdown_draw"] < df["failure_prob"]).astype(int)

    # Sample failure types for all rows (wasteful but vectorised; blanked later)
    df["_failure_type_candidate"] = _sample_failure_types(rng, len(df))

    # Per-vehicle simulation (must be sequential to track service state)
    result_rows = []
    for vid, vdf in df.groupby("vehicle_id"):
        last_svc_str = last_service_dates.get(str(vid))
        if last_svc_str is not None:
            last_svc = pd.Timestamp(last_svc_str)
        else:
            last_svc = None   # new vehicle — no prior service

        for idx, row in vdf.iterrows():
            current_date = pd.Timestamp(row["date"])
            raw_breakdown = int(row["_raw_breakdown"])

            # Determine active interval
            if interval_col in row.index and pd.notna(row[interval_col]):
                active_interval = int(row[interval_col])
            else:
                active_interval = cfg.BASELINE_INTERVAL_DAYS

            # Check if vehicle was serviced within the active interval
            if last_svc is not None:
                days_since_svc = (current_date - last_svc).days
                recently_serviced = days_since_svc <= active_interval
            else:
                # New vehicle — treat as if serviced at simulation start
                recently_serviced = True
                last_svc = current_date

            # Determine outcome
            if raw_breakdown == 1 and not recently_serviced:
                sim_breakdown = 1
                sim_prevented = 0
                sim_type = str(row["_failure_type_candidate"])
            elif raw_breakdown == 1 and recently_serviced:
                sim_breakdown = 0
                sim_prevented = 1
                sim_type = None
            else:
                sim_breakdown = 0
                sim_prevented = 0
                sim_type = None

            # Scheduled service: trigger if interval has elapsed since last service
            if last_svc is not None:
                days_since = (current_date - last_svc).days
                if days_since >= active_interval:
                    last_svc = current_date   # Service performed today

            result_rows.append({
                "record_idx":              idx,
                "sim_breakdown":           sim_breakdown,
                "sim_breakdown_prevented": sim_prevented,
                "sim_breakdown_type":      sim_type,
                "sim_last_service_date":   last_svc.strftime("%Y-%m-%d") if last_svc else None,
                "failure_prob":            row["failure_prob"],
                "model_label":             model_label,
            })

    result_df = pd.DataFrame(result_rows).set_index("record_idx")
    df = df.drop(columns=["_breakdown_draw", "_raw_breakdown", "_failure_type_candidate",
                           "failure_prob"])
    df = df.join(result_df)

    total_bd = int(df["sim_breakdown"].sum())
    total_prev = int(df["sim_breakdown_prevented"].sum())
    logger.info(
        "[%s] Simulation complete: %d breakdowns, %d prevented.",
        model_label, total_bd, total_prev,
    )
    return df


# ---------------------------------------------------------------------------
# Convenience: build initial service state from clean data
# ---------------------------------------------------------------------------

def build_initial_service_state(
    ops_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
) -> dict[str, str]:
    """
    Build a {vehicle_id: last_service_date} dict from the raw operational data.
    Uses service_type_last and days_since_last_service from the first available
    record per vehicle to back-compute the last service date.

    For vehicles with no service history (days_since_last_service is NaN):
    sets last_service_date to None (new vehicle edge case).

    Parameters
    ----------
    ops_df : pd.DataFrame  cleaned operational data
    vehicles_df : pd.DataFrame

    Returns
    -------
    dict[str, str | None]
    """
    state: dict[str, str | None] = {}
    first_records = (
        ops_df.sort_values("date").groupby("vehicle_id").first().reset_index()
    )
    for _, row in first_records.iterrows():
        vid = str(row["vehicle_id"])
        first_date = pd.Timestamp(row["date"])
        days_since = row["days_since_last_service"]
        if pd.isna(days_since):
            state[vid] = None
        else:
            last_svc = first_date - pd.Timedelta(days=int(days_since))
            state[vid] = last_svc.strftime("%Y-%m-%d")
    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick smoke test: load features + DCSS, add constant interval col, run simulator
    from feature_engineering import run_feature_engineering
    from duty_cycle_model import run_duty_cycle_model

    feat_df = run_feature_engineering(project_root=PROJECT_ROOT)
    dcss_df = run_duty_cycle_model(features_df=feat_df, project_root=PROJECT_ROOT)

    clean_df = pd.read_csv(PROJECT_ROOT / cfg.OPERATIONAL_DATA_CLEAN_FILE)
    vehicles_df = pd.read_csv(PROJECT_ROOT / cfg.VEHICLES_META_FILE)

    # Add constant baseline interval
    dcss_df["recommended_interval_days"] = cfg.BASELINE_INTERVAL_DAYS

    # Build initial service state
    svc_state = build_initial_service_state(clean_df, vehicles_df)

    # Run baseline simulation
    result = simulate_breakdowns(
        dcss_df, svc_state,
        interval_col="recommended_interval_days",
        model_label="baseline",
    )

    total = int(result["sim_breakdown"].sum())
    prevented = int(result["sim_breakdown_prevented"].sum())
    bd_rate = 100 * total / len(result)

    print(f"\n=== FAILURE SIMULATOR SMOKE TEST (SYNTHETIC DATA) ===")
    print(f"  Total records:         {len(result)}")
    print(f"  Simulated breakdowns:  {total} ({bd_rate:.2f}%)")
    print(f"  Prevented:             {prevented}")
    print(f"  Breakdown types:")
    for t, n in result["sim_breakdown_type"].value_counts().items():
        print(f"    {t}: {n}")
    print("failure_simulator.py: smoke test complete.")
