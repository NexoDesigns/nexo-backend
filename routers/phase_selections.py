from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from constants.pipeline import PHASE_ORDER
from core.security import get_current_user_id
from core.supabase import get_supabase
from models.phase_selection import PhaseSelection, PhaseSelectionUpsert

router = APIRouter(
    prefix="/projects/{project_id}/phase-selections",
    tags=["Phase Selections"],
)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PhaseSelection])
async def list_phase_selections(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Saved output selections of every phase of a project."""
    result = (
        supabase.table("project_phase_selections")
        .select("*")
        .eq("project_id", str(project_id))
        .execute()
    )
    return result.data


# ── Upsert ────────────────────────────────────────────────────────────────────

@router.put("/{phase_id}", response_model=PhaseSelection)
async def upsert_phase_selection(
    project_id: UUID,
    phase_id: str,
    body: PhaseSelectionUpsert,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Save which items of a phase run's output are sent to the next phase."""
    if phase_id not in PHASE_ORDER:
        raise HTTPException(status_code=400, detail=f"Unknown phase '{phase_id}'")

    run = (
        supabase.table("phase_runs")
        .select("id")
        .eq("id", str(body.source_run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .execute()
    )
    if not run.data:
        raise HTTPException(status_code=404, detail="Run not found")

    result = (
        supabase.table("project_phase_selections")
        .upsert({
            "project_id": str(project_id),
            "phase_id": phase_id,
            "source_run_id": str(body.source_run_id),
            "selected_ids": body.selected_ids,
            "updated_by": user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save selection")
    return result.data[0]
