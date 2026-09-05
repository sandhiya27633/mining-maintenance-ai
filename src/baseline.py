"""
baseline.py — Fixed-Calendar Maintenance Baseline Model
========================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC.

This module implements the fixed-calendar baseline for comparison with the
DCSS prototype. The baseline applies a constant maintenance interval
(default: BASELINE_INTERVAL_DAYS = 30 days) to every vehicle regardless of:
  - mileage, engine hours, load, route severity, fault count, or any other
    operational condition.

The baseline is intentionally simple — it represents the current real-world
practice that this project aims to improve upon.

The same failure simulator (failure_simulator.py) is applied to both models.
The only difference is the maintenance interval used to determine whether
a given breakdown event is prevented by a recent service.

Output:
  A DataFrame with a constant 'recommended_interval_days' column equal to
  BASELINE_INTERVAL_DAYS, and 'risk_level' = 'NORMAL' for all records
  (because the baseline does not compute risk — it ignores conditions entirely).
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("baseline")


def apply_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the fixed-calendar baseline model to a features/DCSS DataFrame.

    Adds columns:
      - baseline_interval_days : int  (constant = BASELINE_INTERVAL_DAYS for all rows)
      - baseline_risk_level    : str  (constant = 'NORMAL' — baseline has no risk model)
      - baseline_maintenance_date : str  (ISO 8601, last_service_date + interval)
      - baseline_reason        : str  (fixed text explanation)

    The baseline does NOT compute DCSS, does NOT rank factors, and does NOT
    respond to any operational condition. This is the comparison point.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: 'vehicle_id', 'date', 'days_since_last_service'.

    Returns
    -------
    pd.DataFrame  — original + baseline columns
    """
    logger.info(
        "Applying fixed-calendar baseline (interval=%d days) to %d records.",
        cfg.BASELINE_INTERVAL_DAYS, len(df),
    )

    df = df.copy()
    df["baseline_interval_days"] = cfg.BASELINE_INTERVAL_DAYS
    df["baseline_risk_level"]    = "NORMAL"   # Baseline has no risk model

    # Recommended maintenance date = current date + remaining days to interval
    # (i.e. interval - days_since_last_service, min 1 day)
    def _baseline_maint_date(row: pd.Series) -> str:
        days_since = row.get("days_since_last_service")
        if pd.isna(days_since):
            days_since = 0  # New vehicle: assume just entered service
        remaining = max(1, cfg.BASELINE_INTERVAL_DAYS - int(days_since))
        maint_date = pd.Timestamp(row["date"]) + pd.Timedelta(days=remaining)
        return maint_date.strftime("%Y-%m-%d")

    df["baseline_maintenance_date"] = df.apply(_baseline_maint_date, axis=1)
    df["baseline_reason"] = (
        f"Fixed-calendar interval: service every {cfg.BASELINE_INTERVAL_DAYS} days "
        "regardless of operating conditions."
    )

    logger.info("Baseline model applied.")
    return df


def get_baseline_service_dates(df: pd.DataFrame) -> dict[str, list[str]]:
    """
    Compute the scheduled service dates for each vehicle under the baseline model.

    For each vehicle, starting from their last_service_date, services are
    scheduled every BASELINE_INTERVAL_DAYS for the duration of the simulation.

    Parameters
    ----------
    df : pd.DataFrame  — must contain 'vehicle_id', 'date', 'days_since_last_service'

    Returns
    -------
    dict[str, list[str]]  vehicle_id -> list of service date strings
    """
    service_schedule: dict[str, list[str]] = {}

    sim_start = pd.Timestamp(cfg.SIMULATION_START_DATE)
    sim_end = sim_start + pd.Timedelta(days=cfg.SIMULATION_DAYS - 1)

    for vid, vdf in df.groupby("vehicle_id"):
        first_row = vdf.sort_values("date").iloc[0]
        days_since = first_row.get("days_since_last_service", 0)
        if pd.isna(days_since):
            days_since = 0

        # Back-compute last service date before simulation start
        first_date = pd.Timestamp(first_row["date"])
        last_svc = first_date - pd.Timedelta(days=int(days_since))

        # Generate all service dates within simulation window
        svc_dates = []
        next_svc = last_svc + pd.Timedelta(days=cfg.BASELINE_INTERVAL_DAYS)
        while next_svc <= sim_end:
            if next_svc >= sim_start:
                svc_dates.append(next_svc.strftime("%Y-%m-%d"))
            next_svc += pd.Timedelta(days=cfg.BASELINE_INTERVAL_DAYS)

        service_schedule[str(vid)] = svc_dates

    return service_schedule


if __name__ == "__main__":
    feat_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_FEATURES_FILE
    df = pd.read_csv(feat_path)
    baseline_df = apply_baseline(df)

    print("\n=== BASELINE MODEL SUMMARY (SYNTHETIC DATA) ===")
    print(f"  Records:          {len(baseline_df)}")
    print(f"  Interval:         {cfg.BASELINE_INTERVAL_DAYS} days (fixed, all vehicles)")
    print(f"  Risk level:       NORMAL (no risk model in baseline)")
    print(f"  Sample outputs (first 3 vehicles):")
    sample = (
        baseline_df[["vehicle_id","date","baseline_interval_days",
                     "baseline_maintenance_date","baseline_risk_level"]]
        .drop_duplicates("vehicle_id").head(3)
    )
    print(sample.to_string(index=False))
    print("baseline.py: standalone run complete.")
