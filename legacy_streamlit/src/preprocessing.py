"""
preprocessing.py — Data Validation, Cleaning, and Quality Logging
==================================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC. This module never silently
modifies data. Every change is logged with: record identifier, field changed,
original value, new value, reason, and timestamp.

Responsibilities:
  1. Load raw operational data from data/raw/
  2. Detect and log all data quality issues (6 categories)
  3. Remove exact duplicate records (keep first, flag all)
  4. Reject / flag records with invalid values (out-of-range)
  5. Impute missing values using documented strategies
  6. Validate mileage consistency (cumulative must be non-decreasing per vehicle)
  7. Validate final clean dataset
  8. Write cleaned data to data/processed/operational_data_clean.csv
  9. Write data quality log to data/processed/data_quality_log.csv
  10. Never crash on dirty input — flag and continue

Usage:
  python src/preprocessing.py

Expected output:
  data/processed/operational_data_clean.csv   (one record per vehicle-day, no dupes)
  data/processed/data_quality_log.csv         (all quality actions logged)
  Console summary of actions taken
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("preprocessing")

# ---------------------------------------------------------------------------
# Quality log accumulator
# ---------------------------------------------------------------------------
_quality_log: List[Dict[str, Any]] = []


def _log_action(
    vehicle_id: str,
    date: str,
    field: str,
    original_value: Any,
    new_value: Any,
    issue_code: str,
    action: str,
    reason: str,
) -> None:
    """Append one quality-log entry. Never raises."""
    _quality_log.append({
        "timestamp":      datetime.now().isoformat(timespec="seconds"),
        "vehicle_id":     vehicle_id,
        "date":           date,
        "field":          field,
        "issue_code":     issue_code,
        "action":         action,
        "original_value": str(original_value),
        "new_value":      str(new_value),
        "reason":         reason,
    })


# ---------------------------------------------------------------------------
# Step 1 — Load raw data
# ---------------------------------------------------------------------------

def load_raw_data(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load raw vehicles metadata and operational data CSVs.

    Returns
    -------
    (vehicles_df, operational_df)

    Raises
    ------
    FileNotFoundError if expected files do not exist.
    """
    vehicles_path = project_root / cfg.VEHICLES_META_FILE
    ops_path = project_root / cfg.OPERATIONAL_DATA_RAW_FILE

    if not vehicles_path.exists():
        raise FileNotFoundError(
            f"vehicles_meta.csv not found at {vehicles_path}. "
            "Run src/data_generator.py first."
        )
    if not ops_path.exists():
        raise FileNotFoundError(
            f"operational_data_raw.csv not found at {ops_path}. "
            "Run src/data_generator.py first."
        )

    vehicles_df = pd.read_csv(vehicles_path)
    ops_df = pd.read_csv(ops_path)
    logger.info(
        "Loaded %d vehicle records and %d operational records.",
        len(vehicles_df), len(ops_df),
    )
    return vehicles_df, ops_df


# ---------------------------------------------------------------------------
# Step 2 — Remove duplicate records
# ---------------------------------------------------------------------------

def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicate (vehicle_id, date) records.

    Strategy: keep the first occurrence, drop subsequent duplicates.
    All removed rows are logged individually.
    This matches the UNIQUE(vehicle_id, date) constraint in the DB schema.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame with duplicates removed
    """
    before = len(df)
    dup_mask = df.duplicated(subset=["vehicle_id", "date"], keep="first")
    dup_rows = df[dup_mask]

    for _, row in dup_rows.iterrows():
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="(record)",
            original_value="DUPLICATE",
            new_value="REMOVED",
            issue_code="DUPLICATE_RECORD",
            action="DROP_ROW",
            reason="Duplicate (vehicle_id, date) pair — keeping first occurrence.",
        )

    df = df[~dup_mask].copy()
    removed = before - len(df)
    logger.info("Removed %d duplicate records (%d remaining).", removed, len(df))
    return df


# ---------------------------------------------------------------------------
# Step 3 — Validate and fix load_percentage
# ---------------------------------------------------------------------------

def validate_load_percentage(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle load_percentage issues:
      - MISSING_LOAD (NaN): impute with vehicle's own median for the simulation,
        falling back to fleet-day median. Flagged MISSING_LOAD.
      - INVALID_LOAD (<0 or >100): set to NaN, then impute as above. Flagged INVALID_LOAD.

    Imputation strategy documented:
      Priority 1: median of the same vehicle's non-null load values.
      Priority 2: median of all vehicles on the same date.
      Priority 3: global median of the entire dataset (last resort).
    This preserves vehicle-specific operating patterns while being robust to
    vehicles with completely missing load sensors.
    """
    # Step 3a: Reject invalid values (set to NaN, log as INVALID_LOAD)
    invalid_mask = df["load_percentage"].notna() & (
        (df["load_percentage"] < 0) | (df["load_percentage"] > 100)
    )
    for idx in df[invalid_mask].index:
        row = df.loc[idx]
        orig = df.at[idx, "load_percentage"]
        df.at[idx, "load_percentage"] = np.nan
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="load_percentage",
            original_value=orig,
            new_value=np.nan,
            issue_code="INVALID_LOAD",
            action="SET_NULL",
            reason=f"load_percentage={orig:.2f} is outside valid range [0, 100]. Set to NaN for imputation.",
        )

    # Step 3b: Impute all NaN load values
    global_median = df["load_percentage"].median()
    vehicle_medians: Dict[str, float] = (
        df.groupby("vehicle_id")["load_percentage"].median().to_dict()
    )
    date_medians: Dict[str, float] = (
        df.groupby("date")["load_percentage"].median().to_dict()
    )

    missing_mask = df["load_percentage"].isna()
    for idx in df[missing_mask].index:
        row = df.loc[idx]
        vid = str(row["vehicle_id"])
        dt = str(row["date"])

        veh_med = vehicle_medians.get(vid, np.nan)
        if not np.isnan(veh_med):
            imputed = round(float(veh_med), 2)
            strategy = "vehicle_median"
        else:
            date_med = date_medians.get(dt, np.nan)
            if not np.isnan(date_med):
                imputed = round(float(date_med), 2)
                strategy = "fleet_day_median"
            else:
                imputed = round(float(global_median), 2)
                strategy = "global_median"

        orig_code = "INVALID_LOAD" if invalid_mask.loc[idx] else "MISSING_LOAD"
        df.at[idx, "load_percentage"] = imputed
        _log_action(
            vehicle_id=vid,
            date=dt,
            field="load_percentage",
            original_value=np.nan,
            new_value=imputed,
            issue_code=orig_code,
            action=f"IMPUTE_{strategy.upper()}",
            reason=f"Missing/invalid load imputed using {strategy} = {imputed}.",
        )

    n_invalid = int(invalid_mask.sum())
    n_missing = int(missing_mask.sum())
    logger.info(
        "load_percentage: %d invalid rejected, %d missing imputed.", n_invalid, n_missing
    )
    return df


# ---------------------------------------------------------------------------
# Step 4 — Validate and fix engine_hours
# ---------------------------------------------------------------------------

def validate_engine_hours(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle engine_hours issues:
      - MISSING_ENGINE_HOURS (NaN): impute with vehicle-type median, then global median.
      - engine_hours > 24: cap at 24.0 and log (physically impossible).
      - engine_hours < 0: set to 0.0 and log.

    Requires vehicles metadata to be merged first; if vehicle_type is not present,
    falls back to global median.
    """
    # Cap values > 24 (physically impossible — day only has 24 hours)
    over_mask = df["engine_hours"].notna() & (df["engine_hours"] > 24.0)
    for idx in df[over_mask].index:
        row = df.loc[idx]
        orig = df.at[idx, "engine_hours"]
        df.at[idx, "engine_hours"] = 24.0
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="engine_hours",
            original_value=orig,
            new_value=24.0,
            issue_code="INVALID_ENGINE_HOURS",
            action="CAP_AT_24",
            reason=f"engine_hours={orig:.2f} exceeds 24h/day. Capped at 24.0.",
        )

    # Set negative values to 0
    neg_mask = df["engine_hours"].notna() & (df["engine_hours"] < 0)
    for idx in df[neg_mask].index:
        row = df.loc[idx]
        orig = df.at[idx, "engine_hours"]
        df.at[idx, "engine_hours"] = 0.0
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="engine_hours",
            original_value=orig,
            new_value=0.0,
            issue_code="INVALID_ENGINE_HOURS",
            action="SET_ZERO",
            reason=f"engine_hours={orig:.2f} is negative. Set to 0.0.",
        )

    # Impute missing values
    global_median = df["engine_hours"].median()
    vehicle_medians: Dict[str, float] = (
        df.groupby("vehicle_id")["engine_hours"].median().to_dict()
    )

    missing_mask = df["engine_hours"].isna()
    for idx in df[missing_mask].index:
        row = df.loc[idx]
        vid = str(row["vehicle_id"])
        dt = str(row["date"])

        veh_med = vehicle_medians.get(vid, np.nan)
        if not np.isnan(veh_med):
            imputed = round(float(veh_med), 2)
            strategy = "vehicle_median"
        else:
            imputed = round(float(global_median), 2)
            strategy = "global_median"

        df.at[idx, "engine_hours"] = imputed
        _log_action(
            vehicle_id=vid,
            date=dt,
            field="engine_hours",
            original_value=np.nan,
            new_value=imputed,
            issue_code="MISSING_ENGINE_HOURS",
            action=f"IMPUTE_{strategy.upper()}",
            reason=f"Missing engine hours imputed using {strategy} = {imputed}.",
        )

    logger.info(
        "engine_hours: %d capped, %d negatives zeroed, %d missing imputed.",
        int(over_mask.sum()), int(neg_mask.sum()), int(missing_mask.sum()),
    )
    return df


# ---------------------------------------------------------------------------
# Step 5 — Validate and fix fault information
# ---------------------------------------------------------------------------

def validate_fault_info(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle missing fault_count and fault_severity_score:
      - MISSING_FAULT_INFO: fault_count is NaN.
        Strategy: impute with 0 (no fault observed is the safest assumption;
        a missing sensor reading should not be treated as a guaranteed fault).
        This is a CONSERVATIVE imputation — it may underestimate risk for vehicles
        with frequently failing fault sensors. Logged explicitly.
      - fault_severity_score NaN: impute with 0.0 (same conservative logic).
    """
    missing_count_mask = df["fault_count"].isna()
    for idx in df[missing_count_mask].index:
        row = df.loc[idx]
        df.at[idx, "fault_count"] = 0
        df.at[idx, "fault_severity_score"] = 0.0
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="fault_count",
            original_value=np.nan,
            new_value=0,
            issue_code="MISSING_FAULT_INFO",
            action="IMPUTE_ZERO",
            reason=(
                "Missing fault count imputed with 0 (conservative). "
                "Missing sensor ≠ confirmed fault. "
                "WARNING: may underestimate risk on vehicles with faulty sensors."
            ),
        )

    missing_sev_mask = df["fault_severity_score"].isna()
    for idx in df[missing_sev_mask].index:
        row = df.loc[idx]
        df.at[idx, "fault_severity_score"] = 0.0
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="fault_severity_score",
            original_value=np.nan,
            new_value=0.0,
            issue_code="MISSING_FAULT_INFO",
            action="IMPUTE_ZERO",
            reason="Missing fault_severity_score imputed with 0.0 (conservative).",
        )

    # Ensure fault_count is integer after imputation
    df["fault_count"] = df["fault_count"].fillna(0).astype(int)

    logger.info(
        "fault_count: %d missing imputed with 0. fault_severity: %d missing imputed with 0.0.",
        int(missing_count_mask.sum()), int(missing_sev_mask.sum()),
    )
    return df


# ---------------------------------------------------------------------------
# Step 6 — Validate mileage consistency
# ---------------------------------------------------------------------------

def validate_mileage(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate cumulative_mileage_km is non-decreasing per vehicle over time.

    Strategy: where cumulative decreases (odometer went backwards — data corruption),
    recompute the affected record's cumulative from the previous day's cumulative
    plus the current day's mileage_km. Log the correction.

    Also flag negative mileage_km values (set to 0 and log).
    """
    # Fix negative daily mileage
    neg_mileage = df["mileage_km"] < 0
    for idx in df[neg_mileage].index:
        row = df.loc[idx]
        orig = df.at[idx, "mileage_km"]
        df.at[idx, "mileage_km"] = 0.0
        _log_action(
            vehicle_id=str(row["vehicle_id"]),
            date=str(row["date"]),
            field="mileage_km",
            original_value=orig,
            new_value=0.0,
            issue_code="INVALID_MILEAGE",
            action="SET_ZERO",
            reason=f"Negative daily mileage={orig:.2f} km set to 0.",
        )

    # Fix decreasing cumulative mileage per vehicle
    df = df.sort_values(["vehicle_id", "date"]).reset_index(drop=True)
    corrections = 0

    for vid, vdf in df.groupby("vehicle_id"):
        prev_cum = None
        for idx in vdf.index:
            curr_cum = df.at[idx, "cumulative_mileage_km"]
            daily = df.at[idx, "mileage_km"]
            dt = df.at[idx, "date"]

            if prev_cum is not None and curr_cum < prev_cum:
                # Reconstruct from previous + daily
                corrected = round(prev_cum + daily, 2)
                _log_action(
                    vehicle_id=str(vid),
                    date=str(dt),
                    field="cumulative_mileage_km",
                    original_value=curr_cum,
                    new_value=corrected,
                    issue_code="INVALID_MILEAGE",
                    action="RECOMPUTE_FROM_PREV_PLUS_DAILY",
                    reason=(
                        f"Cumulative mileage decreased from {prev_cum:.1f} to "
                        f"{curr_cum:.1f} km. Recomputed as prev({prev_cum:.1f}) "
                        f"+ daily({daily:.1f}) = {corrected:.1f}."
                    ),
                )
                df.at[idx, "cumulative_mileage_km"] = corrected
                corrections += 1
                prev_cum = corrected
            else:
                prev_cum = curr_cum

    logger.info(
        "mileage: %d negative daily values zeroed, %d cumulative corrections applied.",
        int(neg_mileage.sum()), corrections,
    )
    return df


# ---------------------------------------------------------------------------
# Step 7 — Validate remaining fields
# ---------------------------------------------------------------------------

def validate_remaining_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and clamp remaining numeric fields:
      - route_severity_score: must be in [0, 10]
      - fault_severity_score: must be in [0, 10]
      - operating_stress_index: must be in [0, 10]
      - days_since_last_service: must be >= 0 (NULL is valid for new vehicles)

    Out-of-range values are clamped and logged. Records are never dropped for
    these fields — clamping preserves the record for analysis.
    """
    clamp_fields = [
        ("route_severity_score",   0.0, 10.0, "INVALID_ROUTE_SEVERITY"),
        ("fault_severity_score",   0.0, 10.0, "INVALID_FAULT_SEVERITY"),
        ("operating_stress_index", 0.0, 10.0, "INVALID_STRESS_INDEX"),
    ]
    total_clamped = 0
    for field, lo, hi, code in clamp_fields:
        if field not in df.columns:
            continue
        out_mask = df[field].notna() & ~df[field].between(lo, hi)
        for idx in df[out_mask].index:
            row = df.loc[idx]
            orig = df.at[idx, field]
            clamped = max(lo, min(hi, orig))
            df.at[idx, field] = clamped
            _log_action(
                vehicle_id=str(row["vehicle_id"]),
                date=str(row["date"]),
                field=field,
                original_value=orig,
                new_value=clamped,
                issue_code=code,
                action="CLAMP",
                reason=f"{field}={orig:.3f} outside [{lo},{hi}]. Clamped to {clamped:.3f}.",
            )
            total_clamped += 1

    # Negative days_since_last_service (should not occur but guard anyway)
    if "days_since_last_service" in df.columns:
        neg_days = df["days_since_last_service"].notna() & (df["days_since_last_service"] < 0)
        for idx in df[neg_days].index:
            row = df.loc[idx]
            orig = df.at[idx, "days_since_last_service"]
            df.at[idx, "days_since_last_service"] = 0
            _log_action(
                vehicle_id=str(row["vehicle_id"]),
                date=str(row["date"]),
                field="days_since_last_service",
                original_value=orig,
                new_value=0,
                issue_code="INVALID_SERVICE_DAYS",
                action="SET_ZERO",
                reason=f"days_since_last_service={orig} is negative. Set to 0.",
            )
            total_clamped += 1

    logger.info("validate_remaining_fields: %d values clamped/corrected.", total_clamped)
    return df


# ---------------------------------------------------------------------------
# Step 8 — Add computed columns needed downstream
# ---------------------------------------------------------------------------

def add_computed_columns(df: pd.DataFrame, vehicles_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add columns that feature_engineering.py needs but that are best computed
    during preprocessing (after cleaning):
      - vehicle_type: joined from vehicles_df (needed for per-type medians)
      - days_since_last_service_clean: alias ensuring nulls are preserved correctly
    """
    # Merge vehicle_type if not already present
    if "vehicle_type" not in df.columns:
        vtype_map = vehicles_df.set_index("vehicle_id")["vehicle_type"].to_dict()
        df["vehicle_type"] = df["vehicle_id"].map(vtype_map)

    return df


# ---------------------------------------------------------------------------
# Step 9 — Final validation of cleaned dataset
# ---------------------------------------------------------------------------

def validate_cleaned_dataset(df: pd.DataFrame) -> tuple[bool, List[str]]:
    """
    Final sanity checks on the cleaned dataset.

    Returns
    -------
    (all_pass: bool, failure_messages: List[str])
    """
    failures: List[str] = []

    # No duplicates remain
    dups = df.duplicated(subset=["vehicle_id", "date"]).sum()
    if dups > 0:
        failures.append(f"Still has {dups} duplicate (vehicle_id, date) pairs after cleaning.")

    # No null load_percentage
    null_load = df["load_percentage"].isna().sum()
    if null_load > 0:
        failures.append(f"Still has {null_load} null load_percentage values after imputation.")

    # No null engine_hours
    null_eh = df["engine_hours"].isna().sum()
    if null_eh > 0:
        failures.append(f"Still has {null_eh} null engine_hours values after imputation.")

    # No null fault_count
    null_fc = df["fault_count"].isna().sum()
    if null_fc > 0:
        failures.append(f"Still has {null_fc} null fault_count values after imputation.")

    # load_percentage in [0, 100]
    bad_load = ((df["load_percentage"] < 0) | (df["load_percentage"] > 100)).sum()
    if bad_load > 0:
        failures.append(f"{bad_load} load_percentage values still outside [0, 100].")

    # engine_hours in [0, 24]
    bad_eh = ((df["engine_hours"] < 0) | (df["engine_hours"] > 24)).sum()
    if bad_eh > 0:
        failures.append(f"{bad_eh} engine_hours values still outside [0, 24].")

    # route_severity in [0, 10]
    bad_route = ((df["route_severity_score"] < 0) | (df["route_severity_score"] > 10)).sum()
    if bad_route > 0:
        failures.append(f"{bad_route} route_severity_score values still outside [0, 10].")

    # breakdown_occurred is 0 or 1
    bad_bd = ~df["breakdown_occurred"].isin([0, 1])
    if bad_bd.sum() > 0:
        failures.append(f"{bad_bd.sum()} breakdown_occurred values not in {{0, 1}}.")

    # Row count must equal NUM_VEHICLES * SIMULATION_DAYS (no more duplicates, no lost records)
    expected = cfg.NUM_VEHICLES * cfg.SIMULATION_DAYS
    if len(df) != expected:
        failures.append(
            f"Clean dataset has {len(df)} rows; expected exactly {expected} "
            f"({cfg.NUM_VEHICLES} vehicles × {cfg.SIMULATION_DAYS} days)."
        )

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# Step 10 — Save outputs
# ---------------------------------------------------------------------------

def save_outputs(
    df: pd.DataFrame,
    project_root: Path,
) -> None:
    """Save cleaned dataset and quality log to data/processed/."""
    processed_dir = project_root / cfg.PROCESSED_DATA_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    clean_path = project_root / cfg.OPERATIONAL_DATA_CLEAN_FILE
    log_path   = project_root / cfg.DATA_QUALITY_LOG_FILE

    df.to_csv(clean_path, index=False)
    logger.info("Saved cleaned data to:    %s (%d rows)", clean_path, len(df))

    quality_log_df = pd.DataFrame(_quality_log)
    quality_log_df.to_csv(log_path, index=False)
    logger.info(
        "Saved quality log to:     %s (%d entries)", log_path, len(quality_log_df)
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_preprocessing(project_root: Optional[Path] = None) -> pd.DataFrame:
    """
    Execute the full preprocessing pipeline.

    Parameters
    ----------
    project_root : Path | None
        Defaults to the directory two levels above this file (project root).

    Returns
    -------
    pd.DataFrame — the cleaned operational dataset.
    """
    global _quality_log
    _quality_log = []  # Reset log for this run

    if project_root is None:
        project_root = PROJECT_ROOT

    logger.info("=== PREPROCESSING PIPELINE START ===")
    logger.info("IMPORTANT: All data is SYNTHETIC.")

    # Step 1: Load
    vehicles_df, ops_df = load_raw_data(project_root)
    original_count = len(ops_df)

    # Step 2: Remove duplicates
    ops_df = remove_duplicates(ops_df)

    # Step 3: Validate load_percentage
    ops_df = validate_load_percentage(ops_df)

    # Step 4: Validate engine_hours
    ops_df = validate_engine_hours(ops_df)

    # Step 5: Validate fault info
    ops_df = validate_fault_info(ops_df)

    # Step 6: Validate mileage
    ops_df = validate_mileage(ops_df)

    # Step 7: Validate remaining fields
    ops_df = validate_remaining_fields(ops_df)

    # Step 8: Add computed columns
    ops_df = add_computed_columns(ops_df, vehicles_df)

    # Step 9: Final validation
    all_pass, failures = validate_cleaned_dataset(ops_df)
    if all_pass:
        logger.info("Final validation: ALL CHECKS PASSED.")
    else:
        for msg in failures:
            logger.warning("Final validation FAILURE: %s", msg)
        # Do not crash — log and continue (Section 30 rule: never crash on dirty data)

    # Step 10: Save
    save_outputs(ops_df, project_root)

    # Summary
    logger.info("=== PREPROCESSING PIPELINE COMPLETE ===")
    logger.info(
        "Records: %d raw -> %d clean (removed %d duplicates).",
        original_count, len(ops_df), original_count - len(ops_df),
    )
    logger.info("Quality log entries: %d total actions logged.", len(_quality_log))

    return ops_df


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_preprocessing_summary(df: pd.DataFrame) -> None:
    """Print a concise preprocessing summary to stdout."""
    actions = pd.DataFrame(_quality_log)

    print("\n" + "=" * 60)
    print("  PREPROCESSING SUMMARY")
    print("  (All data is SYNTHETIC)")
    print("=" * 60)
    print(f"  Clean records:         {len(df)}")
    print(f"  Quality log entries:   {len(actions)}")

    if not actions.empty:
        print("\n  Actions by issue code:")
        for code, grp in actions.groupby("issue_code"):
            print(f"    {code:<35}: {len(grp)} actions")
        print("\n  Actions by type:")
        for act, grp in actions.groupby("action"):
            print(f"    {act:<40}: {len(grp)}")

    print(f"\n  Remaining null values:")
    for col in ["load_percentage", "engine_hours", "fault_count", "fault_severity_score"]:
        nulls = df[col].isna().sum()
        print(f"    {col:<35}: {nulls} nulls")

    print(f"\n  days_since_last_service nulls: {df['days_since_last_service'].isna().sum()} "
          "(expected: new vehicles with no service history)")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    clean_df = run_preprocessing(project_root=PROJECT_ROOT)
    print_preprocessing_summary(clean_df)
    print("Phase 3 Step 1 complete: Preprocessed data saved.")
    print(f"  -> {PROJECT_ROOT / cfg.OPERATIONAL_DATA_CLEAN_FILE}")
    print(f"  -> {PROJECT_ROOT / cfg.DATA_QUALITY_LOG_FILE}")
