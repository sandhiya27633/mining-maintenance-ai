"""
backend/app/routers/auth.py
Profile management endpoints.

Supabase handles the actual signup/login (client-side using supabase-js).
After signup, the frontend calls POST /auth/profile to create the DB profile.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from ..core.auth import get_current_user, CurrentUser
from ..core.database import get_authed_client
from ..models.schemas import ProfileCreate, ProfileResponse, MessageResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/profile", response_model=ProfileResponse, status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Create a profile record for a newly signed-up user.
    Called once after successful Supabase signup.
    user_id is taken from the verified JWT — never from the request body.
    """
    client = get_authed_client(user.user_id)   # will use service role for upsert
    from ..core.database import get_supabase_admin
    admin = get_supabase_admin()

    # Check if profile already exists
    existing = admin.table("profiles").select("id").eq("id", user.user_id).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists for this user.",
        )

    result = admin.table("profiles").insert({
        "id":           user.user_id,
        "email":        user.email,
        "display_name": body.display_name,
    }).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile.",
        )

    return ProfileResponse(**result.data[0])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(user: CurrentUser = Depends(get_current_user)):
    """Get the authenticated user's profile."""
    from ..core.database import get_supabase_admin
    admin = get_supabase_admin()
    result = admin.table("profiles").select("*").eq("id", user.user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return ProfileResponse(**result.data[0])


@router.delete("/profile", response_model=MessageResponse)
async def delete_account(user: CurrentUser = Depends(get_current_user)):
    """
    Delete the user's account. Cascades to all fleet/vehicle/plan data.
    This is irreversible.
    """
    from ..core.database import get_supabase_admin
    admin = get_supabase_admin()
    # Delete via auth admin (Supabase deletes the auth user)
    try:
        admin.auth.admin.delete_user(user.user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {e}")
    return MessageResponse(message="Account deleted successfully.")
