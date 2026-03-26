"""
Webhook router — receives callbacks from n8n when a phase execution completes.
Also triggers auto-ingestion of phase outputs as RAG documents.
Security: all requests must include the header X-N8N-Secret matching
the value configured in settings.N8N_WEBHOOK_SECRET.
This prevents anyone from marking runs as completed from outside.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from core.config import settings
from core.supabase import get_supabase
from models.run import N8nCallbackBody
from services.ingestion_service import ingest_phase_output

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/n8n/callback", status_code=status.HTTP_200_OK)
async def n8n_callback(
    body: N8nCallbackBody,
    background_tasks: BackgroundTasks,
    x_n8n_secret: str = Header(default=None, alias="X-N8N-Secret"),
    supabase=Depends(get_supabase),
):
    """
    Called by n8n at the end of every workflow execution.

    n8n sends the run_id it received in the original trigger payload,
    the final status, the output, and optional metrics.

    This endpoint is intentionally not protected by Supabase Auth — n8n
    cannot easily attach a Bearer token. Instead, the shared webhook secret
    acts as the authentication mechanism.
    Authentication: shared secret via X-N8N-Secret header.
    """
    # ── Auth ──────────────────────────────────────────────────────────────────
    if x_n8n_secret != settings.N8N_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    if body.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'")

    # ── Fetch the run to make sure it exists and is still 'running' ───────────
    run_result = (
        supabase.table("phase_runs")
        .select("id, status, project_id, phase_id, created_by")
        .eq("id", str(body.run_id))
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail=f"Run {body.run_id} not found")

    run = run_result.data

    # Idempotent: already finalized
    if run["status"] not in ("running", "pending"):
        return {"message": "Run already finalized", "run_id": str(body.run_id), "status": run["status"]}

    # ── Update run ────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    update: dict = {"status": body.status, "completed_at": now}
    if body.output_payload is not None:
        update["output_payload"] = body.output_payload
    if body.n8n_execution_id:
        update["n8n_execution_id"] = body.n8n_execution_id
    if body.duration_seconds is not None:
        update["duration_seconds"] = body.duration_seconds
    if body.tokens_used is not None:
        update["llm_tokens_used"] = body.tokens_used
    if body.error_message:
        update["error_message"] = body.error_message

    supabase.table("phase_runs").update(update).eq("id", str(body.run_id)).execute()

    # ── Auto-activate if completed and no active run exists for this phase ────
    # This saves the engineer from having to manually activate the first run
    # of each phase. Subsequent runs still require manual activation.
    if body.status == "completed":
        # ── Auto-activate if no active run exists for this phase ──────────────
        existing_active = (
            supabase.table("project_active_runs")
            .select("run_id")
            .eq("project_id", run["project_id"])
            .eq("phase_id", run["phase_id"])
            .execute()
        )
        if not existing_active.data:
            supabase.table("project_active_runs").insert({
                "project_id": run["project_id"],
                "phase_id": run["phase_id"],
                "run_id": str(body.run_id),
                "updated_at": now,
            }).execute()

        # ── Auto-ingest output as RAG document ────────────────────────────────
        if body.output_payload:
            background_tasks.add_task(
                ingest_phase_output,
                project_id=run["project_id"],
                phase_id=run["phase_id"],
                run_id=str(body.run_id),
                output_payload=body.output_payload,
                created_by=run.get("created_by", ""),
            )

    return {"message": "Run updated successfully", "run_id": str(body.run_id), "status": body.status}