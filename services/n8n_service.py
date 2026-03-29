"""
n8n Service — Nexo Designs Backend

Responsible for:
1. Building the full payload for a phase execution (requirements + previous outputs + RAG).
2. Creating the phase_run record in Supabase.
3. Calling the n8n webhook.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from core.config import settings
from core.supabase import get_supabase
from services import rag_service

PHASE_ORDER = ["research", "ic_selection", "ic_naming_agent", "component_selection", "netlist"]


def _phases_before(phase_id: str) -> list[str]:
    try:
        idx = PHASE_ORDER.index(phase_id)
        return PHASE_ORDER[:idx]
    except ValueError:
        return []


async def _get_project_requirements(project_id: str, supabase) -> Optional[dict]:
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
    if not phase_ids:
        return {}

    outputs: dict[str, Any] = {}

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
    use_perplexity: Optional[bool],
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
    previous_outputs = await _get_active_run_outputs(project_id, previous_phases, supabase)

    # RAG context — phase-specific semantic search
    # Failure here does NOT abort the execution (rag_service handles errors internally)
    rag_context = await rag_service.build_rag_context_for_phase(
        phase_id=phase_id,
        project_id=project_id,
        requirements=requirements,
        custom_inputs=custom_inputs,
        top_k=5,
    )

    run_number = await _get_next_run_number(project_id, phase_id, supabase)
    run_id = str(uuid.uuid4())

    callback_url = f"{settings.BACKEND_URL}/webhooks/n8n/callback"
    payload = {
        "run_id": run_id,
        "phase_id": phase_id,
        "callback_url": callback_url,
        "project_requirements": requirements,
        "previous_phase_outputs": previous_outputs,
        "custom_inputs": custom_inputs or {},
        "use_perplexity": use_perplexity if use_perplexity is not None else True, # por defecto siempre se usa perplexity
        "rag_context": rag_context,
    }

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

    webhook_path = await _get_phase_webhook_path(phase_id, supabase)
    await _call_n8n_webhook(webhook_path, payload)

    return {"run_id": run_id, "run_number": run_number, "status": "running"}


async def _call_n8n_webhook(webhook_path: str, payload: dict) -> None:
    url = f"{settings.N8N_BASE_URL}{webhook_path}"
    headers = {
        "Content-Type": "application/json",
        "X-N8N-Secret": settings.N8N_WEBHOOK_SECRET,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            supabase = get_supabase()
            run_id = payload.get("run_id")
            if run_id:
                error_msg = (
                    f"n8n webhook failed: {e.response.status_code} {e.response.text}"
                    if isinstance(e, httpx.HTTPStatusError)
                    else f"Could not reach n8n: {str(e)}"
                )
                supabase.table("phase_runs").update({
                    "status": "failed",
                    "error_message": error_msg,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", run_id).execute()
            raise