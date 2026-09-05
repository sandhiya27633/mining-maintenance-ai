"""
config.py — Single Source of Truth for All System Parameters
=============================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

RULES:
  - Every numeric threshold, weight, interval, and coefficient lives HERE.
  - No logic module may hard-code any of these values.
  - To tune the system, edit ONLY this file.
  - Config is validated at import time; an invalid config raises ValueError immediately.

All data generated and used by this system is SYNTHETIC.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict

# ---------------------------------------------------------------------------
# 1. REPRODUCIBILITY
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# 2. FLEET / SIMULATION PARAMETERS
# ---------------------------------------------------------------------------
NUM_VEHICLES: int = 40
SIMULATION_START_DATE: str = "2024-01-01"   # ISO 8601
SIMULATION_DAYS: int = 365

# Disruption scenario window (day indices, 0-based)
DISRUPTION_START_DAY: int = 300   # day index (0-based), i.e. day 301 of simulation
DISRUPTION_END_DAY: int = 330     # exclusive end

# ---------------------------------------------------------------------------
# 3. VEHICLE METADATA DISTRIBUTIONS
# ---------------------------------------------------------------------------
VEHICLE_TYPES: list[str] = ["HAUL_TRUCK", "LOADER", "BULLDOZER", "GRADER"]
VEHICLE_TYPE_WEIGHTS: list[float] = [0.50, 0.25, 0.15, 0.10]  # must sum to 1.0

MANUFACTURE_YEAR_RANGE: tuple[int, int] = (2014, 2023)  # inclusive

# Max load capacity (tonnes) by vehicle type
MAX_LOAD_CAPACITY: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK":  (180.0, 240.0),
    "LOADER":      (30.0,  60.0),
    "BULLDOZER":   (20.0,  40.0),
    "GRADER":      (15.0,  25.0),
}

# Odometer at registration (km) — some vehicles come with pre-existing mileage
ODOMETER_AT_REGISTRATION_RANGE: tuple[float, float] = (0.0, 50_000.0)

# ---------------------------------------------------------------------------
# 4. DAILY OPERATIONAL DISTRIBUTIONS (NORMAL SCENARIO)
# ---------------------------------------------------------------------------
# Mileage (km/day) by vehicle type — (mean, std)
DAILY_MILEAGE_DIST: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK":  (180.0, 40.0),
    "LOADER":      (60.0,  15.0),
    "BULLDOZER":   (45.0,  12.0),
    "GRADER":      (80.0,  20.0),
}

# Engine hours (hours/day) — (mean, std)
ENGINE_HOURS_DIST: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK":  (14.0, 2.5),
    "LOADER":      (10.0, 2.0),
    "BULLDOZER":   (11.0, 2.0),
    "GRADER":      (9.0,  2.0),
}

# Load percentage (0–100) — (mean, std); clipped to [0, 100]
LOAD_PERCENTAGE_DIST: tuple[float, float] = (68.0, 15.0)

# Route severity score (0–10) — (mean, std); clipped to [0, 10]
ROUTE_SEVERITY_DIST: tuple[float, float] = (4.5, 2.0)

# Fault count per day — Poisson lambda
FAULT_COUNT_LAMBDA_NORMAL: float = 0.8

# Fault severity score (0–10) | given fault_count > 0 — (mean, std)
FAULT_SEVERITY_DIST: tuple[float, float] = (3.5, 2.0)

# Operating stress index (0–10) — correlated with load + route severity (mean, std)
OPERATING_STRESS_INDEX_DIST: tuple[float, float] = (4.0, 1.5)

# ---------------------------------------------------------------------------
# 5. DISRUPTION SCENARIO — DELTA ADJUSTMENTS
# These values are ADDED to normal parameters during the disruption window.
# ---------------------------------------------------------------------------
DISRUPTION_ROUTE_SEVERITY_DELTA: float = 2.5   # added to route severity
DISRUPTION_LOAD_DELTA: float = 15.0             # added to load percentage
DISRUPTION_ENGINE_HOURS_DELTA: float = 3.0      # added to engine hours
DISRUPTION_FAULT_LAMBDA_MULTIPLIER: float = 4.0 # Poisson lambda multiplied

# ---------------------------------------------------------------------------
# 6. DATA QUALITY INJECTION RATES
# ---------------------------------------------------------------------------
# Fraction of records affected by each quality issue
DQ_MISSING_LOAD_RATE: float = 0.04          # 4% of records
DQ_INVALID_LOAD_RATE: float = 0.01          # 1% — load > 100 or < 0
DQ_MISSING_ENGINE_HOURS_RATE: float = 0.03  # 3%
DQ_DUPLICATE_RATE: float = 0.01             # 1% of records duplicated
DQ_INVALID_MILEAGE_RATE: float = 0.01       # 1% — cumulative decreases
DQ_MISSING_FAULT_INFO_RATE: float = 0.02    # 2%

# ---------------------------------------------------------------------------
# 7. FEATURE ENGINEERING — SUB-SCORE REFERENCE VALUES
# ---------------------------------------------------------------------------
# Daily mileage at which Mileage Score = 100
MILEAGE_SCORE_REF_KM: float = 300.0

# Engine hours/day at which Engine Hour Score = 100
ENGINE_HOUR_SCORE_REF: float = 20.0

# Standard maintenance interval (days) — used in Service/Wear Score denominator
SERVICE_INTERVAL_DAYS: int = 30

# Fault score internal weights
FAULT_SCORE_COUNT_WEIGHT: float = 0.4
FAULT_SCORE_SEVERITY_WEIGHT: float = 0.6

# Rolling window (days) for sub-score smoothing
ROLLING_WINDOW_DAYS: int = 7

# Route severity label thresholds (applied to raw 0–10 score)
ROUTE_SEVERITY_LABELS: Dict[str, tuple[float, float]] = {
    "Low":     (0.0,  3.33),
    "Medium":  (3.33, 6.67),
    "High":    (6.67, 9.5),
    "Extreme": (9.5,  10.0),
}

# ---------------------------------------------------------------------------
# 8. DCSS WEIGHTS — DEFAULT CONFIGURATION
# Must sum to exactly 1.0 (validated at import).
# ---------------------------------------------------------------------------
DCSS_WEIGHTS_DEFAULT: Dict[str, float] = {
    "fault_score":              0.30,
    "route_severity_score":     0.20,
    "load_score":               0.20,
    "engine_hour_score":        0.15,
    "mileage_score":            0.10,
    "service_wear_score":       0.05,
}

# ---------------------------------------------------------------------------
# 9. DCSS WEIGHTS — SENSITIVITY ANALYSIS CONFIGURATIONS
# ---------------------------------------------------------------------------
DCSS_WEIGHTS_FAULT_HEAVY: Dict[str, float] = {
    "fault_score":              0.45,
    "route_severity_score":     0.20,
    "load_score":               0.15,
    "engine_hour_score":        0.10,
    "mileage_score":            0.05,
    "service_wear_score":       0.05,
}

DCSS_WEIGHTS_LOAD_HEAVY: Dict[str, float] = {
    "fault_score":              0.25,
    "route_severity_score":     0.20,
    "load_score":               0.30,
    "engine_hour_score":        0.15,
    "mileage_score":            0.05,
    "service_wear_score":       0.05,
}

# Map of config name -> weights dict (used by evaluation/sensitivity analysis)
DCSS_WEIGHT_CONFIGS: Dict[str, Dict[str, float]] = {
    "Default":     DCSS_WEIGHTS_DEFAULT,
    "Fault-Heavy": DCSS_WEIGHTS_FAULT_HEAVY,
    "Load-Heavy":  DCSS_WEIGHTS_LOAD_HEAVY,
}

# ---------------------------------------------------------------------------
# 10. RISK CLASSIFICATION THRESHOLDS
# ---------------------------------------------------------------------------
RISK_THRESHOLDS: Dict[str, tuple[float, float]] = {
    "LOW":      (0.0,  25.0),
    "NORMAL":   (25.0, 50.0),
    "HIGH":     (50.0, 75.0),
    "CRITICAL": (75.0, 100.0),
}

# fault_severity_score >= this value forces CRITICAL classification regardless of DCSS
CRITICAL_FAULT_SEVERITY_THRESHOLD: float = 8.0

# ---------------------------------------------------------------------------
# 11. MAINTENANCE INTERVAL MAPPING
# ---------------------------------------------------------------------------
STANDARD_INTERVAL_DAYS: int = 30
BASELINE_INTERVAL_DAYS: int = 30      # Fixed-calendar baseline (same as standard)

# Interval multipliers by risk level
LOW_INTERVAL_EXTENSION_FACTOR: float = 1.5   # 30 * 1.5 = 45 days
HIGH_INTERVAL_REDUCTION_FACTOR: float = 0.6  # 30 * 0.6 = 18 days
CRITICAL_MAX_DAYS: int = 3                    # Immediate inspection

# Hard limits
MIN_INTERVAL_DAYS: int = 1
MAX_INTERVAL_DAYS: int = 60

# ---------------------------------------------------------------------------
# 12. FAILURE PROBABILITY FUNCTION COEFFICIENTS
# ---------------------------------------------------------------------------
# sigmoid(alpha_fault*fault_norm + alpha_route*route_norm + ... - beta_intercept)
FAILURE_ALPHA_FAULT: float = 2.0
FAILURE_ALPHA_ROUTE: float = 1.5
FAILURE_ALPHA_LOAD: float = 1.5
FAILURE_ALPHA_ENGINE: float = 1.2
FAILURE_ALPHA_MILEAGE: float = 0.8
FAILURE_ALPHA_DAYS_SINCE: float = 1.0
FAILURE_BETA_INTERCEPT: float = 6.5  # Tuned: produces ~3-8% daily breakdown rate under normal conditions
# (Original 3.5 produced ~50% rate — too high for a meaningful evaluation)

# Failure type probabilities (must sum to 1.0) — given a breakdown occurs, which type?
FAILURE_TYPE_PROBS: Dict[str, float] = {
    "ENGINE":    0.40,
    "DRIVETRAIN": 0.35,
    "BRAKE":     0.25,
}

# Service resets accumulated risk — days after service before full risk re-accumulation
SERVICE_RESET_GRACE_DAYS: int = 3

# ---------------------------------------------------------------------------
# 13. EVALUATION TARGETS
# ---------------------------------------------------------------------------
BREAKDOWN_REDUCTION_TARGET_PCT: float = 20.0  # >= 20% simulated breakdown reduction

# Window (days) for pre-breakdown flag detection
BREAKDOWN_WARNING_WINDOW_DAYS: int = 7

# ---------------------------------------------------------------------------
# 14. DATABASE
# ---------------------------------------------------------------------------
DB_FILENAME: str = "mining_maintenance.db"  # relative to project root
DB_RELATIVE_PATH: str = "mining_maintenance.db"

# ---------------------------------------------------------------------------
# 15. PATHS (relative to project root — no hard-coded absolute paths)
# ---------------------------------------------------------------------------
RAW_DATA_DIR: str = "data/raw"
PROCESSED_DATA_DIR: str = "data/processed"
VEHICLES_META_FILE: str = "data/raw/vehicles_meta.csv"
OPERATIONAL_DATA_RAW_FILE: str = "data/raw/operational_data_raw.csv"
OPERATIONAL_DATA_CLEAN_FILE: str = "data/processed/operational_data_clean.csv"
OPERATIONAL_DATA_FEATURES_FILE: str = "data/processed/operational_data_features.csv"
DATA_QUALITY_LOG_FILE: str = "data/processed/data_quality_log.csv"

# ---------------------------------------------------------------------------
# 16. APPLICATION
# ---------------------------------------------------------------------------
APP_TITLE: str = "Mining Fleet Predictive Maintenance"
APP_VERSION: str = "1.0.0"
MODEL_VERSION: str = "1.0"

# ---------------------------------------------------------------------------
# VALIDATION (runs at import time)
# ---------------------------------------------------------------------------

def _validate_weights(weights: Dict[str, float], name: str) -> None:
    """Validate that a weight dict sums to 1.0 (within floating-point tolerance)."""
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"DCSS weight config '{name}' sums to {total:.6f}, must be 1.0. "
            f"Edit config.py to fix."
        )
    for key, val in weights.items():
        if val < 0.0 or val > 1.0:
            raise ValueError(
                f"Weight '{key}' in config '{name}' is {val}, must be in [0, 1]."
            )


def _validate_failure_types(probs: Dict[str, float]) -> None:
    """Validate failure type probabilities sum to 1.0."""
    total = sum(probs.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"FAILURE_TYPE_PROBS sums to {total:.6f}, must be 1.0."
        )


def _validate_config() -> None:
    """Run all config validation checks. Raises ValueError on any failure."""
    for config_name, weights in DCSS_WEIGHT_CONFIGS.items():
        _validate_weights(weights, config_name)
    _validate_failure_types(FAILURE_TYPE_PROBS)

    if DISRUPTION_START_DAY >= DISRUPTION_END_DAY:
        raise ValueError(
            f"DISRUPTION_START_DAY ({DISRUPTION_START_DAY}) must be < "
            f"DISRUPTION_END_DAY ({DISRUPTION_END_DAY})."
        )
    if DISRUPTION_END_DAY > SIMULATION_DAYS:
        raise ValueError(
            f"DISRUPTION_END_DAY ({DISRUPTION_END_DAY}) exceeds "
            f"SIMULATION_DAYS ({SIMULATION_DAYS})."
        )
    if MIN_INTERVAL_DAYS < 1:
        raise ValueError("MIN_INTERVAL_DAYS must be >= 1.")
    if CRITICAL_MAX_DAYS < 1:
        raise ValueError("CRITICAL_MAX_DAYS must be >= 1.")
    if not (0.0 < BREAKDOWN_REDUCTION_TARGET_PCT < 100.0):
        raise ValueError("BREAKDOWN_REDUCTION_TARGET_PCT must be between 0 and 100.")


# Run validation immediately on import
_validate_config()
