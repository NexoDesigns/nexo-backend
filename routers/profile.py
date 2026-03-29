from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.security import get_current_user_id
from core.supabase import get_supabase

router = APIRouter(prefix="/profile", tags=["Profile"])


class ProfileResponse(BaseModel):
    id: str
    full_name: str | None = None
    email: str | None = None


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return the authenticated user's profile."""
    result = (
        supabase.table("profiles")
        .select("id, full_name, email")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return result.data
