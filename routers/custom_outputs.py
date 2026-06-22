from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from core.security import get_current_user_id
from core.supabase import get_supabase
from models.custom_output import CustomOutputItem, CustomOutputItemCreate, CustomOutputItemUpdate

router = APIRouter(
    prefix="/projects/{project_id}/phases/{phase_id}/runs/{run_id}/custom-outputs",
    tags=["Custom Outputs"],
)


def _get_run_or_404(project_id: str, phase_id: str, run_id: str, supabase):
    result = (
        supabase.table("phase_runs")
        .select("id")
        .eq("id", run_id)
        .eq("project_id", project_id)
        .eq("phase_id", phase_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CustomOutputItem])
async def list_custom_outputs(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    _get_run_or_404(str(project_id), phase_id, str(run_id), supabase)
    result = (
        supabase.table("custom_phase_output_items")
        .select("*")
        .eq("source_run_id", str(run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CustomOutputItem, status_code=status.HTTP_201_CREATED)
async def create_custom_output(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    body: CustomOutputItemCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    _get_run_or_404(str(project_id), phase_id, str(run_id), supabase)
    result = (
        supabase.table("custom_phase_output_items")
        .insert({
            "project_id": str(project_id),
            "phase_id": phase_id,
            "source_run_id": str(run_id),
            "source_item_id": body.source_item_id,
            "source_item_label": body.source_item_label,
            "data": body.data,
            "created_by": user_id,
        })
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create custom output")
    return result.data[0]


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/{item_id}", response_model=CustomOutputItem)
async def update_custom_output(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    item_id: UUID,
    body: CustomOutputItemUpdate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    result = (
        supabase.table("custom_phase_output_items")
        .update({"data": body.data})
        .eq("id", str(item_id))
        .eq("source_run_id", str(run_id))
        .eq("project_id", str(project_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Custom output not found")
    return result.data[0]


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_output(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    item_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    result = (
        supabase.table("custom_phase_output_items")
        .delete()
        .eq("id", str(item_id))
        .eq("source_run_id", str(run_id))
        .eq("project_id", str(project_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Custom output not found")