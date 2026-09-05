"""
backend/app/routers/fleets.py
Fleet CRUD endpoints.

All queries are scoped to the authenticated user via:
  1. FastAPI auth dependency (get_current_user)
  2. Supabase RLS (user_id = auth.uid() policies on fleets table)
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import get_current_user, CurrentUser
from ..core.database import get_supabase_admin
from ..models.schemas import FleetCreate, FleetResponse, MessageResponse

router = APIRouter(prefix="/fleets", tags=["Fleets"])


def _admin():
    return get_supabase_admin()


@router.get("", response_model=List[FleetResponse])
async def list_fleets(user: CurrentUser = Depends(get_current_user)):
    """List all fleets belonging to the authenticated user."""
    result = _admin().table("fleets").select("*").eq("user_id", user.user_id).execute()
    fleets = result.data or []

    # Enrich with vehicle count
    enriched = []
    for fleet in fleets:
        vc = _admin().table("vehicles").select("id", count="exact").eq("fleet_id", fleet["id"]).eq("active", True).execute()
        fleet["vehicle_count"] = vc.count or 0
        enriched.append(FleetResponse(**fleet))
    return enriched


@router.post("", response_model=FleetResponse, status_code=201)
async def create_fleet(
    body: FleetCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new fleet for the authenticated user."""
    result = _admin().table("fleets").insert({
        "user_id":     user.user_id,
        "name":        body.name,
        "description": body.description,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create fleet.")

    fleet = result.data[0]
    fleet["vehicle_count"] = 0
    return FleetResponse(**fleet)


@router.get("/{fleet_id}", response_model=FleetResponse)
async def get_fleet(
    fleet_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """Get a specific fleet. Returns 404 if it doesn't belong to the user."""
    result = _admin().table("fleets").select("*").eq("id", str(fleet_id)).eq("user_id", user.user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Fleet not found.")
    fleet = result.data[0]
    vc = _admin().table("vehicles").select("id", count="exact").eq("fleet_id", str(fleet_id)).eq("active", True).execute()
    fleet["vehicle_count"] = vc.count or 0
    return FleetResponse(**fleet)


@router.delete("/{fleet_id}", response_model=MessageResponse)
async def delete_fleet(
    fleet_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a fleet (and cascade to all its vehicles/plans)."""
    # Verify ownership first
    result = _admin().table("fleets").select("id").eq("id", str(fleet_id)).eq("user_id", user.user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Fleet not found.")

    _admin().table("fleets").delete().eq("id", str(fleet_id)).execute()
    return MessageResponse(message=f"Fleet {fleet_id} deleted.")
