from fastapi import APIRouter, Depends

from core.security import get_current_user_id
from core.supabase import get_supabase

router = APIRouter(tags=["Pipeline"])


@router.get("/pipeline-phases")
async def list_pipeline_phases(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return all pipeline phases ordered by phase_order ascending."""
    result = (
        supabase.table("pipeline_phases")
        .select("*")
        .order("order_index", desc=False)
        .execute()
    )
    return result.data
