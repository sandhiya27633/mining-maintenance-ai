"""
test_edge_cases.py — Edge Case Tests (FR-16)
=============================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data used in these tests is SYNTHETIC.

Covers all 7 required edge cases from FR-16:
  EC-01: Missing load data (load_percentage = NULL)
  EC-02: Invalid load > 100% (out-of-range, must be rejected/clamped)
  EC-03: Critical fault -> immediate inspection (FR-05 override)
  EC-04: Sudden disruption -> DCSS spike (risk elevates)
  EC-05: Dispatcher override with mandatory reason (empty = rejected)
  EC-06: Brand-new vehicle with no service history (neutral imputation)
  EC-07: Vehicle with conflicting/duplicate records (deduplication)

Also covers:
  EC-08: All sub-scores at boundary values (0 and 100)
  EC-09: Maximum interval hard limit enforced
  EC-10: Service reset grace period (serviced vehicle reduces effective risk)
"""

import sys
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg
from duty_cycle_model import compute_dcss_single, classify_risk
from maintenance_engine import compute_interval, compute_maintenance_date
from feature_engineering import (
    compute_mileage_score,
    compute_engine_hour_score,
    compute_load_score,
    compute_route_severity_score,
    compute_fault_score,
    compute_service_wear_score,
)
import database as db


# ---------------------------------------------------------------------------
# Helper: create minimal operational record dict
# ---------------------------------------------------------------------------

def _make_record(
    vehicle_id="VH-TEST",
    date="2024-06-01",
    mileage_km=100.0,
    cumulative_mileage_km=1000.0,
    engine_hours=12.0,
    load_percentage=70.0,
    route_severity_score=5.0,
    fault_count=0,
    fault_severity_score=0.0,
    days_since_last_service=15,
    scenario_tag="NORMAL",
) -> dict:
    return {
        "vehicle_id":             vehicle_id,
        "date":                   date,
        "mileage_km":             mileage_km,
        "cumulative_mileage_km":  cumulative_mileage_km,
        "engine_hours":           engine_hours,
        "load_percentage":        load_percentage,
        "route_severity_score":   route_severity_score,
        "fault_count":            fault_count,
        "fault_severity_score":   fault_severity_score,
        "days_since_last_service":days_since_last_service,
        "scenario_tag":           scenario_tag,
    }


# ---------------------------------------------------------------------------
# In-memory DB fixture (isolated per test)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    """
    Create a fresh in-memory-style SQLite DB in a temp dir for each test.
    Returns the project_root Path pointing to tmp_path.
    """
    # Patch cfg.DB_FILENAME to point inside tmp_path
    original = cfg.DB_FILENAME
    cfg.DB_FILENAME = str(tmp_path / "test.db")
    db.create_schema(project_root=None)   # uses cfg.DB_FILENAME directly
    yield tmp_path
    cfg.DB_FILENAME = original   # restore


# ---------------------------------------------------------------------------
# EC-01: Missing load data
# ---------------------------------------------------------------------------

class TestMissingLoadData:

    def test_load_score_nan_imputed_by_preprocessing(self):
        """
        EC-01: Missing load_percentage is imputed by preprocessing to the
        vehicle-type median (a finite value in [0,100]). The score function
        itself passes through NaN — imputation is preprocessing's responsibility.
        Verify the preprocessing output CSV has no NaN load_percentage.
        """
        clean_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_CLEAN_FILE
        if not clean_path.exists():
            pytest.skip("Clean CSV not found — run preprocessing first.")
        clean_df = pd.read_csv(clean_path)
        null_count = clean_df["load_percentage"].isna().sum()
        assert null_count == 0, (
            f"preprocessing left {null_count} NULL load_percentage values — "
            "imputation failed (EC-01)."
        )

    def test_load_score_imputed_values_in_valid_range(self):
        """EC-01: All load_percentage values in clean CSV must be in [0, 100]."""
        clean_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_CLEAN_FILE
        if not clean_path.exists():
            pytest.skip("Clean CSV not found.")
        clean_df = pd.read_csv(clean_path)
        invalid = clean_df["load_percentage"].between(0, 100).eq(False).sum()
        assert invalid == 0, (
            f"{invalid} load_percentage values outside [0,100] after imputation."
        )

    def test_dcss_with_imputed_load_still_computes(self):
        """
        EC-01: DCSS must be computable with any valid imputed load_score.
        Use the neutral value 50.0 (vehicle-type median approximation).
        """
        imputed_load_score = 50.0  # neutral / median approximation
        dcss = compute_dcss_single(
            fault_score=20.0,
            route_severity_score_n=40.0,
            load_score=imputed_load_score,
            engine_hour_score=60.0,
            mileage_score=30.0,
            service_wear_score=20.0,
        )
        assert 0.0 <= dcss <= 100.0, f"DCSS with imputed load out of range: {dcss}"


# ---------------------------------------------------------------------------
# EC-02: Invalid load > 100%
# ---------------------------------------------------------------------------

class TestInvalidLoadOutOfRange:

    def test_load_score_clamped_at_100(self):
        """EC-02: load_percentage > 100 must be clamped to load_score = 100."""
        score = compute_load_score(pd.Series([120.0])).iloc[0]
        assert score == 100.0, (
            f"load_percentage=120 should clamp to score=100, got {score}"
        )

    def test_load_score_negative_clamped_to_zero(self):
        """EC-02: load_percentage < 0 must clamp to load_score = 0."""
        score = compute_load_score(pd.Series([-10.0])).iloc[0]
        assert score == 0.0, (
            f"load_percentage=-10 should clamp to score=0, got {score}"
        )

    def test_load_score_exactly_100(self):
        """EC-02: load_percentage = 100 must give score = 100 (boundary)."""
        assert compute_load_score(pd.Series([100.0])).iloc[0] == 100.0

    def test_load_score_exactly_0(self):
        """EC-02: load_percentage = 0 must give score = 0 (boundary)."""
        assert compute_load_score(pd.Series([0.0])).iloc[0] == 0.0


# ---------------------------------------------------------------------------
# EC-03: Critical fault → immediate inspection
# ---------------------------------------------------------------------------

class TestCriticalFaultImmediate:

    def test_critical_fault_overrides_low_dcss(self):
        """
        EC-03: A vehicle with fault_severity >= threshold must be classified
        CRITICAL even if DCSS is only 10 (low operational stress otherwise).
        """
        threshold = cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD
        risk = classify_risk(10.0, fault_severity_score=threshold)
        assert risk == "CRITICAL", (
            f"Expected CRITICAL for fault_severity={threshold} regardless of DCSS=10"
        )

    def test_critical_interval_is_immediate(self):
        """EC-03: CRITICAL risk must map to CRITICAL_MAX_DAYS interval (IMMEDIATE)."""
        days, urgency, _ = compute_interval("CRITICAL")
        assert days == cfg.CRITICAL_MAX_DAYS
        assert urgency == "IMMEDIATE"

    def test_critical_interval_within_hard_limits(self):
        """EC-03: CRITICAL_MAX_DAYS must satisfy MIN_INTERVAL_DAYS constraint."""
        assert cfg.CRITICAL_MAX_DAYS >= cfg.MIN_INTERVAL_DAYS, (
            f"CRITICAL_MAX_DAYS={cfg.CRITICAL_MAX_DAYS} < MIN_INTERVAL_DAYS={cfg.MIN_INTERVAL_DAYS}"
        )

    def test_fault_just_below_threshold_not_overridden(self):
        """EC-03: fault_severity just below threshold must NOT force CRITICAL."""
        threshold = cfg.CRITICAL_FAULT_SEVERITY_THRESHOLD
        risk = classify_risk(40.0, fault_severity_score=threshold - 0.01)
        assert risk != "CRITICAL" or 40.0 >= 75.0, (
            "Risk should not be CRITICAL when fault_severity is just below threshold "
            "and DCSS is in HIGH range."
        )


# ---------------------------------------------------------------------------
# EC-04: Sudden disruption → DCSS spike
# ---------------------------------------------------------------------------

class TestDisruptionSpike:

    def _make_normal_row(self):
        """Return a row representing a typical normal-condition vehicle-day."""
        return {
            "fault_score":           15.0,
            "route_severity_score_n": 45.0,
            "load_score":            65.0,
            "engine_hour_score":     60.0,
            "mileage_score":         40.0,
            "service_wear_score":    35.0,
        }

    def _make_disruption_row(self):
        """Return a row representing disruption conditions per Phase 1 spec."""
        return {
            "fault_score":           40.0,   # fault spike
            "route_severity_score_n": 70.0,   # route +25%
            "load_score":            80.0,    # load +15%
            "engine_hour_score":     75.0,    # engine_hours +3h
            "mileage_score":         40.0,
            "service_wear_score":    35.0,
        }

    def test_disruption_dcss_higher_than_normal(self):
        """EC-04: Disruption row DCSS must exceed normal row DCSS."""
        normal_dcss = compute_dcss_single(**self._make_normal_row())
        disrupt_dcss = compute_dcss_single(**self._make_disruption_row())
        assert disrupt_dcss > normal_dcss, (
            f"Disruption DCSS ({disrupt_dcss:.2f}) must exceed Normal ({normal_dcss:.2f})"
        )

    def test_disruption_risk_elevation(self):
        """EC-04: Disruption conditions must result in HIGH or CRITICAL risk."""
        disrupt = self._make_disruption_row()
        dcss = compute_dcss_single(**disrupt)
        risk = classify_risk(dcss)
        assert risk in ("HIGH", "CRITICAL"), (
            f"Disruption conditions should produce HIGH/CRITICAL risk, got {risk} (DCSS={dcss:.2f})"
        )

    def test_disruption_shorter_interval(self):
        """EC-04: Disruption must trigger a shorter maintenance interval than normal."""
        normal  = self._make_normal_row()
        disrupt = self._make_disruption_row()

        normal_risk  = classify_risk(compute_dcss_single(**normal))
        disrupt_risk = classify_risk(compute_dcss_single(**disrupt))

        normal_days,  _, _ = compute_interval(normal_risk)
        disrupt_days, _, _ = compute_interval(disrupt_risk)

        assert disrupt_days <= normal_days, (
            f"Disruption interval ({disrupt_days}d) should be <= normal ({normal_days}d)"
        )


# ---------------------------------------------------------------------------
# EC-05: Dispatcher override — mandatory reason
# ---------------------------------------------------------------------------

class TestDispatcherOverride:

    def _seed_db_with_plan(self, temp_db_path):
        """Insert one vehicle + one plan, return plan_id."""
        vehicles_df = pd.DataFrame([{
            "vehicle_id": "VH-001",
            "vehicle_type": "HAUL_TRUCK",
            "manufacture_year": 2018,
            "vehicle_age_years": 6.0,
            "max_load_capacity_tonnes": 200.0,
            "odometer_at_registration": 0.0,
            "active": 1,
        }])
        db.upsert_vehicles(vehicles_df)
        plan_sql = """
            INSERT INTO maintenance_plans
                (vehicle_id, plan_date, dcss_score, risk_level,
                 recommended_interval_days, recommended_maintenance_date,
                 reason_text, top_factors, model_version, is_overridden)
            VALUES ('VH-001','2024-06-01',55.0,'HIGH',18,'2024-06-19',
                    'Test reason','[]','1.0',0)
        """
        with db.connect() as conn:
            conn.execute(plan_sql)
            return conn.execute(
                "SELECT last_insert_rowid() AS id"
            ).fetchone()["id"]

    def test_empty_reason_rejected(self, temp_db):
        """EC-05: Submitting override with empty reason must raise ValueError."""
        plan_id = self._seed_db_with_plan(temp_db)
        with pytest.raises(ValueError, match="cannot be empty"):
            db.insert_override(
                vehicle_id="VH-001",
                original_plan_id=plan_id,
                original_interval_days=18,
                original_maintenance_date="2024-06-19",
                overridden_interval_days=10,
                overridden_maintenance_date="2024-06-11",
                dispatcher_id="THEMBA_T",
                reason="",
            )

    def test_whitespace_only_reason_rejected(self, temp_db):
        """EC-05: Whitespace-only reason must also be rejected."""
        plan_id = self._seed_db_with_plan(temp_db)
        with pytest.raises(ValueError, match="cannot be empty"):
            db.insert_override(
                vehicle_id="VH-001",
                original_plan_id=plan_id,
                original_interval_days=18,
                original_maintenance_date="2024-06-19",
                overridden_interval_days=10,
                overridden_maintenance_date="2024-06-11",
                dispatcher_id="THEMBA_T",
                reason="    ",
            )

    def test_valid_override_succeeds(self, temp_db):
        """EC-05: A valid override with non-empty reason must succeed."""
        plan_id = self._seed_db_with_plan(temp_db)
        override_id = db.insert_override(
            vehicle_id="VH-001",
            original_plan_id=plan_id,
            original_interval_days=18,
            original_maintenance_date="2024-06-19",
            overridden_interval_days=10,
            overridden_maintenance_date="2024-06-11",
            dispatcher_id="THEMBA_T",
            reason="Vehicle was observed operating on severe terrain — immediate service required.",
        )
        assert isinstance(override_id, int) and override_id > 0

    def test_override_marks_plan_as_overridden(self, temp_db):
        """EC-05: After override, original plan must have is_overridden=1."""
        plan_id = self._seed_db_with_plan(temp_db)
        db.insert_override(
            vehicle_id="VH-001",
            original_plan_id=plan_id,
            original_interval_days=18,
            original_maintenance_date="2024-06-19",
            overridden_interval_days=10,
            overridden_maintenance_date="2024-06-11",
            dispatcher_id="THEMBA_T",
            reason="Load spike observed — early service required.",
        )
        plans = db.get_plans_for_vehicle("VH-001")
        overridden = plans[plans["plan_id"] == plan_id].iloc[0]
        assert int(overridden["is_overridden"]) == 1

    def test_override_out_of_range_interval_rejected(self, temp_db):
        """EC-05: Interval outside [MIN, MAX] must raise ValueError."""
        plan_id = self._seed_db_with_plan(temp_db)
        with pytest.raises(ValueError, match="outside allowed range"):
            db.insert_override(
                vehicle_id="VH-001",
                original_plan_id=plan_id,
                original_interval_days=18,
                original_maintenance_date="2024-06-19",
                overridden_interval_days=999,   # exceeds MAX_INTERVAL_DAYS
                overridden_maintenance_date="2024-06-11",
                dispatcher_id="THEMBA_T",
                reason="Valid reason text.",
            )


# ---------------------------------------------------------------------------
# EC-06: Brand-new vehicle with no service history
# ---------------------------------------------------------------------------

class TestNewVehicleNoServiceHistory:

    def test_service_wear_score_neutral_for_null_days(self):
        """
        EC-06: When days_since_last_service is None (new vehicle),
        compute_service_wear_score must return 50.0 (neutral).
        """
        score = compute_service_wear_score(pd.Series([None])).iloc[0]
        assert score == 50.0, (
            f"New vehicle (no service history) should score 50.0 neutral, got {score}"
        )

    def test_service_wear_score_neutral_for_nan(self):
        """EC-06: NaN days_since_last_service must also produce 50.0."""
        score = compute_service_wear_score(pd.Series([float("nan")])).iloc[0]
        assert score == 50.0

    def test_dcss_with_new_vehicle_still_valid(self):
        """EC-06: DCSS must be in [0,100] even for a new vehicle (no history)."""
        service_score = compute_service_wear_score(pd.Series([None])).iloc[0]
        dcss = compute_dcss_single(
            fault_score=10.0,
            route_severity_score_n=45.0,
            load_score=65.0,
            engine_hour_score=60.0,
            mileage_score=35.0,
            service_wear_score=service_score,
        )
        assert 0.0 <= dcss <= 100.0

    def test_new_vehicle_not_flagged_critical_by_service_alone(self):
        """
        EC-06: A new vehicle with neutral service score and otherwise normal
        conditions must NOT be classified CRITICAL solely due to missing history.
        """
        service_score = compute_service_wear_score(pd.Series([None])).iloc[0]  # 50.0
        dcss = compute_dcss_single(
            fault_score=10.0,
            route_severity_score_n=40.0,
            load_score=65.0,
            engine_hour_score=60.0,
            mileage_score=35.0,
            service_wear_score=service_score,
        )
        risk = classify_risk(dcss, fault_severity_score=0.0)
        assert risk != "CRITICAL", (
            f"New vehicle with normal conditions should not be CRITICAL, got {risk} (DCSS={dcss:.2f})"
        )


# ---------------------------------------------------------------------------
# EC-07: Duplicate records (deduplication)
# ---------------------------------------------------------------------------

class TestDuplicateRecords:

    def test_duplicate_injection_in_features(self):
        """
        EC-07: The features file must have zero duplicate (vehicle_id, date) pairs —
        deduplication was applied in preprocessing.
        """
        feat_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_FEATURES_FILE
        if not feat_path.exists():
            pytest.skip("Feature CSV not found.")
        df = pd.read_csv(feat_path)
        dup_count = df.duplicated(subset=["vehicle_id","date"]).sum()
        assert dup_count == 0, (
            f"Found {dup_count} duplicate (vehicle_id, date) pairs in features CSV — "
            "deduplication failed."
        )

    def test_clean_data_no_duplicates(self):
        """EC-07: The clean CSV must have no duplicate (vehicle_id, date) pairs."""
        clean_path = PROJECT_ROOT / cfg.OPERATIONAL_DATA_CLEAN_FILE
        if not clean_path.exists():
            pytest.skip("Clean CSV not found.")
        df = pd.read_csv(clean_path)
        dup_count = df.duplicated(subset=["vehicle_id","date"]).sum()
        assert dup_count == 0, (
            f"Found {dup_count} duplicates in clean CSV — preprocessing failed."
        )


# ---------------------------------------------------------------------------
# EC-08: All sub-scores at boundary values
# ---------------------------------------------------------------------------

class TestBoundarySubScores:

    def test_mileage_score_zero(self):
        """Mileage = 0 km/day must produce score = 0."""
        assert compute_mileage_score(pd.Series([0.0])).iloc[0] == 0.0

    def test_mileage_score_at_reference(self):
        """Mileage = MILEAGE_SCORE_REF_KM must produce score = 100."""
        assert compute_mileage_score(
            pd.Series([float(cfg.MILEAGE_SCORE_REF_KM)])
        ).iloc[0] == 100.0

    def test_mileage_score_above_reference_capped(self):
        """Mileage > MILEAGE_SCORE_REF_KM must be capped at 100."""
        assert compute_mileage_score(
            pd.Series([float(cfg.MILEAGE_SCORE_REF_KM) * 2])
        ).iloc[0] == 100.0

    def test_engine_hour_score_zero(self):
        """0 engine hours must produce score = 0."""
        assert compute_engine_hour_score(pd.Series([0.0])).iloc[0] == 0.0

    def test_engine_hour_score_at_reference(self):
        """ENGINE_HOUR_SCORE_REF hours/day must produce score = 100."""
        assert compute_engine_hour_score(
            pd.Series([float(cfg.ENGINE_HOUR_SCORE_REF)])
        ).iloc[0] == 100.0

    def test_fault_score_zero_faults(self):
        """0 faults and 0 fault severity must produce score = 0."""
        assert compute_fault_score(pd.Series([0]), pd.Series([0.0])).iloc[0] == 0.0

    def test_route_severity_zero(self):
        """route_severity_score = 0 must produce normalised score = 0."""
        assert compute_route_severity_score(pd.Series([0.0])).iloc[0] == 0.0

    def test_route_severity_max(self):
        """route_severity_score = 10 must produce normalised score = 100."""
        assert compute_route_severity_score(pd.Series([10.0])).iloc[0] == 100.0


# ---------------------------------------------------------------------------
# EC-09: Maximum interval hard limit
# ---------------------------------------------------------------------------

class TestMaxIntervalHardLimit:

    def test_low_risk_interval_does_not_exceed_max(self):
        """EC-09: LOW risk interval must not exceed MAX_INTERVAL_DAYS."""
        days, _, _ = compute_interval("LOW")
        assert days <= cfg.MAX_INTERVAL_DAYS, (
            f"LOW interval {days} exceeds MAX_INTERVAL_DAYS={cfg.MAX_INTERVAL_DAYS}"
        )

    def test_all_intervals_at_least_min(self):
        """EC-09: No interval may be less than MIN_INTERVAL_DAYS."""
        for risk in ["LOW","NORMAL","HIGH","CRITICAL"]:
            days, _, _ = compute_interval(risk)
            assert days >= cfg.MIN_INTERVAL_DAYS, (
                f"{risk} interval {days} < MIN_INTERVAL_DAYS={cfg.MIN_INTERVAL_DAYS}"
            )


# ---------------------------------------------------------------------------
# EC-10: Service wear score progression
# ---------------------------------------------------------------------------

class TestServiceWearProgression:

    def test_service_wear_increases_with_days(self):
        """EC-10: service_wear_score must increase as days_since_last_service increases."""
        scores = [
            compute_service_wear_score(pd.Series([d])).iloc[0]
            for d in [0, 10, 20, 30, 60]
        ]
        assert scores == sorted(scores), (
            f"Service wear scores not monotonically increasing: {scores}"
        )

    def test_service_wear_caps_at_100(self):
        """EC-10: Very large days_since_service must cap at 100."""
        score = compute_service_wear_score(pd.Series([9999])).iloc[0]
        assert score == 100.0, f"Expected 100.0 for very large days, got {score}"

    def test_service_wear_zero_days(self):
        """EC-10: 0 days since service (just serviced) must produce score = 0."""
        assert compute_service_wear_score(pd.Series([0])).iloc[0] == 0.0
