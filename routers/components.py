"""
Components Router

Exposes the component search + availability pipeline as a REST endpoint.
Can be called directly from the frontend or from n8n via HTTP Request node.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user_id
from integrations.components.bom import build_bom

router = APIRouter(prefix="/components", tags=["Components"])


class ComponentSearchRequest(BaseModel):
    components: list[dict[str, Any]]


class ComponentSearchResponse(BaseModel):
    available: list[dict[str, Any]]
    unavailable: list[dict[str, Any]]
    summary: dict[str, Any]


@router.post("/search", response_model=ComponentSearchResponse)
async def search_components(
    body: ComponentSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Full component search pipeline:
      1. Classifies passives by type
      2. Searches each type in Digikey by category + specs
      3. Verifies all part numbers (ICs + passives) in Mouser + Digikey
      4. Returns available and unavailable parts with price and supplier

    Input: list of components from the Component Selection agent.
    Each component has at minimum: ref, partNumber, and type-specific fields.

    ICs (ref starting with 'U') must already have a real partNumber.
    Passives (resistors, capacitors, etc.) use 'resistor', 'capacitor', etc.
    as their partNumber — these are looked up in Digikey.

    This endpoint is designed to be called both from the frontend
    and from n8n workflows via HTTP Request node.

    For n8n: include the Authorization header with the user JWT,
    or use a service token if calling from a workflow without user context.
    """
    if not body.components:
        raise HTTPException(status_code=400, detail="components list cannot be empty")

    try:
        result = await build_bom(body.components)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Component search pipeline failed: {str(e)}",
        )

    return result
