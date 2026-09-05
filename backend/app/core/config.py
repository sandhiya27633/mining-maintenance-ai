"""
backend/app/core/config.py

Settings loaded from environment variables using Pydantic Settings.
All settings have defaults safe for development; override via backend/.env.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/.env
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Supabase ──────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # JWT secret is no longer required.
    # Backend authentication is handled through Supabase Auth.
    supabase_jwt_secret: str = ""

    # ── Database ──────────────────────────────────────────────
    # Direct DB connection is not required.
    # The application uses the Supabase Python client.
    database_url: str = ""

    # ── Application ───────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "2.0.0"
    app_title: str = "Mining Maintenance AI"

    # ── CORS ──────────────────────────────────────────────────
    cors_origins: str = (
        "http://localhost:5173,"
        "http://localhost:5174,"
        "http://localhost:3000"
    )

    # ── Demo seed ─────────────────────────────────────────────
    demo_vehicles_count: int = 10
    demo_simulation_days: int = 90
    demo_random_seed: int = 42

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a cleaned list."""
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_development(self) -> bool:
        """Return True when running in development mode."""
        return self.app_env.lower() == "development"

    def validate_supabase(self) -> None:
        """
        Validate the Supabase configuration required by the backend.

        SUPABASE_JWT_SECRET is intentionally not required because
        authentication is verified through Supabase Auth.
        """
        missing = []

        if not self.supabase_url:
            missing.append("SUPABASE_URL")

        if not self.supabase_anon_key:
            missing.append("SUPABASE_ANON_KEY")

        if not self.supabase_service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Check backend/.env and make sure the required values are present."
            )


# Singleton — import this everywhere
settings = Settings()