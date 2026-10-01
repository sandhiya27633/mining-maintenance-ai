"""
backend/app/tests/test_dcss_edge_cases.py

Comprehensive edge-case and disruption-scenario test suite for the DCSS engine.
All data used in these tests is SYNTHETIC — no real mining fleet data is used.

SCOPE:
  - TestDCSSEdgeCases:             DCSS formula, weights, clipping, boundary values
  - TestRiskBoundaries:            Risk classification at exact boundary DCSS values
  - TestMaintenanceIntervalEdgeCases: Interval and urgency for each risk level
  - TestFeatureEngineeringEdgeCases:  Sub-score formulas, reference values, NaN handling
  - TestDisruptionScenarios:       Synthetic scenario comparisons via model_service.analyze()

NOTE ON TEMPERATURE AND DUST:
  Temperature and dust/environment stress are NOT inputs to the production DCSS model.
  The model has exactly 6 inputs: fault, route severity, load, engine hours, mileage,
  service wear. These tests only cover what the production model actually computes.

VERIFIED WEIGHTS (from backend/app/engine/config.py):
  fault_score:          0.30
  route_severity_score: 0.20
  load_score:           0.20
  engine_hour_score:    0.15
  mileage_score:        0.10
  service_wear_score:   0.05
  Total:                1.00

VERIFIED REFERENCE VALUES (from config.py):
  ENGINE_HOUR_SCORE_REF   = 20.0 hrs/day  (score 100 at 20 hrs)
  MILEAGE_SCORE_REF_KM    = 300.0 km/day  (score 100 at 300 km)
  SERVICE_INTERVAL_DAYS   = 30 days        (score 100 at 30 days since service)
  FAULT_SCORE_COUNT_WEIGHT  = 0.4
  FAULT_SCORE_SEVERITY_WEIGHT = 0.6
  CRITICAL_FAULT_SEVERITY_THRESHOLD = 8.0  (FR-05 override)
"""

import sys
import math
from pathlib import Path

import pytest
import pandas as pd

# Add engine directory to path — same pattern as other test files
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))

from duty_cycle_model import compute_dcss_single, classify_risk
from feature_engineering import (
    compute_mileage_score,
    compute_engine_hour_score,
    compute_load_score,
    compute_route_severity_score,
    compute_fault_score,
    compute_service_wear_score,
)
from maintenance_engine import compute_interval, compute_maintenance_date
from model_service import analyze
import config as cfg


# =============================================================================
# DCSS Formula Edge Cases
# =============================================================================

class TestDCSSEdgeCases:
    """
    Test the core DCSS weighted-sum formula (compute_dcss_single).
    All sub-scores are in [0, 100]; DCSS output is clipped to [0, 100].
    """

    def test_dcss_all_zeros(self):
        """Zero input on every factor -> DCSS = 0."""
        result = compute_dcss_single(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert result == 0.0

    def test_dcss_all_max(self):
        """Maximum input on every factor -> DCSS = 100."""
        result = compute_dcss_single(100.0, 100.0, 100.0, 100.0, 100.0, 100.0)
        assert abs(result - 100.0) < 0.001

    def test_dcss_clip_above_100(self):
        """Over-range inputs are clipped — DCSS never exceeds 100."""
        result = compute_dcss_single(200.0, 200.0, 200.0, 200.0, 200.0, 200.0)
        assert result <= 100.0

    def test_dcss_clip_below_zero(self):
        """Negative sub-scores are clipped — DCSS never goes below 0."""
        result = compute_dcss_single(-50.0, -50.0, -50.0, -50.0, -50.0, -50.0)
        assert result >= 0.0

    def test_dcss_weight_fault_only(self):
        """fault_score=100, all others=0 -> DCSS = 100*0.30 = 30.0."""
        result = compute_dcss_single(
            fault_score=100.0,
            route_severity_score_n=0.0,
            load_score=0.0,
            engine_hour_score=0.0,
            mileage_score=0.0,
            service_wear_score=0.0,
        )
        assert abs(result - 30.0) < 0.01

    def test_dcss_weight_route_only(self):
        """route_severity_score_n=100, all others=0 -> DCSS = 100*0.20 = 20.0."""
        result = compute_dcss_single(0.0, 100.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(result - 20.0) < 0.01

    def test_dcss_weight_load_only(self):
        """load_score=100, all others=0 -> DCSS = 100*0.20 = 20.0."""
        result = compute_dcss_single(0.0, 0.0, 100.0, 0.0, 0.0, 0.0)
        assert abs(result - 20.0) < 0.01

    def test_dcss_weight_engine_only(self):
        """engine_hour_score=100, all others=0 -> DCSS = 100*0.15 = 15.0."""
        result = compute_dcss_single(0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
        assert abs(result - 15.0) < 0.01

    def test_dcss_weight_mileage_only(self):
        """mileage_score=100, all others=0 -> DCSS = 100*0.10 = 10.0."""
        result = compute_dcss_single(0.0, 0.0, 0.0, 0.0, 100.0, 0.0)
        assert abs(result - 10.0) < 0.01

    def test_dcss_weight_service_only(self):
        """service_wear_score=100, all others=0 -> DCSS = 100*0.05 = 5.0."""
        result = compute_dcss_single(0.0, 0.0, 0.0, 0.0, 0.0, 100.0)
        assert abs(result - 5.0) < 0.01

    def test_dcss_weights_sum_to_one(self):
        """Default DCSS weights must sum exactly to 1.0 (validated in config.py at import)."""
        total = sum(cfg.DCSS_WEIGHTS_DEFAULT.values())
        assert abs(total - 1.0) < 1e-9

    def test_dcss_normal_operation(self):
        """Typical daily conditions produce a DCSS within [0, 100] and matches formula."""
        fs, rs, ls, es, ms, ss = 10.0, 40.0, 60.0, 50.0, 33.33, 33.33
        result = compute_dcss_single(fs, rs, ls, es, ms, ss)
        expected = 0.30*fs + 0.20*rs + 0.20*ls + 0.15*es + 0.10*ms + 0.05*ss
        assert 0.0 <= result <= 100.0
        assert abs(result - expected) < 0.1

    def test_dcss_boundary_produces_25(self):
        """
        Construct sub-scores that sum to exactly 25.0:
        load=100 (20.0) + service=100 (5.0) = 25.0. All others = 0.
        """
        result = compute_dcss_single(0.0, 0.0, 100.0, 0.0, 0.0, 100.0)
        assert abs(result - 25.0) < 0.001

    def test_dcss_high_load_higher_than_normal(self):
        """Increasing load above baseline raises DCSS."""
        normal = compute_dcss_single(10.0, 40.0, 60.0, 50.0, 33.0, 33.0)
        elevated = compute_dcss_single(10.0, 40.0, 100.0, 50.0, 33.0, 33.0)
        assert elevated > normal

    def test_dcss_high_route_severity_higher_than_normal(self):
        """Increasing route severity above baseline raises DCSS."""
        normal = compute_dcss_single(10.0, 40.0, 60.0, 50.0, 33.0, 33.0)
        elevated = compute_dcss_single(10.0, 100.0, 60.0, 50.0, 33.0, 33.0)
        assert elevated > normal

    def test_fr05_override_forces_critical_with_low_dcss(self):
        """
        FR-05: fault_severity >= 8.0 forces CRITICAL even when DCSS is low.
        This ensures a single severe fault event is never overlooked.
        """
        risk = classify_risk(dcss=10.0, fault_severity_score=9.0)
        assert risk == "CRITICAL"

    def test_fr05_below_threshold_follows_dcss(self):
        """
        FR-05 does NOT trigger at fault_severity = 7.9 (below 8.0 threshold).
        Risk follows DCSS normally — DCSS=10 -> LOW.
        """
        risk = classify_risk(dcss=10.0, fault_severity_score=7.9)
        assert risk == "LOW"

    def test_dcss_missing_service_score_handled(self):
        """
        Missing service history is handled at the feature engineering level
        (NaN -> imputed to 15 days, score ~50). At the DCSS level, we verify
        that a mid-range service_wear_score (50) produces a valid float DCSS.
        """
        # 15 days / 30 days reference = 0.5 -> service_wear_score = 50
        result = compute_dcss_single(10.0, 40.0, 60.0, 50.0, 33.0, 50.0)
        assert isinstance(result, float)
        assert not math.isnan(result)
        assert 0.0 <= result <= 100.0


# =============================================================================
# Risk Classification Boundaries
# =============================================================================

class TestRiskBoundaries:
    """
    Test risk classification at exact boundary DCSS values.
    Thresholds (from config.py): LOW<=25, NORMAL<=50, HIGH<=75, CRITICAL>75.
    FR-05: fault_severity >= 8.0 always -> CRITICAL.
    """

    def test_risk_dcss_0_is_low(self):
        assert classify_risk(0.0) == "LOW"

    def test_risk_dcss_24_is_low(self):
        assert classify_risk(24.0) == "LOW"

    def test_risk_boundary_25_is_low_or_normal(self):
        """Exact boundary 25.0 — inclusive range determines which tier."""
        risk = classify_risk(25.0)
        assert risk in ("LOW", "NORMAL")

    def test_risk_dcss_49_is_normal(self):
        assert classify_risk(49.0) == "NORMAL"

    def test_risk_boundary_50_is_normal_or_high(self):
        """Exact boundary 50.0."""
        risk = classify_risk(50.0)
        assert risk in ("NORMAL", "HIGH")

    def test_risk_dcss_74_is_high(self):
        assert classify_risk(74.0) == "HIGH"

    def test_risk_boundary_75_is_high_or_critical(self):
        """Exact boundary 75.0."""
        risk = classify_risk(75.0)
        assert risk in ("HIGH", "CRITICAL")

    def test_risk_dcss_100_is_critical(self):
        assert classify_risk(100.0) == "CRITICAL"

    def test_fr05_forces_critical_at_8(self):
        """fault_severity exactly 8.0 triggers CRITICAL override."""
        risk = classify_risk(dcss=5.0, fault_severity_score=8.0)
        assert risk == "CRITICAL"

    def test_fr05_does_not_trigger_at_7_99(self):
        """fault_severity 7.99 does NOT trigger the FR-05 override."""
        risk = classify_risk(dcss=5.0, fault_severity_score=7.99)
        assert risk == "LOW"


# =============================================================================
# Maintenance Interval Edge Cases
# =============================================================================

class TestMaintenanceIntervalEdgeCases:
    """
    Test compute_interval() from maintenance_engine for every risk level.
    All intervals must be within [MIN_INTERVAL_DAYS=1, MAX_INTERVAL_DAYS=60].
    """

    def test_interval_critical_is_3_days_immediate(self):
        """CRITICAL -> 3 days, IMMEDIATE urgency."""
        days, urgency, reason = compute_interval("CRITICAL")
        assert days == 3
        assert urgency == "IMMEDIATE"
        assert isinstance(reason, str) and len(reason) > 0

    def test_interval_high_is_18_days_urgent(self):
        """HIGH -> round(30 * 0.60) = 18 days, URGENT urgency."""
        days, urgency, reason = compute_interval("HIGH")
        assert days == 18
        assert urgency == "URGENT"

    def test_interval_normal_is_30_days_routine(self):
        """NORMAL -> 30 days (standard interval), ROUTINE urgency."""
        days, urgency, reason = compute_interval("NORMAL")
        assert days == 30
        assert urgency == "ROUTINE"

    def test_interval_low_is_45_days_deferred(self):
        """LOW -> round(30 * 1.50) = 45 days, DEFERRED urgency."""
        days, urgency, reason = compute_interval("LOW")
        assert days == 45
        assert urgency == "DEFERRED"

    def test_interval_unknown_falls_back_to_30_routine(self):
        """Unknown risk level safely defaults to 30 days / ROUTINE (no crash)."""
        days, urgency, reason = compute_interval("UNKNOWN_RISK")
        assert days == 30
        assert urgency == "ROUTINE"

    def test_all_intervals_within_hard_bounds(self):
        """All standard risk levels must produce intervals within [1, 60]."""
        for risk in ("LOW", "NORMAL", "HIGH", "CRITICAL", "UNKNOWN"):
            days, _, _ = compute_interval(risk)
            assert 1 <= days <= 60, f"{risk} produced out-of-bounds interval: {days}"

    def test_maintenance_date_critical_adds_3_days(self):
        """compute_maintenance_date: 2024-01-10 + 3 days = 2024-01-13."""
        result = compute_maintenance_date("2024-01-10", 3)
        assert result == "2024-01-13"

    def test_maintenance_date_low_adds_45_days(self):
        """compute_maintenance_date: 2024-01-10 + 45 days = 2024-02-24."""
        result = compute_maintenance_date("2024-01-10", 45)
        assert result == "2024-02-24"


# =============================================================================
# Feature Engineering Sub-Score Edge Cases
# =============================================================================

class TestFeatureEngineeringEdgeCases:
    """
    Test individual sub-score functions from feature_engineering.py.
    All functions take pd.Series and return pd.Series.

    NOTE: Temperature and dust/environment stress are NOT production model inputs.
    Only the 6 production sub-scores are tested here.

    Reference values (from config.py):
      MILEAGE_SCORE_REF_KM    = 300.0   km/day -> score 100
      ENGINE_HOUR_SCORE_REF   = 20.0    hrs/day -> score 100
      SERVICE_INTERVAL_DAYS   = 30      days since service -> score 100
      FAULT_SCORE_COUNT_WEIGHT  = 0.4
      FAULT_SCORE_SEVERITY_WEIGHT = 0.6
    """

    def test_mileage_score_zero(self):
        """0 km/day -> mileage_score = 0."""
        res = compute_mileage_score(pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_mileage_score_at_reference(self):
        """300 km/day (reference) -> mileage_score = 100."""
        res = compute_mileage_score(pd.Series([cfg.MILEAGE_SCORE_REF_KM]))
        assert abs(res.iloc[0] - 100.0) < 0.001

    def test_mileage_score_above_reference_is_capped(self):
        """600 km/day (2x reference) -> mileage_score capped at 100."""
        res = compute_mileage_score(pd.Series([600.0]))
        assert res.iloc[0] == 100.0

    def test_engine_hour_score_zero(self):
        """0 hrs/day -> engine_hour_score = 0."""
        res = compute_engine_hour_score(pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_engine_hour_score_at_reference(self):
        """ENGINE_HOUR_SCORE_REF hrs/day (20.0) -> engine_hour_score = 100."""
        res = compute_engine_hour_score(pd.Series([cfg.ENGINE_HOUR_SCORE_REF]))
        assert abs(res.iloc[0] - 100.0) < 0.001

    def test_engine_hour_score_above_reference_is_capped(self):
        """36 hrs/day (above 20 ref) -> engine_hour_score capped at 100."""
        res = compute_engine_hour_score(pd.Series([36.0]))
        assert res.iloc[0] == 100.0

    def test_load_score_is_direct_mapping(self):
        """load_percentage=75 -> load_score=75 (direct, no transformation)."""
        res = compute_load_score(pd.Series([75.0]))
        assert res.iloc[0] == 75.0

    def test_load_score_above_100_is_capped(self):
        """load_percentage=150 -> load_score capped at 100."""
        res = compute_load_score(pd.Series([150.0]))
        assert res.iloc[0] == 100.0

    def test_load_score_zero(self):
        """load_percentage=0 -> load_score=0."""
        res = compute_load_score(pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_route_severity_at_max(self):
        """route_severity_score=10.0 (maximum) -> normalised score = 100."""
        res = compute_route_severity_score(pd.Series([10.0]))
        assert abs(res.iloc[0] - 100.0) < 0.001

    def test_route_severity_at_midpoint(self):
        """route_severity_score=5.0 (midpoint) -> normalised score = 50."""
        res = compute_route_severity_score(pd.Series([5.0]))
        assert abs(res.iloc[0] - 50.0) < 0.001

    def test_route_severity_zero(self):
        """route_severity_score=0.0 -> normalised score = 0."""
        res = compute_route_severity_score(pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_service_wear_nan_is_safely_imputed(self):
        """
        NaN days_since_last_service (new vehicle with no history) is imputed
        to SERVICE_INTERVAL_DAYS / 2 = 15 days. The result must be a valid float.
        """
        res = compute_service_wear_score(pd.Series([float("nan")]))
        assert not pd.isna(res.iloc[0]), "NaN service days must be imputed, not propagated"
        assert 0.0 <= res.iloc[0] <= 100.0

    def test_service_wear_just_serviced(self):
        """0 days since service -> service_wear_score = 0 (just serviced, no wear)."""
        res = compute_service_wear_score(pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_service_wear_at_reference_interval(self):
        """30 days since service (= SERVICE_INTERVAL_DAYS) -> service_wear_score = 100."""
        res = compute_service_wear_score(pd.Series([float(cfg.SERVICE_INTERVAL_DAYS)]))
        assert abs(res.iloc[0] - 100.0) < 0.001

    def test_service_wear_overdue_is_capped(self):
        """60 days since service (overdue) -> service_wear_score capped at 100."""
        res = compute_service_wear_score(pd.Series([60.0]))
        assert res.iloc[0] == 100.0

    def test_fault_score_zero_faults_zero_severity(self):
        """No faults, zero severity -> fault_score = 0."""
        res = compute_fault_score(pd.Series([0.0]), pd.Series([0.0]))
        assert res.iloc[0] == 0.0

    def test_fault_score_is_capped_at_100(self):
        """Extreme fault count and high severity -> fault_score capped at 100."""
        res = compute_fault_score(pd.Series([100.0]), pd.Series([10.0]))
        assert res.iloc[0] == 100.0


# =============================================================================
# Disruption Scenarios (using model_service.analyze)
# =============================================================================

class TestDisruptionScenarios:
    """
    Synthetic scenario comparisons using model_service.analyze().
    All scenarios are SYNTHETIC SIMULATIONS — not real mining incidents.

    Each scenario calls analyze() with a conditions dict and verifies:
    - The result dict contains expected keys
    - DCSS is in [0, 100]
    - Stress scenarios produce higher DCSS than normal operation
    - Combined stress produces the highest DCSS

    Scenarios:
      NORMAL:           Typical daily mining operation
      FAULT_HEAVY:      Elevated fault count + severity (e.g., after equipment abuse)
      LOAD_HEAVY:       Near-maximum load + extended engine hours
      ROUTE_DISRUPTION: Extreme route severity (haul-road flooding simulation)
      COMBINED_STRESS:  All factors simultaneously elevated
      DOWNSIZING:       Same total work on fewer vehicles -> higher per-vehicle load
    """

    # Reference conditions for normal daily operation
    NORMAL = {
        "mileage_km": 100.0,
        "engine_hours": 8.0,
        "load_percentage": 60.0,
        "route_severity_score": 4.0,
        "fault_count": 0,
        "fault_severity_score": 0.0,
        "days_since_last_service": 10.0,
        "cumulative_mileage_km": 1000.0,
    }

    def _make(self, **overrides):
        """Return a copy of NORMAL conditions with specified overrides applied."""
        data = dict(self.NORMAL)
        data.update(overrides)
        return data

    def test_scenario_normal_returns_valid_structure(self):
        """Normal conditions: analyze() returns expected keys with DCSS in [0, 100]."""
        res = analyze(self.NORMAL)
        assert "dcss_score" in res
        assert "risk_level" in res
        assert "recommended_interval_days" in res
        assert 0.0 <= res["dcss_score"] <= 100.0
        assert res["risk_level"] in ("LOW", "NORMAL", "HIGH", "CRITICAL")
        assert 1 <= res["recommended_interval_days"] <= 60

    def test_scenario_fault_heavy_exceeds_normal(self):
        """
        Fault-heavy operation (fault_count=4, severity=7.0) must produce
        higher DCSS than normal operation. Faults carry the highest weight (30%).
        [SYNTHETIC SIMULATION]
        """
        normal_dcss = analyze(self.NORMAL)["dcss_score"]
        fault_dcss = analyze(self._make(fault_count=4, fault_severity_score=7.0))["dcss_score"]
        assert fault_dcss > normal_dcss, (
            f"Fault-heavy DCSS ({fault_dcss:.1f}) should exceed normal ({normal_dcss:.1f})"
        )

    def test_scenario_load_heavy_exceeds_normal(self):
        """
        Load-heavy operation (load=95%, engine=16 hrs) must produce higher
        DCSS than normal. Load and engine-hours together carry 35% weight.
        [SYNTHETIC SIMULATION]
        """
        normal_dcss = analyze(self.NORMAL)["dcss_score"]
        load_dcss = analyze(self._make(load_percentage=95.0, engine_hours=16.0))["dcss_score"]
        assert load_dcss > normal_dcss, (
            f"Load-heavy DCSS ({load_dcss:.1f}) should exceed normal ({normal_dcss:.1f})"
        )

    def test_scenario_route_disruption_exceeds_normal(self):
        """
        Severe route disruption (route_severity=9.5, haul-road flooding simulation)
        must produce higher DCSS than normal. Route carries 20% weight.
        [SYNTHETIC SIMULATION]
        """
        normal_dcss = analyze(self.NORMAL)["dcss_score"]
        route_dcss = analyze(self._make(route_severity_score=9.5))["dcss_score"]
        assert route_dcss > normal_dcss, (
            f"Route-disruption DCSS ({route_dcss:.1f}) should exceed normal ({normal_dcss:.1f})"
        )

    def test_scenario_combined_stress_is_high_or_critical(self):
        """
        Combined operational stress (all factors elevated simultaneously)
        must produce HIGH or CRITICAL risk. [SYNTHETIC SIMULATION]
        """
        combined = self._make(
            mileage_km=250.0,
            engine_hours=15.0,
            load_percentage=90.0,
            route_severity_score=8.0,
            fault_count=3,
            fault_severity_score=6.0,
        )
        res = analyze(combined)
        assert res["risk_level"] in ("HIGH", "CRITICAL"), (
            f"Combined stress should be HIGH or CRITICAL, got {res['risk_level']} "
            f"(DCSS={res['dcss_score']:.1f})"
        )

    def test_scenario_combined_stress_highest_dcss(self):
        """
        Combined stress DCSS must be >= DCSS from any single-factor scenario.
        [SYNTHETIC SIMULATION]
        """
        combined = self._make(
            mileage_km=250.0,
            engine_hours=15.0,
            load_percentage=90.0,
            route_severity_score=8.0,
            fault_count=3,
            fault_severity_score=6.0,
        )
        combined_dcss = analyze(combined)["dcss_score"]

        single_factor_scores = [
            analyze(self.NORMAL)["dcss_score"],
            analyze(self._make(fault_count=4, fault_severity_score=7.0))["dcss_score"],
            analyze(self._make(load_percentage=95.0, engine_hours=16.0))["dcss_score"],
            analyze(self._make(route_severity_score=9.5))["dcss_score"],
        ]
        assert combined_dcss >= max(single_factor_scores), (
            f"Combined DCSS ({combined_dcss:.1f}) should >= max single-factor "
            f"({max(single_factor_scores):.1f})"
        )

    def test_scenario_fleet_downsizing_exceeds_normal(self):
        """
        Fleet downsizing: same total operational output on fewer vehicles.
        Simulated as higher per-vehicle load, mileage, and engine hours.
        Must produce higher DCSS than normal operation. [SYNTHETIC SIMULATION]
        """
        normal_dcss = analyze(self.NORMAL)["dcss_score"]
        downsized_dcss = analyze(self._make(
            mileage_km=280.0,
            engine_hours=18.0,
            load_percentage=100.0,
        ))["dcss_score"]
        assert downsized_dcss > normal_dcss, (
            f"Downsizing DCSS ({downsized_dcss:.1f}) should exceed normal ({normal_dcss:.1f})"
        )

    def test_all_scenarios_produce_valid_dcss(self):
        """All scenarios produce DCSS in [0, 100] with a valid risk level."""
        scenarios = [
            self.NORMAL,
            self._make(fault_count=4, fault_severity_score=7.0),
            self._make(load_percentage=95.0, engine_hours=16.0),
            self._make(route_severity_score=9.5),
            self._make(mileage_km=250.0, engine_hours=15.0, load_percentage=90.0,
                       route_severity_score=8.0, fault_count=3, fault_severity_score=6.0),
            self._make(mileage_km=280.0, engine_hours=18.0, load_percentage=100.0),
        ]
        for i, scenario in enumerate(scenarios):
            res = analyze(scenario)
            assert 0.0 <= res["dcss_score"] <= 100.0, \
                f"Scenario {i}: DCSS out of range: {res['dcss_score']}"
            assert res["risk_level"] in ("LOW", "NORMAL", "HIGH", "CRITICAL"), \
                f"Scenario {i}: Invalid risk level: {res['risk_level']}"
            assert 1 <= res["recommended_interval_days"] <= 60, \
                f"Scenario {i}: Interval out of bounds: {res['recommended_interval_days']}"
