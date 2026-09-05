"""
feature_engineering.py — Sub-Score Computation (0–100 each)
============================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data processed here is SYNTHETIC.

Computes six normalised sub-scores (0–100) per vehicle per day:
  1. mileage_score          — based on daily mileage vs reference
  2. engine_hour_score      — based on daily engine hours vs reference
  3. load_score             — direct mapping from load_percentage
  4. route_severity_score_n — normalised route severity (0–10 → 0–100)
  5. fault_score            — weighted combination of fault_count + fault_severity
  6. service_wear_score     — days since last service vs standard interval

All formulas are documented in Phase 1 design (docs/phase1_design.md Section 8.1).
All reference values come from config.py — no hard-coding here.

Rolling window smoothing (ROLLING_WINDOW_DAYS) is applied where sufficient history
is available; the current day's value is used as fallback.

Usage:
  python src/feature_engineering.py

Expected output:
  data/processed/operational_data_features.csv  (all sub-scores added as columns)
  Console summary statistics
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Dict

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
logger = logging.getLogger("feature_engineering")


# ---------------------------------------------------------------------------
# Individual sub-score functions (scalar, vectorised-friendly)
# ---------------------------------------------------------------------------

def compute_mileage_score(daily_mileage_km: pd.Series) -> pd.Series:
    """
    Mileage Score = min(100, (daily_mileage_km / MILEAGE_SCORE_REF_KM) * 100)

    Reference: 300 km/day = score 100 (extreme cycle frequency).
    Values below reference scale linearly; values above are capped at 100.

    Parameters
    ----------
    daily_mileage_km : pd.Series  (non-negative, post-cleaning)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    score = (daily_mileage_km / cfg.MILEAGE_SCORE_REF_KM) * 100.0
    return score.clip(0.0, 100.0)


def compute_engine_hour_score(engine_hours: pd.Series) -> pd.Series:
    """
    Engine Hour Score = min(100, (engine_hours / ENGINE_HOUR_SCORE_REF) * 100)

    Reference: 20 hours/day = score 100 (virtually no thermal rest period).

    Parameters
    ----------
    engine_hours : pd.Series  (non-negative, post-cleaning)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    score = (engine_hours / cfg.ENGINE_HOUR_SCORE_REF) * 100.0
    return score.clip(0.0, 100.0)


def compute_load_score(load_percentage: pd.Series) -> pd.Series:
    """
    Load Score = load_percentage  (direct mapping, already 0–100 post-cleaning)

    No additional normalisation needed — the field is already a percentage.

    Parameters
    ----------
    load_percentage : pd.Series  (0–100, no nulls after preprocessing)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    return load_percentage.clip(0.0, 100.0)


def compute_route_severity_score(route_severity_score: pd.Series) -> pd.Series:
    """
    Route Severity Score (normalised) = (route_severity_score / 10.0) * 100

    Raw field is 0–10 continuous. Normalised to 0–100 for weighted-sum consistency.

    Parameters
    ----------
    route_severity_score : pd.Series  (0–10, post-cleaning)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    score = (route_severity_score / 10.0) * 100.0
    return score.clip(0.0, 100.0)


def compute_fault_score(
    fault_count: pd.Series,
    fault_severity_score: pd.Series,
) -> pd.Series:
    """
    Fault Score = min(100,
        (fault_count * FAULT_COUNT_WEIGHT + fault_severity * FAULT_SEVERITY_WEIGHT) * 10
    )

    Fault severity (0–10) is weighted more heavily than raw count because a single
    critical fault (severity ~9) is more predictive of failure than many minor faults.

    Scale factor of 10: at fault_count=1, severity=10 → (0.4*1 + 0.6*10)*10 = 64
                         at fault_count=3, severity=5  → (0.4*3 + 0.6*5)*10  = 42

    Parameters
    ----------
    fault_count : pd.Series  (int >= 0)
    fault_severity_score : pd.Series  (float 0–10)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    raw = (
        fault_count.astype(float) * cfg.FAULT_SCORE_COUNT_WEIGHT
        + fault_severity_score * cfg.FAULT_SCORE_SEVERITY_WEIGHT
    ) * 10.0
    return raw.clip(0.0, 100.0)


def compute_service_wear_score(
    days_since_last_service: pd.Series,
) -> pd.Series:
    """
    Service/Wear Score = min(100, (days_since_last_service / SERVICE_INTERVAL_DAYS) * 100)

    Interpretation:
      0 days since service → score ~0 (just serviced, low accumulated wear)
      30 days since service (= standard interval) → score 100 (max accumulated wear)

    Special case: NULL days (new vehicle, no service history):
      Imputed to SERVICE_INTERVAL_DAYS / 2 = 15 days (neutral assumption).
      This is a conservative mid-point: not assuming fresh (0) or overdue (30).
      Flagged by the MISSING_SERVICE_HISTORY flag added in feature engineering output.

    Parameters
    ----------
    days_since_last_service : pd.Series  (int >= 0, or NaN for new vehicles)

    Returns
    -------
    pd.Series  float, range [0, 100]
    """
    # Fill NaN with neutral mid-point
    neutral = cfg.SERVICE_INTERVAL_DAYS / 2.0  # 15 days
    filled = days_since_last_service.fillna(neutral)
    score = (filled / cfg.SERVICE_INTERVAL_DAYS) * 100.0
    return score.clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# Rolling window smoothing
# ---------------------------------------------------------------------------

def apply_rolling_window(
    df: pd.DataFrame,
    score_cols: list[str],
    window: int = cfg.ROLLING_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Apply a rolling mean over the past `window` days per vehicle per score column.

    The rolling window smooths daily volatility in sub-scores. For days with
    fewer than `window` records (start of simulation), the available records are
    used (min_periods=1 ensures no NaN is introduced).

    The result replaces the raw daily scores with smoothed values.
    Original (pre-roll) scores are retained with the suffix `_raw`.

    Parameters
    ----------
    df : pd.DataFrame  (sorted by vehicle_id, date)
    score_cols : list of column names to smooth
    window : int  rolling window size in days

    Returns
    -------
    pd.DataFrame with `_raw` columns added and main columns smoothed
    """
    df = df.sort_values(["vehicle_id", "date"]).reset_index(drop=True)

    for col in score_cols:
        # Preserve raw value
        df[f"{col}_raw"] = df[col].copy()
        # Apply rolling per vehicle
        df[col] = (
            df.groupby("vehicle_id")[col]
            .transform(lambda x: x.rolling(window=window, min_periods=1).mean())
            .round(4)
        )

    logger.info(
        "Applied %d-day rolling window to: %s", window, ", ".join(score_cols)
    )
    return df


# ---------------------------------------------------------------------------
# Service history flag column
# ---------------------------------------------------------------------------

def add_service_history_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a boolean column `missing_service_history` = True for records where
    days_since_last_service is NaN (new vehicle edge case).

    This flag is used by downstream modules to identify and track the edge case.
    """
    df["missing_service_history"] = df["days_since_last_service"].isna()
    n_missing = int(df["missing_service_history"].sum())
    if n_missing > 0:
        logger.info(
            "missing_service_history flag: %d records marked (new vehicles with no prior service).",
            n_missing,
        )
    return df


# ---------------------------------------------------------------------------
# Main feature engineering function
# ---------------------------------------------------------------------------

def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all six sub-scores for every record in the cleaned operational dataset.

    Steps:
    1. Compute raw daily sub-scores (6 features).
    2. Apply rolling window smoothing.
    3. Add missing_service_history flag.
    4. Round all scores to 4 decimal places.

    Parameters
    ----------
    df : pd.DataFrame  — cleaned operational data (output of preprocessing.py)

    Returns
    -------
    pd.DataFrame  — original columns + sub-scores + _raw columns
    """
    logger.info("Computing sub-scores for %d records...", len(df))

    # --- Raw daily sub-scores ---
    df["mileage_score"]          = compute_mileage_score(df["mileage_km"])
    df["engine_hour_score"]      = compute_engine_hour_score(df["engine_hours"])
    df["load_score"]             = compute_load_score(df["load_percentage"])
    df["route_severity_score_n"] = compute_route_severity_score(df["route_severity_score"])
    df["fault_score"]            = compute_fault_score(df["fault_count"], df["fault_severity_score"])
    df["service_wear_score"]     = compute_service_wear_score(df["days_since_last_service"])

    sub_score_cols = [
        "mileage_score",
        "engine_hour_score",
        "load_score",
        "route_severity_score_n",
        "fault_score",
        "service_wear_score",
    ]

    # --- Add missing service history flag before rolling (so flag is preserved) ---
    df = add_service_history_flag(df)

    # --- Rolling window smoothing ---
    df = apply_rolling_window(df, sub_score_cols, window=cfg.ROLLING_WINDOW_DAYS)

    # --- Round final scores ---
    for col in sub_score_cols:
        df[col] = df[col].round(4)

    logger.info("Sub-score computation complete.")
    _log_score_statistics(df, sub_score_cols)

    return df


def _log_score_statistics(df: pd.DataFrame, cols: list[str]) -> None:
    """Log descriptive statistics for each sub-score column."""
    logger.info("Sub-score statistics (post-smoothing):")
    for col in cols:
        s = df[col]
        logger.info(
            "  %-30s  min=%5.1f  mean=%5.1f  max=%5.1f  std=%5.1f",
            col, s.min(), s.mean(), s.max(), s.std(),
        )


# ---------------------------------------------------------------------------
# Correlation check (for validation/reporting)
# ---------------------------------------------------------------------------

def compute_score_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Pearson correlation matrix among the six sub-scores.
    Used in reporting to confirm realistic correlations exist
    (e.g. load_score should correlate with engine_hour_score).

    Returns
    -------
    pd.DataFrame — 6x6 correlation matrix
    """
    score_cols = [
        "mileage_score", "engine_hour_score", "load_score",
        "route_severity_score_n", "fault_score", "service_wear_score",
    ]
    return df[score_cols].corr().round(3)


# ---------------------------------------------------------------------------
# Save output
# ---------------------------------------------------------------------------

def save_features(df: pd.DataFrame, project_root: Path) -> None:
    """Save the feature-engineered dataset to data/processed/."""
    out_path = project_root / cfg.OPERATIONAL_DATA_FEATURES_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    logger.info("Saved feature dataset to: %s (%d rows, %d cols)", out_path, len(df), len(df.columns))


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_feature_summary(df: pd.DataFrame) -> None:
    """Print sub-score statistics and correlation summary to stdout."""
    sub_score_cols = [
        "mileage_score", "engine_hour_score", "load_score",
        "route_severity_score_n", "fault_score", "service_wear_score",
    ]

    print("\n" + "=" * 60)
    print("  FEATURE ENGINEERING SUMMARY")
    print("  (All data is SYNTHETIC)")
    print("=" * 60)
    print(f"  Total records: {len(df)}")
    print(f"  Sub-score columns: {sub_score_cols}")

    print("\n  Sub-score descriptive statistics (post-rolling-window):")
    print(f"  {'Score':<30} {'Min':>6} {'Mean':>6} {'Max':>6} {'Std':>6}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
    for col in sub_score_cols:
        s = df[col]
        print(f"  {col:<30} {s.min():6.1f} {s.mean():6.1f} {s.max():6.1f} {s.std():6.1f}")

    print("\n  Score correlations (Pearson, post-smoothing):")
    corr = compute_score_correlations(df)
    header = f"  {'':30}" + "".join(f"{c[:8]:>10}" for c in corr.columns)
    print(header)
    for row_name, row in corr.iterrows():
        vals = "".join(f"{v:10.3f}" for v in row)
        print(f"  {row_name:<30}{vals}")

    # Spot-check: disruption vs normal fault_score comparison
    if "scenario_tag" in df.columns:
        normal_fs = df[df["scenario_tag"] == "NORMAL"]["fault_score"].mean()
        disrupt_fs = df[df["scenario_tag"] == "DISRUPTION"]["fault_score"].mean()
        print(f"\n  Disruption scenario check:")
        print(f"    Normal avg fault_score:     {normal_fs:.2f}")
        print(f"    Disruption avg fault_score: {disrupt_fs:.2f}")
        ratio = disrupt_fs / normal_fs if normal_fs > 0 else float("inf")
        print(f"    Disruption/Normal ratio:    {ratio:.2f}x")

    missing_svc = df["missing_service_history"].sum() if "missing_service_history" in df.columns else 0
    print(f"\n  Edge case records (missing service history): {missing_svc}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Pipeline runner (used by run_experiment.py and standalone)
# ---------------------------------------------------------------------------

def run_feature_engineering(
    clean_df: pd.DataFrame | None = None,
    project_root: Path | None = None,
) -> pd.DataFrame:
    """
    Run the feature engineering pipeline.

    Parameters
    ----------
    clean_df : pd.DataFrame | None
        Pre-loaded cleaned dataframe. If None, loads from disk.
    project_root : Path | None
        Defaults to PROJECT_ROOT.

    Returns
    -------
    pd.DataFrame  with all sub-scores added.
    """
    if project_root is None:
        project_root = PROJECT_ROOT

    if clean_df is None:
        clean_path = project_root / cfg.OPERATIONAL_DATA_CLEAN_FILE
        if not clean_path.exists():
            raise FileNotFoundError(
                f"Clean data not found at {clean_path}. "
                "Run src/preprocessing.py first."
            )
        clean_df = pd.read_csv(clean_path)
        logger.info("Loaded clean data: %d rows.", len(clean_df))


    logger.info("=== FEATURE ENGINEERING PIPELINE START ===")
    logger.info("IMPORTANT: All data is SYNTHETIC.")

    features_df = compute_all_features(clean_df)
    save_features(features_df, project_root)

    logger.info("=== FEATURE ENGINEERING PIPELINE COMPLETE ===")
    return features_df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    features_df = run_feature_engineering(project_root=PROJECT_ROOT)
    print_feature_summary(features_df)
    print("Phase 3 Step 2 complete: Feature engineering done.")
    print(f"  -> {PROJECT_ROOT / cfg.OPERATIONAL_DATA_FEATURES_FILE}")
