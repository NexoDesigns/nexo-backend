from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from core.security import get_current_user_id
from core.supabase import get_supabase
from models.run import RunComplete, RunCreate, RunDetail, RunNotesUpdate, RunSummary, RunTriggerResponse
from services import n8n_service

router = APIRouter(prefix="/projects/{project_id}/phases/{phase_id}", tags=["Runs"])


def _check_project_and_phase(project_id: str, phase_id: str, supabase):
    """Validate that both the project and the phase exist."""
    project = (
        supabase.table("projects")
        .select("id")
        .eq("id", project_id)
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    phase = (
        supabase.table("pipeline_phases")
        .select("id")
        .eq("id", phase_id)
        .execute()
    )
    if not phase.data:
        raise HTTPException(
            status_code=404,
            detail=f"Phase '{phase_id}' not found. Valid phases: research, ic_selection, component_selection, netlist",
        )


# ── Trigger a new run ─────────────────────────────────────────────────────────

@router.post("/run", response_model=RunTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    project_id: UUID,
    phase_id: str,
    body: RunCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Trigger a new execution of a pipeline phase.

    - Assembles the full payload (requirements + previous phase outputs + RAG).
    - Creates a phase_run record with status='running'.
    - Fires the corresponding n8n webhook.
    - Returns immediately with run_id. Poll GET /runs/{run_id} for status.

    HTTP 202 Accepted is semantically correct: the work has been accepted
    but not yet completed.
    """
    _check_project_and_phase(str(project_id), phase_id, supabase)

    try:
        result = await n8n_service.trigger_phase(
            project_id=str(project_id),
            phase_id=phase_id,
            custom_inputs=body.custom_inputs,
            use_perplexity=body.use_perplexity,
            user_id=user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to trigger n8n workflow: {str(e)}",
        )

    return result


# ── List runs for a phase ─────────────────────────────────────────────────────

@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    project_id: UUID,
    phase_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    List all runs for a given project phase, ordered by run_number DESC
    (most recent first). Lightweight — does not include input/output payloads.
    """
    _check_project_and_phase(str(project_id), phase_id, supabase)

    result = (
        supabase.table("phase_runs")
        .select(
            "id, run_number, status, created_by, created_at, completed_at, "
            "duration_seconds, llm_tokens_used, notes"
        )
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .order("run_number", desc=True)
        .execute()
    )
    return result.data


# ── Get run detail ────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Full detail of a single run, including input_payload, output_payload,
    and rag_context. Used by the frontend for polling and for displaying results.
    """
    result = (
        supabase.table("phase_runs")
        .select("*")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.data


# ── Activate a run ────────────────────────────────────────────────────────────

@router.post("/runs/{run_id}/activate", status_code=status.HTTP_200_OK)
async def activate_run(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Mark a specific run as the 'active' run for this phase.
    The active run is what subsequent pipeline phases use as their input.

    Only completed runs can be activated.
    """
    # Verify the run exists, belongs to this project/phase, and is completed
    run_result = (
        supabase.table("phase_runs")
        .select("id, status")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Run not found")

    if run_result.data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Only completed runs can be activated. This run has status '{run_result.data['status']}'",
        )

    # Upsert into project_active_runs
    from datetime import datetime, timezone
    supabase.table("project_active_runs").upsert({
        "project_id": str(project_id),
        "phase_id": phase_id,
        "run_id": str(run_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {
        "message": f"Run {run_id} is now active for phase '{phase_id}'",
        "run_id": str(run_id),
        "phase_id": phase_id,
    }


# ── Complete a run ────────────────────────────────────────────────────────────

@router.patch("/runs/{run_id}/complete", status_code=status.HTTP_200_OK)
async def complete_run(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    body: RunComplete,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Mark a run as completed and record duration and token usage."""
    from datetime import datetime, timezone
    result = (
        supabase.table("phase_runs")
        .update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": body.duration_seconds,
            "llm_tokens_used": body.llm_tokens_used,
        })
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": str(run_id), "status": "completed"}


# ── Update run notes ──────────────────────────────────────────────────────────

@router.patch("/runs/{run_id}/notes", status_code=status.HTTP_200_OK)
async def update_run_notes(
    project_id: UUID,
    phase_id: str,
    run_id: UUID,
    body: RunNotesUpdate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Update the notes field of a run."""
    result = (
        supabase.table("phase_runs")
        .update({"notes": body.notes})
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .eq("phase_id", phase_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": str(run_id), "notes": body.notes}