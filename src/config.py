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

from typing import Dict


# ---------------------------------------------------------------------------
# 1. REPRODUCIBILITY
# ---------------------------------------------------------------------------

RANDOM_SEED: int = 42


# ---------------------------------------------------------------------------
# 2. FLEET / SIMULATION PARAMETERS
# ---------------------------------------------------------------------------

NUM_VEHICLES: int = 40
SIMULATION_START_DATE: str = "2024-01-01"
SIMULATION_DAYS: int = 365

# Disruption scenario window (day indices, 0-based)
DISRUPTION_START_DAY: int = 300
DISRUPTION_END_DAY: int = 330


# ---------------------------------------------------------------------------
# 3. VEHICLE METADATA DISTRIBUTIONS
# ---------------------------------------------------------------------------

VEHICLE_TYPES: list[str] = [
    "HAUL_TRUCK",
    "LOADER",
    "BULLDOZER",
    "GRADER",
]

VEHICLE_TYPE_WEIGHTS: list[float] = [
    0.50,
    0.25,
    0.15,
    0.10,
]


MANUFACTURE_YEAR_RANGE: tuple[int, int] = (
    2014,
    2023,
)


# Max load capacity (tonnes) by vehicle type
MAX_LOAD_CAPACITY: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK": (180.0, 240.0),
    "LOADER": (30.0, 60.0),
    "BULLDOZER": (20.0, 40.0),
    "GRADER": (15.0, 25.0),
}


# Odometer at registration (km)
ODOMETER_AT_REGISTRATION_RANGE: tuple[float, float] = (
    0.0,
    50_000.0,
)


# ---------------------------------------------------------------------------
# 4. DAILY OPERATIONAL DISTRIBUTIONS (NORMAL SCENARIO)
# ---------------------------------------------------------------------------

# Mileage (km/day) by vehicle type — (mean, std)
DAILY_MILEAGE_DIST: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK": (180.0, 40.0),
    "LOADER": (60.0, 15.0),
    "BULLDOZER": (45.0, 12.0),
    "GRADER": (80.0, 20.0),
}


# Engine hours (hours/day) — (mean, std)
ENGINE_HOURS_DIST: Dict[str, tuple[float, float]] = {
    "HAUL_TRUCK": (14.0, 2.5),
    "LOADER": (10.0, 2.0),
    "BULLDOZER": (11.0, 2.0),
    "GRADER": (9.0, 2.0),
}


# Load percentage (0–100)
LOAD_PERCENTAGE_DIST: tuple[float, float] = (
    68.0,
    15.0,
)


# Route severity score (0–10)
ROUTE_SEVERITY_DIST: tuple[float, float] = (
    4.5,
    2.0,
)


# Fault count per day — Poisson lambda
FAULT_COUNT_LAMBDA_NORMAL: float = 0.8


# Fault severity score (0–10) | given fault_count > 0
FAULT_SEVERITY_DIST: tuple[float, float] = (
    3.5,
    2.0,
)


# Operating stress index (0–10)
OPERATING_STRESS_INDEX_DIST: tuple[float, float] = (
    4.0,
    1.5,
)


# ---------------------------------------------------------------------------
# 5. DISRUPTION SCENARIO — DELTA ADJUSTMENTS
# ---------------------------------------------------------------------------

# These values are ADDED to normal parameters during the disruption window.

DISRUPTION_ROUTE_SEVERITY_DELTA: float = 2.5
DISRUPTION_LOAD_DELTA: float = 15.0
DISRUPTION_ENGINE_HOURS_DELTA: float = 3.0
DISRUPTION_FAULT_LAMBDA_MULTIPLIER: float = 4.0


# ---------------------------------------------------------------------------
# 6. DATA QUALITY INJECTION RATES
# ---------------------------------------------------------------------------

DQ_MISSING_LOAD_RATE: float = 0.04
DQ_INVALID_LOAD_RATE: float = 0.01
DQ_MISSING_ENGINE_HOURS_RATE: float = 0.03
DQ_DUPLICATE_RATE: float = 0.01
DQ_INVALID_MILEAGE_RATE: float = 0.01
DQ_MISSING_FAULT_INFO_RATE: float = 0.02


# ---------------------------------------------------------------------------
# 7. FEATURE ENGINEERING — SUB-SCORE REFERENCE VALUES
# ---------------------------------------------------------------------------

# Daily mileage at which Mileage Score = 100
MILEAGE_SCORE_REF_KM: float = 300.0

# Engine hours/day at which Engine Hour Score = 100
ENGINE_HOUR_SCORE_REF: float = 20.0

# Standard maintenance interval (days)
SERVICE_INTERVAL_DAYS: int = 30


# Fault score internal weights
FAULT_SCORE_COUNT_WEIGHT: float = 0.4
FAULT_SCORE_SEVERITY_WEIGHT: float = 0.6


# Rolling window (days) for sub-score smoothing
ROLLING_WINDOW_DAYS: int = 7


# Route severity label thresholds
ROUTE_SEVERITY_LABELS: Dict[str, tuple[float, float]] = {
    "Low": (0.0, 3.33),
    "Medium": (3.33, 6.67),
    "High": (6.67, 9.5),
    "Extreme": (9.5, 10.0),
}


# ---------------------------------------------------------------------------
# 8. DCSS WEIGHTS — DEFAULT CONFIGURATION
# ---------------------------------------------------------------------------

# Must sum to exactly 1.0

DCSS_WEIGHTS_DEFAULT: Dict[str, float] = {
    "fault_score": 0.30,
    "route_severity_score": 0.20,
    "load_score": 0.20,
    "engine_hour_score": 0.15,
    "mileage_score": 0.10,
    "service_wear_score": 0.05,
}


# ---------------------------------------------------------------------------
# 9. DCSS WEIGHTS — SENSITIVITY ANALYSIS CONFIGURATIONS
# ---------------------------------------------------------------------------

DCSS_WEIGHTS_FAULT_HEAVY: Dict[str, float] = {
    "fault_score": 0.45,
    "route_severity_score": 0.20,
    "load_score": 0.15,
    "engine_hour_score": 0.10,
    "mileage_score": 0.05,
    "service_wear_score": 0.05,
}


DCSS_WEIGHTS_LOAD_HEAVY: Dict[str, float] = {
    "fault_score": 0.25,
    "route_severity_score": 0.20,
    "load_score": 0.30,
    "engine_hour_score": 0.15,
    "mileage_score": 0.05,
    "service_wear_score": 0.05,
}


# Map of config name -> weights dict
DCSS_WEIGHT_CONFIGS: Dict[str, Dict[str, float]] = {
    "Default": DCSS_WEIGHTS_DEFAULT,
    "Fault-Heavy": DCSS_WEIGHTS_FAULT_HEAVY,
    "Load-Heavy": DCSS_WEIGHTS_LOAD_HEAVY,
}


# ---------------------------------------------------------------------------
# 10. RISK CLASSIFICATION THRESHOLDS
# ---------------------------------------------------------------------------

RISK_THRESHOLDS: Dict[str, tuple[float, float]] = {
    "LOW": (0.0, 25.0),
    "NORMAL": (25.0, 50.0),
    "HIGH": (50.0, 75.0),
    "CRITICAL": (75.0, 100.0),
}


# Fault severity >= this value forces CRITICAL classification
CRITICAL_FAULT_SEVERITY_THRESHOLD: float = 8.0


# ---------------------------------------------------------------------------
# 11. MAINTENANCE INTERVAL MAPPING
# ---------------------------------------------------------------------------

STANDARD_INTERVAL_DAYS: int = 30
BASELINE_INTERVAL_DAYS: int = 30


# Interval multipliers by risk level

# IMPORTANT:
# LOW-risk vehicles receive a slightly longer interval
# than the standard 30-day interval.
#
# 30 * 1.2 = 36 days
#
# This preserves the required ordering:
# CRITICAL < HIGH < NORMAL < LOW
LOW_INTERVAL_EXTENSION_FACTOR: float = 1.2


# HIGH-risk vehicles receive a shorter interval.
#
# 30 * 0.25 = 7.5 -> rounded to 8 days
HIGH_INTERVAL_REDUCTION_FACTOR: float = 0.25


# CRITICAL-risk vehicles require immediate inspection.
CRITICAL_MAX_DAYS: int = 3


# Hard limits
MIN_INTERVAL_DAYS: int = 1
MAX_INTERVAL_DAYS: int = 60


# ---------------------------------------------------------------------------
# 12. FAILURE PROBABILITY FUNCTION COEFFICIENTS
# ---------------------------------------------------------------------------

# sigmoid(
#     alpha_fault*fault_norm
#     + alpha_route*route_norm
#     + alpha_load*load_norm
#     + alpha_engine*engine_norm
#     + alpha_mileage*mileage_norm
#     + alpha_days_since*days_since_norm
#     - beta_intercept
# )

FAILURE_ALPHA_FAULT: float = 2.0
FAILURE_ALPHA_ROUTE: float = 1.5
FAILURE_ALPHA_LOAD: float = 1.5
FAILURE_ALPHA_ENGINE: float = 1.2
FAILURE_ALPHA_MILEAGE: float = 0.8
FAILURE_ALPHA_DAYS_SINCE: float = 1.0

FAILURE_BETA_INTERCEPT: float = 6.5


# Failure type probabilities
FAILURE_TYPE_PROBS: Dict[str, float] = {
    "ENGINE": 0.40,
    "DRIVETRAIN": 0.35,
    "BRAKE": 0.25,
}


# ---------------------------------------------------------------------------
# 13. SERVICE / FAILURE SIMULATION
# ---------------------------------------------------------------------------

# Service resets accumulated risk
SERVICE_RESET_GRACE_DAYS: int = 7


# ---------------------------------------------------------------------------
# 14. EVALUATION TARGETS
# ---------------------------------------------------------------------------

BREAKDOWN_REDUCTION_TARGET_PCT: float = 20.0


# Window (days) for pre-breakdown flag detection
BREAKDOWN_WARNING_WINDOW_DAYS: int = 7


# ---------------------------------------------------------------------------
# 15. DATABASE
# ---------------------------------------------------------------------------

DB_FILENAME: str = "mining_maintenance.db"
DB_RELATIVE_PATH: str = "mining_maintenance.db"


# ---------------------------------------------------------------------------
# 16. PATHS
# ---------------------------------------------------------------------------

RAW_DATA_DIR: str = "data/raw"
PROCESSED_DATA_DIR: str = "data/processed"

VEHICLES_META_FILE: str = "data/raw/vehicles_meta.csv"

OPERATIONAL_DATA_RAW_FILE: str = (
    "data/raw/operational_data_raw.csv"
)

OPERATIONAL_DATA_CLEAN_FILE: str = (
    "data/processed/operational_data_clean.csv"
)

OPERATIONAL_DATA_FEATURES_FILE: str = (
    "data/processed/operational_data_features.csv"
)

DATA_QUALITY_LOG_FILE: str = (
    "data/processed/data_quality_log.csv"
)


# ---------------------------------------------------------------------------
# 17. APPLICATION
# ---------------------------------------------------------------------------

APP_TITLE: str = "Mining Fleet Predictive Maintenance"
APP_VERSION: str = "1.0.0"
MODEL_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# 18. VALIDATION
# ---------------------------------------------------------------------------

def _validate_weights(
    weights: Dict[str, float],
    name: str,
) -> None:
    """Validate that a weight dict sums to 1.0."""

    total = sum(weights.values())

    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"DCSS weight config '{name}' sums to "
            f"{total:.6f}, must be 1.0. "
            f"Edit config.py to fix."
        )

    for key, val in weights.items():
        if val < 0.0 or val > 1.0:
            raise ValueError(
                f"Weight '{key}' in config '{name}' "
                f"is {val}, must be in [0, 1]."
            )


def _validate_failure_types(
    probs: Dict[str, float],
) -> None:
    """Validate failure type probabilities sum to 1.0."""

    total = sum(probs.values())

    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"FAILURE_TYPE_PROBS sums to "
            f"{total:.6f}, must be 1.0."
        )


def _validate_config() -> None:
    """Run all config validation checks."""

    # Validate all DCSS configurations
    for config_name, weights in DCSS_WEIGHT_CONFIGS.items():
        _validate_weights(
            weights,
            config_name,
        )

    # Validate failure type probabilities
    _validate_failure_types(
        FAILURE_TYPE_PROBS
    )

    # Validate disruption window
    if DISRUPTION_START_DAY >= DISRUPTION_END_DAY:
        raise ValueError(
            f"DISRUPTION_START_DAY "
            f"({DISRUPTION_START_DAY}) must be < "
            f"DISRUPTION_END_DAY "
            f"({DISRUPTION_END_DAY})."
        )

    if DISRUPTION_END_DAY > SIMULATION_DAYS:
        raise ValueError(
            f"DISRUPTION_END_DAY "
            f"({DISRUPTION_END_DAY}) exceeds "
            f"SIMULATION_DAYS "
            f"({SIMULATION_DAYS})."
        )

    # Validate interval limits
    if MIN_INTERVAL_DAYS < 1:
        raise ValueError(
            "MIN_INTERVAL_DAYS must be >= 1."
        )

    if CRITICAL_MAX_DAYS < 1:
        raise ValueError(
            "CRITICAL_MAX_DAYS must be >= 1."
        )

    # Validate evaluation target
    if not (
        0.0
        < BREAKDOWN_REDUCTION_TARGET_PCT
        < 100.0
    ):
        raise ValueError(
            "BREAKDOWN_REDUCTION_TARGET_PCT "
            "must be between 0 and 100."
        )


# Run validation immediately on import
_validate_config()