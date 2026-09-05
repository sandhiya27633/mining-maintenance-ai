"""
backend/app/routers/upload.py
CSV upload endpoint: validate, preview, then import operational data.

Uploaded data is always associated with the authenticated user.
Demo seeding is idempotent: existing vehicle/date records are skipped
instead of causing duplicate-key errors.
"""

import io
from datetime import date, timedelta
from typing import List
from uuid import UUID

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..core.auth import get_current_user, CurrentUser
from ..core.database import get_supabase_admin
from ..models.schemas import UploadValidationResult, UploadImportResult

router = APIRouter(prefix="/upload", tags=["Data Upload"])


# ── CSV schema ────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {
    "record_date",
    "mileage_km",
    "engine_hours",
    "load_percentage",
    "route_severity_score",
    "fault_count",
    "fault_severity_score",
}

OPTIONAL_COLUMNS = {
    "cumulative_mileage_km",
    "days_since_last_service",
    "scenario_tag",
}


def _admin():
    return get_supabase_admin()


# ── CSV validation ────────────────────────────────────────────────────────────

@router.post("/validate", response_model=UploadValidationResult)
async def validate_csv(
    file: UploadFile = File(..., description="Operational data CSV"),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Validate an uploaded CSV without importing it.
    Returns detected columns, missing columns, row counts, and sample issues.
    """

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=422,
            detail="Only .csv files are accepted.",
        )

    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size: 5 MB.",
        )

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse CSV: {e}",
        )

    # Normalize column names
    df.columns = df.columns.astype(str).str.strip().str.lower()

    detected = set(df.columns)

    missing = sorted(
        REQUIRED_COLUMNS - detected
    )

    issues = []

    valid_rows = len(df)
    invalid_rows = 0

    if not missing:

        # ── Numeric validation ────────────────────────────────────────────────

        numeric_columns = [
            "mileage_km",
            "engine_hours",
            "load_percentage",
            "route_severity_score",
            "fault_count",
            "fault_severity_score",
        ]

        for col in numeric_columns:
            if col in df.columns:
                numeric_values = pd.to_numeric(
                    df[col],
                    errors="coerce",
                )

                bad = numeric_values.isna().sum()

                if bad > 0:
                    issues.append(
                        f"'{col}': {bad} missing/invalid values "
                        "(will be imputed or defaulted)."
                    )

        # ── Range checks ──────────────────────────────────────────────────────

        if "load_percentage" in df.columns:
            values = pd.to_numeric(
                df["load_percentage"],
                errors="coerce",
            )

            out_range = ((values < 0) | (values > 150)).sum()

            if out_range > 0:
                issues.append(
                    f"'load_percentage': {out_range} values outside "
                    "0–150% range (will be clamped)."
                )

        if "engine_hours" in df.columns:
            values = pd.to_numeric(
                df["engine_hours"],
                errors="coerce",
            )

            out_range = ((values < 0) | (values > 24)).sum()

            if out_range > 0:
                issues.append(
                    f"'engine_hours': {out_range} values outside "
                    "0–24h range (will be clamped)."
                )

        # ── Duplicate date check ──────────────────────────────────────────────

        if "record_date" in df.columns:
            duplicate_count = df.duplicated(
                subset=["record_date"]
            ).sum()

            if duplicate_count > 0:
                invalid_rows = duplicate_count

                issues.append(
                    f"{duplicate_count} duplicate record_date entries "
                    "(duplicates will be skipped)."
                )

    return UploadValidationResult(
        filename=file.filename,
        total_rows=len(df),
        valid_rows=max(0, valid_rows - invalid_rows),
        invalid_rows=invalid_rows,
        missing_columns=missing,
        detected_columns=sorted(detected),
        sample_issues=issues[:10],
        ready_to_import=(len(missing) == 0),
    )


# ── CSV import ────────────────────────────────────────────────────────────────

@router.post("/import", response_model=UploadImportResult)
async def import_csv(
    vehicle_id: UUID = Form(...),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Import validated CSV data for a specific vehicle.

    Existing vehicle/date records are skipped so repeated imports
    do not create duplicate records.
    """

    # Verify vehicle ownership
    veh = (
        _admin()
        .table("vehicles")
        .select("id")
        .eq("id", str(vehicle_id))
        .eq("user_id", user.user_id)
        .execute()
    )

    if not veh.data:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found.",
        )

    content = await file.read()

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse CSV: {e}",
        )

    # Normalize column names
    df.columns = df.columns.astype(str).str.strip().str.lower()

    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns: {sorted(missing)}",
        )

    # Deduplicate uploaded CSV itself
    df = df.drop_duplicates(
        subset=["record_date"],
        keep="first",
    )

    # Clamp ranges
    if "load_percentage" in df.columns:
        df["load_percentage"] = (
            pd.to_numeric(
                df["load_percentage"],
                errors="coerce",
            )
            .fillna(70)
            .clip(0, 150)
        )

    if "engine_hours" in df.columns:
        df["engine_hours"] = (
            pd.to_numeric(
                df["engine_hours"],
                errors="coerce",
            )
            .fillna(0)
            .clip(0, 24)
        )

    # Fill optional columns
    if "cumulative_mileage_km" not in df.columns:
        df["cumulative_mileage_km"] = df["mileage_km"]

    if "days_since_last_service" not in df.columns:
        df["days_since_last_service"] = None

    if "scenario_tag" not in df.columns:
        df["scenario_tag"] = "NORMAL"

    # Remove rows with essential missing values
    df = df.dropna(
        subset=[
            "record_date",
            "mileage_km",
        ]
    )

    # ── Get existing dates for this vehicle ───────────────────────────────────

    existing_result = (
        _admin()
        .table("operational_records")
        .select("record_date")
        .eq("vehicle_id", str(vehicle_id))
        .eq("user_id", user.user_id)
        .execute()
    )

    existing_dates = {
        str(row["record_date"])
        for row in (existing_result.data or [])
    }

    imported = 0
    skipped = 0

    # ── Insert only records that don't already exist ──────────────────────────

    records = []

    for _, row in df.iterrows():

        record_date = str(row["record_date"])

        if record_date in existing_dates:
            skipped += 1
            continue

        records.append({
            "vehicle_id": str(vehicle_id),
            "user_id": user.user_id,
            "record_date": record_date,
            "mileage_km": float(
                pd.to_numeric(
                    row.get("mileage_km", 0),
                    errors="coerce",
                ) or 0
            ),
            "cumulative_mileage_km": float(
                pd.to_numeric(
                    row.get("cumulative_mileage_km", 0),
                    errors="coerce",
                ) or 0
            ),
            "engine_hours": float(
                pd.to_numeric(
                    row.get("engine_hours", 0),
                    errors="coerce",
                ) or 0
            ),
            "load_percentage": float(
                pd.to_numeric(
                    row.get("load_percentage", 70),
                    errors="coerce",
                ) or 70
            ),
            "route_severity_score": float(
                pd.to_numeric(
                    row.get("route_severity_score", 5),
                    errors="coerce",
                ) or 5
            ),
            "fault_count": int(
                pd.to_numeric(
                    row.get("fault_count", 0),
                    errors="coerce",
                ) or 0
            ),
            "fault_severity_score": float(
                pd.to_numeric(
                    row.get("fault_severity_score", 0),
                    errors="coerce",
                ) or 0
            ),
            "days_since_last_service": (
                int(row["days_since_last_service"])
                if pd.notna(row.get("days_since_last_service"))
                else None
            ),
            "scenario_tag": str(
                row.get("scenario_tag", "NORMAL")
            ),
        })

    # Insert as one batch
    if records:
        try:
            result = (
                _admin()
                .table("operational_records")
                .insert(records)
                .execute()
            )

            imported = len(result.data or [])

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Import failed: {e}",
            )

    return UploadImportResult(
        imported_rows=imported,
        skipped_rows=skipped,
        vehicle_id=vehicle_id,
        message=(
            f"Import complete: {imported} new rows imported, "
            f"{skipped} existing/duplicate rows skipped."
        ),
    )


# ── Demo seed ─────────────────────────────────────────────────────────────────

@router.post("/demo-seed", response_model=UploadImportResult)
async def seed_demo_data(
    vehicle_id: UUID = Form(...),
    days: int = Form(90, ge=30, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Generate synthetic demo operational data for a vehicle.

    IMPORTANT:
    This endpoint is idempotent.

    If demo data for a vehicle/date already exists, that date is skipped.
    Therefore the button can safely be clicked multiple times without
    producing duplicate-key errors or 409 conflicts.
    """

    from ..core.config import settings

    # ── Verify vehicle ownership ───────────────────────────────────────────────

    veh = (
        _admin()
        .table("vehicles")
        .select("id, vehicle_type")
        .eq("id", str(vehicle_id))
        .eq("user_id", user.user_id)
        .execute()
    )

    if not veh.data:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found.",
        )

    vehicle_type = veh.data[0]["vehicle_type"]

    rng = np.random.default_rng(
        settings.demo_random_seed
    )

    start = date.today() - timedelta(days=days)

    disruption_start = max(
        0,
        days - 30,
    )

    # ── Find existing operational dates ───────────────────────────────────────

    try:
        existing_result = (
            _admin()
            .table("operational_records")
            .select("record_date")
            .eq("vehicle_id", str(vehicle_id))
            .eq("user_id", user.user_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not check existing operational data: {e}",
        )

    existing_dates = {
        str(row["record_date"])
        for row in (existing_result.data or [])
    }

    records = []
    skipped = 0

    # ── Generate synthetic records ────────────────────────────────────────────

    last_service_days = 0

    for d in range(days):

        current_date = start + timedelta(days=d)
        current_date_str = current_date.isoformat()

        # Existing record → skip
        if current_date_str in existing_dates:
            skipped += 1

            # Keep service-cycle progression consistent
            last_service_days += 1

            if last_service_days >= 30:
                last_service_days = 0

            continue

        is_disruption = d >= disruption_start

        # Vehicle-specific operating profile
        if vehicle_type == "HAUL_TRUCK":
            mileage_mean = 120
            engine_hours_mean = 14
        else:
            mileage_mean = 90
            engine_hours_mean = 10

        # Synthetic operating conditions
        mileage = float(
            rng.normal(
                mileage_mean,
                20,
            )
        )

        engine_hours = float(
            rng.normal(
                engine_hours_mean,
                2,
            )
        )

        # Disruption increases operating severity
        load_pct = float(
            rng.normal(
                80 if is_disruption else 65,
                10,
            )
        )

        route_sev = float(
            rng.normal(
                7.0 if is_disruption else 4.5,
                1.0,
            )
        )

        fault_count = int(
            rng.poisson(
                2 if is_disruption else 0.5
            )
        )

        fault_sev = float(
            rng.uniform(3, 8)
            if fault_count > 0
            else 0
        )

        records.append({
            "vehicle_id": str(vehicle_id),
            "user_id": user.user_id,
            "record_date": current_date_str,

            "mileage_km": max(
                0,
                mileage,
            ),

            "cumulative_mileage_km": max(
                0,
                mileage,
            ) * (d + 1),

            "engine_hours": min(
                24,
                max(0, engine_hours),
            ),

            "load_percentage": min(
                120,
                max(0, load_pct),
            ),

            "route_severity_score": min(
                10,
                max(0, route_sev),
            ),

            "fault_count": fault_count,

            "fault_severity_score": min(
                10,
                fault_sev,
            ),

            "days_since_last_service": last_service_days,

            "scenario_tag": (
                "DISRUPTION"
                if is_disruption
                else "NORMAL"
            ),
        })

        last_service_days += 1

        # Synthetic service cycle
        if last_service_days >= 30:
            last_service_days = 0

    # ── Insert only NEW records ────────────────────────────────────────────────

    imported = 0

    if records:

        try:
            result = (
                _admin()
                .table("operational_records")
                .insert(records)
                .execute()
            )

            imported = len(
                result.data or []
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Demo seed failed while saving "
                    f"new records: {e}"
                ),
            )

    # ── Response ───────────────────────────────────────────────────────────────

    if imported == 0 and skipped > 0:
        message = (
            f"Demo data already exists for this vehicle. "
            f"{skipped} existing days were skipped. "
            f"No duplicates were created. "
            f"ALL DATA IS SYNTHETIC."
        )
    else:
        message = (
            f"Demo data seeded successfully: "
            f"{imported} new days added, "
            f"{skipped} existing days skipped. "
            f"Final 30 days are DISRUPTION scenario. "
            f"ALL DATA IS SYNTHETIC."
        )

    return UploadImportResult(
        imported_rows=imported,
        skipped_rows=skipped,
        vehicle_id=vehicle_id,
        message=message,
    )