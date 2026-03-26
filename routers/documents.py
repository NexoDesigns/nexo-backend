import os
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from core.security import get_current_user_id
from core.supabase import get_supabase
from models.document import (
    ALLOWED_EXTENSIONS,
    ALLOWED_DOCUMENT_TYPES,
    DocumentResponse,
)
from services.ingestion_service import ingest_document

router = APIRouter(prefix="/documents", tags=["Documents"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _validate_file(file: UploadFile) -> None:
    """Check extension. MIME type alone is not reliable."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file extension '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    project_id: Optional[str] = Form(default=None),
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Upload a document and trigger background ingestion (text extraction + embedding).

    - file: PDF, DOCX, XLSX, TXT, MD
    - document_type: one of datasheet | manufacturer_list | design_note |
                     reference_schematic | other
    - project_id: optional — if omitted the document is global (visible to all projects)

    Returns the document record immediately with embedding_status='pending'.
    Ingestion runs in the background; poll GET /documents/{id} to check status.
    """
    _validate_file(file)

    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Allowed: {', '.join(ALLOWED_DOCUMENT_TYPES)}",
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB",
        )

    # Build storage path
    filename = file.filename or "unnamed"
    import uuid as uuid_module
    file_id = str(uuid_module.uuid4())
    ext = os.path.splitext(filename)[1].lower()

    if project_id:
        storage_path = f"projects/{project_id}/{file_id}{ext}"
    else:
        storage_path = f"global/{file_id}{ext}"

    # Upload to Supabase Storage
    try:
        supabase.storage.from_("documents").upload(
            storage_path,
            content,
            {"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Storage upload failed: {str(e)}",
        )

    # Create DB record
    doc_payload: dict = {
        "name": filename,
        "type": document_type,
        "source": "internal",
        "storage_path": storage_path,
        "file_size_bytes": len(content),
        "mime_type": file.content_type,
        "embedding_status": "pending",
        "created_by": user_id,
    }
    if project_id:
        doc_payload["project_id"] = project_id

    result = supabase.table("documents").insert(doc_payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create document record")

    document = result.data[0]
    document_id = document["id"]

    # Trigger ingestion in background
    background_tasks.add_task(ingest_document, document_id)

    return document


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    project_id: Optional[str] = Query(default=None),
    document_type: Optional[str] = Query(default=None),
    embedding_status: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    List documents with optional filters.
    Returns both project-specific and global documents when project_id is provided.
    """
    query = supabase.table("documents").select("*").order("created_at", desc=True)

    if project_id:
        # Documents belonging to this project OR global documents (project_id IS NULL)
        query = query.or_(f"project_id.eq.{project_id},project_id.is.null")
    if document_type:
        query = query.eq("type", document_type)
    if embedding_status:
        query = query.eq("embedding_status", embedding_status)

    result = query.execute()
    return result.data


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Get a single document. Useful for polling embedding_status after upload."""
    result = (
        supabase.table("documents")
        .select("*")
        .eq("id", str(document_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return result.data


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Delete a document:
    1. Remove file from Supabase Storage.
    2. Delete document_chunks (CASCADE from DB foreign key handles this).
    3. Delete document record.
    """
    # Fetch storage path first
    result = (
        supabase.table("documents")
        .select("id, storage_path")
        .eq("id", str(document_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = result.data["storage_path"]

    # Delete from Storage (best-effort — don't fail if the file is already gone)
    try:
        supabase.storage.from_("documents").remove([storage_path])
    except Exception:
        pass  # File may have already been deleted; proceed with DB cleanup

    # Delete record (document_chunks cascade via FK)
    supabase.table("documents").delete().eq("id", str(document_id)).execute()


# ── Re-ingest ─────────────────────────────────────────────────────────────────

@router.post("/{document_id}/reingest", status_code=status.HTTP_202_ACCEPTED)
async def reingest_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Re-trigger ingestion for a document stuck in 'error' or 'processing' status.
    Useful when a background task was interrupted by a process restart.
    """
    result = (
        supabase.table("documents")
        .select("id, embedding_status")
        .eq("id", str(document_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    supabase.table("documents").update(
        {"embedding_status": "pending"}
    ).eq("id", str(document_id)).execute()

    background_tasks.add_task(ingest_document, str(document_id))

    return {"message": "Re-ingestion triggered", "document_id": str(document_id)}