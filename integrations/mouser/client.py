"""
Mouser API Client

Mouser uses simple query-string API key authentication.
No OAuth2, no token refresh needed.
"""

from __future__ import annotations

import httpx

from core.config import settings

MOUSER_SEARCH_URL = "https://api.mouser.com/api/v1/search/partnumber"


async def partnumber_search(part_number: str) -> dict:
    """
    Search Mouser by exact part number.
    Returns the full SearchResults response.
    """
    url = f"{MOUSER_SEARCH_URL}?apiKey={settings.MOUSER_API_KEY}"

    body = {
        "SearchByPartRequest": {
            "mouserPartNumber": part_number,
            "partSearchOptions": "Exact",
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
        )

    response.raise_for_status()
    return response.json()


def filter_and_pick_cheapest(
    search_result: dict,
    original_part_number: str,
) -> dict | None:
    """
    From a Mouser SearchResults response, return the cheapest part
    that has stock.
    Mirrors MouserFilterJS_A* nodes from the original n8n workflow.
    """
    parts = (search_result.get("SearchResults") or {}).get("Parts") or []

    if not parts:
        return None

    mapped = []
    for part in parts:
        price_breaks = part.get("PriceBreaks") or []
        price_break = next(
            (pb for pb in price_breaks if int(pb.get("Quantity", 0)) == 1),
            price_breaks[0] if price_breaks else None,
        )

        raw_price = (price_break or {}).get("Price")
        if raw_price:
            unit_price_str = raw_price.replace("€", "").replace(" ", "").replace(",", ".")
        else:
            unit_price_str = None

        try:
            price_num = float(unit_price_str) if unit_price_str else None
        except ValueError:
            price_num = None

        availability_in_stock = part.get("AvailabilityInStock", 0) or 0
        factory_stock = part.get("FactoryStock", 0) or 0

        in_stock = str(availability_in_stock) if availability_in_stock > 0 else None
        factory = str(factory_stock) if factory_stock > 0 else None

        mapped.append({
            "Manufacturer": part.get("Manufacturer"),
            "ManufacturerPartNumber": original_part_number,
            "PartNumber": part.get("MouserPartNumber"),
            "InStock": in_stock,
            "FactoryStock": factory,
            "UnitPrice": unit_price_str,
            "PriceNumber": price_num,
            "Currency": (price_break or {}).get("Currency"),
            "Supplier": "Mouser",
        })

    if not mapped:
        return None

    in_stock_parts = [p for p in mapped if p["InStock"] is not None]
    pool = in_stock_parts if in_stock_parts else mapped

    # Filter out parts with no price
    pool_with_price = [p for p in pool if p["PriceNumber"] is not None]
    if not pool_with_price:
        pool_with_price = pool

    cheapest = min(pool_with_price, key=lambda p: p["PriceNumber"] or float("inf"))
    cheapest.pop("PriceNumber", None)
    return cheapest
