"""
backend/app/engine/model_config.py
Model constants extracted from the original config.py.

Only the model-relevant constants are here (DCSS weights, thresholds,
intervals, simulator params). Infrastructure constants (paths, DB settings,
simulation counts) live in core/config.py.

These are the same values validated across 109 tests in Phase 7.
"""
from __future__ import annotations
from typing import Dict, Tuple

# ── DCSS Weight Configurations ───────────────────────────────────────────────
# Each config must sum to exactly 1.0

DCSS_WEIGHTS_DEFAULT: Dict[str, float] = {
    "fault_score":           0.30,
    "route_severity_score":  0.20,
    "load_score":            0.20,
    "engine_hour_score":     0.15,
    "mileage_score":         0.10,
    "service_wear_score":    0.05,
}

DCSS_WEIGHTS_FAULT_HEAVY: Dict[str, float] = {
    "fault_score":           0.45,
    "route_severity_score":  0.20,
    "load_score":            0.15,
    "engine_hour_score":     0.10,
    "mileage_score":         0.05,
    "service_wear_score":    0.05,
}

DCSS_WEIGHTS_LOAD_HEAVY: Dict[str, float] = {
    "fault_score":           0.25,
    "route_severity_score":  0.20,
    "load_score":            0.30,
    "engine_hour_score":     0.15,
    "mileage_score":         0.05,
    "service_wear_score":    0.05,
}

DCSS_WEIGHT_CONFIGS: Dict[str, Dict[str, float]] = {
    "Default":     DCSS_WEIGHTS_DEFAULT,
    "Fault-Heavy": DCSS_WEIGHTS_FAULT_HEAVY,
    "Load-Heavy":  DCSS_WEIGHTS_LOAD_HEAVY,
}

# ── Risk Thresholds ──────────────────────────────────────────────────────────
# (inclusive low, inclusive high)
RISK_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "LOW":      (0.0,   25.0),
    "NORMAL":   (25.0,  50.0),
    "HIGH":     (50.0,  75.0),
    "CRITICAL": (75.0, 100.0),
}

# FR-05: fault_severity >= this value forces CRITICAL regardless of DCSS
CRITICAL_FAULT_SEVERITY_THRESHOLD: float = 8.0

# ── Maintenance Intervals ────────────────────────────────────────────────────
CRITICAL_MAX_DAYS: int = 3           # CRITICAL → 3 days (IMMEDIATE)
HIGH_INTERVAL_REDUCTION_FACTOR: float = 0.60   # HIGH → 30 * 0.60 = 18 days
STANDARD_INTERVAL_DAYS: int = 30     # NORMAL → 30 days (ROUTINE)
LOW_INTERVAL_EXTENSION_FACTOR: float = 1.50    # LOW → 30 * 1.50 = 45 days
MAX_INTERVAL_DAYS: int = 60
MIN_INTERVAL_DAYS: int = 1

# Baseline (fixed-calendar)
BASELINE_INTERVAL_DAYS: int = 30

# ── Feature Engineering Reference Values ────────────────────────────────────
MILEAGE_SCORE_REF_KM: float = 300.0     # daily km that scores 100
ENGINE_HOUR_SCORE_REF: float = 18.0     # engine hours/day that scores 100
SERVICE_WEAR_REF_DAYS: int = 60         # days since service that scores 100
ROUTE_SEVERITY_MAX: float = 10.0

# ── Failure Simulator ────────────────────────────────────────────────────────
FAILURE_BETA_INTERCEPT: float = 6.5
FAILURE_ALPHA_FAULT: float = 0.30
FAILURE_ALPHA_ROUTE: float = 0.15
FAILURE_ALPHA_LOAD: float = 0.12
FAILURE_ALPHA_ENGINE: float = 0.10
FAILURE_ALPHA_MILEAGE: float = 0.08
FAILURE_ALPHA_SERVICE: float = 0.05
BREAKDOWN_WARNING_WINDOW_DAYS: int = 7

# ── Disruption Defaults ──────────────────────────────────────────────────────
DISRUPTION_ROUTE_DELTA: float = 2.5
DISRUPTION_LOAD_DELTA: float = 15.0
DISRUPTION_ENGINE_DELTA: float = 3.0
