"""
backend/app/core/database.py
Supabase client factory.

Provides two clients:
  - supabase_client()  → uses anon key (respects RLS, for user-scoped queries)
  - supabase_admin()   → uses service_role key (bypasses RLS, for admin tasks only)

All user-facing API endpoints must use the anon client with the user's JWT,
so Supabase RLS policies are enforced at the database level.
"""
from __future__ import annotations

from functools import lru_cache
from supabase import create_client, Client
from .config import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Anon-key Supabase client (RLS enforced).
    Cached — one client per process.
    """
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache(maxsize=1)
def get_supabase_admin() -> Client:
    """
    Service-role Supabase client (bypasses RLS).
    Only for: schema migrations, demo seeding, admin tasks.
    NEVER expose this client to user-facing endpoints.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_authed_client(access_token: str) -> Client:
    """
    Returns an anon client with the user's access token set.
    All queries through this client will be scoped to the authenticated user
    by Supabase RLS policies.
    
    Usage:
        client = get_authed_client(token)
        result = client.table("vehicles").select("*").execute()
        # Only returns rows where user_id = auth.uid()
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.auth.set_session(access_token, "")
    return client
