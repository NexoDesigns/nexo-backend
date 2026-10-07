from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PhaseSelectionUpsert(BaseModel):
    source_run_id: UUID
    selected_ids: list[str]


class PhaseSelection(BaseModel):
    project_id: UUID
    phase_id: str
    source_run_id: UUID
    selected_ids: list[str]
    updated_by: Optional[UUID]
    updated_at: datetime
