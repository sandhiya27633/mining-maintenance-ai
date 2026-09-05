"""
backend/app/routers/vehicles.py
Vehicle CRUD + analysis + disruption simulation endpoints.

Critical: every DB query filters by user_id from the JWT.
The /analyze and /simulate-disruption endpoints call the existing validated
model functions — no ML inference, just the transparent DCSS formula.
"""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.auth import get_current_user, CurrentUser
from ..core.database import get_supabase_admin
from ..engine.model_service import analyze, simulate_disruption
from ..models.schemas import (
    VehicleCreate, VehicleUpdate, VehicleResponse,
    OperationalRecordCreate, OperationalRecordResponse,
    AnalyzeRequest, AnalyzeResponse,
    SimulateDisruptionRequest, DisruptionResult,
    MessageResponse, FactorDetail,
)

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


def _admin():
    return get_supabase_admin()


def _assert_vehicle_owner(vehicle_id: UUID, user_id: str) -> dict:
    """Fetch vehicle and verify it belongs to this user. Raises 404 if not."""
    result = _admin().table("vehicles").select("*").eq("id", str(vehicle_id)).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return result.data[0]


def _build_vehicle_response(v: dict) -> VehicleResponse:
    """Enrich vehicle dict with latest plan summary."""
    # Get latest plan
    plan = _admin().table("maintenance_plans") \
        .select("dcss_score,risk_level,recommended_maintenance_date") \
        .eq("vehicle_id", v["id"]) \
        .order("plan_date", desc=True) \
        .limit(1) \
        .execute()

    days_until = None
    latest_maintenance_date = None
    if plan.data:
        p = plan.data[0]
        v["latest_dcss"] = p.get("dcss_score")
        v["latest_risk_level"] = p.get("risk_level")
        mdate_str = p.get("recommended_maintenance_date")
        if mdate_str:
            mdate = date.fromisoformat(mdate_str)
            v["latest_maintenance_date"] = mdate
            days_until = (mdate - date.today()).days
            v["days_until_service"] = days_until
    return VehicleResponse(**v)


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[VehicleResponse])
async def list_vehicles(
    fleet_id: Optional[UUID] = Query(None, description="Filter by fleet"),
    active_only: bool = Query(True),
    user: CurrentUser = Depends(get_current_user),
):
    """List vehicles for the authenticated user, optionally filtered by fleet."""
    q = _admin().table("vehicles").select("*").eq("user_id", user.user_id)
    if fleet_id:
        q = q.eq("fleet_id", str(fleet_id))
    if active_only:
        q = q.eq("active", True)
    result = q.order("created_at", desc=False).execute()
    return [_build_vehicle_response(v) for v in (result.data or [])]


@router.post("", response_model=VehicleResponse, status_code=201)
async def create_vehicle(
    body: VehicleCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a vehicle to the user's fleet."""
    # Verify fleet ownership
    fleet = _admin().table("fleets").select("id").eq("id", str(body.fleet_id)).eq("user_id", user.user_id).execute()
    if not fleet.data:
        raise HTTPException(status_code=404, detail="Fleet not found.")

    result = _admin().table("vehicles").insert({
        "fleet_id":                  str(body.fleet_id),
        "user_id":                   user.user_id,
        "vehicle_id_label":          body.vehicle_id_label,
        "vehicle_type":              body.vehicle_type,
        "model_name":                body.model_name,
        "manufacture_year":          body.manufacture_year,
        "max_load_capacity_tonnes":  body.max_load_capacity_tonnes,
        "active":                    True,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create vehicle.")
    return _build_vehicle_response(result.data[0])


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    v = _assert_vehicle_owner(vehicle_id, user.user_id)
    return _build_vehicle_response(v)


@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    body: VehicleUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    _assert_vehicle_owner(vehicle_id, user.user_id)
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update.")
    result = _admin().table("vehicles").update(updates).eq("id", str(vehicle_id)).execute()
    return _build_vehicle_response(result.data[0])


@router.delete("/{vehicle_id}", response_model=MessageResponse)
async def archive_vehicle(
    vehicle_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """Archive (soft-delete) a vehicle by setting active=False."""
    _assert_vehicle_owner(vehicle_id, user.user_id)
    _admin().table("vehicles").update({"active": False}).eq("id", str(vehicle_id)).execute()
    return MessageResponse(message=f"Vehicle {vehicle_id} archived.")


# ── Operational records ───────────────────────────────────────────────────────

@router.post("/{vehicle_id}/records", response_model=OperationalRecordResponse, status_code=201)
async def add_operational_record(
    vehicle_id: UUID,
    body: OperationalRecordCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a daily operational record for a vehicle."""
    _assert_vehicle_owner(vehicle_id, user.user_id)
    result = _admin().table("operational_records").insert({
        "vehicle_id":              str(vehicle_id),
        "user_id":                 user.user_id,
        "record_date":             body.record_date.isoformat(),
        "mileage_km":              body.mileage_km,
        "cumulative_mileage_km":   body.cumulative_mileage_km,
        "engine_hours":            body.engine_hours,
        "load_percentage":         body.load_percentage,
        "route_severity_score":    body.route_severity_score,
        "fault_count":             body.fault_count,
        "fault_severity_score":    body.fault_severity_score,
        "days_since_last_service": body.days_since_last_service,
        "scenario_tag":            body.scenario_tag,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save record.")
    return OperationalRecordResponse(**result.data[0])


@router.get("/{vehicle_id}/records", response_model=List[OperationalRecordResponse])
async def get_vehicle_records(
    vehicle_id: UUID,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(90, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """Get operational history for a vehicle."""
    _assert_vehicle_owner(vehicle_id, user.user_id)
    q = _admin().table("operational_records").select("*").eq("vehicle_id", str(vehicle_id))
    if start_date:
        q = q.gte("record_date", start_date)
    if end_date:
        q = q.lte("record_date", end_date)
    result = q.order("record_date", desc=True).limit(limit).execute()
    return [OperationalRecordResponse(**r) for r in (result.data or [])]


# ── Analysis ──────────────────────────────────────────────────────────────────

@router.post("/{vehicle_id}/analyze", response_model=AnalyzeResponse)
async def analyze_vehicle(
    vehicle_id: UUID,
    body: AnalyzeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Run DCSS analysis on provided operating conditions.
    Uses the existing validated duty-cycle model (unchanged from Phase 1–7).
    Saves the resulting plan to maintenance_plans.
    Returns: DCSS, risk level, interval, top factors.
    """
    vehicle = _assert_vehicle_owner(vehicle_id, user.user_id)

    conditions = body.model_dump()
    result = analyze(conditions, weight_config=body.weight_config)

    # Persist the plan
    _admin().table("maintenance_plans").insert({
        "vehicle_id":                  str(vehicle_id),
        "user_id":                     user.user_id,
        "plan_date":                   (body.as_of_date or date.today()).isoformat(),
        "dcss_score":                  result["dcss_score"],
        "risk_level":                  result["risk_level"],
        "recommended_interval_days":   result["recommended_interval_days"],
        "recommended_maintenance_date":result["recommended_maintenance_date"],
        "reason_text":                 result["reason"],
        "top_factors":                 result["top_factors"],
        "weight_config":               result["weight_config"],
        "is_overridden":               False,
    }).execute()

    # Return response
    return AnalyzeResponse(
        **{k: v for k, v in result.items() if k != "top_factors"},
        top_factors=[FactorDetail(**f) for f in result["top_factors"]],
    )


@router.post("/{vehicle_id}/simulate-disruption", response_model=DisruptionResult)
async def simulate_vehicle_disruption(
    vehicle_id: UUID,
    body: SimulateDisruptionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Simulate how a disruption scenario would change the DCSS and recommendation.
    Does NOT save a plan — for what-if analysis only.
    """
    _assert_vehicle_owner(vehicle_id, user.user_id)

    base_conditions = body.base.model_dump()
    deltas = {
        "mileage_km":           body.delta_mileage_km,
        "engine_hours":         body.delta_engine_hours,
        "load_percentage":      body.delta_load_percentage,
        "route_severity_score": body.delta_route_severity_score,
        "fault_count":          body.delta_fault_count,
        "fault_severity_score": body.delta_fault_severity_score,
    }

    result = simulate_disruption(
        base_conditions=base_conditions,
        deltas=deltas,
        disruption_type=body.disruption_type,
        weight_config=body.base.weight_config,
    )

    def _to_analyze_response(d: dict) -> AnalyzeResponse:
        return AnalyzeResponse(
            **{k: v for k, v in d.items() if k != "top_factors"},
            top_factors=[FactorDetail(**f) for f in d["top_factors"]],
        )

    return DisruptionResult(
        before=_to_analyze_response(result["before"]),
        after=_to_analyze_response(result["after"]),
        disruption_type=result["disruption_type"],
        dcss_delta=result["dcss_delta"],
        risk_changed=result["risk_changed"],
        interval_change_days=result["interval_change_days"],
        changes_summary=result["changes_summary"],
    )
