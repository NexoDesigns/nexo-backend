"""
Requirements runs router.

Manages the Drive-based requirements workflow:
- Store input Google Drive URL on the project
- Trigger an n8n workflow that processes the input Excel and generates an output Excel
- Track run history per project
- Receive the n8n callback with the output Drive URL

Auth:
  - User endpoints: JWT via Depends(get_current_user_id)
  - n8n callback (POST /runs/{run_id}/complete): X-N8N-Secret header
"""

from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status

from core.config import settings
from core.security import get_current_user_id
from core.supabase import get_supabase
from models.requirements_run import (
    RequirementsRunComplete,
    RequirementsRunCreate,
    RequirementsRunSummary,
    RequirementsRunTriggerResponse,
)

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["Requirements Runs"])


# ── Trigger a new requirements run ────────────────────────────────────────────

@router.post("/run", response_model=RequirementsRunTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_requirements_run(
    project_id: UUID,
    body: RequirementsRunCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Trigger the requirements n8n workflow for a project.

    Requires that the project has a requirements_input_drive_url set.
    Creates a requirements_run record with status='running' and fires the
    n8n webhook asynchronously (fire-and-forget). Returns immediately with run_id.
    Poll GET /runs/{run_id} for status updates.
    """
    # ── Validate project exists and has an input URL ───────────────────────────
    project_result = (
        supabase.table("projects")
        .select("id, requirements_input_drive_url")
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data
    input_drive_url = project.get("requirements_input_drive_url")
    if not input_drive_url:
        raise HTTPException(
            status_code=400,
            detail="Project has no requirements_input_drive_url. Set it before triggering a run.",
        )

    # ── Calculate next run_number ──────────────────────────────────────────────
    count_result = (
        supabase.table("requirements_runs")
        .select("id", count="exact")
        .eq("project_id", str(project_id))
        .execute()
    )
    run_number = (count_result.count or 0) + 1

    # ── Create the run record ──────────────────────────────────────────────────
    insert_result = (
        supabase.table("requirements_runs")
        .insert({
            "project_id": str(project_id),
            "run_number": run_number,
            "status": "running",
            "custom_prompt": body.custom_prompt,
            "input_drive_url": input_drive_url,
            "created_by": user_id,
        })
        .execute()
    )
    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Failed to create requirements run record")

    run_id = insert_result.data[0]["id"]

    # ── Fire n8n webhook (fire-and-forget) ────────────────────────────────────
    callback_url = (
        f"{settings.BACKEND_URL}/projects/{project_id}/requirements/runs/{run_id}/complete"
    )
    webhook_payload = {
        "run_id": run_id,
        "project_id": str(project_id),
        "callback_url": callback_url,
        "input_drive_url": input_drive_url,
        "custom_prompt": body.custom_prompt,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.N8N_REQUIREMENTS_WEBHOOK_URL,
                json=webhook_payload,
                headers={"X-N8N-Secret": settings.N8N_WEBHOOK_SECRET},
            )
    except Exception as e:
        # Mark run as failed if we cannot even reach n8n
        supabase.table("requirements_runs").update({
            "status": "failed",
            "error_message": f"Failed to reach n8n: {str(e)}",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        raise HTTPException(status_code=502, detail=f"Failed to trigger n8n workflow: {str(e)}")

    return RequirementsRunTriggerResponse(
        run_id=run_id,
        run_number=run_number,
        status="running",
    )


# ── List requirements runs ─────────────────────────────────────────────────────

@router.get("/runs", response_model=list[RequirementsRunSummary])
async def list_requirements_runs(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    List all requirements runs for a project, ordered by run_number DESC
    (most recent first).
    """
    result = (
        supabase.table("requirements_runs")
        .select(
            "id, run_number, status, custom_prompt, input_drive_url, "
            "output_drive_url, output_drive_file_id, error_message, "
            "created_by, created_at, completed_at, duration_seconds"
        )
        .eq("project_id", str(project_id))
        .order("run_number", desc=True)
        .execute()
    )
    return result.data


# ── Get requirements run detail ───────────────────────────────────────────────

@router.get("/runs/{run_id}", response_model=RequirementsRunSummary)
async def get_requirements_run(
    project_id: UUID,
    run_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Get the detail of a single requirements run."""
    result = (
        supabase.table("requirements_runs")
        .select("*")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Requirements run not found")
    return result.data


# ── n8n callback — complete a requirements run ────────────────────────────────

@router.post("/runs/{run_id}/complete", status_code=status.HTTP_200_OK)
async def complete_requirements_run(
    project_id: UUID,
    run_id: UUID,
    body: RequirementsRunComplete,
    x_n8n_secret: str = Header(default=None, alias="X-N8N-Secret"),
    supabase=Depends(get_supabase),
):
    """
    Called by n8n when the requirements workflow finishes.

    Saves the output Google Drive URL and file ID, marks the run as completed.
    Not protected by Supabase Auth — uses X-N8N-Secret header instead.
    Idempotent: if the run is already finalized, returns early.
    """
    # ── Auth ──────────────────────────────────────────────────────────────────
    if x_n8n_secret != settings.N8N_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    # ── Fetch run ─────────────────────────────────────────────────────────────
    run_result = (
        supabase.table("requirements_runs")
        .select("id, status")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Requirements run not found")

    run = run_result.data

    # Idempotent: already finalized
    if run["status"] not in ("running", "pending"):
        return {"message": "Run already finalized", "run_id": str(run_id), "status": run["status"]}

    # ── Update run ────────────────────────────────────────────────────────────
    final_status = "failed" if body.error_message else "completed"
    update: dict = {
        "status": final_status,
        "output_drive_url": body.output_drive_url,
        "output_drive_file_id": body.output_drive_file_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.duration_seconds is not None:
        update["duration_seconds"] = body.duration_seconds
    if body.error_message:
        update["error_message"] = body.error_message

    supabase.table("requirements_runs").update(update).eq("id", str(run_id)).execute()

    return {"message": "Run updated successfully", "run_id": str(run_id), "status": final_status}
