"""
backend/app/routers/analytics.py

Fleet KPI dashboard and evaluation endpoints.

All fleet data is scoped to the authenticated user's fleet.
Evaluation results are loaded from the project's pre-generated
synthetic evaluation_results.json file.
"""

from datetime import date
from pathlib import Path
from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, Query

from ..core.auth import get_current_user, CurrentUser
from ..core.database import get_supabase_admin
from ..models.schemas import FleetKPIs, EvaluationResponse


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


def _admin():
    """
    Return the Supabase admin client.

    Backend authentication and user ownership checks are still
    performed before accessing user-scoped data.
    """
    return get_supabase_admin()


# ============================================================
# FLEET KPIs
# ============================================================

@router.get("/kpis", response_model=FleetKPIs)
async def get_fleet_kpis(
    fleet_id: Optional[UUID] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Get fleet-level KPIs for the authenticated user's dashboard.

    Only active vehicles belonging to the authenticated user
    are included.
    """

    admin = _admin()

    # --------------------------------------------------------
    # Get active vehicles
    # --------------------------------------------------------

    vehicle_query = (
        admin
        .table("vehicles")
        .select("id")
        .eq("user_id", user.user_id)
        .eq("active", True)
    )

    if fleet_id:
        vehicle_query = vehicle_query.eq(
            "fleet_id",
            str(fleet_id),
        )

    vehicles_result = vehicle_query.execute()

    vehicle_rows = vehicles_result.data or []

    vehicle_ids = [
        vehicle["id"]
        for vehicle in vehicle_rows
        if vehicle.get("id")
    ]

    total_vehicles = len(vehicle_ids)

    # --------------------------------------------------------
    # No vehicles
    # --------------------------------------------------------

    if total_vehicles == 0:
        return FleetKPIs(
            total_vehicles=0,
            active_vehicles=0,
            critical_count=0,
            high_count=0,
            normal_count=0,
            low_count=0,
            due_within_7_days=0,
            due_within_14_days=0,
            avg_dcss=None,
            overrides_total=0,
            risk_distribution={
                "CRITICAL": 0,
                "HIGH": 0,
                "NORMAL": 0,
                "LOW": 0,
            },
        )

    # --------------------------------------------------------
    # Get maintenance plans
    # --------------------------------------------------------

    plans_result = (
        admin
        .table("maintenance_plans")
        .select(
            """
            vehicle_id,
            dcss_score,
            risk_level,
            recommended_maintenance_date,
            plan_date
            """
        )
        .eq("user_id", user.user_id)
        .order("plan_date", desc=True)
        .execute()
    )

    plans_raw = plans_result.data or []

    # --------------------------------------------------------
    # Keep latest plan for each vehicle
    # --------------------------------------------------------

    latest_plans_by_vehicle = {}

    for plan in plans_raw:
        vehicle_id = plan.get("vehicle_id")

        if not vehicle_id:
            continue

        if vehicle_id not in vehicle_ids:
            continue

        if vehicle_id not in latest_plans_by_vehicle:
            latest_plans_by_vehicle[vehicle_id] = plan

    latest_plans = list(
        latest_plans_by_vehicle.values()
    )

    # --------------------------------------------------------
    # KPI calculations
    # --------------------------------------------------------

    risk_counts = {
        "CRITICAL": 0,
        "HIGH": 0,
        "NORMAL": 0,
        "LOW": 0,
    }

    due_within_7_days = 0
    due_within_14_days = 0

    dcss_sum = 0.0
    dcss_count = 0

    today = date.today()

    for plan in latest_plans:

        # ----------------------------
        # Risk
        # ----------------------------

        risk_level = (
            plan.get("risk_level")
            or "NORMAL"
        )

        risk_level = str(
            risk_level
        ).upper()

        if risk_level not in risk_counts:
            risk_level = "NORMAL"

        risk_counts[risk_level] += 1

        # ----------------------------
        # DCSS score
        # ----------------------------

        dcss_score = plan.get(
            "dcss_score"
        )

        if dcss_score is not None:
            try:
                dcss_sum += float(
                    dcss_score
                )
                dcss_count += 1
            except (
                TypeError,
                ValueError,
            ):
                pass

        # ----------------------------
        # Maintenance due date
        # ----------------------------

        maintenance_date = plan.get(
            "recommended_maintenance_date"
        )

        if maintenance_date:

            try:
                maintenance_date = date.fromisoformat(
                    str(maintenance_date)
                )

                days_until = (
                    maintenance_date - today
                ).days

                if days_until <= 7:
                    due_within_7_days += 1

                if days_until <= 14:
                    due_within_14_days += 1

            except (
                TypeError,
                ValueError,
            ):
                pass

    # --------------------------------------------------------
    # Override count
    # --------------------------------------------------------

    override_result = (
        admin
        .table("override_history")
        .select(
            "id",
            count="exact",
        )
        .eq(
            "user_id",
            user.user_id,
        )
        .execute()
    )

    overrides_total = (
        override_result.count
        or 0
    )

    # --------------------------------------------------------
    # Average DCSS
    # --------------------------------------------------------

    average_dcss = None

    if dcss_count > 0:
        average_dcss = round(
            dcss_sum / dcss_count,
            2,
        )

    # --------------------------------------------------------
    # Return KPI response
    # --------------------------------------------------------

    return FleetKPIs(
        total_vehicles=total_vehicles,
        active_vehicles=total_vehicles,

        critical_count=risk_counts[
            "CRITICAL"
        ],

        high_count=risk_counts[
            "HIGH"
        ],

        normal_count=risk_counts[
            "NORMAL"
        ],

        low_count=risk_counts[
            "LOW"
        ],

        due_within_7_days=due_within_7_days,
        due_within_14_days=due_within_14_days,

        avg_dcss=average_dcss,

        overrides_total=overrides_total,

        risk_distribution=risk_counts,
    )


# ============================================================
# EVALUATION RESULTS
# ============================================================

@router.get(
    "/evaluation",
    response_model=EvaluationResponse,
)
async def get_evaluation(
    user: CurrentUser = Depends(get_current_user),
):
    """
    Return pre-computed evaluation results.

    The evaluation compares:

        Prototype / AI maintenance
        versus
        Fixed-calendar baseline

    All values are based on synthetic simulation data.

    The evaluation file is generated by:

        python src/evaluation.py

    and stored at:

        data/processed/evaluation_results.json
    """

    # --------------------------------------------------------
    # Locate project root
    # --------------------------------------------------------

    # Current file:
    #
    # backend/
    #   app/
    #     routers/
    #       analytics.py  <-- current file
    #
    # parents[0] = routers
    # parents[1] = app
    # parents[2] = backend
    # parents[3] = mining-maintenance
    #
    # Therefore parents[3] is the project root.

    project_root = (
        Path(__file__)
        .resolve()
        .parents[3]
    )

    eval_path = (
        project_root
        / "data"
        / "processed"
        / "evaluation_results.json"
    )

    # --------------------------------------------------------
    # File does not exist
    # --------------------------------------------------------

    if not eval_path.exists():

        return EvaluationResponse(
            prototype_breakdowns=0,
            baseline_breakdowns=0,
            breakdowns_avoided=0,
            reduction_pct=0.0,

            target_reduction_pct=20.0,
            target_met=False,

            avg_prototype_interval_days=28.4,
            avg_baseline_interval_days=30.0,

            error_analysis=None,
            scenario_results=None,
            sensitivity_results=None,

            notes=[
                (
                    "Evaluation has not been run. "
                    "Run python src/evaluation.py first."
                )
            ],

            synthetic_data=True,
        )

    # --------------------------------------------------------
    # Read evaluation JSON
    # --------------------------------------------------------

    try:

        with open(
            eval_path,
            "r",
            encoding="utf-8",
        ) as file:

            evaluation_data = json.load(file)

    except (
        json.JSONDecodeError,
        OSError,
    ) as exc:

        return EvaluationResponse(
            prototype_breakdowns=0,
            baseline_breakdowns=0,
            breakdowns_avoided=0,
            reduction_pct=0.0,

            target_reduction_pct=20.0,
            target_met=False,

            avg_prototype_interval_days=28.4,
            avg_baseline_interval_days=30.0,

            error_analysis=None,
            scenario_results=None,
            sensitivity_results=None,

            notes=[
                (
                    "Evaluation results file could not be read."
                ),
                str(exc),
            ],

            synthetic_data=True,
        )

    # --------------------------------------------------------
    # Extract values safely
    # --------------------------------------------------------

    prototype_breakdowns = evaluation_data.get(
        "prototype_breakdowns",
        0,
    )

    baseline_breakdowns = evaluation_data.get(
        "baseline_breakdowns",
        0,
    )

    breakdowns_avoided = evaluation_data.get(
        "breakdowns_avoided",
        0,
    )

    reduction_pct = evaluation_data.get(
        "reduction_pct",
        0.0,
    )

    target_reduction_pct = evaluation_data.get(
        "target_reduction_pct",
        20.0,
    )

    target_met = evaluation_data.get(
        "target_met",
        False,
    )

    avg_prototype_interval_days = evaluation_data.get(
        "avg_prototype_interval_days",
        0.0,
    )

    avg_baseline_interval_days = evaluation_data.get(
        "avg_baseline_interval_days",
        30.0,
    )

    error_analysis = evaluation_data.get(
        "error_analysis"
    )

    scenario_results = evaluation_data.get(
        "scenario_results"
    )

    sensitivity_results = evaluation_data.get(
        "sensitivity_results"
    )

    notes = evaluation_data.get(
        "notes",
        [],
    )

    # --------------------------------------------------------
    # Ensure notes is a list
    # --------------------------------------------------------

    if notes is None:
        notes = []

    elif not isinstance(
        notes,
        list,
    ):
        notes = [str(notes)]

    # --------------------------------------------------------
    # Add synthetic-data note
    # --------------------------------------------------------

    synthetic_note = (
        "Evaluation results are based on "
        "synthetic simulation data."
    )

    if synthetic_note not in notes:
        notes.append(
            synthetic_note
        )

    # --------------------------------------------------------
    # Return evaluation response
    # --------------------------------------------------------

    return EvaluationResponse(

        prototype_breakdowns=int(
            prototype_breakdowns
        ),

        baseline_breakdowns=int(
            baseline_breakdowns
        ),

        breakdowns_avoided=int(
            breakdowns_avoided
        ),

        reduction_pct=float(
            reduction_pct
        ),

        target_reduction_pct=float(
            target_reduction_pct
        ),

        target_met=bool(
            target_met
        ),

        avg_prototype_interval_days=float(
            avg_prototype_interval_days
        ),

        avg_baseline_interval_days=float(
            avg_baseline_interval_days
        ),

        error_analysis=error_analysis,

        scenario_results=scenario_results,

        sensitivity_results=sensitivity_results,

        notes=notes,

        synthetic_data=True,
    )