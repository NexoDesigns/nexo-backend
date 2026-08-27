from fastapi import APIRouter, Depends

from constants.pipeline import PHASE_ORDER
from core.security import get_current_user_id
from core.supabase import get_supabase

router = APIRouter(tags=["Pipeline"])


@router.get("/pipeline-phases")
async def list_pipeline_phases(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return active pipeline phases ordered by phase_order ascending.

    Filtered to PHASE_ORDER rather than returning every pipeline_phases row: a
    retired phase (e.g. ic_naming_agent) stays in the table for historical
    phase_runs FK safety but is excluded here instead of being deleted.
    """
    result = (
        supabase.table("pipeline_phases")
        .select("*")
        .in_("id", PHASE_ORDER)
        .order("order_index", desc=False)
        .execute()
    )
    return result.data
