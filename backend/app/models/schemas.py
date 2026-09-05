"""
backend/app/models/schemas.py
All Pydantic v2 request and response models.

These schemas:
  - Validate API inputs (raise 422 on bad data)
  - Document the API (FastAPI auto-generates OpenAPI from these)
  - Never expose internal fields (user_id is always injected from token)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Auth / Profile
# ─────────────────────────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)


class ProfileResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Fleet
# ─────────────────────────────────────────────────────────────────────────────

class FleetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class FleetResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    vehicle_count: int = 0
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Vehicle
# ─────────────────────────────────────────────────────────────────────────────

VEHICLE_TYPES = {"HAUL_TRUCK", "LOADER", "BULLDOZER", "GRADER"}


class VehicleCreate(BaseModel):
    fleet_id: UUID
    vehicle_id_label: str = Field(..., min_length=1, max_length=50,
                                   description="User-visible ID, e.g. 'VH-001'")
    vehicle_type: str = Field(..., description="HAUL_TRUCK | LOADER | BULLDOZER | GRADER")
    model_name: Optional[str] = Field(None, max_length=100)
    manufacture_year: Optional[int] = Field(None, ge=1980, le=2030)
    max_load_capacity_tonnes: Optional[float] = Field(None, ge=0)

    @field_validator("vehicle_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v.upper() not in VEHICLE_TYPES:
            raise ValueError(f"vehicle_type must be one of {sorted(VEHICLE_TYPES)}")
        return v.upper()


class VehicleUpdate(BaseModel):
    vehicle_id_label: Optional[str] = Field(None, min_length=1, max_length=50)
    vehicle_type: Optional[str] = None
    model_name: Optional[str] = Field(None, max_length=100)
    manufacture_year: Optional[int] = Field(None, ge=1980, le=2030)
    max_load_capacity_tonnes: Optional[float] = Field(None, ge=0)
    active: Optional[bool] = None


class VehicleResponse(BaseModel):
    id: UUID
    fleet_id: UUID
    vehicle_id_label: str
    vehicle_type: str
    model_name: Optional[str]
    manufacture_year: Optional[int]
    max_load_capacity_tonnes: Optional[float]
    active: bool
    created_at: datetime
    # Latest plan summary (joined)
    latest_dcss: Optional[float] = None
    latest_risk_level: Optional[str] = None
    latest_maintenance_date: Optional[date] = None
    days_until_service: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Operational Record
# ─────────────────────────────────────────────────────────────────────────────

class OperationalRecordCreate(BaseModel):
    record_date: date
    mileage_km: float = Field(..., ge=0, le=2000,
                               description="Daily distance driven (km)")
    cumulative_mileage_km: float = Field(..., ge=0)
    engine_hours: float = Field(..., ge=0, le=24,
                                description="Engine hours on this day")
    load_percentage: float = Field(..., ge=0, le=150,
                                   description="Load as % of max capacity")
    route_severity_score: float = Field(..., ge=0, le=10,
                                        description="Terrain difficulty 0–10")
    fault_count: int = Field(0, ge=0)
    fault_severity_score: float = Field(0.0, ge=0, le=10)
    days_since_last_service: Optional[int] = Field(None, ge=0)
    scenario_tag: str = Field("NORMAL", pattern="^(NORMAL|DISRUPTION|MAINTENANCE)$")


class OperationalRecordResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    record_date: date
    mileage_km: float
    engine_hours: float
    load_percentage: float
    route_severity_score: float
    fault_count: int
    fault_severity_score: float
    days_since_last_service: Optional[int]
    scenario_tag: str
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Analysis — DCSS calculation
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Input conditions for on-demand DCSS calculation."""
    mileage_km: float = Field(..., ge=0, le=2000)
    engine_hours: float = Field(..., ge=0, le=24)
    load_percentage: float = Field(..., ge=0, le=150)
    route_severity_score: float = Field(..., ge=0, le=10)
    fault_count: int = Field(0, ge=0)
    fault_severity_score: float = Field(0.0, ge=0, le=10)
    days_since_last_service: Optional[int] = Field(None, ge=0)
    cumulative_mileage_km: float = Field(0.0, ge=0)
    weight_config: str = Field("Default",
                                pattern="^(Default|Fault-Heavy|Load-Heavy)$")
    as_of_date: Optional[date] = None


class FactorDetail(BaseModel):
    factor: str
    sub_score: float
    contribution: float


class AnalyzeResponse(BaseModel):
    dcss_score: float
    risk_level: str
    recommended_interval_days: int
    recommended_maintenance_date: str
    urgency: str
    reason: str
    top_factors: List[FactorDetail]
    weight_config: str
    sub_scores: Dict[str, float]
    baseline_interval_days: int = 30


# ─────────────────────────────────────────────────────────────────────────────
# Disruption Simulation
# ─────────────────────────────────────────────────────────────────────────────

DISRUPTION_PRESETS = {
    "heavy_rain":        {"route_severity_score": +2.5, "load_percentage": +5.0},
    "steep_route":       {"route_severity_score": +3.0},
    "extreme_load":      {"load_percentage": +25.0},
    "extended_hours":    {"engine_hours": +3.0},
    "fault_spike":       {"fault_count": +5, "fault_severity_score": +3.0},
    "combined":          {"route_severity_score": +2.5, "load_percentage": +15.0,
                          "engine_hours": +3.0, "fault_count": +3, "fault_severity_score": +2.0},
}


class SimulateDisruptionRequest(BaseModel):
    """Base conditions + disruption type or custom deltas."""
    base: AnalyzeRequest
    disruption_type: Optional[str] = Field(
        None,
        description="Preset: heavy_rain | steep_route | extreme_load | extended_hours | fault_spike | combined"
    )
    # Or provide custom deltas:
    delta_mileage_km: float = 0.0
    delta_engine_hours: float = 0.0
    delta_load_percentage: float = 0.0
    delta_route_severity_score: float = 0.0
    delta_fault_count: int = 0
    delta_fault_severity_score: float = 0.0

    @model_validator(mode="after")
    def apply_preset(self) -> "SimulateDisruptionRequest":
        if self.disruption_type:
            preset = DISRUPTION_PRESETS.get(self.disruption_type, {})
            for key, delta in preset.items():
                attr = f"delta_{key}"
                current = getattr(self, attr, 0)
                object.__setattr__(self, attr, current + delta)
        return self


class DisruptionResult(BaseModel):
    before: AnalyzeResponse
    after: AnalyzeResponse
    disruption_type: Optional[str]
    dcss_delta: float
    risk_changed: bool
    interval_change_days: int
    changes_summary: List[str]


# ─────────────────────────────────────────────────────────────────────────────
# Maintenance Plans
# ─────────────────────────────────────────────────────────────────────────────

class MaintenancePlanResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    vehicle_id_label: str
    plan_date: date
    dcss_score: float
    risk_level: str
    recommended_interval_days: int
    recommended_maintenance_date: date
    reason_text: str
    top_factors: List[FactorDetail]
    weight_config: str
    is_overridden: bool
    days_until_service: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher Override
# ─────────────────────────────────────────────────────────────────────────────

class OverrideCreate(BaseModel):
    original_plan_id: UUID
    overridden_interval_days: int = Field(
        ..., ge=1, le=60,
        description=f"New interval. Must be between 1 and 60 days."
    )
    dispatcher_id: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=5, max_length=1000,
                        description="Mandatory justification. Cannot be empty.")

    @field_validator("reason")
    @classmethod
    def reason_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Override reason cannot be empty or whitespace-only.")
        return v.strip()


class OverrideResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    vehicle_id_label: str
    original_plan_id: UUID
    original_interval_days: int
    original_maintenance_date: date
    overridden_interval_days: int
    overridden_maintenance_date: date
    dispatcher_id: str
    reason: str
    dcss_at_override: Optional[float]
    timestamp: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Analytics / Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class FleetKPIs(BaseModel):
    total_vehicles: int
    active_vehicles: int
    critical_count: int
    high_count: int
    normal_count: int
    low_count: int
    due_within_7_days: int
    due_within_14_days: int
    avg_dcss: Optional[float]
    overrides_total: int
    risk_distribution: Dict[str, int]


class EvaluationResponse(BaseModel):
    prototype_breakdowns: int
    baseline_breakdowns: int
    breakdowns_avoided: int
    reduction_pct: float
    target_reduction_pct: float
    target_met: bool
    avg_prototype_interval_days: float
    avg_baseline_interval_days: float
    error_analysis: Optional[Dict[str, Any]]
    scenario_results: Optional[List[Dict[str, Any]]]
    sensitivity_results: Optional[List[Dict[str, Any]]]
    notes: List[str]
    synthetic_data: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# CSV Upload
# ─────────────────────────────────────────────────────────────────────────────

class UploadValidationResult(BaseModel):
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    missing_columns: List[str]
    detected_columns: List[str]
    sample_issues: List[str]
    ready_to_import: bool


class UploadImportResult(BaseModel):
    imported_rows: int
    skipped_rows: int
    vehicle_id: UUID
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Generic responses
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    supabase_configured: bool
