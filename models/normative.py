from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


class NormativeMetadata(BaseModel):
    """Stored in documents.metadata for type='normative'."""
    standard_code: Optional[str] = None          # e.g. "IEC 62368-1"
    standard_version: Optional[str] = None        # e.g. "3rd Edition 2023"
    issuing_body: Optional[str] = None            # "IEC", "UL", "ISO"...
    applicable_industries: Optional[List[str]] = None  # ["consumer_electronics"]
    applicable_countries: Optional[List[str]] = None   # ["ES", "DE"] or [] = global
    applicable_user_types: Optional[List[str]] = None  # ["consumer", "professional"]
    scope_summary: Optional[str] = None
    source_url: Optional[str] = None


class NormativeDocumentResponse(BaseModel):
    id: UUID
    name: str
    storage_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    embedding_status: str
    metadata: Optional[dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: datetime


class ProjectNormativesUpdateRequest(BaseModel):
    document_ids: List[UUID]
    selection_source: str = "manual"  # 'manual' | 'suggested_confirmed'


class NormativeSuggestion(BaseModel):
    document_id: UUID
    name: str
    metadata: Optional[dict[str, Any]] = None
    relevance: Optional[str] = None   # 'mandatory' | 'recommended'
    relevance_reason: str | None = None  # no "reason"
    standard_code: str | None = None
    score: float | None = None


class NormativeSuggestResponse(BaseModel):
    suggestions: List[NormativeSuggestion]


# Decision-tree answers: questionId → list of selected option values
DecisionTreeAnswers = dict[str, list[str]]


class DecisionTreeResponse(BaseModel):
    answers: DecisionTreeAnswers


class DecisionTreeSaveRequest(BaseModel):
    answers: DecisionTreeAnswers
