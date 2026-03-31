from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RequirementsRunCreate(BaseModel):
    custom_prompt: Optional[str] = None


class RequirementsRunComplete(BaseModel):
    output_drive_url: str
    output_drive_file_id: str
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None


class RequirementsRunSummary(BaseModel):
    id: UUID
    run_number: int
    status: str
    custom_prompt: Optional[str]
    input_drive_url: Optional[str]
    output_drive_url: Optional[str]
    output_drive_file_id: Optional[str]
    error_message: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]


class RequirementsRunTriggerResponse(BaseModel):
    run_id: UUID
    run_number: int
    status: str  # 'running'
