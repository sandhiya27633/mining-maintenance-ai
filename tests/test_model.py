"""
test_model.py — Core Model Unit Tests
=======================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data used in these tests is SYNTHETIC.

Covers (FR-15):
  - DCSS calculation (formula correctness, weight configs, boundary values)
  - Risk classification (all four levels, threshold boundaries)
  - Interval calculation (all four risk levels, hard limits)
  - Critical fault override rule (FR-05)
  - Disruption response (DCSS elevation under disruption scenario)
  - Failure probability function (range, monotonicity, disruption sensitivity)
  - Factor ranking (order, count, contribution sum)
  - Vectorised DCSS on DataFrame (shape, NaN delta, weight_config label)
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make src/ importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg
from duty_cycle_model import (
    compute_dcss_single,
    classify_risk,
    rank_factors,
    compute_dcss_dataframe,
)
from maintenance_engine import compute_interval, compute_maintenance_date
from failure_simulator import compute_failure_probability


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample_features_df():
    """Load the feature-engineered dataset (generated in Phase 3)."""
    feat_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_FEATURES_FILE
    if not feat_path.exists():
        pytest.skip("Feature CSV not found — run preprocessing and feature_engineering first.")
    return pd.read_csv(feat_path)


@pytest.fixture(scope="module")
def dcss_df(sample_features_df):
    """Full DCSS-enriched DataFrame."""
    return compute_dcss_dataframe(sample_features_df)


# ---------------------------------------------------------------------------
# TC-01: DCSS formula correctness
# ---------------------------------------------------------------------------

class TestDCSSCalculation:

    def test_dcss_manual_match(self):
        """DCSS must match the hand-computed weighted sum exactly."""
        w = cfg.DCSS_WEIGHTS_DEFAULT
        fault, route, load, engine, mileage, service = 50.0, 40.0, 70.0, 60.0, 30.0, 20.0
        expected = (
            w["fault_score"]          * fault
            + w["route_severity_score"] * route
            + w["load_score"]           * load
            + w["engine_hour_score"]    * engine
            + w["mileage_score"]        * mileage
            + w["service_wear_score"]   * service
        )
        result = compute_dcss_single(fault, route, load, engine, mileage, service)
        assert abs(result - expected) < 1e-9, (
            f"DCSS={result:.6f} does not match expected={expected:.6f}"
        )

    def test_dcss_zero_inputs(self):
        """All-zero inputs must produce DCSS = 0."""
        assert compute_dcss_single(0, 0, 0, 0, 0, 0) == 0.0

    def test_dcss_max_inputs(self):
        """All-100 inputs must produce DCSS = 100 (weights sum to 1)."""
        result = compute_dcss_single(100, 100, 100, 100, 100, 100)
        assert abs(result - 100.0) < 1e-9, f"Expected 100.0, got {result}"

    def test_dcss_clipped_above_100(self):
        """DCSS is clipped to 100 even if inputs exceed normalised range."""
        result = compute_dcss_single(110, 110, 110, 110, 110, 110)
        assert result == 100.0

    def test_dcss_clipped_below_0(self):
        """DCSS is clipped to 0 for negative inputs."""
        result = compute_dcss_single(-10, -10, -10, -10, -10, -10)
        assert result == 0.0

    def test_dcss_weights_sum_to_one(self):
        """All weight configs must sum to exactly 1.0 (validated in config)."""
        for name, weights in cfg.DCSS_WEIGHT_CONFIGS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 1e-9, (
                f"Weight config '{name}' sums to {total:.9f}, must be 1.0"
            )

    def test_dcss_fault_heavy_weights(self):
        """Fault-Heavy config gives more weight to fault_score."""
        # With high fault score (100) and everything else 0,
        # Fault-Heavy should produce a higher DCSS than Default.
        default_dcss = compute_dcss_single(
            100, 0, 0, 0, 0, 0,
            weights=cfg.DCSS_WEIGHTS_DEFAULT,
        )
        fault_heavy_dcss = compute_dcss_single(
            100, 0, 0, 0, 0, 0,
            weights=cfg.DCSS_WEIGHTS_FAULT_HEAVY,
        )
        assert fault_heavy_dcss > default_dcss, (
            f"Fault-Heavy ({fault_heavy_dcss}) should exceed Default ({default_dcss}) "
            "when fault_score=100."
        )

    def test_dcss_monotonic_in_fault_score(self):
        """DCSS increases monotonically as fault_score increases."""
        scores = [compute_dcss_single(fs, 50, 50, 50, 50, 50) for fs in range(0, 101, 10)]
        assert scores == sorted(scores), "DCSS must be monotonically non-decreasing in fault_score."


# ---------------------------------------------------------------------------
# TC-02: Risk classification
# ---------------------------------------------------------------------------

class TestRiskClassification:

    def test_low_boundary(self):
        """DCSS at 0 must be LOW."""
        assert classify_risk(0.0) == "LOW"

    def test_low_upper_boundary(self):
        """DCSS at exactly 25 must be LOW (boundary inclusive)."""
        lo, hi = cfg.RISK_THRESHOLDS["LOW"]
        assert classify_risk(hi) == "LOW", f"DCSS={hi} should be LOW"

    def test_normal_level(self):
        """DCSS in (25, 50] must be NORMAL."""
        assert classify_risk(35.0) == "NORMAL"
        assert classify_risk(50.0) == "NORMAL"

    def test_high_level(self):
        """DCSS in (50, 75] must be HIGH."""
        assert classify_risk(60.0) == "HIGH"
        assert classify_risk(75.0) == "HIGH"

    def test_critical_level(self):
        """DCSS > 75 must be CRITICAL."""
        assert classify_risk(75.1) == "CRITICAL"
        assert classify_risk(100.0) == "CRITICAL"

    def test_fr05_critical_fault_override(self):
        """
        FR-05: fault_severity_score >= CRITICAL_FAULT_SEVERITY_THRESHOLD
        must force CRITICAL regardless of DCSS value.
        """
        threshold = cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD
        # Even with very low DCSS (10), critical fault forces CRITICAL
        result = classify_risk(10.0, fault_severity_score=threshold)
        assert result == "CRITICAL", (
            f"Expected CRITICAL (FR-05 override) for dcss=10, "
            f"fault_severity={threshold}, got {result}"
        )

    def test_fr05_does_not_trigger_below_threshold(self):
        """FR-05 must NOT trigger if fault_severity < threshold."""
        threshold = cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD
        result = classify_risk(60.0, fault_severity_score=threshold - 0.1)
        assert result == "HIGH", (
            f"Expected HIGH for dcss=60, fault_severity={threshold - 0.1}, got {result}"
        )

    def test_fr05_triggers_at_exact_threshold(self):
        """FR-05 must trigger at exactly the threshold value."""
        threshold = cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD
        assert classify_risk(0.0, fault_severity_score=threshold) == "CRITICAL"


# ---------------------------------------------------------------------------
# TC-03: Maintenance interval calculation
# ---------------------------------------------------------------------------

class TestIntervalCalculation:

    def test_critical_interval(self):
        """CRITICAL must produce CRITICAL_MAX_DAYS interval."""
        days, urgency, reason = compute_interval("CRITICAL")
        assert days == cfg.CRITICAL_MAX_DAYS, (
            f"Expected {cfg.CRITICAL_MAX_DAYS}, got {days}"
        )
        assert urgency == "IMMEDIATE"
        assert len(reason) > 0

    def test_high_interval(self):
        """HIGH must produce shortened interval = round(std * reduction_factor)."""
        days, urgency, reason = compute_interval("HIGH")
        expected = int(round(cfg.STANDARD_INTERVAL_DAYS * cfg.HIGH_INTERVAL_REDUCTION_FACTOR))
        assert days == expected, f"Expected {expected}, got {days}"
        assert urgency == "URGENT"

    def test_normal_interval(self):
        """NORMAL must produce exactly STANDARD_INTERVAL_DAYS."""
        days, urgency, reason = compute_interval("NORMAL")
        assert days == cfg.STANDARD_INTERVAL_DAYS, (
            f"Expected {cfg.STANDARD_INTERVAL_DAYS}, got {days}"
        )
        assert urgency == "ROUTINE"

    def test_low_interval(self):
        """LOW must produce extended interval = round(std * extension_factor), capped at MAX."""
        days, urgency, reason = compute_interval("LOW")
        expected = min(
            cfg.MAX_INTERVAL_DAYS,
            int(round(cfg.STANDARD_INTERVAL_DAYS * cfg.LOW_INTERVAL_EXTENSION_FACTOR)),
        )
        assert days == expected, f"Expected {expected}, got {days}"
        assert urgency == "DEFERRED"

    def test_all_intervals_within_hard_limits(self):
        """All risk levels must produce intervals within [MIN, MAX] hard limits."""
        for risk in ["LOW", "NORMAL", "HIGH", "CRITICAL"]:
            days, _, _ = compute_interval(risk)
            assert cfg.MIN_INTERVAL_DAYS <= days <= cfg.MAX_INTERVAL_DAYS, (
                f"Interval {days} for {risk} outside [{cfg.MIN_INTERVAL_DAYS}, {cfg.MAX_INTERVAL_DAYS}]"
            )

    def test_maintenance_date_arithmetic(self):
        """Maintenance date = current_date + interval_days (ISO 8601)."""
        mdate = compute_maintenance_date("2024-03-01", 18)
        assert mdate == "2024-03-19", f"Expected 2024-03-19, got {mdate}"

    def test_maintenance_date_leap_year(self):
        """Leap year date arithmetic must be correct."""
        mdate = compute_maintenance_date("2024-02-15", 14)
        assert mdate == "2024-02-29", f"Expected 2024-02-29, got {mdate}"

    def test_reason_is_non_empty_for_all_levels(self):
        """All four risk levels must produce a non-empty reason string."""
        for risk in ["LOW", "NORMAL", "HIGH", "CRITICAL"]:
            _, _, reason = compute_interval(risk)
            assert isinstance(reason, str) and len(reason.strip()) > 0, (
                f"Reason is empty for risk level {risk}"
            )

    def test_interval_ordering(self):
        """Intervals must be ordered: CRITICAL < HIGH < NORMAL < LOW."""
        intervals = {r: compute_interval(r)[0] for r in ["CRITICAL","HIGH","NORMAL","LOW"]}
        assert intervals["CRITICAL"] < intervals["HIGH"] < intervals["NORMAL"] < intervals["LOW"], (
            f"Interval ordering violated: {intervals}"
        )


# ---------------------------------------------------------------------------
# TC-04: Factor ranking
# ---------------------------------------------------------------------------

class TestFactorRanking:

    def test_rank_factors_count(self):
        """rank_factors must return exactly top_n items (default 3)."""
        factors = rank_factors(80, 50, 70, 60, 40, 30)
        assert len(factors) == 3

    def test_rank_factors_sorted_descending(self):
        """Factors must be sorted by contribution descending."""
        factors = rank_factors(80, 50, 70, 60, 40, 30, top_n=6)
        contributions = [f["contribution"] for f in factors]
        assert contributions == sorted(contributions, reverse=True), (
            f"Contributions not sorted descending: {contributions}"
        )

    def test_rank_factors_keys_present(self):
        """Each factor dict must have factor, sub_score, contribution keys."""
        factors = rank_factors(80, 50, 70, 60, 40, 30)
        for f in factors:
            assert "factor" in f
            assert "sub_score" in f
            assert "contribution" in f

    def test_rank_factors_contributions_sum_to_dcss(self):
        """Sum of all contributions must equal DCSS."""
        scores = (20.0, 50.0, 70.0, 60.0, 40.0, 30.0)
        factors = rank_factors(*scores, top_n=6)
        total = sum(f["contribution"] for f in factors)
        dcss = compute_dcss_single(*scores)
        assert abs(total - dcss) < 1e-9, (
            f"Contribution sum {total:.6f} != DCSS {dcss:.6f}"
        )

    def test_highest_weighted_factor_ranks_first_when_scores_equal(self):
        """When all sub-scores are equal, highest-weight factor must rank first."""
        factors = rank_factors(50, 50, 50, 50, 50, 50)
        # Default weights: fault_score=0.30 is highest
        assert factors[0]["factor"] == "fault_score", (
            f"Expected fault_score first (highest weight), got {factors[0]['factor']}"
        )


# ---------------------------------------------------------------------------
# TC-05: Disruption response
# ---------------------------------------------------------------------------

class TestDisruptionResponse:

    def test_disruption_dcss_higher_than_normal(self, sample_features_df):
        """Mean DCSS must be higher during DISRUPTION than NORMAL days."""
        dcss_full = compute_dcss_dataframe(sample_features_df)
        normal_mean = dcss_full[dcss_full["scenario_tag"] == "NORMAL"]["dcss"].mean()
        disrupt_mean = dcss_full[dcss_full["scenario_tag"] == "DISRUPTION"]["dcss"].mean()
        assert disrupt_mean > normal_mean, (
            f"Disruption DCSS ({disrupt_mean:.2f}) must exceed "
            f"Normal DCSS ({normal_mean:.2f})"
        )

    def test_disruption_fault_score_higher(self, sample_features_df):
        """Mean fault_score must be higher during DISRUPTION than NORMAL."""
        normal_fs = sample_features_df[
            sample_features_df["scenario_tag"] == "NORMAL"
        ]["fault_score"].mean()
        disrupt_fs = sample_features_df[
            sample_features_df["scenario_tag"] == "DISRUPTION"
        ]["fault_score"].mean()
        assert disrupt_fs > normal_fs, (
            f"Disruption fault_score ({disrupt_fs:.2f}) must exceed "
            f"Normal ({normal_fs:.2f})"
        )

    def test_disruption_risk_distribution_more_critical(self, dcss_df):
        """DISRUPTION days must have a higher proportion of HIGH/CRITICAL risk."""
        normal_high_pct = (
            dcss_df[dcss_df["scenario_tag"] == "NORMAL"]["risk_level"]
            .isin(["HIGH","CRITICAL"]).mean()
        )
        disrupt_high_pct = (
            dcss_df[dcss_df["scenario_tag"] == "DISRUPTION"]["risk_level"]
            .isin(["HIGH","CRITICAL"]).mean()
        )
        assert disrupt_high_pct > normal_high_pct, (
            f"Disruption HIGH/CRITICAL % ({disrupt_high_pct:.3f}) must exceed "
            f"Normal ({normal_high_pct:.3f})"
        )


# ---------------------------------------------------------------------------
# TC-06: Vectorised DCSS DataFrame
# ---------------------------------------------------------------------------

class TestVectorisedDCSS:

    def test_dcss_shape(self, dcss_df, sample_features_df):
        """Output DataFrame must have same number of rows as input."""
        assert len(dcss_df) == len(sample_features_df)

    def test_dcss_range_in_dataframe(self, dcss_df):
        """All DCSS values in DataFrame must be in [0, 100]."""
        assert dcss_df["dcss"].between(0, 100).all(), (
            f"DCSS out of range: min={dcss_df['dcss'].min():.2f}, max={dcss_df['dcss'].max():.2f}"
        )

    def test_dcss_delta_nan_for_first_vehicle_record(self, dcss_df):
        """First record per vehicle (by date) must have NaN dcss_delta."""
        sorted_df = dcss_df.sort_values(["vehicle_id","date"])
        first_records = sorted_df.groupby("vehicle_id").nth(0)
        assert first_records["dcss_delta"].isna().all(), (
            "First record per vehicle should have NaN dcss_delta."
        )

    def test_dcss_delta_not_nan_for_subsequent_records(self, dcss_df):
        """Subsequent records per vehicle must have numeric dcss_delta."""
        sorted_df = dcss_df.sort_values(["vehicle_id","date"])
        non_first = sorted_df.groupby("vehicle_id").apply(
            lambda g: g.iloc[1:]
        ).reset_index(drop=True)
        assert non_first["dcss_delta"].notna().all()

    def test_top_factors_valid_json(self, dcss_df):
        """Every top_factors cell must be valid JSON with 3 items."""
        for tf_str in dcss_df["top_factors"].head(50):
            parsed = json.loads(tf_str)
            assert isinstance(parsed, list) and len(parsed) == 3, (
                f"top_factors should be a list of 3, got {parsed}"
            )

    def test_weight_config_label(self, dcss_df):
        """Default run must label weight_config as 'Default'."""
        assert (dcss_df["weight_config"] == "Default").all()


# ---------------------------------------------------------------------------
# TC-07: Failure probability function
# ---------------------------------------------------------------------------

class TestFailureProbability:

    def test_failure_prob_in_range(self, sample_features_df):
        """All failure probabilities must be in [0, 1]."""
        probs = compute_failure_probability(sample_features_df)
        assert probs.between(0, 1).all(), (
            f"Failure prob out of [0,1]: min={probs.min():.4f}, max={probs.max():.4f}"
        )

    def test_failure_prob_disruption_higher(self, sample_features_df):
        """Disruption days must have higher mean failure probability than normal."""
        probs = compute_failure_probability(sample_features_df)
        normal_p   = probs[sample_features_df["scenario_tag"] == "NORMAL"].mean()
        disrupt_p  = probs[sample_features_df["scenario_tag"] == "DISRUPTION"].mean()
        assert disrupt_p > normal_p, (
            f"Disruption prob ({disrupt_p:.4f}) must exceed Normal ({normal_p:.4f})"
        )

    def test_failure_prob_realistic_range(self, sample_features_df):
        """Mean failure probability must be realistic (1–20% per day)."""
        probs = compute_failure_probability(sample_features_df)
        mean_p = probs.mean()
        assert 0.01 <= mean_p <= 0.20, (
            f"Mean failure prob {mean_p:.4f} outside expected range [0.01, 0.20]"
        )
