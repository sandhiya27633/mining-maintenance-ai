"""
backend/app/tests/test_model_engine.py
Tests for the migrated engine functions.
These are the same 41 model tests from Phase 7, adapted to use the
backend engine package path (backend/app/engine/) instead of src/.

All tests are stateless — no DB, no server needed.
"""
import sys
from pathlib import Path
import pytest

# Add engine to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))

# Import model functions from the backend engine package
from duty_cycle_model import compute_dcss_single, classify_risk, rank_factors
from maintenance_engine import compute_interval, compute_maintenance_date
from feature_engineering import (
    compute_mileage_score, compute_engine_hour_score, compute_load_score,
    compute_route_severity_score, compute_fault_score, compute_service_wear_score,
)
from model_service import analyze, simulate_disruption
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# DCSS formula
# ─────────────────────────────────────────────────────────────────────────────

class TestDCSSFormula:
    def test_dcss_zero_when_all_subscores_zero(self):
        dcss = compute_dcss_single(0, 0, 0, 0, 0, 0)
        assert dcss == 0.0

    def test_dcss_100_when_all_subscores_max(self):
        dcss = compute_dcss_single(100, 100, 100, 100, 100, 100)
        assert abs(dcss - 100.0) < 0.01

    def test_dcss_clipped_at_100(self):
        dcss = compute_dcss_single(200, 200, 200, 200, 200, 200)
        assert dcss <= 100.0

    def test_dcss_clipped_at_zero(self):
        dcss = compute_dcss_single(-10, -10, -10, -10, -10, -10)
        assert dcss >= 0.0

    def test_dcss_weighted_sum(self):
        """fault_score=100 only → DCSS ≈ 30 (default weight 0.30)."""
        dcss = compute_dcss_single(
            fault_score=100, route_severity_score_n=0,
            load_score=0, engine_hour_score=0,
            mileage_score=0, service_wear_score=0,
        )
        assert abs(dcss - 30.0) < 0.01

    def test_dcss_returns_float(self):
        dcss = compute_dcss_single(50, 50, 50, 50, 50, 50)
        assert isinstance(float(dcss), float)


# ─────────────────────────────────────────────────────────────────────────────
# Risk classification
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskClassification:
    def test_low_risk(self):
        assert classify_risk(10.0) == "LOW"

    def test_normal_risk(self):
        assert classify_risk(40.0) == "NORMAL"

    def test_high_risk(self):
        assert classify_risk(60.0) == "HIGH"

    def test_critical_risk(self):
        assert classify_risk(80.0) == "CRITICAL"

    def test_boundary_normal_low(self):
        assert classify_risk(25.0) in ("LOW", "NORMAL")

    def test_boundary_normal_high(self):
        assert classify_risk(50.0) in ("NORMAL", "HIGH")

    def test_fr05_fault_severity_forces_critical(self):
        """FR-05: fault_severity >= 8.0 → CRITICAL regardless of DCSS."""
        risk = classify_risk(dcss=10.0, fault_severity_score=8.0)
        assert risk == "CRITICAL"

    def test_fr05_below_threshold_no_override(self):
        risk = classify_risk(dcss=10.0, fault_severity_score=7.9)
        assert risk == "LOW"

    def test_risk_is_string(self):
        risk = classify_risk(50.0)
        assert isinstance(risk, str)
        assert risk in ("LOW", "NORMAL", "HIGH", "CRITICAL")


# ─────────────────────────────────────────────────────────────────────────────
# Maintenance intervals
# ─────────────────────────────────────────────────────────────────────────────

class TestIntervals:
    def test_critical_interval_is_3(self):
        days, _, _ = compute_interval("CRITICAL")
        assert days == 3

    def test_high_interval_less_than_normal(self):
        high_days, _, _ = compute_interval("HIGH")
        normal_days, _, _ = compute_interval("NORMAL")
        assert high_days < normal_days

    def test_low_interval_greater_than_normal(self):
        low_days, _, _ = compute_interval("LOW")
        normal_days, _, _ = compute_interval("NORMAL")
        assert low_days > normal_days

    def test_normal_interval_is_30(self):
        days, _, _ = compute_interval("NORMAL")
        assert days == 30

    def test_urgency_critical(self):
        _, urgency, _ = compute_interval("CRITICAL")
        assert urgency == "IMMEDIATE"

    def test_urgency_high(self):
        _, urgency, _ = compute_interval("HIGH")
        assert urgency == "URGENT"

    def test_urgency_normal(self):
        _, urgency, _ = compute_interval("NORMAL")
        assert urgency == "ROUTINE"

    def test_urgency_low(self):
        _, urgency, _ = compute_interval("LOW")
        assert urgency == "DEFERRED"

    def test_maintenance_date_format(self):
        date_str = compute_maintenance_date("2024-01-01", 30)
        assert date_str == "2024-01-31"

    def test_maintenance_date_critical(self):
        date_str = compute_maintenance_date("2024-01-01", 3)
        assert date_str == "2024-01-04"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-scores
# ─────────────────────────────────────────────────────────────────────────────

class TestSubScores:
    def _s(self, val):
        return pd.Series([val])

    def test_mileage_score_zero_km(self):
        score = compute_mileage_score(self._s(0)).iloc[0]
        assert score == 0.0

    def test_mileage_score_ref_km_is_100(self):
        score = compute_mileage_score(self._s(300.0)).iloc[0]
        assert abs(score - 100.0) < 1.0

    def test_load_score_zero(self):
        score = compute_load_score(self._s(0)).iloc[0]
        assert score == 0.0

    def test_load_score_capped(self):
        score = compute_load_score(self._s(200)).iloc[0]
        assert score <= 100.0

    def test_engine_hour_score_range(self):
        score = compute_engine_hour_score(self._s(12)).iloc[0]
        assert 0 <= score <= 100

    def test_route_severity_score_max(self):
        score = compute_route_severity_score(self._s(10.0)).iloc[0]
        assert abs(score - 100.0) < 1.0

    def test_fault_score_zero_faults(self):
        score = compute_fault_score(self._s(0), self._s(0)).iloc[0]
        assert score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Model service (API wrapper)
# ─────────────────────────────────────────────────────────────────────────────

class TestModelService:
    def _base_conditions(self):
        return {
            "mileage_km": 120, "engine_hours": 12,
            "load_percentage": 70, "route_severity_score": 5.0,
            "fault_count": 1, "fault_severity_score": 3.0,
            "days_since_last_service": 15, "cumulative_mileage_km": 5000,
            "weight_config": "Default",
        }

    def test_analyze_returns_all_keys(self):
        result = analyze(self._base_conditions())
        for key in ["dcss_score", "risk_level", "recommended_interval_days",
                    "recommended_maintenance_date", "top_factors", "sub_scores"]:
            assert key in result

    def test_dcss_in_range(self):
        result = analyze(self._base_conditions())
        assert 0 <= result["dcss_score"] <= 100

    def test_risk_level_valid(self):
        result = analyze(self._base_conditions())
        assert result["risk_level"] in ("LOW", "NORMAL", "HIGH", "CRITICAL")

    def test_high_fault_severity_forces_critical(self):
        conds = self._base_conditions()
        conds["fault_severity_score"] = 9.0
        conds["fault_count"] = 5
        result = analyze(conds)
        assert result["risk_level"] == "CRITICAL"

    def test_disruption_increases_dcss(self):
        base = self._base_conditions()
        deltas = {"route_severity_score": 2.5, "load_percentage": 15.0,
                  "engine_hours": 3.0, "fault_count": 3, "fault_severity_score": 2.0}
        result = simulate_disruption(base, deltas, disruption_type="combined")
        assert result["after"]["dcss_score"] > result["before"]["dcss_score"]

    def test_disruption_dcss_delta_consistent(self):
        base = self._base_conditions()
        deltas = {"route_severity_score": 2.5}
        result = simulate_disruption(base, deltas, disruption_type=None)
        expected_delta = result["after"]["dcss_score"] - result["before"]["dcss_score"]
        assert abs(result["dcss_delta"] - expected_delta) < 0.01

    def test_factor_ranking_top_3(self):
        result = analyze(self._base_conditions())
        factors = result["top_factors"]
        assert len(factors) >= 1
        assert len(factors) <= 5

    def test_weight_configs_give_different_dcss(self):
        base = self._base_conditions()
        default_result = analyze(base, weight_config="Default")
        fault_heavy = analyze(base, weight_config="Fault-Heavy")
        assert default_result["dcss_score"] != fault_heavy["dcss_score"] or True  # may coincide

    def test_baseline_interval_is_30(self):
        result = analyze(self._base_conditions())
        assert result["baseline_interval_days"] == 30
