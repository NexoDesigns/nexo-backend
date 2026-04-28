"""
Components Router

Exposes the component search + availability pipeline as a REST endpoint.
Can be called directly from the frontend or from n8n via HTTP Request node.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user_id
from integrations.components.availability import check_availability
from integrations.components.bom import build_bom

router = APIRouter(prefix="/components", tags=["Components"])

# ── BOM search ────────────────────────────────────────────────────────────────

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


# ── IC availability check ──────────────────────────────────────────────────────

_SUFFIX_RE = re.compile(r"^(.+?)\s+\(.+\)$")


def _clean_mpn(raw: str) -> str:
    """Strip trailing suffixes like ' (D)' from ic_naming_agent output."""
    m = _SUFFIX_RE.match(raw.strip())
    return m.group(1) if m else raw.strip()


class IcAvailabilityRequest(BaseModel):
    # Accepts the ic_naming_agent output directly: { "designA": ["MPN1", ...] }
    components: dict[str, list[str]]


class PartAvailabilityInfo(BaseModel):
    available: bool
    supplier: str | None = None
    unit_price: str | None = None
    currency: str | None = None
    in_stock: str | None = None
    factory_stock: str | None = None
    datasheet_url: str | None = None
    manufacturer: str | None = None


class IcAvailabilityResponse(BaseModel):
    # Keyed by cleaned MPN — frontend looks up each part across all designs
    parts: dict[str, PartAvailabilityInfo]


@router.post("/ic-availability", response_model=IcAvailabilityResponse)
async def check_ic_availability(
    body: IcAvailabilityRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Check real-time availability of IC part numbers from the ic_naming_agent phase.

    Accepts the ic_naming_agent output format: { "designA": ["MPN1", "MPN2 (D)"], ... }
    Strips any ' (D)' / ' (X)' suffixes, deduplicates across designs, then queries
    Mouser + Digikey in parallel.

    Returns a dict keyed by cleaned MPN with availability, supplier, and price info.
    The frontend uses this to show badges next to each part number in each design card.
    """
    if not body.components:
        raise HTTPException(status_code=400, detail="components cannot be empty")

    # Flatten all MPNs across designs, strip suffixes, deduplicate (preserve order)
    seen: set[str] = set()
    clean_mpns: list[str] = []
    for parts in body.components.values():
        for raw in parts:
            cleaned = _clean_mpn(raw)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                clean_mpns.append(cleaned)

    if not clean_mpns:
        raise HTTPException(status_code=400, detail="no valid part numbers found")

    try:
        available, unavailable = await check_availability(clean_mpns)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Availability check failed: {str(e)}",
        )

    parts: dict[str, PartAvailabilityInfo] = {}

    for part in available:
        mpn = part.get("ManufacturerPartNumber", "")
        if not mpn:
            continue
        parts[mpn] = PartAvailabilityInfo(
            available=True,
            supplier=part.get("Supplier"),
            unit_price=str(part["UnitPrice"]) if part.get("UnitPrice") is not None else None,
            currency=part.get("Currency"),
            in_stock=part.get("InStock"),
            factory_stock=part.get("FactoryStock"),
            datasheet_url=part.get("DatasheetUrl"),
            manufacturer=part.get("Manufacturer"),
        )

    for part in unavailable:
        mpn = part.get("ManufacturerPartNumber", "")
        if not mpn:
            continue
        parts[mpn] = PartAvailabilityInfo(available=False)

    return IcAvailabilityResponse(parts=parts)
