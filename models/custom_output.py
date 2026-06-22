from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class CustomOutputItemCreate(BaseModel):
    source_item_id: str
    source_item_label: str
    data: dict[str, Any]


class CustomOutputItemUpdate(BaseModel):
    data: dict[str, Any]


class CustomOutputItem(BaseModel):
    id: UUID
    project_id: UUID
    phase_id: str
    source_run_id: UUID
    source_item_id: str
    source_item_label: str
    data: dict[str, Any]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime