from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


# ── Run trigger ───────────────────────────────────────────────────────────────

class RunCreate(BaseModel):
    """
    Body sent by the frontend when triggering a phase execution.
    custom_inputs is free-form: each phase has different input fields.
    use_perplexity is only relevant for phase_id='research'.
    """
    custom_inputs: Optional[dict[str, Any]] = None
    use_perplexity: Optional[bool] = None


# ── Run responses ─────────────────────────────────────────────────────────────

class RunSummary(BaseModel):
    """Lightweight run representation for list views."""
    id: UUID
    run_number: int
    status: str  # 'pending' | 'running' | 'completed' | 'failed'
    created_by: Optional[UUID]
    created_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    llm_tokens_used: Optional[int]
    notes: Optional[str] = None


class RunDetail(BaseModel):
    """Full run detail including all payloads."""
    id: UUID
    project_id: UUID
    phase_id: str
    run_number: int
    status: str
    input_payload: Optional[dict[str, Any]]
    output_payload: Optional[dict[str, Any]]
    rag_context: Optional[dict[str, Any]]
    n8n_execution_id: Optional[str]
    error_message: Optional[str]
    duration_seconds: Optional[int]
    llm_tokens_used: Optional[int]
    notes: Optional[str] = None
    created_by: Optional[UUID]
    created_at: datetime
    completed_at: Optional[datetime]


class RunTriggerResponse(BaseModel):
    """Returned immediately after triggering a run."""
    run_id: UUID
    run_number: int
    status: str


# ── Run notes update ──────────────────────────────────────────────────────────

class RunNotesUpdate(BaseModel):
    notes: Optional[str] = None


# ── n8n callback ──────────────────────────────────────────────────────────────

class N8nCallbackBody(BaseModel):
    run_id: UUID
    status: str  # 'completed' | 'failed'
    output_payload: Optional[dict[str, Any]] = None
    n8n_execution_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None