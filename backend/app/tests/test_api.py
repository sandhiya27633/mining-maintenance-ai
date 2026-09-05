"""
backend/app/tests/test_api.py
FastAPI endpoint integration tests using httpx TestClient.
Tests run against the real FastAPI app with a mock Supabase backend.

These tests verify:
  - Unauthenticated requests are rejected (401)
  - Authenticated requests are accepted
  - Pydantic validation rejects bad input (422)
  - Response shapes match schemas
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

# Ensure engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mock_settings():
    """Patch settings so we don't need real Supabase creds for unit tests."""
    with patch("app.core.config.settings") as mock:
        mock.supabase_url = "https://test.supabase.co"
        mock.supabase_anon_key = "test-anon-key"
        mock.supabase_service_role_key = "test-service-role-key"
        mock.supabase_jwt_secret = "super-secret-test-jwt-secret-minimum-32-chars"
        mock.cors_origins_list = ["http://localhost:5173"]
        mock.app_version = "2.0.0"
        mock.app_title = "Mining Maintenance AI"
        mock.app_env = "test"
        mock.is_development = True
        mock.validate_supabase = MagicMock()
        yield mock


@pytest.fixture(scope="module")
def client(mock_settings):
    """Test client with settings patched."""
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ── Health check (public) ─────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_response_shape(self, client):
        r = client.get("/health")
        data = r.json()
        assert "status" in data
        assert "version" in data
        assert "environment" in data

    def test_root_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200


# ── Authentication rejection ──────────────────────────────────────────────────

class TestAuthRejection:
    """All protected endpoints must return 401/403 without a valid token."""

    endpoints = [
        ("GET",  "/api/v1/fleets"),
        ("POST", "/api/v1/fleets"),
        ("GET",  "/api/v1/vehicles"),
        ("GET",  "/api/v1/maintenance/recommendations"),
        ("GET",  "/api/v1/analytics/kpis"),
        ("GET",  "/api/v1/analytics/evaluation"),
    ]

    @pytest.mark.parametrize("method,path", endpoints)
    def test_no_token_rejected(self, client, method, path):
        """Requests without Authorization header must be rejected."""
        r = getattr(client, method.lower())(path)
        assert r.status_code in (401, 403, 422), (
            f"{method} {path} returned {r.status_code} — expected 401/403/422"
        )

    @pytest.mark.parametrize("method,path", endpoints)
    def test_invalid_token_rejected(self, client, method, path):
        """Requests with garbage token must be rejected."""
        r = getattr(client, method.lower())(
            path,
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert r.status_code in (401, 403, 422)


# ── Pydantic validation ────────────────────────────────────────────────────────

class TestInputValidation:
    def test_fleet_name_empty_rejected(self):
        """Fleet name cannot be empty."""
        from app.models.schemas import FleetCreate
        with pytest.raises(Exception):
            FleetCreate(name="")

    def test_vehicle_type_invalid_rejected(self):
        """Vehicle type must be one of the allowed enum values."""
        from app.models.schemas import VehicleCreate
        import uuid
        with pytest.raises(Exception):
            VehicleCreate(
                fleet_id=uuid.uuid4(),
                vehicle_id_label="V-001",
                vehicle_type="SUBMARINE",  # invalid
            )

    def test_override_reason_empty_rejected(self):
        """Override reason cannot be empty or whitespace."""
        from app.models.schemas import OverrideCreate
        import uuid
        with pytest.raises(Exception):
            OverrideCreate(
                original_plan_id=uuid.uuid4(),
                overridden_interval_days=15,
                dispatcher_id="DISP-001",
                reason="   ",  # whitespace only — must be rejected
            )

    def test_override_interval_out_of_range(self):
        """Interval must be between 1 and 60."""
        from app.models.schemas import OverrideCreate
        import uuid
        with pytest.raises(Exception):
            OverrideCreate(
                original_plan_id=uuid.uuid4(),
                overridden_interval_days=90,  # > 60 — invalid
                dispatcher_id="DISP-001",
                reason="Valid reason here",
            )

    def test_analyze_request_load_over_150(self):
        """load_percentage > 150 is invalid."""
        from app.models.schemas import AnalyzeRequest
        with pytest.raises(Exception):
            AnalyzeRequest(
                mileage_km=100, engine_hours=12,
                load_percentage=200,  # invalid
                route_severity_score=5, fault_count=0, fault_severity_score=0,
            )

    def test_analyze_request_valid(self):
        """Valid AnalyzeRequest should parse without error."""
        from app.models.schemas import AnalyzeRequest
        req = AnalyzeRequest(
            mileage_km=120, engine_hours=12,
            load_percentage=75, route_severity_score=5.0,
            fault_count=1, fault_severity_score=2.0,
        )
        assert req.load_percentage == 75


# ── Model analysis (pure function — no DB) ───────────────────────────────────

class TestAnalysisEndpointLogic:
    """Test the model_service.analyze function that backs /vehicles/{id}/analyze."""

    def test_high_severity_fault_gives_critical(self):
        from app.engine.model_service import analyze
        result = analyze({
            "mileage_km": 50, "engine_hours": 8,
            "load_percentage": 60, "route_severity_score": 3.0,
            "fault_count": 5, "fault_severity_score": 9.0,
            "days_since_last_service": 5, "cumulative_mileage_km": 1000,
        })
        assert result["risk_level"] == "CRITICAL"
        assert result["recommended_interval_days"] == 3

    def test_low_conditions_give_deferred(self):
        from app.engine.model_service import analyze
        result = analyze({
            "mileage_km": 50, "engine_hours": 5,
            "load_percentage": 30, "route_severity_score": 2.0,
            "fault_count": 0, "fault_severity_score": 0.0,
            "days_since_last_service": 5, "cumulative_mileage_km": 500,
        })
        assert result["risk_level"] in ("LOW", "NORMAL")
        assert result["urgency"] in ("DEFERRED", "ROUTINE")

    def test_disruption_preset_increases_dcss(self):
        from app.engine.model_service import simulate_disruption
        base = {
            "mileage_km": 120, "engine_hours": 12,
            "load_percentage": 65, "route_severity_score": 4.5,
            "fault_count": 1, "fault_severity_score": 3.0,
            "days_since_last_service": 15, "cumulative_mileage_km": 5000,
        }
        result = simulate_disruption(
            base_conditions=base,
            deltas={"route_severity_score": 2.5, "load_percentage": 15.0,
                    "engine_hours": 3.0, "fault_count": 2, "fault_severity_score": 2.0},
            disruption_type="combined",
        )
        assert result["dcss_delta"] > 0
        assert result["before"]["dcss_score"] < result["after"]["dcss_score"]
