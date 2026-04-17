from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class NormativeRunCreate(BaseModel):
    custom_prompt: Optional[str] = None


class NormativeRunComplete(BaseModel):
    output_data: Optional[dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    n8n_execution_id: Optional[str] = None
    error_message: Optional[str] = None


class NormativeRunSummary(BaseModel):
    id: UUID
    run_number: int
    status: str
    custom_prompt: Optional[str]
    output_data: Optional[dict[str, Any]]
    n8n_execution_id: Optional[str]
    error_message: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]


class NormativeRunTriggerResponse(BaseModel):
    run_id: UUID
    run_number: int
    status: str  # 'running'
