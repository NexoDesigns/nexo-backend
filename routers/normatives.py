"""
Normatives router.

Manages the global normative document library and project-level normative assignments.

Endpoints:
  POST   /normatives/upload                         — Upload a PDF normative
  GET    /normatives                                — List all normatives (with optional filters)
  DELETE /normatives/{document_id}                  — Delete a normative document
  POST   /projects/{project_id}/normatives/suggest  — Suggest applicable normatives for a project
  GET    /projects/{project_id}/normatives           — Get active normatives for a project
  POST   /projects/{project_id}/normatives           — Set active normatives for a project

Auth:
  All endpoints: JWT via Depends(get_current_user_id)
"""

import io
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status

from core.security import get_current_user_id
from core.supabase import get_supabase
from models.normative import (
    NormativeDocumentResponse,
    NormativeSuggestResponse,
    NormativeSuggestion,
    ProjectNormativesUpdateRequest,
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
