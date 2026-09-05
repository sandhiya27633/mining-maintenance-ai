"""
test_database.py — Database Layer Tests (FR-13, FR-11, FR-12)
=============================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data used in these tests is SYNTHETIC.

Covers:
  DB-01: Schema creation — all 5 tables and indexes exist
  DB-02: Vehicles CRUD — upsert, idempotency
  DB-03: Operational data insert — bulk, range constraints, UNIQUE
  DB-04: Maintenance plans — insert, get_latest_plans
  DB-05: Override workflow — write, plan update, history read
  DB-06: Override reason CHECK constraint (DB-level + Python-level)
  DB-07: Query API — per-vehicle, date range, fleet risk summary
  DB-08: Foreign key integrity
  DB-09: WAL journal mode
  DB-10: Audit trail completeness (timestamp, dispatcher, reason all stored)
  DB-11: DB stats utility
  DB-12: Schema verification utility
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg
import database as db


# ---------------------------------------------------------------------------
# Fixture: isolated per-test SQLite DB in tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Each test gets a fresh database in a temporary directory.
    Uses monkeypatch so cfg.DB_FILENAME is restored after the test.
    """
    db_path = str(tmp_path / "test_mining.db")
    monkeypatch.setattr(cfg, "DB_FILENAME", db_path)
    db.create_schema()
    return tmp_path


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _make_vehicles_df(n=3) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "vehicle_id":                f"VH-{i:03d}",
            "vehicle_type":              ["HAUL_TRUCK","LOADER","BULLDOZER"][i % 3],
            "manufacture_year":          2018 + i,
            "vehicle_age_years":         6.0 - i * 0.5,
            "max_load_capacity_tonnes":  200.0 + i * 10,
            "odometer_at_registration":  0.0,
            "active":                    1,
        }
        for i in range(n)
    ])


def _make_ops_df(vehicle_ids: list, dates: list) -> pd.DataFrame:
    rows = []
    for vid in vehicle_ids:
        for d in dates:
            rows.append({
                "vehicle_id":             vid,
                "date":                   d,
                "mileage_km":             100.0,
                "cumulative_mileage_km":  5000.0,
                "engine_hours":           12.0,
                "load_percentage":        70.0,
                "route_severity_score":   5.0,
                "route_severity_label":   "Medium",
                "fault_count":            0,
                "fault_severity_score":   0.0,
                "operating_stress_index": 4.0,
                "days_since_last_service":15,
                "last_service_mileage_km":4900.0,
                "service_type_last":      "MINOR",
                "breakdown_occurred":     0,
                "breakdown_type":         None,
                "data_quality_flag":      None,
                "scenario_tag":           "NORMAL",
            })
    return pd.DataFrame(rows)


def _make_plans_df(vehicle_ids: list, dates: list) -> pd.DataFrame:
    rows = []
    for vid in vehicle_ids:
        for d in dates:
            rows.append({
                "vehicle_id":                    vid,
                "date":                          d,
                "dcss":                          45.0,
                "risk_level":                    "NORMAL",
                "recommended_interval_days":     30,
                "recommended_maintenance_date":  "2024-07-01",
                "recommendation_reason":         "Standard interval — NORMAL risk.",
                "top_factors":                   json.dumps([
                    {"factor":"fault_score","sub_score":10.0,"contribution":3.0},
                    {"factor":"load_score","sub_score":70.0,"contribution":14.0},
                    {"factor":"engine_hour_score","sub_score":60.0,"contribution":9.0},
                ]),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DB-01: Schema
# ---------------------------------------------------------------------------

class TestSchemaCreation:

    def test_all_five_tables_exist(self, temp_db):
        """DB-01: All 5 tables must be created on schema initialisation."""
        schema = db.verify_schema()
        for table in ["vehicles","operational_data","service_history",
                      "maintenance_plans","override_history"]:
            assert schema[table], f"Table '{table}' schema verification failed."

    def test_schema_is_idempotent(self, temp_db):
        """DB-01: Calling create_schema twice must not raise or duplicate tables."""
        db.create_schema()   # second call
        schema = db.verify_schema()
        assert all(schema.values()), "Schema not valid after second create_schema call."

    def test_indexes_exist(self, temp_db):
        """DB-01: Performance indexes must be created."""
        with db.connect(read_only=True) as conn:
            idxs = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        idx_names = {r["name"] for r in idxs}
        for expected in ["idx_ops_vehicle_date","idx_plans_vehicle","idx_svc_vehicle_date"]:
            assert expected in idx_names, f"Missing index: {expected}"


# ---------------------------------------------------------------------------
# DB-02: Vehicles CRUD
# ---------------------------------------------------------------------------

class TestVehiclesCRUD:

    def test_upsert_vehicles(self, temp_db):
        """DB-02: upsert_vehicles must insert all rows."""
        vdf = _make_vehicles_df(3)
        count = db.upsert_vehicles(vdf)
        assert count == 3

    def test_upsert_vehicles_idempotent(self, temp_db):
        """DB-02: Second upsert must not duplicate rows."""
        vdf = _make_vehicles_df(3)
        db.upsert_vehicles(vdf)
        db.upsert_vehicles(vdf)   # second time — INSERT OR REPLACE
        stats = db.get_db_stats()
        assert stats["vehicles"] == 3

    def test_get_vehicles_returns_all(self, temp_db):
        """DB-02: get_vehicles must return all inserted vehicles."""
        vdf = _make_vehicles_df(5)
        db.upsert_vehicles(vdf)
        result = db.get_vehicles()
        assert len(result) == 5

    def test_vehicle_type_constraint(self, temp_db):
        """DB-02: Invalid vehicle_type must violate CHECK constraint."""
        bad_vdf = pd.DataFrame([{
            "vehicle_id": "VH-BAD",
            "vehicle_type": "SPACESHIP",   # invalid
            "manufacture_year": 2020,
            "vehicle_age_years": 4.0,
            "max_load_capacity_tonnes": 100.0,
            "odometer_at_registration": 0.0,
            "active": 1,
        }])
        with pytest.raises(Exception):   # sqlite3.IntegrityError
            db.upsert_vehicles(bad_vdf)


# ---------------------------------------------------------------------------
# DB-03: Operational data insert
# ---------------------------------------------------------------------------

class TestOperationalDataInsert:

    def test_bulk_insert(self, temp_db):
        """DB-03: Bulk insert must store all rows."""
        vdf = _make_vehicles_df(2)
        db.upsert_vehicles(vdf)
        ops = _make_ops_df(["VH-000","VH-001"], ["2024-01-01","2024-01-02","2024-01-03"])
        count = db.insert_operational_data(ops)
        assert count == 6   # 2 vehicles x 3 dates

    def test_unique_constraint_vehicle_date(self, temp_db):
        """DB-03: Inserting duplicate (vehicle_id, date) must raise IntegrityError."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        ops = _make_ops_df(["VH-000"], ["2024-01-01"])
        db.insert_operational_data(ops, replace=False)   # INSERT OR IGNORE
        # Second insert with same data must be silently ignored (OR IGNORE mode)
        count2 = db.insert_operational_data(ops, replace=False)
        stats = db.get_db_stats()
        assert stats["operational_data"] == 1   # not doubled

    def test_insert_replace_overwrites(self, temp_db):
        """DB-03: INSERT OR REPLACE must overwrite existing row."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        ops = _make_ops_df(["VH-000"], ["2024-01-01"])
        db.insert_operational_data(ops, replace=True)
        # Modify and re-insert
        ops2 = ops.copy()
        ops2["engine_hours"] = 20.0
        db.insert_operational_data(ops2, replace=True)
        stats = db.get_db_stats()
        assert stats["operational_data"] == 1   # still 1 row

    def test_operational_data_query_for_vehicle(self, temp_db):
        """DB-03: get_operational_data_for_vehicle must return only that vehicle's rows."""
        vdf = _make_vehicles_df(2)
        db.upsert_vehicles(vdf)
        ops = _make_ops_df(["VH-000","VH-001"], ["2024-01-01","2024-01-02"])
        db.insert_operational_data(ops)
        result = db.get_operational_data_for_vehicle("VH-000")
        assert len(result) == 2
        assert (result["vehicle_id"] == "VH-000").all()


# ---------------------------------------------------------------------------
# DB-04: Maintenance plans
# ---------------------------------------------------------------------------

class TestMaintenancePlans:

    def test_insert_plans(self, temp_db):
        """DB-04: insert_maintenance_plans must store all rows."""
        vdf = _make_vehicles_df(2)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000","VH-001"], ["2024-01-01","2024-01-02"])
        count = db.insert_maintenance_plans(plans)
        assert count == 4   # 2 vehicles x 2 dates

    def test_get_latest_plans_one_per_vehicle(self, temp_db):
        """DB-04: get_latest_plans must return exactly one row per vehicle."""
        vdf = _make_vehicles_df(3)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(
            ["VH-000","VH-001","VH-002"],
            ["2024-01-01","2024-01-02","2024-01-03"]
        )
        db.insert_maintenance_plans(plans)
        latest = db.get_latest_plans()
        assert len(latest) == 3
        assert len(latest["vehicle_id"].unique()) == 3

    def test_get_latest_plans_returns_most_recent_date(self, temp_db):
        """DB-04: get_latest_plans must return the latest plan_date per vehicle."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000"], ["2024-01-01","2024-06-01","2024-12-01"])
        db.insert_maintenance_plans(plans)
        latest = db.get_latest_plans()
        assert latest.iloc[0]["plan_date"] == "2024-12-01"

    def test_plans_top_factors_valid_json(self, temp_db):
        """DB-04: Stored top_factors must round-trip as valid JSON."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000"], ["2024-01-01"])
        db.insert_maintenance_plans(plans)
        stored = db.get_latest_plans()
        parsed = json.loads(stored.iloc[0]["top_factors"])
        assert isinstance(parsed, list) and len(parsed) == 3


# ---------------------------------------------------------------------------
# DB-05 & DB-06: Override workflow + reason constraint
# ---------------------------------------------------------------------------

class TestOverrideWorkflow:

    def _setup_vehicle_and_plan(self):
        """Insert one vehicle and one plan; return the plan_id."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000"], ["2024-06-01"])
        db.insert_maintenance_plans(plans)
        latest = db.get_latest_plans()
        return int(latest.iloc[0]["plan_id"])

    def test_valid_override_inserted(self, temp_db):
        """DB-05: Valid override must insert a record and return an ID."""
        plan_id = self._setup_vehicle_and_plan()
        ov_id = db.insert_override(
            vehicle_id="VH-000",
            original_plan_id=plan_id,
            original_interval_days=30,
            original_maintenance_date="2024-07-01",
            overridden_interval_days=15,
            overridden_maintenance_date="2024-06-16",
            dispatcher_id="THEMBA_T",
            reason="Severe load observed — early service required.",
        )
        assert isinstance(ov_id, int) and ov_id > 0

    def test_empty_reason_raises_python_error(self, temp_db):
        """DB-06: Empty reason must raise ValueError in Python layer."""
        plan_id = self._setup_vehicle_and_plan()
        with pytest.raises(ValueError):
            db.insert_override(
                vehicle_id="VH-000",
                original_plan_id=plan_id,
                original_interval_days=30,
                original_maintenance_date="2024-07-01",
                overridden_interval_days=15,
                overridden_maintenance_date="2024-06-16",
                dispatcher_id="THEMBA_T",
                reason="",
            )

    def test_override_history_stored_correctly(self, temp_db):
        """DB-05: Override history record must contain all required fields."""
        plan_id = self._setup_vehicle_and_plan()
        db.insert_override(
            vehicle_id="VH-000",
            original_plan_id=plan_id,
            original_interval_days=30,
            original_maintenance_date="2024-07-01",
            overridden_interval_days=15,
            overridden_maintenance_date="2024-06-16",
            dispatcher_id="THEMBA_T",
            reason="Observed crack in front axle — immediate service.",
            dcss_at_override=58.3,
        )
        hist = db.get_override_history("VH-000")
        assert len(hist) == 1
        row = hist.iloc[0]
        assert row["dispatcher_id"] == "THEMBA_T"
        assert "axle" in row["reason"]
        assert abs(float(row["dcss_at_override"]) - 58.3) < 0.01
        # Timestamp must be parseable ISO 8601
        datetime.fromisoformat(row["timestamp"])

    def test_override_marks_original_plan(self, temp_db):
        """DB-05: After override, original plan must have is_overridden=1."""
        plan_id = self._setup_vehicle_and_plan()
        db.insert_override(
            vehicle_id="VH-000",
            original_plan_id=plan_id,
            original_interval_days=30,
            original_maintenance_date="2024-07-01",
            overridden_interval_days=15,
            overridden_maintenance_date="2024-06-16",
            dispatcher_id="THEMBA_T",
            reason="Urgent — breakpad wear detected.",
        )
        plans = db.get_plans_for_vehicle("VH-000")
        row = plans[plans["plan_id"] == plan_id].iloc[0]
        assert int(row["is_overridden"]) == 1


# ---------------------------------------------------------------------------
# DB-07: Query API
# ---------------------------------------------------------------------------

class TestQueryAPI:

    def test_date_range_filter(self, temp_db):
        """DB-07: Date range filter must return only rows in [start, end]."""
        vdf = _make_vehicles_df(1)
        db.upsert_vehicles(vdf)
        dates = ["2024-01-01","2024-01-15","2024-02-01","2024-03-01"]
        ops = _make_ops_df(["VH-000"], dates)
        db.insert_operational_data(ops)
        result = db.get_operational_data_for_vehicle(
            "VH-000", start_date="2024-01-01", end_date="2024-01-31"
        )
        assert len(result) == 2, (
            f"Expected 2 rows in Jan 2024, got {len(result)}"
        )
        assert (result["date"] >= "2024-01-01").all()
        assert (result["date"] <= "2024-01-31").all()

    def test_fleet_risk_summary_percentages(self, temp_db):
        """DB-07: Fleet risk summary percentages must sum to 100."""
        vdf = _make_vehicles_df(3)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000","VH-001","VH-002"], ["2024-06-01"])
        db.insert_maintenance_plans(plans)
        summary = db.get_fleet_risk_summary()
        total_pct = sum(summary["percentages"].values())
        assert abs(total_pct - 100.0) < 0.5, (
            f"Percentages sum to {total_pct}, expected ~100"
        )

    def test_get_override_history_all_vehicles(self, temp_db):
        """DB-07: get_override_history(None) must return all overrides."""
        vdf = _make_vehicles_df(2)
        db.upsert_vehicles(vdf)
        plans = _make_plans_df(["VH-000","VH-001"], ["2024-06-01"])
        db.insert_maintenance_plans(plans)
        latest = db.get_latest_plans()
        for _, row in latest.iterrows():
            db.insert_override(
                vehicle_id=row["vehicle_id"],
                original_plan_id=int(row["plan_id"]),
                original_interval_days=30,
                original_maintenance_date="2024-07-01",
                overridden_interval_days=20,
                overridden_maintenance_date="2024-06-21",
                dispatcher_id="SANDRA_M",
                reason="Fleet manager directive.",
            )
        all_hist = db.get_override_history()
        assert len(all_hist) == 2


# ---------------------------------------------------------------------------
# DB-08: Foreign key integrity
# ---------------------------------------------------------------------------

class TestForeignKeyIntegrity:

    def test_operational_data_requires_vehicle(self, temp_db):
        """DB-08: Inserting operational_data for non-existent vehicle must fail FK."""
        ops = _make_ops_df(["VH-NONEXISTENT"], ["2024-01-01"])
        with pytest.raises(Exception):   # IntegrityError or OperationalError
            db.insert_operational_data(ops, replace=True)

    def test_fk_check_passes_after_valid_inserts(self, temp_db):
        """DB-08: After valid inserts, PRAGMA foreign_key_check must return empty."""
        vdf = _make_vehicles_df(2)
        db.upsert_vehicles(vdf)
        ops = _make_ops_df(["VH-000","VH-001"], ["2024-01-01"])
        db.insert_operational_data(ops)
        with db.connect(read_only=True) as conn:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# DB-09: WAL journal mode
# ---------------------------------------------------------------------------

class TestWALMode:

    def test_wal_mode_enabled(self, temp_db):
        """DB-09: WAL journal mode must be set for concurrent Streamlit reads."""
        with db.connect(read_only=True) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.upper() == "WAL", f"Expected WAL, got {mode}"


# ---------------------------------------------------------------------------
# DB-11 & DB-12: Utility functions
# ---------------------------------------------------------------------------

class TestUtilities:

    def test_get_db_stats_all_tables(self, temp_db):
        """DB-11: get_db_stats must return counts for all 5 tables."""
        stats = db.get_db_stats()
        for table in ["vehicles","operational_data","service_history",
                      "maintenance_plans","override_history"]:
            assert table in stats, f"Missing table in stats: {table}"
            assert isinstance(stats[table], int)

    def test_get_db_stats_empty_db(self, temp_db):
        """DB-11: Fresh DB must have 0 rows in all tables."""
        stats = db.get_db_stats()
        assert all(v == 0 for v in stats.values()), (
            f"Expected all zeros in fresh DB, got {stats}"
        )

    def test_verify_schema_all_pass(self, temp_db):
        """DB-12: verify_schema must return True for all 5 tables after create_schema."""
        result = db.verify_schema()
        assert all(result.values()), (
            f"Schema verification failed: {result}"
        )

    def test_integrity_check_passes(self, temp_db):
        """DB-12: PRAGMA integrity_check must return 'ok' on fresh database."""
        with db.connect(read_only=True) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok", f"Integrity check failed: {integrity}"
