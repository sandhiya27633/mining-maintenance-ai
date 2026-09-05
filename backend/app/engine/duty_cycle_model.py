"""
duty_cycle_model.py — DCSS Computation, Risk Classification, Factor Ranking
=============================================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC.

This module implements the core Duty Cycle Severity Score (DCSS) model:

  DCSS = w_fault        * fault_score
       + w_route        * route_severity_score_n
       + w_load         * load_score
       + w_engine_hours * engine_hour_score
       + w_mileage      * mileage_score
       + w_service      * service_wear_score

All weights come from config.py — no values are hard-coded here.

Outputs per vehicle per day:
  - dcss             : float 0–100
  - risk_level       : LOW / NORMAL / HIGH / CRITICAL
  - top_factors      : JSON-serialisable list of top-3 ranked (factor, contribution)
  - dcss_delta       : change in DCSS vs previous day (disruption detection proxy)

Special override rule (FR-05):
  If fault_severity_score >= CRITICAL_FAULT_SEVERITY_THRESHOLD,
  risk_level is forced to CRITICAL regardless of DCSS value.
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
logger = logging.getLogger("duty_cycle_model")

# ---------------------------------------------------------------------------
# Sub-score column mapping — keys match DCSS_WEIGHTS_DEFAULT keys
# ---------------------------------------------------------------------------
SCORE_COL_MAP: Dict[str, str] = {
    "fault_score":          "fault_score",
    "route_severity_score": "route_severity_score_n",   # normalised col name in features DF
    "load_score":           "load_score",
    "engine_hour_score":    "engine_hour_score",
    "mileage_score":        "mileage_score",
    "service_wear_score":   "service_wear_score",
}


# ---------------------------------------------------------------------------
# DCSS computation (single row — used for overrides and unit tests)
# ---------------------------------------------------------------------------

def compute_dcss_single(
    fault_score: float,
    route_severity_score_n: float,
    load_score: float,
    engine_hour_score: float,
    mileage_score: float,
    service_wear_score: float,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute DCSS for a single vehicle-day observation.

    Parameters
    ----------
    fault_score, route_severity_score_n, load_score,
    engine_hour_score, mileage_score, service_wear_score : float
        Sub-scores in range [0, 100].
    weights : dict | None
        DCSS weight config. Defaults to cfg.DCSS_WEIGHTS_DEFAULT.

    Returns
    -------
    float  DCSS in [0, 100]
    """
    if weights is None:
        weights = cfg.DCSS_WEIGHTS_DEFAULT

    dcss = (
        weights["fault_score"]          * fault_score
        + weights["route_severity_score"] * route_severity_score_n
        + weights["load_score"]           * load_score
        + weights["engine_hour_score"]    * engine_hour_score
        + weights["mileage_score"]        * mileage_score
        + weights["service_wear_score"]   * service_wear_score
    )
    return float(np.clip(dcss, 0.0, 100.0))


# ---------------------------------------------------------------------------
# Risk classification (single row)
# ---------------------------------------------------------------------------

def classify_risk(
    dcss: float,
    fault_severity_score: float = 0.0,
) -> str:
    """
    Classify DCSS into a risk level.

    Rules (in priority order):
    1. If fault_severity_score >= CRITICAL_FAULT_SEVERITY_THRESHOLD → CRITICAL
       (FR-05 override rule — a critical fault always demands immediate attention)
    2. Otherwise: DCSS < 25 → LOW, < 50 → NORMAL, < 75 → HIGH, else CRITICAL

    Parameters
    ----------
    dcss : float  [0, 100]
    fault_severity_score : float  [0, 10]

    Returns
    -------
    str  'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL'
    """
    # Critical fault override (FR-05)
    if fault_severity_score >= cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD:
        return "CRITICAL"

    lo_low,  hi_low  = cfg.RISK_THRESHOLDS["LOW"]
    lo_norm, hi_norm = cfg.RISK_THRESHOLDS["NORMAL"]
    lo_high, hi_high = cfg.RISK_THRESHOLDS["HIGH"]

    if dcss <= hi_low:
        return "LOW"
    elif dcss <= hi_norm:
        return "NORMAL"
    elif dcss <= hi_high:
        return "HIGH"
    else:
        return "CRITICAL"


# ---------------------------------------------------------------------------
# Factor ranking (single row)
# ---------------------------------------------------------------------------

def rank_factors(
    fault_score: float,
    route_severity_score_n: float,
    load_score: float,
    engine_hour_score: float,
    mileage_score: float,
    service_wear_score: float,
    weights: Optional[Dict[str, float]] = None,
    top_n: int = 3,
) -> List[Dict[str, float]]:
    """
    Rank contributing factors by their weighted contribution to DCSS.

    contribution[i] = weight[i] * sub_score[i]

    Parameters
    ----------
    (sub-scores) : float  [0, 100] each
    weights : dict | None   defaults to cfg.DCSS_WEIGHTS_DEFAULT
    top_n : int             number of top factors to return (default 3)

    Returns
    -------
    list of dicts: [{"factor": str, "sub_score": float, "contribution": float}, ...]
    Sorted descending by contribution. Length = top_n.
    """
    if weights is None:
        weights = cfg.DCSS_WEIGHTS_DEFAULT

    scores = {
        "fault_score":          fault_score,
        "route_severity_score": route_severity_score_n,
        "load_score":           load_score,
        "engine_hour_score":    engine_hour_score,
        "mileage_score":        mileage_score,
        "service_wear_score":   service_wear_score,
    }

    contributions = [
        {
            "factor":       factor,
            "sub_score":    round(sub_score, 2),
            "contribution": round(weights[factor] * sub_score, 4),
        }
        for factor, sub_score in scores.items()
    ]
    contributions.sort(key=lambda x: x["contribution"], reverse=True)
    return contributions[:top_n]


# ---------------------------------------------------------------------------
# Vectorised DCSS computation (full DataFrame)
# ---------------------------------------------------------------------------

def compute_dcss_dataframe(
    df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    weight_config_name: str = "Default",
) -> pd.DataFrame:
    """
    Compute DCSS, risk level, factor ranking, and day-over-day delta
    for every row in the features DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain the 6 sub-score columns (post feature_engineering).
    weights : dict | None
        Weight config. Defaults to cfg.DCSS_WEIGHTS_DEFAULT.
    weight_config_name : str
        Label for this weight configuration (stored in output column).

    Returns
    -------
    pd.DataFrame  — original columns + dcss, risk_level, top_factors,
                    dcss_delta, weight_config
    """
    if weights is None:
        weights = cfg.DCSS_WEIGHTS_DEFAULT

    logger.info(
        "Computing DCSS for %d records (weight config: %s).",
        len(df), weight_config_name,
    )

    df = df.copy()

    # --- Compute DCSS ---
    df["dcss"] = (
        weights["fault_score"]          * df["fault_score"]
        + weights["route_severity_score"] * df["route_severity_score_n"]
        + weights["load_score"]           * df["load_score"]
        + weights["engine_hour_score"]    * df["engine_hour_score"]
        + weights["mileage_score"]        * df["mileage_score"]
        + weights["service_wear_score"]   * df["service_wear_score"]
    ).clip(0.0, 100.0).round(4)

    # --- Classify risk (vectorised, with critical fault override) ---
    df["risk_level"] = df.apply(
        lambda row: classify_risk(
            dcss=row["dcss"],
            fault_severity_score=row.get("fault_severity_score", 0.0),
        ),
        axis=1,
    )

    # --- Day-over-day DCSS delta per vehicle ---
    df = df.sort_values(["vehicle_id", "date"]).reset_index(drop=True)
    df["dcss_delta"] = (
        df.groupby("vehicle_id")["dcss"]
        .transform(lambda x: x.diff())
        .round(4)
    )

    # --- Top-3 contributing factors (JSON string for DB storage) ---
    def _top_factors_json(row: pd.Series) -> str:
        factors = rank_factors(
            fault_score=row["fault_score"],
            route_severity_score_n=row["route_severity_score_n"],
            load_score=row["load_score"],
            engine_hour_score=row["engine_hour_score"],
            mileage_score=row["mileage_score"],
            service_wear_score=row["service_wear_score"],
            weights=weights,
        )
        return json.dumps(factors)

    df["top_factors"] = df.apply(_top_factors_json, axis=1)
    df["weight_config"] = weight_config_name

    # --- Logging ---
    risk_dist = df["risk_level"].value_counts().to_dict()
    logger.info("DCSS computed. Risk distribution: %s", risk_dist)
    logger.info(
        "DCSS stats: min=%.1f, mean=%.1f, max=%.1f, std=%.1f",
        df["dcss"].min(), df["dcss"].mean(), df["dcss"].max(), df["dcss"].std(),
    )

    # Critical fault override count
    critical_fault_override = int(
        (df["fault_severity_score"] >= cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD).sum()
    )
    if critical_fault_override > 0:
        logger.info(
            "Critical fault override applied to %d records "
            "(fault_severity >= %.1f forced CRITICAL).",
            critical_fault_override, cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD,
        )

    return df


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_duty_cycle_model(
    features_df: Optional[pd.DataFrame] = None,
    project_root: Optional[Path] = None,
    weights: Optional[Dict[str, float]] = None,
    weight_config_name: str = "Default",
) -> pd.DataFrame:
    """
    Run the DCSS model pipeline.

    Parameters
    ----------
    features_df : pd.DataFrame | None
        Pre-loaded features dataframe. If None, loads from disk.
    project_root : Path | None
    weights : dict | None
        DCSS weights. Defaults to cfg.DCSS_WEIGHTS_DEFAULT.
    weight_config_name : str

    Returns
    -------
    pd.DataFrame with DCSS columns added.
    """
    if project_root is None:
        project_root = PROJECT_ROOT

    if features_df is None:
        feat_path = project_root / cfg.OPERATIONAL_DATA_FEATURES_FILE
        if not feat_path.exists():
            raise FileNotFoundError(
                f"Features file not found at {feat_path}. "
                "Run src/feature_engineering.py first."
            )
        features_df = pd.read_csv(feat_path)
        logger.info("Loaded features: %d rows.", len(features_df))

    dcss_df = compute_dcss_dataframe(features_df, weights=weights,
                                      weight_config_name=weight_config_name)
    return dcss_df


# ---------------------------------------------------------------------------
# Entry point (standalone run)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dcss_df = run_duty_cycle_model(project_root=PROJECT_ROOT)

    print("\n" + "=" * 55)
    print("  DCSS MODEL OUTPUT SUMMARY (SYNTHETIC DATA)")
    print("=" * 55)
    print(f"  Records:      {len(dcss_df)}")
    print(f"  DCSS range:   {dcss_df['dcss'].min():.1f} – {dcss_df['dcss'].max():.1f}")
    print(f"  DCSS mean:    {dcss_df['dcss'].mean():.2f}")
    print(f"\n  Risk Level Distribution:")
    for lvl in ["LOW", "NORMAL", "HIGH", "CRITICAL"]:
        n = (dcss_df["risk_level"] == lvl).sum()
        pct = 100 * n / len(dcss_df)
        print(f"    {lvl:<10}: {n:5d} ({pct:.1f}%)")
    print(f"\n  Disruption vs Normal DCSS:")
    for tag in ["NORMAL", "DISRUPTION"]:
        m = dcss_df[dcss_df["scenario_tag"] == tag]["dcss"].mean()
        print(f"    {tag:<12}: mean DCSS = {m:.2f}")
    print("=" * 55)
    print("duty_cycle_model.py: standalone run complete.")
