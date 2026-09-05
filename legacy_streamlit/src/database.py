"""
database.py — SQLite Persistence Layer
=======================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data stored here is SYNTHETIC.

Implements the five-table schema from Phase 1 design (Section 7):
  1. vehicles             — fleet metadata
  2. operational_data     — daily vehicle telemetry (cleaned + feature-engineered)
  3. service_history      — maintenance service events
  4. maintenance_plans    — DCSS model recommendations per vehicle per day
  5. override_history     — dispatcher overrides with full audit trail

Design principles:
  - All DDL lives in this file. No raw SQL in other modules.
  - Business rule: override reason cannot be empty (CHECK constraint + Python guard).
  - All inserts use parameterised queries (no f-string SQL).
  - Bulk inserts use executemany with explicit chunking for memory safety.
  - Context manager protocol: database.connect() returns a context manager.
  - Thread-safety: each call gets its own connection (stateless API).
  - WAL mode enabled for concurrent reads from Streamlit.
"""

from __future__ import annotations

import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Dict, Any, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("database")

# ---------------------------------------------------------------------------
# DDL — Table Creation Statements
# Exactly matches Phase 1 design Section 7. Any deviation is a design drift.
# ---------------------------------------------------------------------------

_DDL_VEHICLES = """
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id                TEXT PRIMARY KEY,
    vehicle_type              TEXT NOT NULL CHECK(vehicle_type IN ('HAUL_TRUCK','LOADER','BULLDOZER','GRADER')),
    manufacture_year          INTEGER NOT NULL,
    vehicle_age_years         REAL    NOT NULL,
    max_load_capacity_tonnes  REAL    NOT NULL,
    odometer_at_registration  REAL    DEFAULT 0.0,
    active                    INTEGER DEFAULT 1 CHECK(active IN (0,1))
);
"""

_DDL_OPERATIONAL_DATA = """
CREATE TABLE IF NOT EXISTS operational_data (
    record_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id             TEXT    NOT NULL REFERENCES vehicles(vehicle_id),
    date                   TEXT    NOT NULL,
    mileage_km             REAL    CHECK(mileage_km >= 0),
    cumulative_mileage_km  REAL    CHECK(cumulative_mileage_km >= 0),
    engine_hours           REAL    CHECK(engine_hours >= 0),
    load_percentage        REAL    CHECK(load_percentage IS NULL OR (load_percentage >= 0 AND load_percentage <= 100)),
    route_severity_score   REAL    NOT NULL CHECK(route_severity_score >= 0 AND route_severity_score <= 10),
    route_severity_label   TEXT    NOT NULL CHECK(route_severity_label IN ('Low','Medium','High','Extreme')),
    fault_count            INTEGER DEFAULT 0 CHECK(fault_count >= 0),
    fault_severity_score   REAL    DEFAULT 0.0 CHECK(fault_severity_score >= 0 AND fault_severity_score <= 10),
    operating_stress_index REAL    NOT NULL CHECK(operating_stress_index >= 0 AND operating_stress_index <= 10),
    days_since_last_service INTEGER CHECK(days_since_last_service IS NULL OR days_since_last_service >= 0),
    last_service_mileage_km REAL,
    service_type_last      TEXT    CHECK(service_type_last IS NULL OR service_type_last IN ('MINOR','MAJOR','EMERGENCY','NONE')),
    breakdown_occurred     INTEGER DEFAULT 0 CHECK(breakdown_occurred IN (0,1)),
    breakdown_type         TEXT    CHECK(breakdown_type IS NULL OR breakdown_type IN ('ENGINE','DRIVETRAIN','BRAKE')),
    data_quality_flag      TEXT,
    scenario_tag           TEXT    DEFAULT 'NORMAL' CHECK(scenario_tag IN ('NORMAL','DISRUPTION')),
    UNIQUE(vehicle_id, date)
);
"""

_DDL_SERVICE_HISTORY = """
CREATE TABLE IF NOT EXISTS service_history (
    service_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id               TEXT    NOT NULL REFERENCES vehicles(vehicle_id),
    service_date             TEXT    NOT NULL,
    service_type             TEXT    NOT NULL CHECK(service_type IN ('MINOR','MAJOR','EMERGENCY')),
    mileage_at_service_km    REAL    NOT NULL,
    engine_hours_at_service  REAL,
    technician_notes         TEXT,
    triggered_by             TEXT    NOT NULL CHECK(triggered_by IN ('CALENDAR','DCSS_MODEL','OVERRIDE','EMERGENCY')),
    dcss_at_service          REAL
);
"""

_DDL_MAINTENANCE_PLANS = """
CREATE TABLE IF NOT EXISTS maintenance_plans (
    plan_id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id                   TEXT    NOT NULL REFERENCES vehicles(vehicle_id),
    plan_date                    TEXT    NOT NULL,
    dcss_score                   REAL    CHECK(dcss_score >= 0 AND dcss_score <= 100),
    risk_level                   TEXT    NOT NULL CHECK(risk_level IN ('LOW','NORMAL','HIGH','CRITICAL')),
    recommended_interval_days    INTEGER CHECK(recommended_interval_days >= 1),
    recommended_maintenance_date TEXT    NOT NULL,
    reason_text                  TEXT    NOT NULL,
    top_factors                  TEXT    NOT NULL,
    model_version                TEXT    DEFAULT '1.0',
    is_overridden                INTEGER DEFAULT 0 CHECK(is_overridden IN (0,1)),
    override_plan_id             INTEGER REFERENCES override_history(override_id)
);
"""

_DDL_OVERRIDE_HISTORY = """
CREATE TABLE IF NOT EXISTS override_history (
    override_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id                   TEXT    NOT NULL REFERENCES vehicles(vehicle_id),
    original_plan_id             INTEGER REFERENCES maintenance_plans(plan_id),
    original_interval_days       INTEGER NOT NULL,
    original_maintenance_date    TEXT    NOT NULL,
    overridden_interval_days     INTEGER NOT NULL,
    overridden_maintenance_date  TEXT    NOT NULL,
    dispatcher_id                TEXT    NOT NULL,
    reason                       TEXT    NOT NULL CHECK(LENGTH(TRIM(reason)) > 0),
    timestamp                    TEXT    NOT NULL,
    dcss_at_override             REAL
);
"""

# Performance indexes
_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ops_vehicle_date ON operational_data(vehicle_id, date);",
    "CREATE INDEX IF NOT EXISTS idx_ops_date         ON operational_data(date);",
    "CREATE INDEX IF NOT EXISTS idx_ops_risk         ON operational_data(scenario_tag);",
    "CREATE INDEX IF NOT EXISTS idx_plans_vehicle    ON maintenance_plans(vehicle_id, plan_date);",
    "CREATE INDEX IF NOT EXISTS idx_override_vehicle ON override_history(vehicle_id);",
    "CREATE INDEX IF NOT EXISTS idx_svc_vehicle_date ON service_history(vehicle_id, service_date);",
]

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _get_db_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or PROJECT_ROOT
    return root / cfg.DB_FILENAME


@contextmanager
def connect(
    project_root: Optional[Path] = None,
    read_only: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for a SQLite connection.

    Usage:
        with database.connect() as conn:
            cursor = conn.execute("SELECT * FROM vehicles")

    Parameters
    ----------
    project_root : Path | None
    read_only : bool
        If True opens with uri=True and ?mode=ro for safe reads.

    Yields
    ------
    sqlite3.Connection  with row_factory = sqlite3.Row (dict-like rows).
    """
    db_path = _get_db_path(project_root)
    if read_only:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

def create_schema(project_root: Optional[Path] = None) -> None:
    """
    Create all five tables and indexes. Idempotent (IF NOT EXISTS).

    Parameters
    ----------
    project_root : Path | None
    """
    with connect(project_root) as conn:
        for ddl in [
            _DDL_VEHICLES,
            _DDL_OPERATIONAL_DATA,
            _DDL_SERVICE_HISTORY,
            _DDL_MAINTENANCE_PLANS,
            _DDL_OVERRIDE_HISTORY,
        ]:
            conn.executescript(ddl)
        for idx_sql in _DDL_INDEXES:
            conn.execute(idx_sql)
    logger.info("Schema created/verified: 5 tables, %d indexes.", len(_DDL_INDEXES))


def drop_all_tables(project_root: Optional[Path] = None) -> None:
    """
    Drop all tables (used for test isolation / fresh re-runs).
    WARNING: destroys all data.
    """
    with connect(project_root) as conn:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS override_history;
            DROP TABLE IF EXISTS maintenance_plans;
            DROP TABLE IF EXISTS service_history;
            DROP TABLE IF EXISTS operational_data;
            DROP TABLE IF EXISTS vehicles;
            PRAGMA foreign_keys = ON;
        """)
    logger.warning("All tables dropped.")


# ---------------------------------------------------------------------------
# Bulk insert helpers (chunked executemany)
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 500   # rows per executemany batch


def _chunked_insert(
    conn: sqlite3.Connection,
    sql: str,
    rows: List[tuple],
    table_name: str,
) -> int:
    """Insert rows in chunks. Returns total rows inserted."""
    total = 0
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i: i + _CHUNK_SIZE]
        conn.executemany(sql, chunk)
        total += len(chunk)
    logger.info("Inserted %d rows into %s.", total, table_name)
    return total


# ---------------------------------------------------------------------------
# Table: vehicles
# ---------------------------------------------------------------------------

def upsert_vehicles(
    vehicles_df: pd.DataFrame,
    project_root: Optional[Path] = None,
) -> int:
    """
    Insert or replace all vehicle metadata records.

    Uses INSERT OR REPLACE so re-runs are idempotent.

    Parameters
    ----------
    vehicles_df : pd.DataFrame
        Must match vehicles table schema.
    project_root : Path | None

    Returns
    -------
    int  number of rows upserted
    """
    sql = """
        INSERT OR REPLACE INTO vehicles
            (vehicle_id, vehicle_type, manufacture_year, vehicle_age_years,
             max_load_capacity_tonnes, odometer_at_registration, active)
        VALUES (?,?,?,?,?,?,?)
    """
    rows = [
        (
            str(r["vehicle_id"]),
            str(r["vehicle_type"]),
            int(r["manufacture_year"]),
            float(r["vehicle_age_years"]),
            float(r["max_load_capacity_tonnes"]),
            float(r.get("odometer_at_registration", 0.0)),
            int(r.get("active", 1)),
        )
        for _, r in vehicles_df.iterrows()
    ]
    with connect(project_root) as conn:
        return _chunked_insert(conn, sql, rows, "vehicles")


# ---------------------------------------------------------------------------
# Table: operational_data
# ---------------------------------------------------------------------------

def insert_operational_data(
    ops_df: pd.DataFrame,
    project_root: Optional[Path] = None,
    replace: bool = True,
) -> int:
    """
    Bulk-insert cleaned operational records.

    Parameters
    ----------
    ops_df : pd.DataFrame  — cleaned, validated operational data
    project_root : Path | None
    replace : bool
        If True, uses INSERT OR REPLACE (idempotent re-runs).
        If False, uses INSERT OR IGNORE (skip existing).

    Returns
    -------
    int  number of rows inserted
    """
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
    sql = f"""
        {verb} INTO operational_data
            (vehicle_id, date, mileage_km, cumulative_mileage_km, engine_hours,
             load_percentage, route_severity_score, route_severity_label,
             fault_count, fault_severity_score, operating_stress_index,
             days_since_last_service, last_service_mileage_km, service_type_last,
             breakdown_occurred, breakdown_type, data_quality_flag, scenario_tag)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    def _safe(val, dtype=None):
        """Convert NaN/NaT to None for SQLite NULL."""
        if val is None:
            return None
        try:
            import math
            if isinstance(val, float) and math.isnan(val):
                return None
        except Exception:
            pass
        if dtype == "int":
            return int(val) if val is not None else None
        if dtype == "float":
            return float(val) if val is not None else None
        return val

    rows = [
        (
            str(r["vehicle_id"]),
            str(r["date"]),
            _safe(r.get("mileage_km"), "float"),
            _safe(r.get("cumulative_mileage_km"), "float"),
            _safe(r.get("engine_hours"), "float"),
            _safe(r.get("load_percentage"), "float"),
            float(r["route_severity_score"]),
            str(r["route_severity_label"]),
            _safe(r.get("fault_count"), "int") or 0,
            _safe(r.get("fault_severity_score"), "float") or 0.0,
            float(r["operating_stress_index"]),
            _safe(r.get("days_since_last_service"), "int"),
            _safe(r.get("last_service_mileage_km"), "float"),
            _safe(r.get("service_type_last")),
            int(r.get("breakdown_occurred", 0)),
            _safe(r.get("breakdown_type")),
            _safe(r.get("data_quality_flag")),
            str(r.get("scenario_tag", "NORMAL")),
        )
        for _, r in ops_df.iterrows()
    ]
    with connect(project_root) as conn:
        return _chunked_insert(conn, sql, rows, "operational_data")


# ---------------------------------------------------------------------------
# Table: maintenance_plans
# ---------------------------------------------------------------------------

def insert_maintenance_plans(
    recs_df: pd.DataFrame,
    project_root: Optional[Path] = None,
) -> int:
    """
    Insert maintenance recommendation records (one per vehicle per plan_date).

    Uses INSERT OR REPLACE for idempotent re-runs.

    Parameters
    ----------
    recs_df : pd.DataFrame  — output of maintenance_engine.apply_recommendations()
    project_root : Path | None

    Returns
    -------
    int  rows inserted
    """
    sql = """
        INSERT OR REPLACE INTO maintenance_plans
            (vehicle_id, plan_date, dcss_score, risk_level,
             recommended_interval_days, recommended_maintenance_date,
             reason_text, top_factors, model_version, is_overridden)
        VALUES (?,?,?,?,?,?,?,?,?,0)
    """
    rows = [
        (
            str(r["vehicle_id"]),
            str(r["date"]),
            float(r.get("dcss", 0.0)),
            str(r["risk_level"]),
            int(r["recommended_interval_days"]),
            str(r["recommended_maintenance_date"]),
            str(r["recommendation_reason"]),
            str(r.get("top_factors", "[]")),
            str(cfg.MODEL_VERSION),
        )
        for _, r in recs_df.iterrows()
    ]
    with connect(project_root) as conn:
        return _chunked_insert(conn, sql, rows, "maintenance_plans")


# ---------------------------------------------------------------------------
# Table: service_history (derive from operational data)
# ---------------------------------------------------------------------------

def insert_service_history_from_ops(
    recs_df: pd.DataFrame,
    project_root: Optional[Path] = None,
    triggered_by: str = "DCSS_MODEL",
) -> int:
    """
    Derive simulated service events from the recommendations DataFrame.

    A service event is generated whenever a vehicle's recommended_interval_days
    elapses from its last service date. This approximates a realistic service log.

    In Phase 5 we generate one service record per vehicle for the most recent
    recommendation (as a starter record). Full service timeline is in Phase 6/7.

    Parameters
    ----------
    recs_df : pd.DataFrame
    project_root : Path | None
    triggered_by : str  'CALENDAR' | 'DCSS_MODEL' | 'OVERRIDE' | 'EMERGENCY'

    Returns
    -------
    int  rows inserted
    """
    sql = """
        INSERT OR IGNORE INTO service_history
            (vehicle_id, service_date, service_type,
             mileage_at_service_km, engine_hours_at_service,
             technician_notes, triggered_by, dcss_at_service)
        VALUES (?,?,?,?,?,?,?,?)
    """
    # Take the latest recommendation per vehicle as the service trigger point
    latest = recs_df.sort_values("date").groupby("vehicle_id").last().reset_index()

    rows = []
    for _, r in latest.iterrows():
        risk = str(r.get("risk_level", "NORMAL"))
        svc_type = "EMERGENCY" if risk == "CRITICAL" else ("MAJOR" if risk == "HIGH" else "MINOR")
        rows.append((
            str(r["vehicle_id"]),
            str(r["recommended_maintenance_date"]),
            svc_type,
            float(r.get("cumulative_mileage_km", 0.0)),
            float(r.get("engine_hours", 0.0)) if r.get("engine_hours") is not None else None,
            f"Auto-generated service record. Risk: {risk}. DCSS: {r.get('dcss', 0.0):.2f}. "
            f"SYNTHETIC DATA.",
            triggered_by,
            float(r.get("dcss", 0.0)),
        ))

    with connect(project_root) as conn:
        return _chunked_insert(conn, sql, rows, "service_history")


# ---------------------------------------------------------------------------
# Table: override_history — dispatcher override write
# ---------------------------------------------------------------------------

def insert_override(
    vehicle_id: str,
    original_plan_id: int,
    original_interval_days: int,
    original_maintenance_date: str,
    overridden_interval_days: int,
    overridden_maintenance_date: str,
    dispatcher_id: str,
    reason: str,
    dcss_at_override: Optional[float] = None,
    project_root: Optional[Path] = None,
) -> int:
    """
    Record a dispatcher override.

    Business rules enforced here (before DB constraint):
      - reason must not be empty or whitespace-only.
      - overridden_interval_days must be in [MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS].

    Parameters
    ----------
    (see override_history schema, Section 7.5)

    Returns
    -------
    int  override_id of the new record.

    Raises
    ------
    ValueError  if business rules are violated.
    """
    # Business rule guard (Python layer, before DB constraint)
    if not reason or not reason.strip():
        raise ValueError(
            "Override reason cannot be empty. Dispatcher must provide a justification."
        )
    if not (cfg.MIN_INTERVAL_DAYS <= overridden_interval_days <= cfg.MAX_INTERVAL_DAYS):
        raise ValueError(
            f"Overridden interval {overridden_interval_days} days is outside "
            f"allowed range [{cfg.MIN_INTERVAL_DAYS}, {cfg.MAX_INTERVAL_DAYS}]."
        )

    sql = """
        INSERT INTO override_history
            (vehicle_id, original_plan_id, original_interval_days,
             original_maintenance_date, overridden_interval_days,
             overridden_maintenance_date, dispatcher_id, reason,
             timestamp, dcss_at_override)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    ts = datetime.now().isoformat(timespec="seconds")
    params = (
        vehicle_id, original_plan_id, original_interval_days,
        original_maintenance_date, overridden_interval_days,
        overridden_maintenance_date, dispatcher_id, reason.strip(),
        ts, dcss_at_override,
    )

    with connect(project_root) as conn:
        cursor = conn.execute(sql, params)
        override_id = cursor.lastrowid

        # Mark the original plan as overridden
        conn.execute(
            "UPDATE maintenance_plans SET is_overridden=1, override_plan_id=? WHERE plan_id=?",
            (override_id, original_plan_id),
        )

    logger.info(
        "Override recorded: vehicle=%s, interval %d->%d days, override_id=%d.",
        vehicle_id, original_interval_days, overridden_interval_days, override_id,
    )
    return override_id


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_vehicles(project_root: Optional[Path] = None) -> pd.DataFrame:
    """Return all vehicles as a DataFrame."""
    with connect(project_root, read_only=True) as conn:
        return pd.read_sql_query("SELECT * FROM vehicles ORDER BY vehicle_id", conn)


def get_latest_plans(project_root: Optional[Path] = None) -> pd.DataFrame:
    """
    Return the most recent maintenance plan per vehicle (non-overridden).
    Used by the Streamlit dashboard to show current fleet status.
    """
    sql = """
        SELECT mp.*
        FROM maintenance_plans mp
        INNER JOIN (
            SELECT vehicle_id, MAX(plan_date) AS max_date
            FROM maintenance_plans
            GROUP BY vehicle_id
        ) latest ON mp.vehicle_id = latest.vehicle_id
                 AND mp.plan_date = latest.max_date
        ORDER BY mp.dcss_score DESC
    """
    with connect(project_root, read_only=True) as conn:
        return pd.read_sql_query(sql, conn)


def get_plans_for_vehicle(
    vehicle_id: str,
    project_root: Optional[Path] = None,
) -> pd.DataFrame:
    """Return all maintenance plans for a specific vehicle, newest first."""
    sql = """
        SELECT * FROM maintenance_plans
        WHERE vehicle_id = ?
        ORDER BY plan_date DESC
    """
    with connect(project_root, read_only=True) as conn:
        return pd.read_sql_query(sql, conn, params=(vehicle_id,))


def get_override_history(
    vehicle_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> pd.DataFrame:
    """Return override history, optionally filtered by vehicle."""
    if vehicle_id:
        sql = "SELECT * FROM override_history WHERE vehicle_id=? ORDER BY timestamp DESC"
        params = (vehicle_id,)
    else:
        sql = "SELECT * FROM override_history ORDER BY timestamp DESC"
        params = ()
    with connect(project_root, read_only=True) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_operational_data_for_vehicle(
    vehicle_id: str,
    project_root: Optional[Path] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Return operational data for a vehicle, optionally filtered by date range."""
    where_clauses = ["vehicle_id = ?"]
    params: List[Any] = [vehicle_id]
    if start_date:
        where_clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("date <= ?")
        params.append(end_date)
    sql = f"""
        SELECT * FROM operational_data
        WHERE {' AND '.join(where_clauses)}
        ORDER BY date ASC
    """
    with connect(project_root, read_only=True) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_fleet_risk_summary(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Compute fleet-level risk summary from latest plans.
    Returns dict with counts and percentages per risk level.
    """
    sql = """
        SELECT risk_level, COUNT(*) AS count
        FROM (
            SELECT mp.risk_level
            FROM maintenance_plans mp
            INNER JOIN (
                SELECT vehicle_id, MAX(plan_date) AS max_date
                FROM maintenance_plans GROUP BY vehicle_id
            ) latest ON mp.vehicle_id=latest.vehicle_id AND mp.plan_date=latest.max_date
        )
        GROUP BY risk_level
    """
    with connect(project_root, read_only=True) as conn:
        rows = conn.execute(sql).fetchall()

    counts = {r["risk_level"]: r["count"] for r in rows}
    total = sum(counts.values())
    summary = {
        "total_vehicles": total,
        "counts": counts,
        "percentages": {k: round(100*v/total, 1) if total > 0 else 0 for k, v in counts.items()},
    }
    return summary


def get_db_stats(project_root: Optional[Path] = None) -> Dict[str, int]:
    """Return row counts for all five tables."""
    tables = ["vehicles", "operational_data", "service_history",
              "maintenance_plans", "override_history"]
    stats: Dict[str, int] = {}
    with connect(project_root, read_only=True) as conn:
        for t in tables:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()
            stats[t] = row["n"]
    return stats


def verify_schema(project_root: Optional[Path] = None) -> Dict[str, bool]:
    """
    Verify that all five tables and expected columns exist.
    Returns dict of {table_name: bool}.
    """
    expected = {
        "vehicles":          {"vehicle_id","vehicle_type","manufacture_year",
                              "vehicle_age_years","max_load_capacity_tonnes",
                              "odometer_at_registration","active"},
        "operational_data":  {"record_id","vehicle_id","date","mileage_km",
                              "engine_hours","load_percentage","route_severity_score",
                              "fault_count","breakdown_occurred","scenario_tag"},
        "service_history":   {"service_id","vehicle_id","service_date",
                              "service_type","triggered_by"},
        "maintenance_plans": {"plan_id","vehicle_id","plan_date","dcss_score",
                              "risk_level","recommended_interval_days",
                              "recommended_maintenance_date","reason_text",
                              "top_factors","is_overridden"},
        "override_history":  {"override_id","vehicle_id","dispatcher_id",
                              "reason","timestamp"},
    }
    results: Dict[str, bool] = {}
    with connect(project_root, read_only=True) as conn:
        for table, required_cols in expected.items():
            try:
                cursor = conn.execute(f"PRAGMA table_info({table})")
                actual_cols = {row["name"] for row in cursor.fetchall()}
                results[table] = required_cols.issubset(actual_cols)
            except Exception:
                results[table] = False
    return results


# ---------------------------------------------------------------------------
# Entry point (standalone — creates schema + reports)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Creating database schema...")
    create_schema(PROJECT_ROOT)

    schema_ok = verify_schema(PROJECT_ROOT)
    print("\n=== DATABASE SCHEMA VERIFICATION (SYNTHETIC DATA) ===")
    for table, ok in schema_ok.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] Table: {table}")

    stats = get_db_stats(PROJECT_ROOT)
    print("\n  Row counts (should be 0 before pipeline run):")
    for table, count in stats.items():
        print(f"    {table:<25}: {count}")
    print("database.py: schema creation complete.")
