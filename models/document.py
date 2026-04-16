from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


ALLOWED_DOCUMENT_TYPES = (
    "datasheet",
    "manufacturer_list",
    "project_output",
    "design_note",
    "reference_schematic",
    "other",
    "normative",
)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".md"}


class DocumentResponse(BaseModel):
    id: UUID
    name: str
    type: str
    source: Optional[str]
    project_id: Optional[UUID]
    storage_path: str
    file_size_bytes: Optional[int]
    mime_type: Optional[str]
    embedding_status: str
    metadata: Optional[dict[str, Any]]
    created_by: Optional[UUID]
    created_at: datetime


class RAGSearchRequest(BaseModel):
    query: str
    project_id: Optional[str] = None
    type_filter: Optional[str] = None
    top_k: int = 5
    document_ids: Optional[List[UUID]] = None


class RAGSearchResult(BaseModel):
    query: str
    results: list[dict[str, Any]]
    total: int