from datetime import datetime
from typing import Optional
from uuid import UUID
import json

from pydantic import BaseModel, field_validator


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    client_name: Optional[str] = None
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # 'active' | 'archived' | 'completed'


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    client_name: Optional[str]
    description: Optional[str]
    status: str
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime


# ── Project Requirements ──────────────────────────────────────────────────────

class RequirementsCreate(BaseModel):
    input_voltage_min: Optional[float] = None
    input_voltage_max: Optional[float] = None
    output_voltage: Optional[float] = None
    max_current: Optional[float] = None
    max_ripple_percent: Optional[float] = None
    temperature_range: Optional[str] = None
    main_function: Optional[str] = None
    constraints: Optional[str] = None
    kpis: Optional[str] = None
    notes: Optional[str] = None
    raw_json: Optional[dict] = None


class RequirementsResponse(BaseModel):
    id: UUID
    project_id: UUID
    input_voltage_min: Optional[float]
    input_voltage_max: Optional[float]
    output_voltage: Optional[float]
    max_current: Optional[float]
    max_ripple_percent: Optional[float]
    temperature_range: Optional[str]
    main_function: Optional[str]
    constraints: Optional[str]
    kpis: Optional[str]
    notes: Optional[str]
    raw_json: Optional[dict]
    created_at: datetime