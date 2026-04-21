"""
Normatives router.

Manages the global normative document library, project-level normative assignments,
and normative analysis workflow runs.

Endpoints:
  POST   /normatives/upload                               — Upload a PDF normative
  GET    /normatives                                      — List all normatives (with optional filters)
  DELETE /normatives/{document_id}                        — Delete a normative document
  POST   /projects/{project_id}/normatives/suggest        — Suggest applicable normatives for a project
  GET    /projects/{project_id}/normatives                 — Get active normatives for a project
  POST   /projects/{project_id}/normatives                 — Set active normatives for a project
  POST   /projects/{project_id}/normatives/run             — Trigger a normative analysis run
  GET    /projects/{project_id}/normatives/runs            — List normative runs for a project
  GET    /projects/{project_id}/normatives/runs/{run_id}   — Get a single normative run
  POST   /projects/{project_id}/normatives/runs/{run_id}/complete — n8n callback

Auth:
  User endpoints: JWT via Depends(get_current_user_id)
  n8n callback: X-N8N-Secret header
"""

import io
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile, status

from core.config import settings
from core.security import get_current_user_id
from core.supabase import get_supabase
from models.normative import (
    DecisionTreeResponse,
    DecisionTreeSaveRequest,
    NormativeDocumentResponse,
    NormativeSuggestResponse,
    NormativeSuggestion,
    ProjectNormativesUpdateRequest,
)
from models.normative_run import (
    NormativeRunComplete,
    NormativeRunCreate,
    NormativeRunSummary,
    NormativeRunTriggerResponse,
)
from services import normative_service
from services.ingestion_service import ingest_document

router = APIRouter(tags=["Normatives"])

NORMATIVES_STORAGE_BUCKET = "documents"
NORMATIVES_STORAGE_PREFIX = "normatives"


# ── Upload a normative document ───────────────────────────────────────────────

@router.post(
    "/normatives/upload",
    response_model=NormativeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_normative(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    standard_code: Optional[str] = Form(None),
    standard_version: Optional[str] = Form(None),
    issuing_body: Optional[str] = Form(None),
    applicable_industries: Optional[str] = Form(None),
    applicable_countries: Optional[str] = Form(None),
    applicable_user_types: Optional[str] = Form(None),
    scope_summary: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Upload a PDF normative document to the global normatives library.
    The file is stored and queued for background ingestion (chunking + embeddings).
    applicable_industries, applicable_countries, applicable_user_types accept
    comma-separated strings (e.g. "ES,DE,FR").
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted for normatives")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")

    doc_id = str(uuid.uuid4())
    storage_path = f"{NORMATIVES_STORAGE_PREFIX}/{doc_id}.pdf"

    supabase.storage.from_(NORMATIVES_STORAGE_BUCKET).upload(
        storage_path,
        io.BytesIO(content),
        {"content-type": "application/pdf"},
    )

    def _split(val: Optional[str]) -> Optional[list[str]]:
        return [v.strip() for v in val.split(",") if v.strip()] if val else None

    metadata = {
        "standard_code": standard_code,
        "standard_version": standard_version,
        "issuing_body": issuing_body,
        "applicable_industries": _split(applicable_industries),
        "applicable_countries": _split(applicable_countries),
        "applicable_user_types": _split(applicable_user_types),
        "scope_summary": scope_summary,
        "source_url": source_url,
    }

    insert_result = (
        supabase.table("documents")
        .insert({
            "id": doc_id,
            "name": name,
            "type": "normative",
            "storage_path": storage_path,
            "file_size_bytes": len(content),
            "mime_type": "application/pdf",
            "embedding_status": "pending",
            "metadata": metadata,
            "created_by": user_id,
        })
        .execute()
    )
    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Failed to create normative record")

    background_tasks.add_task(ingest_document, doc_id)

    return insert_result.data[0]


# ── List normatives ───────────────────────────────────────────────────────────

@router.get("/normatives", response_model=list[NormativeDocumentResponse])
async def list_normatives(
    industry: Optional[str] = None,
    country: Optional[str] = None,
    embedding_status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """List all normatives in the global library with optional filters."""
    query = (
        supabase.table("documents")
        .select("id, name, storage_path, file_size_bytes, mime_type, embedding_status, metadata, created_by, created_at")
        .eq("type", "normative")
        .is_("project_id", "null")
    )
    if embedding_status:
        query = query.eq("embedding_status", embedding_status)

    result = query.order("created_at", desc=True).execute()
    docs = result.data or []

    if industry:
        docs = [
            d for d in docs
            if industry in ((d.get("metadata") or {}).get("applicable_industries") or [])
        ]
    if country:
        docs = [
            d for d in docs
            if country in ((d.get("metadata") or {}).get("applicable_countries") or [])
        ]

    return docs


# ── Get signed download URL for a normative ──────────────────────────────────

@router.get("/normatives/{document_id}/download-url")
async def get_normative_download_url(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Returns a short-lived signed URL to download the normative PDF.
    The URL is valid for 60 minutes.
    """
    doc_result = (
        supabase.table("documents")
        .select("id, storage_path, type")
        .eq("id", document_id)
        .single()
        .execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=404, detail="Normative not found")
    if doc_result.data["type"] != "normative":
        raise HTTPException(status_code=400, detail="Document is not a normative")

    signed = supabase.storage.from_(NORMATIVES_STORAGE_BUCKET).create_signed_url(
        doc_result.data["storage_path"],
        expires_in=3600,  # 1 hour
    )
    if not signed or not signed.get("signedURL"):
        raise HTTPException(status_code=500, detail="Failed to generate download URL")

    return {"url": signed["signedURL"], "expires_in": 3600}


# ── Delete a normative ────────────────────────────────────────────────────────

@router.delete("/normatives/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_normative(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Delete a normative document, its chunks, and its project assignments."""
    doc_result = (
        supabase.table("documents")
        .select("id, storage_path, type")
        .eq("id", document_id)
        .single()
        .execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=404, detail="Normative not found")
    if doc_result.data["type"] != "normative":
        raise HTTPException(status_code=400, detail="Document is not a normative")

    storage_path = doc_result.data["storage_path"]
    supabase.storage.from_(NORMATIVES_STORAGE_BUCKET).remove([storage_path])
    supabase.table("documents").delete().eq("id", document_id).execute()


# ── Suggest normatives for a project ─────────────────────────────────────────

@router.post(
    "/projects/{project_id}/normatives/suggest",
    response_model=NormativeSuggestResponse,
)
async def suggest_normatives(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Suggest applicable normatives for a project.
    Uses tag-filter + n8n GPT mini agent for ranking and justification.
    """
    proj = supabase.table("projects").select("id").eq("id", project_id).single().execute()
    if not proj.data:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        suggestions_raw = await normative_service.suggest_normatives(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Suggest failed: {str(e)}")

    suggestions = [NormativeSuggestion(**s) for s in suggestions_raw]
    return NormativeSuggestResponse(suggestions=suggestions)


# ── Decision-tree answers ─────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/normatives/decision-tree",
    response_model=DecisionTreeResponse,
)
async def get_decision_tree(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return the saved decision-tree answers for a project."""
    result = (
        supabase.table("projects")
        .select("normative_decision_tree_answers")
        .eq("id", project_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return DecisionTreeResponse(answers=result.data.get("normative_decision_tree_answers") or {})


@router.put(
    "/projects/{project_id}/normatives/decision-tree",
    response_model=DecisionTreeResponse,
)
async def save_decision_tree(
    project_id: str,
    body: DecisionTreeSaveRequest,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Save (replace) the decision-tree answers for a project."""
    result = (
        supabase.table("projects")
        .update({"normative_decision_tree_answers": body.answers})
        .eq("id", project_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return DecisionTreeResponse(answers=result.data[0].get("normative_decision_tree_answers") or {})


# ── Get active normatives for a project ──────────────────────────────────────

@router.get(
    "/projects/{project_id}/normatives",
    response_model=list[NormativeDocumentResponse],
)
async def get_project_normatives(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """List active (confirmed) normatives for a project."""
    result = (
        supabase.table("project_normatives")
        .select("document_id, documents(id, name, storage_path, file_size_bytes, mime_type, embedding_status, metadata, created_by, created_at)")
        .eq("project_id", project_id)
        .execute()
    )
    return [row["documents"] for row in (result.data or []) if row.get("documents")]


# ── Set active normatives for a project ──────────────────────────────────────


@router.post(
    "/projects/{project_id}/normatives",
    response_model=list[NormativeDocumentResponse],
    status_code=status.HTTP_200_OK,
)
async def set_project_normatives(
    project_id: str,
    body: ProjectNormativesUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Replace the active normatives for a project.
    Deletes all existing assignments and inserts the provided document_ids.
    """
    proj = supabase.table("projects").select("id").eq("id", project_id).single().execute()
    if not proj.data:
        raise HTTPException(status_code=404, detail="Project not found")

    supabase.table("project_normatives").delete().eq("project_id", project_id).execute()

    if body.document_ids:
        rows = [
            {
                "project_id": project_id,
                "document_id": str(doc_id),
                "selection_source": body.selection_source,
                "selected_by": user_id,
            }
            for doc_id in body.document_ids
        ]
        supabase.table("project_normatives").insert(rows).execute()

    result = (
        supabase.table("project_normatives")
        .select("document_id, documents(id, name, storage_path, file_size_bytes, mime_type, embedding_status, metadata, created_by, created_at)")
        .eq("project_id", project_id)
        .execute()
    )
    return [row["documents"] for row in (result.data or []) if row.get("documents")]


# ── Trigger a normative analysis run ─────────────────────────────────────────

@router.post(
    "/projects/{project_id}/normatives/run",
    response_model=NormativeRunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_normative_run(
    project_id: UUID,
    body: NormativeRunCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Trigger the normative analysis n8n workflow for a project.

    Sends project normative context + active normatives to n8n.
    Creates a normative_run record with status='running' and fires the
    webhook asynchronously. Returns immediately with run_id.
    Poll GET /normatives/runs/{run_id} for status updates.
    """
    project_result = (
        supabase.table("projects")
        .select(
            "id, normative_industry, normative_client_type, normative_user_age_range, "
            "normative_target_countries, normative_extra_context"
        )
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data

    active_norms_result = (
        supabase.table("project_normatives")
        .select("document_id, documents(id, name, metadata)")
        .eq("project_id", str(project_id))
        .execute()
    )
    active_normatives = active_norms_result.data or []
    normative_document_ids = [row["document_id"] for row in active_normatives]
    normative_metadata = [
        {
            "document_id": row["document_id"],
            "name": row["documents"]["name"] if row.get("documents") else None,
            "standard_code": (row["documents"]["metadata"] or {}).get("standard_code") if row.get("documents") else None,
            "scope_summary": (row["documents"]["metadata"] or {}).get("scope_summary") if row.get("documents") else None,
        }
        for row in active_normatives
        if row.get("documents")
    ]

    count_result = (
        supabase.table("normative_runs")
        .select("id", count="exact")
        .eq("project_id", str(project_id))
        .execute()
    )
    run_number = (count_result.count or 0) + 1

    insert_result = (
        supabase.table("normative_runs")
        .insert({
            "project_id": str(project_id),
            "run_number": run_number,
            "status": "running",
            "custom_prompt": body.custom_prompt,
            "created_by": user_id,
        })
        .execute()
    )
    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Failed to create normative run record")

    run_id = insert_result.data[0]["id"]

    callback_url = f"{settings.BACKEND_URL}/projects/{project_id}/normatives/runs/{run_id}/complete"
    webhook_payload = {
        "run_id": run_id,
        "project_id": str(project_id),
        "callback_url": callback_url,
        "custom_prompt": body.custom_prompt,
        "normative_context": {
            "industry": project.get("normative_industry"),
            "client_type": project.get("normative_client_type"),
            "user_age_range": project.get("normative_user_age_range"),
            "target_countries": project.get("normative_target_countries"),
            "extra_context": project.get("normative_extra_context"),
        },
        "normatives": {
            "document_ids": normative_document_ids,
            "metadata": normative_metadata,
            "rag_search_endpoint": f"{settings.BACKEND_URL}/rag/search",
            "rag_auth_header": settings.N8N_WEBHOOK_SECRET,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.N8N_NORMATIVES_WEBHOOK_URL,
                json=webhook_payload,
                headers={"X-N8N-Secret": settings.N8N_WEBHOOK_SECRET},
            )
    except Exception as e:
        supabase.table("normative_runs").update({
            "status": "failed",
            "error_message": f"Failed to reach n8n: {str(e)}",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        raise HTTPException(status_code=502, detail=f"Failed to trigger n8n workflow: {str(e)}")

    return NormativeRunTriggerResponse(run_id=run_id, run_number=run_number, status="running")


# ── List normative runs ───────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/normatives/runs",
    response_model=list[NormativeRunSummary],
)
async def list_normative_runs(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """List all normative runs for a project, ordered by run_number DESC."""
    result = (
        supabase.table("normative_runs")
        .select(
            "id, run_number, status, custom_prompt, output_data, "
            "n8n_execution_id, error_message, created_by, created_at, "
            "completed_at, duration_seconds"
        )
        .eq("project_id", str(project_id))
        .order("run_number", desc=True)
        .execute()
    )
    return result.data or []


# ── Get normative run detail ──────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/normatives/runs/{run_id}",
    response_model=NormativeRunSummary,
)
async def get_normative_run(
    project_id: UUID,
    run_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Get the detail of a single normative run."""
    result = (
        supabase.table("normative_runs")
        .select("*")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Normative run not found")
    return result.data


# ── n8n callback — complete a normative run ───────────────────────────────────

@router.post(
    "/projects/{project_id}/normatives/runs/{run_id}/complete",
    status_code=status.HTTP_200_OK,
)
async def complete_normative_run(
    project_id: UUID,
    run_id: UUID,
    body: NormativeRunComplete,
    x_n8n_secret: str = Header(default=None, alias="X-N8N-Secret"),
    supabase=Depends(get_supabase),
):
    """
    Called by n8n when the normative analysis workflow finishes.

    Saves the JSON output and marks the run as completed or failed.
    Not protected by Supabase Auth — uses X-N8N-Secret header instead.
    Idempotent: if the run is already finalized, returns early.
    """
    if x_n8n_secret != settings.N8N_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    run_result = (
        supabase.table("normative_runs")
        .select("id, status")
        .eq("id", str(run_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Normative run not found")

    if run_result.data["status"] not in ("running", "pending"):
        return {"message": "Run already finalized", "run_id": str(run_id), "status": run_result.data["status"]}

    final_status = "failed" if body.error_message else "completed"
    update: dict = {
        "status": final_status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.output_data is not None:
        update["output_data"] = body.output_data
    if body.n8n_execution_id is not None:
        update["n8n_execution_id"] = body.n8n_execution_id
    if body.duration_seconds is not None:
        update["duration_seconds"] = body.duration_seconds
    if body.error_message:
        update["error_message"] = body.error_message

    supabase.table("normative_runs").update(update).eq("id", str(run_id)).execute()

    return {"message": "Run updated successfully", "run_id": str(run_id), "status": final_status}
