"""
backend/app/engine/model_service.py
Thin service layer that wraps the validated model functions for API use.

Takes plain Python dicts/values (from API requests), calls the existing
feature_engineering + duty_cycle_model + maintenance_engine functions,
and returns structured dicts (mapped to Pydantic response schemas).

No DataFrame I/O here — input is a dict, output is a dict.
This keeps the API handlers clean and the model logic testable.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    # FastAPI loads this as app.engine.model_service (package context)
    from .model_config import (
        DCSS_WEIGHT_CONFIGS,
        DCSS_WEIGHTS_DEFAULT,
        CRITICAL_FAULT_SEVERITY_THRESHOLD,
        CRITICAL_MAX_DAYS,
        HIGH_INTERVAL_REDUCTION_FACTOR,
        STANDARD_INTERVAL_DAYS,
        LOW_INTERVAL_EXTENSION_FACTOR,
        MAX_INTERVAL_DAYS,
        MIN_INTERVAL_DAYS,
        BASELINE_INTERVAL_DAYS,
        MILEAGE_SCORE_REF_KM,
        ENGINE_HOUR_SCORE_REF,
        SERVICE_WEAR_REF_DAYS,
        ROUTE_SEVERITY_MAX,
        DISRUPTION_ROUTE_DELTA,
        DISRUPTION_LOAD_DELTA,
        DISRUPTION_ENGINE_DELTA,
    )
except ImportError:
    # pytest loads this as a flat module via sys.path → app/engine/
    from model_config import (  # type: ignore[no-redef]
        DCSS_WEIGHT_CONFIGS,
        DCSS_WEIGHTS_DEFAULT,
        CRITICAL_FAULT_SEVERITY_THRESHOLD,
        CRITICAL_MAX_DAYS,
        HIGH_INTERVAL_REDUCTION_FACTOR,
        STANDARD_INTERVAL_DAYS,
        LOW_INTERVAL_EXTENSION_FACTOR,
        MAX_INTERVAL_DAYS,
        MIN_INTERVAL_DAYS,
        BASELINE_INTERVAL_DAYS,
        MILEAGE_SCORE_REF_KM,
        ENGINE_HOUR_SCORE_REF,
        SERVICE_WEAR_REF_DAYS,
        ROUTE_SEVERITY_MAX,
        DISRUPTION_ROUTE_DELTA,
        DISRUPTION_LOAD_DELTA,
        DISRUPTION_ENGINE_DELTA,
    )

# Import the validated model functions (unchanged from Phase 1-7)
# These use bare imports internally (import config as cfg) and are resolved
# via sys.path set in app/main.py at startup.
from feature_engineering import (
    compute_mileage_score,
    compute_engine_hour_score,
    compute_load_score,
    compute_route_severity_score,
    compute_fault_score,
    compute_service_wear_score,
)
from duty_cycle_model import compute_dcss_single, classify_risk, rank_factors
from maintenance_engine import compute_interval, compute_maintenance_date


# ————————————————————————————————————————————————————————————————————————————————
# Core computation
# ————————————————————————————————————————————————————————————————————————————————

def _compute_sub_scores(conditions: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute all 6 DCSS sub-scores from raw operating conditions.
    Uses pd.Series([value]).iloc[0] to call the vectorised feature functions.
    """
    def s(val) -> pd.Series:
        return pd.Series([val])

    mileage_score       = float(compute_mileage_score(s(conditions["mileage_km"])).iloc[0])
    engine_hour_score   = float(compute_engine_hour_score(s(conditions["engine_hours"])).iloc[0])
    load_score          = float(compute_load_score(s(conditions["load_percentage"])).iloc[0])
    route_score         = float(compute_route_severity_score(s(conditions["route_severity_score"])).iloc[0])
    fault_score         = float(compute_fault_score(
        s(conditions["fault_count"]),
        s(conditions["fault_severity_score"]),
    ).iloc[0])
    service_wear_score  = float(compute_service_wear_score(
        s(conditions.get("days_since_last_service"))
    ).iloc[0])

    return {
        "mileage_score":          round(mileage_score, 2),
        "engine_hour_score":      round(engine_hour_score, 2),
        "load_score":             round(load_score, 2),
        "route_severity_score_n": round(route_score, 2),
        "fault_score":            round(fault_score, 2),
        "service_wear_score":     round(service_wear_score, 2),
    }


def analyze(conditions: Dict[str, Any], weight_config: str = "Default") -> Dict[str, Any]:
    """
    Run the full DCSS analysis on a single set of operating conditions.

    Args:
        conditions: dict with keys matching AnalyzeRequest fields
        weight_config: one of 'Default' | 'Fault-Heavy' | 'Load-Heavy'

    Returns:
        dict matching AnalyzeResponse schema
    """
    weights = DCSS_WEIGHT_CONFIGS.get(weight_config, DCSS_WEIGHTS_DEFAULT)
    sub = _compute_sub_scores(conditions)

    dcss = compute_dcss_single(
        fault_score            = sub["fault_score"],
        route_severity_score_n = sub["route_severity_score_n"],
        load_score             = sub["load_score"],
        engine_hour_score      = sub["engine_hour_score"],
        mileage_score          = sub["mileage_score"],
        service_wear_score     = sub["service_wear_score"],
        weights                = weights,
    )
    dcss = round(float(dcss), 2)

    risk = classify_risk(dcss, fault_severity_score=conditions.get("fault_severity_score", 0.0))
    interval_days, urgency, reason = compute_interval(risk)

    # Use today or the provided date for maintenance date calculation
    as_of = conditions.get("as_of_date") or date.today().isoformat()
    if hasattr(as_of, "isoformat"):
        as_of = as_of.isoformat()
    maintenance_date = compute_maintenance_date(as_of, interval_days)

    # Factor ranking
    factors_raw = rank_factors(
        fault_score            = sub["fault_score"],
        route_severity_score_n = sub["route_severity_score_n"],
        load_score             = sub["load_score"],
        engine_hour_score      = sub["engine_hour_score"],
        mileage_score          = sub["mileage_score"],
        service_wear_score     = sub["service_wear_score"],
        weights                = weights,
        top_n                  = 5,
    )
    factors = [
        {
            "factor":       f["factor"],
            "sub_score":    round(float(f["sub_score"]), 2),
            "contribution": round(float(f["contribution"]), 2),
        }
        for f in factors_raw
    ]

    # Expose sub-scores with readable names
    readable_sub = {
        "mileage_score":       sub["mileage_score"],
        "engine_hour_score":   sub["engine_hour_score"],
        "load_score":          sub["load_score"],
        "route_severity_score": sub["route_severity_score_n"],
        "fault_score":         sub["fault_score"],
        "service_wear_score":  sub["service_wear_score"],
    }

    return {
        "dcss_score":                  dcss,
        "risk_level":                  risk,
        "recommended_interval_days":   interval_days,
        "recommended_maintenance_date": maintenance_date,
        "urgency":                     urgency,
        "reason":                      reason,
        "top_factors":                 factors,
        "weight_config":               weight_config,
        "sub_scores":                  readable_sub,
        "baseline_interval_days":      BASELINE_INTERVAL_DAYS,
    }


def simulate_disruption(
    base_conditions: Dict[str, Any],
    deltas: Dict[str, float],
    disruption_type: Optional[str],
    weight_config: str = "Default",
) -> Dict[str, Any]:
    """
    Run DCSS before and after applying disruption deltas.
    Returns a DisruptionResult-shaped dict.
    """
    before = analyze(base_conditions, weight_config)

    # Build disrupted conditions by adding deltas, clamped to valid ranges
    disrupted = dict(base_conditions)
    clamp_rules = {
        "mileage_km":           (0, 2000),
        "engine_hours":         (0, 24),
        "load_percentage":      (0, 150),
        "route_severity_score": (0, 10),
        "fault_count":          (0, 100),
        "fault_severity_score": (0, 10),
    }
    changes_summary = []
    for key, delta in deltas.items():
        if delta == 0:
            continue
        base_val = float(disrupted.get(key, 0))
        new_val  = base_val + delta
        lo, hi   = clamp_rules.get(key, (0, 9999))
        clamped  = max(lo, min(hi, new_val))
        disrupted[key] = clamped
        direction = "â–²" if delta > 0 else "â–¼"
        label = key.replace("_", " ").title()
        changes_summary.append(
            f"{direction} {label}: {base_val:.1f} â†’ {clamped:.1f} (Î” {delta:+.1f})"
        )

    after = analyze(disrupted, weight_config)

    return {
        "before":              before,
        "after":               after,
        "disruption_type":     disruption_type,
        "dcss_delta":          round(after["dcss_score"] - before["dcss_score"], 2),
        "risk_changed":        after["risk_level"] != before["risk_level"],
        "interval_change_days": (
            after["recommended_interval_days"] - before["recommended_interval_days"]
        ),
        "changes_summary":     changes_summary,
    }

