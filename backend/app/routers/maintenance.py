"""
backend/app/routers/maintenance.py

Maintenance plans, dispatcher override, and history endpoints.

Security:
- Every endpoint requires a verified Supabase user.
- All database queries are additionally filtered by user_id.
- Dispatcher overrides require a reason.
- Override history is persisted for auditability.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.auth import CurrentUser, get_current_user
from ..core.database import get_supabase_admin
from ..engine.maintenance_engine import compute_maintenance_date
from ..engine.model_config import MAX_INTERVAL_DAYS, MIN_INTERVAL_DAYS
from ..models.schemas import (
    FactorDetail,
    MaintenancePlanResponse,
    MessageResponse,
    OverrideCreate,
    OverrideResponse,
)


router = APIRouter(
    prefix="/maintenance",
    tags=["Maintenance"],
)


def _admin():
    """
    Return the Supabase service-role client.

    The service-role client bypasses RLS, so every user-facing
    query MUST explicitly filter by the authenticated user's ID.
    """
    return get_supabase_admin()


def _plan_to_response(
    plan: dict,
    vehicle_label: str = "",
) -> MaintenancePlanResponse:
    """
    Convert a database maintenance-plan row into the API response model.
    """

    factors_raw = plan.get("top_factors") or []

    if isinstance(factors_raw, str):
        import json

        try:
            factors_raw = json.loads(factors_raw)
        except json.JSONDecodeError:
            factors_raw = []

    maintenance_date = plan.get("recommended_maintenance_date")

    days_until_service = None

    if maintenance_date:
        try:
            days_until_service = (
                date.fromisoformat(str(maintenance_date)) - date.today()
            ).days
        except ValueError:
            days_until_service = None

    return MaintenancePlanResponse(
        id=plan["id"],
        vehicle_id=plan["vehicle_id"],
        vehicle_id_label=(
            vehicle_label
            or plan.get("vehicle_id_label", "")
        ),
        plan_date=plan["plan_date"],
        dcss_score=plan["dcss_score"],
        risk_level=plan["risk_level"],
        recommended_interval_days=plan[
            "recommended_interval_days"
        ],
        recommended_maintenance_date=maintenance_date,
        reason_text=plan.get("reason_text", ""),
        top_factors=[
            FactorDetail(**factor)
            for factor in factors_raw
        ],
        weight_config=plan.get(
            "weight_config",
            "Default",
        ),
        is_overridden=plan.get(
            "is_overridden",
            False,
        ),
        days_until_service=days_until_service,
    )


# ============================================================================
# LATEST MAINTENANCE RECOMMENDATIONS
# ============================================================================


@router.get(
    "/recommendations",
    response_model=List[MaintenancePlanResponse],
)
async def get_recommendations(
    risk_level: Optional[str] = Query(
        None,
        pattern="^(LOW|NORMAL|HIGH|CRITICAL)$",
    ),
    due_within_days: Optional[int] = Query(
        None,
        ge=1,
        le=60,
    ),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Get the latest maintenance plan for each vehicle
    belonging to the authenticated user.

    Optional filters:
    - risk_level
    - due_within_days
    """

    result = (
        _admin()
        .table("maintenance_plans")
        .select(
            "*, vehicles(vehicle_id_label)"
        )
        .eq("user_id", user.user_id)
        .order(
            "plan_date",
            desc=True,
        )
        .execute()
    )

    plans = result.data or []

    # Keep only the newest plan for each vehicle.
    seen_vehicle_ids = set()
    latest_plans = []

    for plan in plans:
        vehicle_id = plan["vehicle_id"]

        if vehicle_id in seen_vehicle_ids:
            continue

        seen_vehicle_ids.add(vehicle_id)
        latest_plans.append(plan)

    filtered_plans = []

    for plan in latest_plans:

        # Risk-level filter
        if (
            risk_level
            and plan.get("risk_level") != risk_level
        ):
            continue

        # Upcoming-maintenance filter
        if due_within_days is not None:

            maintenance_date = (
                plan.get(
                    "recommended_maintenance_date"
                )
            )

            if maintenance_date:

                try:
                    days_until = (
                        date.fromisoformat(
                            str(maintenance_date)
                        )
                        - date.today()
                    ).days

                    if days_until > due_within_days:
                        continue

                except ValueError:
                    pass

        vehicle_data = plan.get("vehicles") or {}

        vehicle_label = vehicle_data.get(
            "vehicle_id_label",
            "",
        )

        filtered_plans.append(
            _plan_to_response(
                plan,
                vehicle_label,
            )
        )

    return filtered_plans


# ============================================================================
# MAINTENANCE PLAN HISTORY
# ============================================================================


@router.get(
    "/history",
    response_model=List[MaintenancePlanResponse],
)
async def get_plan_history(
    vehicle_id: Optional[UUID] = Query(None),
    limit: int = Query(
        50,
        ge=1,
        le=200,
    ),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Get maintenance-plan history for the authenticated user.

    Optionally filter by vehicle.
    """

    query = (
        _admin()
        .table("maintenance_plans")
        .select(
            "*, vehicles(vehicle_id_label)"
        )
        .eq("user_id", user.user_id)
    )

    if vehicle_id:
        query = query.eq(
            "vehicle_id",
            str(vehicle_id),
        )

    result = (
        query
        .order(
            "plan_date",
            desc=True,
        )
        .limit(limit)
        .execute()
    )

    plans = result.data or []

    responses = []

    for plan in plans:

        vehicle_data = plan.get("vehicles") or {}

        vehicle_label = vehicle_data.get(
            "vehicle_id_label",
            "",
        )

        responses.append(
            _plan_to_response(
                plan,
                vehicle_label,
            )
        )

    return responses


# ============================================================================
# DISPATCHER OVERRIDE
# ============================================================================


@router.post(
    "/{vehicle_id}/override",
    response_model=OverrideResponse,
    status_code=201,
)
async def submit_override(
    vehicle_id: UUID,
    body: OverrideCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Submit a dispatcher override.

    Steps:
    1. Verify vehicle ownership.
    2. Verify maintenance-plan ownership.
    3. Validate overridden interval.
    4. Calculate new maintenance date.
    5. Save override history.
    6. Mark original plan as overridden.
    """

    # ----------------------------------------------------------------------
    # 1. Verify vehicle ownership
    # ----------------------------------------------------------------------

    vehicle_result = (
        _admin()
        .table("vehicles")
        .select(
            "id, vehicle_id_label"
        )
        .eq(
            "id",
            str(vehicle_id),
        )
        .eq(
            "user_id",
            user.user_id,
        )
        .execute()
    )

    if not vehicle_result.data:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found.",
        )

    vehicle = vehicle_result.data[0]

    vehicle_label = vehicle.get(
        "vehicle_id_label",
        "",
    )

    # ----------------------------------------------------------------------
    # 2. Verify maintenance-plan ownership
    # ----------------------------------------------------------------------

    plan_result = (
        _admin()
        .table("maintenance_plans")
        .select("*")
        .eq(
            "id",
            str(body.original_plan_id),
        )
        .eq(
            "user_id",
            user.user_id,
        )
        .execute()
    )

    if not plan_result.data:
        raise HTTPException(
            status_code=404,
            detail="Maintenance plan not found.",
        )

    original_plan = plan_result.data[0]

    # ----------------------------------------------------------------------
    # 3. Validate interval
    # ----------------------------------------------------------------------

    overridden_interval = (
        body.overridden_interval_days
    )

    if not (
        MIN_INTERVAL_DAYS
        <= overridden_interval
        <= MAX_INTERVAL_DAYS
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Interval {overridden_interval} "
                f"outside allowed range "
                f"[{MIN_INTERVAL_DAYS}, "
                f"{MAX_INTERVAL_DAYS}]."
            ),
        )

    # ----------------------------------------------------------------------
    # 4. Calculate new maintenance date
    # ----------------------------------------------------------------------

    new_maintenance_date = compute_maintenance_date(
        str(
            original_plan["plan_date"]
        ),
        overridden_interval,
    )

    # ----------------------------------------------------------------------
    # 5. Save override history
    # ----------------------------------------------------------------------

    override_payload = {
        "vehicle_id": str(vehicle_id),
        "user_id": user.user_id,
        "original_plan_id": str(
            body.original_plan_id
        ),
        "original_interval_days": (
            original_plan[
                "recommended_interval_days"
            ]
        ),
        "original_maintenance_date": (
            original_plan[
                "recommended_maintenance_date"
            ]
        ),
        "overridden_interval_days": (
            overridden_interval
        ),
        "overridden_maintenance_date": (
            new_maintenance_date
        ),
        "dispatcher_id": body.dispatcher_id,
        "reason": body.reason,
        "dcss_at_override": (
            original_plan.get(
                "dcss_score"
            )
        ),
    }

    override_result = (
        _admin()
        .table("override_history")
        .insert(override_payload)
        .execute()
    )

    if not override_result.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to save override.",
        )

    # ----------------------------------------------------------------------
    # 6. Mark original maintenance plan as overridden
    # ----------------------------------------------------------------------

    (
        _admin()
        .table("maintenance_plans")
        .update(
            {
                "is_overridden": True
            }
        )
        .eq(
            "id",
            str(body.original_plan_id),
        )
        .eq(
            "user_id",
            user.user_id,
        )
        .execute()
    )

    override = override_result.data[0]

    return OverrideResponse(
        id=override["id"],
        vehicle_id=vehicle_id,
        vehicle_id_label=vehicle_label,
        original_plan_id=body.original_plan_id,
        original_interval_days=(
            original_plan[
                "recommended_interval_days"
            ]
        ),
        original_maintenance_date=(
            date.fromisoformat(
                str(
                    original_plan[
                        "recommended_maintenance_date"
                    ]
                )
            )
        ),
        overridden_interval_days=(
            overridden_interval
        ),
        overridden_maintenance_date=(
            date.fromisoformat(
                str(new_maintenance_date)
            )
        ),
        dispatcher_id=body.dispatcher_id,
        reason=body.reason,
        dcss_at_override=(
            original_plan.get(
                "dcss_score"
            )
        ),
        timestamp=override["timestamp"],
    )


# ============================================================================
# OVERRIDE HISTORY
# ============================================================================


@router.get(
    "/overrides",
    response_model=List[OverrideResponse],
)
async def get_override_history(
    vehicle_id: Optional[UUID] = Query(None),
    limit: int = Query(
        50,
        ge=1,
        le=200,
    ),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Get dispatcher override history for
    the authenticated user's workspace.
    """

    query = (
        _admin()
        .table("override_history")
        .select(
            "*, vehicles(vehicle_id_label)"
        )
        .eq(
            "user_id",
            user.user_id,
        )
    )

    if vehicle_id:
        query = query.eq(
            "vehicle_id",
            str(vehicle_id),
        )

    result = (
        query
        .order(
            "timestamp",
            desc=True,
        )
        .limit(limit)
        .execute()
    )

    overrides = []

    for override in result.data or []:

        vehicle_data = (
            override.get("vehicles")
            or {}
        )

        vehicle_label = vehicle_data.get(
            "vehicle_id_label",
            "",
        )

        overrides.append(
            OverrideResponse(
                id=override["id"],
                vehicle_id=override["vehicle_id"],
                vehicle_id_label=vehicle_label,
                original_plan_id=(
                    override[
                        "original_plan_id"
                    ]
                ),
                original_interval_days=(
                    override[
                        "original_interval_days"
                    ]
                ),
                original_maintenance_date=(
                    date.fromisoformat(
                        str(
                            override[
                                "original_maintenance_date"
                            ]
                        )
                    )
                ),
                overridden_interval_days=(
                    override[
                        "overridden_interval_days"
                    ]
                ),
                overridden_maintenance_date=(
                    date.fromisoformat(
                        str(
                            override[
                                "overridden_maintenance_date"
                            ]
                        )
                    )
                ),
                dispatcher_id=override[
                    "dispatcher_id"
                ],
                reason=override["reason"],
                dcss_at_override=override.get(
                    "dcss_at_override"
                ),
                timestamp=override[
                    "timestamp"
                ],
            )
        )

    return overrides