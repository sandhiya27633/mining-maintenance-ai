"""
backend/app/core/auth.py
FastAPI authentication via Supabase token verification.

Architecture:
  1. Frontend: supabase.auth.signInWithPassword() → receives access_token
  2. Frontend: sends Authorization: Bearer <access_token> on every request
  3. Backend: calls GET {SUPABASE_URL}/auth/v1/user with the token
  4. Supabase Auth server validates the token and returns the user object
  5. We extract user.id (= auth.uid()) as the verified identity
  6. user_id is NEVER accepted from the request body

Why this instead of local PyJWT decode:
  - Supabase's JWT secret from the dashboard is base64url-encoded; PyJWT
    needs the decoded bytes, creating a fragile mismatch.
  - The /auth/v1/user approach is the officially recommended server-side
    verification method and works regardless of JWT algorithm or key format.
  - Token expiry, rotation, and revocation are handled by Supabase.

Caching:
  - Each verified token is cached for 60 s to avoid one network call per request.
  - Cache is bounded at 500 entries; oldest 10% evicted when full.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# FastAPI security scheme — reads Authorization: Bearer <token>
_bearer = HTTPBearer(auto_error=True)

# ── Token cache ───────────────────────────────────────────────────────────────
_TOKEN_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL_SECONDS = 60
_CACHE_MAX_SIZE = 500


def _cache_get(token: str) -> Optional[dict]:
    """Return cached user data if not yet expired, else None."""
    entry = _TOKEN_CACHE.get(token)
    if entry and entry[1] > time.time():
        return entry[0]
    _TOKEN_CACHE.pop(token, None)
    return None


def _cache_set(token: str, user_data: dict) -> None:
    """Cache user data. Evicts oldest 10 % of entries when at capacity."""
    if len(_TOKEN_CACHE) >= _CACHE_MAX_SIZE:
        oldest = sorted(_TOKEN_CACHE.items(), key=lambda x: x[1][1])
        for k, _ in oldest[:_CACHE_MAX_SIZE // 10]:
            _TOKEN_CACHE.pop(k, None)
    _TOKEN_CACHE[token] = (user_data, time.time() + _CACHE_TTL_SECONDS)


# ── Core types ────────────────────────────────────────────────────────────────

@dataclass
class CurrentUser:
    """Verified identity extracted from the Supabase access token."""
    user_id: str    # = auth.uid() — used in every DB query and RLS policy
    email:   str
    role:    str = "authenticated"


# ── Token verification ────────────────────────────────────────────────────────

async def _verify_token_with_supabase(token: str) -> dict:
    """
    Verify a Supabase access token by calling the Supabase Auth REST API.

    GET {SUPABASE_URL}/auth/v1/user
        Authorization: Bearer <token>
        apikey: <anon_key>

    Returns the user dict from Supabase on success.
    Raises HTTPException 401 on invalid/expired token.
    Raises HTTPException 503 on network failure.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication service not configured. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY in backend/.env"
            ),
        )

    # Serve from cache if available
    cached = _cache_get(token)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.supabase_anon_key,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service timeout. Please retry.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Authentication service unreachable: {exc}",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed (Supabase returned {response.status_code}).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_data: dict = response.json()
    _cache_set(token, user_data)
    return user_data


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency — inject into any protected endpoint:

        @router.get("/protected")
        async def route(user: CurrentUser = Depends(get_current_user)):
            # user.user_id is verified; use it for every DB query
            ...

    Verifies the Supabase access token and returns a CurrentUser.
    user_id is extracted from the verified token — never the request body.

    Note: user_id lives in the "id" field (not "sub") of the Supabase
    /auth/v1/user response.
    """
    token = credentials.credentials
    user_data = await _verify_token_with_supabase(token)

    user_id: Optional[str] = user_data.get("id")
    email:   str = user_data.get("email") or ""
    role:    str = user_data.get("role")  or "authenticated"

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(user_id=user_id, email=email, role=role)


# Convenience alias — shorter to write in routers
AuthUser = Depends(get_current_user)
