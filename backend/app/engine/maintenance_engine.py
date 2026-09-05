"""
maintenance_engine.py — Maintenance Interval Recommendation Engine
===================================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC.

This module translates the DCSS risk level into actionable maintenance
recommendations for each vehicle on each day.

Recommendation Rules (from Phase 1 design Section 8.3):
  CRITICAL (DCSS >= 75 OR fault_severity >= 8.0):
    → Immediate inspection: recommended_interval_days = CRITICAL_MAX_DAYS (3)
    → recommendation_urgency = 'IMMEDIATE'

  HIGH (50 <= DCSS < 75):
    → Accelerated service: interval = STANDARD_INTERVAL_DAYS * HIGH_REDUCTION_FACTOR
    → recommended_interval_days = round(30 * 0.6) = 18 days
    → recommendation_urgency = 'URGENT'

  NORMAL (25 <= DCSS < 50):
    → Standard interval: interval = STANDARD_INTERVAL_DAYS (30 days)
    → recommendation_urgency = 'ROUTINE'

  LOW (DCSS < 25):
    → Extended interval: interval = STANDARD_INTERVAL_DAYS * LOW_EXTENSION_FACTOR
    → recommended_interval_days = round(30 * 1.5) = 45 days
    → Hard cap: MAX_INTERVAL_DAYS (60)
    → recommendation_urgency = 'DEFERRED'

Hard limits (always enforced):
  MIN_INTERVAL_DAYS = 1
  MAX_INTERVAL_DAYS = 60

All values are sourced from config.py.

Output columns:
  recommended_interval_days : int        [1, 60]
  recommended_maintenance_date : str     ISO 8601
  recommendation_urgency : str          IMMEDIATE / URGENT / ROUTINE / DEFERRED
  recommendation_reason : str           human-readable explanation
  top_factors : str                     JSON list (from DCSS model)
  recommended_by : str                  'prototype' or 'baseline'
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("maintenance_engine")


# ---------------------------------------------------------------------------
# Interval computation (single row — deterministic, testable)
# ---------------------------------------------------------------------------

def compute_interval(risk_level: str) -> tuple[int, str, str]:
    """
    Compute the recommended maintenance interval for a given risk level.

    Parameters
    ----------
    risk_level : str  'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL'

    Returns
    -------
    (interval_days: int, urgency: str, reason: str)
    """
    std = cfg.STANDARD_INTERVAL_DAYS

    if risk_level == "CRITICAL":
        days = cfg.CRITICAL_MAX_DAYS
        urgency = "IMMEDIATE"
        reason = (
            f"CRITICAL risk: DCSS >= {cfg.RISK_THRESHOLDS['HIGH'][1]:.0f} or "
            f"fault_severity >= {cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD:.0f}. "
            f"Immediate inspection required within {days} day(s)."
        )

    elif risk_level == "HIGH":
        days = int(round(std * cfg.HIGH_INTERVAL_REDUCTION_FACTOR))
        days = max(cfg.MIN_INTERVAL_DAYS, min(cfg.MAX_INTERVAL_DAYS, days))
        urgency = "URGENT"
        reason = (
            f"HIGH risk: DCSS in [{cfg.RISK_THRESHOLDS['HIGH'][0]:.0f}, "
            f"{cfg.RISK_THRESHOLDS['HIGH'][1]:.0f}). "
            f"Accelerated service in {days} day(s) "
            f"({cfg.HIGH_INTERVAL_REDUCTION_FACTOR:.0%} of standard {std}-day interval)."
        )

    elif risk_level == "NORMAL":
        days = std
        urgency = "ROUTINE"
        reason = (
            f"NORMAL risk: DCSS in [{cfg.RISK_THRESHOLDS['NORMAL'][0]:.0f}, "
            f"{cfg.RISK_THRESHOLDS['NORMAL'][1]:.0f}). "
            f"Standard {days}-day maintenance interval."
        )

    elif risk_level == "LOW":
        days = int(round(std * cfg.LOW_INTERVAL_EXTENSION_FACTOR))
        days = max(cfg.MIN_INTERVAL_DAYS, min(cfg.MAX_INTERVAL_DAYS, days))
        urgency = "DEFERRED"
        reason = (
            f"LOW risk: DCSS < {cfg.RISK_THRESHOLDS['NORMAL'][0]:.0f}. "
            f"Extended service interval of {days} day(s) "
            f"({cfg.LOW_INTERVAL_EXTENSION_FACTOR:.1f}× standard {std} days). "
            f"Vehicle is operating below typical stress levels."
        )

    else:
        # Unknown risk level — fall back to standard interval safely
        logger.warning("Unknown risk_level='%s'. Defaulting to NORMAL interval.", risk_level)
        days = std
        urgency = "ROUTINE"
        reason = f"Unknown risk level '{risk_level}'. Defaulting to standard {std}-day interval."

    return days, urgency, reason


# ---------------------------------------------------------------------------
# Maintenance date computation
# ---------------------------------------------------------------------------

def compute_maintenance_date(current_date: str, interval_days: int) -> str:
    """
    Compute the recommended maintenance date.

    recommended_date = current_date + interval_days

    Parameters
    ----------
    current_date : str  ISO 8601
    interval_days : int

    Returns
    -------
    str  ISO 8601 date
    """
    return (pd.Timestamp(current_date) + pd.Timedelta(days=interval_days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Vectorised recommendation engine (full DataFrame)
# ---------------------------------------------------------------------------

def apply_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply maintenance recommendations to every row in the DCSS-enriched DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: 'risk_level', 'date', 'dcss', 'vehicle_id'.
        Optionally: 'top_factors' (JSON string from duty_cycle_model).

    Returns
    -------
    pd.DataFrame  — with added recommendation columns.
    """
    logger.info("Applying maintenance recommendations to %d records...", len(df))

    intervals, urgencies, reasons = [], [], []
    maint_dates = []

    for idx, row in df.iterrows():
        days, urgency, reason = compute_interval(row["risk_level"])
        maint_date = compute_maintenance_date(row["date"], days)
        intervals.append(days)
        urgencies.append(urgency)
        reasons.append(reason)
        maint_dates.append(maint_date)

    df = df.copy()
    df["recommended_interval_days"]    = intervals
    df["recommended_maintenance_date"] = maint_dates
    df["recommendation_urgency"]       = urgencies
    df["recommendation_reason"]        = reasons
    df["recommended_by"]               = "prototype"

    # Summary log
    urgency_dist = df["recommendation_urgency"].value_counts().to_dict()
    logger.info("Recommendation urgency distribution: %s", urgency_dist)
    logger.info(
        "Recommended intervals — min: %d, mean: %.1f, max: %d days",
        df["recommended_interval_days"].min(),
        df["recommended_interval_days"].mean(),
        df["recommended_interval_days"].max(),
    )

    return df


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def get_recommendations_for_vehicle(
    df: pd.DataFrame,
    vehicle_id: str,
    most_recent_only: bool = True,
) -> pd.DataFrame:
    """
    Retrieve maintenance recommendations for a single vehicle.

    Parameters
    ----------
    df : pd.DataFrame  — full recommendations DataFrame
    vehicle_id : str
    most_recent_only : bool
        If True, return only the most recent record. If False, return all records.

    Returns
    -------
    pd.DataFrame  (possibly a single row)
    """
    vdf = df[df["vehicle_id"] == vehicle_id].sort_values("date")
    if most_recent_only:
        return vdf.tail(1)
    return vdf


def get_immediate_action_vehicles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return all vehicles currently requiring IMMEDIATE or URGENT action.
    Uses the most recent record per vehicle.
    """
    latest = df.sort_values("date").groupby("vehicle_id").tail(1)
    urgent = latest[latest["recommendation_urgency"].isin(["IMMEDIATE", "URGENT"])]
    return urgent.sort_values("dcss", ascending=False)


# ---------------------------------------------------------------------------
# Save output
# ---------------------------------------------------------------------------

def save_recommendations(df: pd.DataFrame, project_root: Path) -> None:
    """Save full recommendations DataFrame to data/processed/."""
    out_path = project_root / cfg.PROCESSED_DATA_DIR / "maintenance_recommendations.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    logger.info(
        "Saved recommendations to: %s (%d rows, %d cols)",
        out_path, len(df), len(df.columns),
    )


# ---------------------------------------------------------------------------
# Pipeline runner (called by run_experiment.py and tests)
# ---------------------------------------------------------------------------

def run_maintenance_engine(
    dcss_df: Optional[pd.DataFrame] = None,
    project_root: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Run the full maintenance engine pipeline.

    Parameters
    ----------
    dcss_df : pd.DataFrame | None
        DCSS-enriched dataframe from duty_cycle_model. If None, loads features
        from disk and runs DCSS in-process.
    project_root : Path | None

    Returns
    -------
    pd.DataFrame  with full recommendation columns.
    """
    if project_root is None:
        project_root = PROJECT_ROOT

    if dcss_df is None:
        # Load features and compute DCSS in-process
        from feature_engineering import run_feature_engineering
        from duty_cycle_model import run_duty_cycle_model
        feat_df = run_feature_engineering(project_root=project_root)
        dcss_df = run_duty_cycle_model(features_df=feat_df, project_root=project_root)

    logger.info("=== MAINTENANCE ENGINE PIPELINE START ===")
    logger.info("IMPORTANT: All data is SYNTHETIC.")

    recs_df = apply_recommendations(dcss_df)
    save_recommendations(recs_df, project_root)

    logger.info("=== MAINTENANCE ENGINE PIPELINE COMPLETE ===")
    return recs_df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from feature_engineering import run_feature_engineering
    from duty_cycle_model import run_duty_cycle_model

    feat_df = run_feature_engineering(project_root=PROJECT_ROOT)
    dcss_df = run_duty_cycle_model(features_df=feat_df, project_root=PROJECT_ROOT)
    recs_df = run_maintenance_engine(dcss_df=dcss_df, project_root=PROJECT_ROOT)

    print("\n" + "=" * 60)
    print("  MAINTENANCE ENGINE SUMMARY (SYNTHETIC DATA)")
    print("=" * 60)
    print(f"  Total recommendations:  {len(recs_df)}")

    print("\n  Urgency Distribution:")
    for u in ["IMMEDIATE","URGENT","ROUTINE","DEFERRED"]:
        n = (recs_df["recommendation_urgency"] == u).sum()
        pct = 100 * n / len(recs_df)
        print(f"    {u:<12}: {n:6d} ({pct:.1f}%)")

    print("\n  Interval Distribution:")
    ivdist = recs_df["recommended_interval_days"].value_counts().sort_index()
    for days, count in ivdist.items():
        print(f"    {days:3d} days: {count}")

    print("\n  Latest Immediate/Urgent Vehicles:")
    urgent = get_immediate_action_vehicles(recs_df)
    cols = ["vehicle_id","date","dcss","risk_level","recommendation_urgency",
            "recommended_interval_days","recommended_maintenance_date"]
    print(urgent[cols].head(10).to_string(index=False))

    print("\n  Sample reason text (first CRITICAL record):")
    critical_sample = recs_df[recs_df["risk_level"] == "CRITICAL"].head(1)
    if len(critical_sample):
        print(f"    {critical_sample.iloc[0]['recommendation_reason']}")
    print("=" * 60)
    print("maintenance_engine.py: standalone run complete.")
