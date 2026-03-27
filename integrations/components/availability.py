"""
Availability Checker (Part 2 of the workflow)

Mirrors the A1-A12 block pattern from n8n:
  For each part number:
    1. Search Mouser and Digikey in parallel
    2. Filter for available parts
    3. Select cheapest between suppliers

Also handles the part selection logic from PartSelectionJS_A* nodes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from integrations.digikey.client import keyword_search as digikey_search
from integrations.digikey.client import filter_and_pick_cheapest as digikey_pick
from integrations.mouser.client import partnumber_search as mouser_search
from integrations.mouser.client import filter_and_pick_cheapest as mouser_pick


async def _check_single_part(part_number: str) -> dict[str, Any]:
    """
    Check availability of a single part number in both suppliers in parallel.
    Returns a merged result with the cheapest available option.
    """
    mouser_result, digikey_result = await asyncio.gather(
        _safe_mouser(part_number),
        _safe_digikey(part_number),
        return_exceptions=False,
    )

    mouser_part = mouser_pick(mouser_result, part_number) if mouser_result else None
    digikey_part = digikey_pick((digikey_result.get("Products") or []) if digikey_result else [])

    return _select_cheapest(part_number, mouser_part, digikey_part)


async def _safe_mouser(part_number: str) -> dict | None:
    try:
        return await mouser_search(part_number)
    except Exception:
        return None


async def _safe_digikey(part_number: str) -> dict | None:
    try:
        result = await digikey_search({
            "Keywords": part_number,
            "Limit": 10,
            "Offset": 0,
            "FilterOptionsRequest": {"SearchOptions": []},
            "SortOptions": {"Field": "QuantityAvailable", "SortOrder": "Descending"},
        })
        return result
    except Exception:
        return None


def _parse_price(price: Any) -> float | None:
    if price is None:
        return None
    try:
        return float(str(price).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _select_cheapest(
    part_number: str,
    mouser: dict | None,
    digikey: dict | None,
) -> dict[str, Any]:
    """
    Mirrors PartSelectionJS_A* logic:
    Priority: InStock > FactoryStock > cheapest price
    When both available: pick cheapest.
    """
    if not mouser and not digikey:
        return {"ManufacturerPartNumber": part_number, "numberOfResults": 0}

    if mouser and not digikey:
        return mouser

    if digikey and not mouser:
        return digikey

    # Both available — pick based on stock then price
    m_in_stock = mouser.get("InStock") is not None
    d_in_stock = digikey.get("InStock") is not None
    m_factory = mouser.get("FactoryStock") is not None
    d_factory = digikey.get("FactoryStock") is not None

    m_price = _parse_price(mouser.get("UnitPrice"))
    d_price = _parse_price(digikey.get("UnitPrice"))

    def prefer_digikey() -> dict:
        """Return digikey but add Digikey datasheet URL to mouser part if mouser wins."""
        return digikey

    def prefer_mouser() -> dict:
        result = dict(mouser)
        if digikey and digikey.get("DatasheetUrl"):
            result["DatasheetUrl"] = digikey["DatasheetUrl"]
        return result

    # Both in stock → cheapest
    if m_in_stock and d_in_stock:
        if d_price is not None and m_price is not None:
            return prefer_digikey() if d_price <= m_price else prefer_mouser()
        return prefer_digikey() if d_price is not None else prefer_mouser()

    if m_in_stock and not d_in_stock:
        return prefer_mouser()

    if d_in_stock and not m_in_stock:
        return prefer_digikey()

    # Neither in stock — try factory stock
    if m_factory and d_factory:
        if d_price is not None and m_price is not None:
            return prefer_digikey() if d_price <= m_price else prefer_mouser()

    if m_factory:
        return prefer_mouser()

    if d_factory:
        return prefer_digikey()

    # No stock anywhere — cheapest by price
    if d_price is not None and m_price is not None:
        return prefer_digikey() if d_price <= m_price else prefer_mouser()

    return prefer_digikey() if digikey else prefer_mouser()


async def check_availability(
    part_numbers: list[str],
    concurrency: int = 5,
) -> tuple[list[dict], list[dict]]:
    """
    Check availability for a list of part numbers.

    Args:
        part_numbers: List of MPN strings to check.
        concurrency: Max parallel requests (be kind to the APIs).

    Returns:
        (available, unavailable) — each is a list of part dicts.
        Mirrors the PartAvailabilityCheck_A* output structure.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def check_with_limit(mpn: str) -> dict:
        async with semaphore:
            return await _check_single_part(mpn)

    results = await asyncio.gather(
        *[check_with_limit(mpn) for mpn in part_numbers]
    )

    available = []
    unavailable = []

    for part in results:
        has_in_stock = part.get("InStock") is not None and part.get("InStock") != ""
        has_factory = part.get("FactoryStock") is not None and part.get("FactoryStock") != ""

        if has_in_stock or has_factory:
            available.append(part)
        else:
            unavailable.append(part)

    return available, unavailable
