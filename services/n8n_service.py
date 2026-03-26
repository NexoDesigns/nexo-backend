"""
n8n Service — Nexo Designs Backend

Responsible for:
1. Building the full payload for a phase execution (requirements + previous outputs + RAG).
2. Creating the phase_run record in Supabase.
3. Calling the n8n webhook.

RAG context injection is intentionally skipped in Phase 2 (no embeddings yet).
It will be wired in Phase 3 once ingestion_service and rag_service are implemented.
The payload field 'rag_context' is included but empty so n8n workflows don't need
to be changed again when RAG is added.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from core.config import settings
from core.supabase import get_supabase

# Pipeline phase order — used to determine which previous phases to pull outputs from.
PHASE_ORDER = ["research", "ic_selection", "component_selection", "netlist"]


def _phases_before(phase_id: str) -> list[str]:
    """Return all phase IDs that come before the given phase in the pipeline."""
    try:
        idx = PHASE_ORDER.index(phase_id)
        return PHASE_ORDER[:idx]
    except ValueError:
        return []


async def _get_project_requirements(project_id: str, supabase) -> Optional[dict]:
    """Fetch the project requirements from Supabase."""
    result = (
        supabase.table("project_requirements")
        .select("*")
        .eq("project_id", project_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def _get_active_run_outputs(
    project_id: str, phase_ids: list[str], supabase
) -> dict[str, Any]:
    """
    For each phase in phase_ids, retrieve the output_payload of the currently
    active run. Returns a dict keyed by phase_id.
    """
    if not phase_ids:
        return {}

    outputs: dict[str, Any] = {}

    # Fetch active run IDs for this project
    active_runs_result = (
        supabase.table("project_active_runs")
        .select("phase_id, run_id")
        .eq("project_id", project_id)
        .in_("phase_id", phase_ids)
        .execute()
    )

    if not active_runs_result.data:
        return {}

    for active in active_runs_result.data:
        run_result = (
            supabase.table("phase_runs")
            .select("output_payload")
            .eq("id", active["run_id"])
            .single()
            .execute()
        )
        if run_result.data and run_result.data.get("output_payload"):
            outputs[active["phase_id"]] = run_result.data["output_payload"]

    return outputs


async def _get_next_run_number(project_id: str, phase_id: str, supabase) -> int:
    """Calculate the next sequential run number for a (project, phase) pair."""
    result = (
        supabase.table("phase_runs")
        .select("run_number")
        .eq("project_id", project_id)
        .eq("phase_id", phase_id)
        .order("run_number", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["run_number"] + 1
    return 1


async def _get_phase_webhook_path(phase_id: str, supabase) -> str:
    """Fetch the n8n webhook path for a given phase."""
    result = (
        supabase.table("pipeline_phases")
        .select("n8n_webhook_path")
        .eq("id", phase_id)
        .single()
        .execute()
    )
    if not result.data:
        raise ValueError(f"Phase '{phase_id}' not found in pipeline_phases catalog")
    return result.data["n8n_webhook_path"]


async def trigger_phase(
    project_id: str,
    phase_id: str,
    custom_inputs: Optional[dict],
    user_id: str,
) -> dict:
    """
    Main entry point. Called by routers/runs.py.

    Orchestrates:
      1. Load project requirements
      2. Load active outputs from previous phases
      3. Assemble payload
      4. Create phase_run record (status='running')
      5. Call n8n webhook (fire-and-forget async)

    Returns: { run_id, run_number, status }
    """
    supabase = get_supabase()

    # 1. Requirements
    requirements = await _get_project_requirements(project_id, supabase)

    # 2. Previous phase outputs
    previous_phases = _phases_before(phase_id)
    previous_outputs = await _get_active_run_outputs(
        project_id, previous_phases, supabase
    )

    # 3. RAG context — empty in Phase 2, populated in Phase 3
    rag_context: dict = {}

    # 4. Run number
    run_number = await _get_next_run_number(project_id, phase_id, supabase)
    run_id = str(uuid.uuid4())

    # 5. Build full payload for n8n
    callback_url = f"{settings.BACKEND_URL}/webhooks/n8n/callback"
    payload = {
        "run_id": run_id,
        "callback_url": callback_url,
        "project_requirements": requirements,
        "previous_phase_outputs": previous_outputs,
        "custom_inputs": custom_inputs or {},
        "rag_context": rag_context,
    }

    # 6. Insert run record (status='running')
    supabase.table("phase_runs").insert({
        "id": run_id,
        "project_id": project_id,
        "phase_id": phase_id,
        "run_number": run_number,
        "status": "running",
        "input_payload": payload,
        "rag_context": rag_context,
        "created_by": user_id,
    }).execute()

    # 7. Call n8n webhook (non-blocking — n8n will callback when done)
    webhook_path = await _get_phase_webhook_path(phase_id, supabase)
    await _call_n8n_webhook(webhook_path, payload)

    return {
        "run_id": run_id,
        "run_number": run_number,
        "status": "running",
    }


async def _call_n8n_webhook(webhook_path: str, payload: dict) -> None:
    """
    Fire the n8n webhook. Uses a generous timeout since n8n may queue the
    execution. We don't wait for the agent to finish — n8n will callback
    to /webhooks/n8n/callback when done.
    """
    url = f"{settings.N8N_BASE_URL}{webhook_path}"
    headers = {
        "Content-Type": "application/json",
        "X-N8N-Secret": settings.N8N_WEBHOOK_SECRET,
    }

    # httpx async client with a 30s connect timeout.
    # The actual agent execution happens asynchronously in n8n.
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # If n8n rejects the webhook, mark the run as failed immediately
            supabase = get_supabase()
            run_id = payload.get("run_id")
            if run_id:
                supabase.table("phase_runs").update({
                    "status": "failed",
                    "error_message": f"n8n webhook call failed: {e.response.status_code} {e.response.text}",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", run_id).execute()
            raise
        except httpx.RequestError as e:
            supabase = get_supabase()
            run_id = payload.get("run_id")
            if run_id:
                supabase.table("phase_runs").update({
                    "status": "failed",
                    "error_message": f"Could not reach n8n: {str(e)}",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", run_id).execute()
            raise