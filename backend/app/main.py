"""
backend/app/main.py
FastAPI application entry point.

Configures:
  - CORS (frontend origins from .env)
  - All routers
  - Startup validation (Supabase credentials)
  - Health check
  - Auto-generated OpenAPI docs at /docs
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Engine sys.path patch ────────────────────────────────────────────────────
# The 7 original engine files (feature_engineering, duty_cycle_model, etc.)
# use bare `import config as cfg`. They find each other via sys.path when run
# standalone, but not when loaded as `app.engine.*` by FastAPI.
# Adding the engine directory to sys.path restores the bare imports without
# modifying any validated engine file.
_ENGINE_DIR = Path(__file__).parent / "engine"

if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

# ────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .models.schemas import HealthResponse

# Import all routers
from .routers import auth, fleets, vehicles, maintenance, analytics, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run at startup: validate required environment variables."""
    try:
        settings.validate_supabase()

        print(
            f"✅ Mining Maintenance AI v{settings.app_version} "
            f"starting [{settings.app_env}]"
        )
        print(f"✅ Supabase: {settings.supabase_url}")
        print(f"✅ CORS origins: {settings.cors_origins_list}")

    except ValueError as e:
        print(f"⚠️  WARNING: {e}")
        print("   Server will start but authenticated endpoints will fail.")
        print("   Copy backend/.env.example → backend/.env and fill in values.")

    yield

    print("Mining Maintenance AI shutting down.")


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="""
Mining Fleet Predictive Maintenance API

Multi-user, duty-cycle-based predictive maintenance for heavy mining vehicles.
All demo data is **SYNTHETIC** — clearly labelled throughout.

## Authentication

All endpoints (except `/health`) require a valid Supabase JWT in the
`Authorization: Bearer <token>` header.

## Data Isolation

Every query is scoped to the authenticated user's data via:
- FastAPI auth dependency (JWT-derived user_id)
- Supabase Row Level Security policies (database level)

User A cannot access User B's vehicles, plans, or override history.

## Model

The duty-cycle scoring model (DCSS) is a transparent, explainable
weighted-sum formula — not a black-box ML model. All weights and thresholds
are published in this API's documentation.
""",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/v1")
app.include_router(fleets.router, prefix="/api/v1")
app.include_router(vehicles.router, prefix="/api/v1")
app.include_router(maintenance.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """
    Public health check — no authentication required.
    Used by Render/Railway deployment health probes.
    """
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.app_env,
        supabase_configured=bool(
            settings.supabase_url and settings.supabase_anon_key
        ),
    )


@app.get("/", tags=["System"])
async def root():
    return {
        "service": settings.app_title,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }