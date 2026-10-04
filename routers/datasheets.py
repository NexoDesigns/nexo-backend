"""
Datasheets Router

The component catalog: the IC fact sheets engineers extracted, reviewed and
approved at datasheets.nexodesign.ai (repo datasheet_extractor). They belong
to no project — a component serves every design — and live in the
`datasheets` schema of this Supabase project.

Read-only here. The design agents (n8n, X-Api-Key) and the frontend (Bearer)
ask it whether an approved component meets what a design needs, so a part
the team already reviewed is preferred over one nobody has read.

    GET /datasheets/search?q=&manufacturer=&package=&temp_min=&temp_max=
                           &qualifications=&supply_v=&limit=
    GET /datasheets/by-part/{part_number}    the approved sheet covering it
    GET /datasheets/{sheet_id}               one approved sheet, facts included
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user_id_flexible
from core.supabase import get_supabase

router = APIRouter(prefix="/datasheets", tags=["Datasheets"])

SCHEMA = "datasheets"


def _catalog():
    """The catalog's schema. It must be among the project's exposed schemas
    (Supabase → API settings); anon is refused it, the service key is not."""
    return get_supabase().schema(SCHEMA)


def _run(query) -> list[dict[str, Any]]:
    try:
        return query.execute().data or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Datasheet catalog unavailable: {e}")


class CatalogEntry(BaseModel):
    """What a design agent needs to prefer a component: who it is and the
    ranges it works in. The whole sheet is one call away (/datasheets/{id})."""

    file_name: str
    gpn: str
    part_numbers: list[str]
    manufacturer: str | None = None
    package: str | None = None
    description: str | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    qualifications: list[str] = []
    rohs: bool | None = None
    supplies: list[dict[str, Any]] | None = None
    rank: float | None = None


class CatalogSearchResponse(BaseModel):
    results: list[CatalogEntry]
    count: int


@router.get("/search", response_model=CatalogSearchResponse)
def search_datasheets(
    q: str | None = Query(default=None, description="Words (what it is, parameter names) or the start of a part number"),
    manufacturer: str | None = Query(default=None, description="Manufacturer key, e.g. 'ti', 'analog'"),
    package: str | None = Query(default=None, description="Part of the package text, e.g. 'SOT-23', 'QFN'"),
    temp_min: float | None = Query(default=None, description="The part must work down to this (°C)"),
    temp_max: float | None = Query(default=None, description="…and up to this (°C)"),
    qualifications: list[str] | None = Query(default=None, description="Every one claimed, e.g. AEC-Q100"),
    supply_v: float | None = Query(default=None, description="A supply rail of the part accepts this voltage"),
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id_flexible),
):
    """
    Approved components that meet what a design asks for. Every filter is
    optional; the best matches for `q` come first.

    For n8n: call with the X-Api-Key header. A component found here has a
    reviewed fact sheet (pinout, external components, equations, limits):
    prefer it over an equivalent part without one.
    """
    params = {
        "q": q, "maker": manufacturer, "pkg": package, "min_temp": temp_min, "max_temp": temp_max,
        "quals": qualifications or None, "supply_v": supply_v, "max_results": limit,
    }
    rows = _run(_catalog().rpc("search_components", {k: v for k, v in params.items() if v is not None}))
    results = [CatalogEntry(**row) for row in rows]
    return CatalogSearchResponse(results=results, count=len(results))


@router.get("/by-part/{part_number}")
def datasheet_by_part(part_number: str, user_id: str = Depends(get_current_user_id_flexible)):
    """
    The approved sheet that covers an orderable part number: the exact
    number first, then one the datasheet lists with or without a packing
    suffix (BQ24075TRGT covers BQ24075TRGTR). 404 when the catalog has none.
    """
    rows = _run(_catalog().rpc("find_by_part", {"part": part_number}))
    if not rows:
        raise HTTPException(status_code=404, detail=f"No approved datasheet covers {part_number}")
    return rows[0]


@router.get("/{sheet_id}")
def datasheet_by_id(sheet_id: UUID, user_id: str = Depends(get_current_user_id_flexible)):
    """One approved sheet with its facts (what the design agents read)."""
    rows = _run(_catalog().table("approved_components").select("*").eq("id", str(sheet_id)).limit(1))
    if not rows:
        raise HTTPException(status_code=404, detail="No such approved datasheet")
    return rows[0]
