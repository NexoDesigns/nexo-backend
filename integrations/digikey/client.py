"""
Digikey API Client

Wraps the Digikey Products v4 keyword search endpoint.
All calls go through auth.py which handles token refresh automatically.
"""

from __future__ import annotations

import httpx

from core.config import settings
from integrations.digikey.auth import get_access_token

DIGIKEY_SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"


async def keyword_search(search_body: dict) -> dict:
    """
    POST to Digikey keyword search endpoint.
    Returns the full response JSON.

    search_body follows the Digikey v4 FilterOptionsRequest schema,
    as constructed by integrations/components/digikey_queries.py
    """
    token = await get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": settings.DIGIKEY_CLIENT_ID,
        "X-DIGIKEY-Locale-Site": "ES",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "EUR",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DIGIKEY_SEARCH_URL,
            json=search_body,
            headers=headers,
        )

    if response.status_code == 401:
        # Token may have just expired between check and request — retry once
        from integrations.digikey.auth import _load_token, _refresh_token, _save_token
        stored = _load_token()
        if stored and stored.get("refresh_token"):
            new_token = await _refresh_token(stored["refresh_token"])
            _save_token(new_token)
            headers["Authorization"] = f"Bearer {new_token['access_token']}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    DIGIKEY_SEARCH_URL,
                    json=search_body,
                    headers=headers,
                )

    response.raise_for_status()
    return response.json()


def filter_and_pick_cheapest(products: list[dict]) -> dict | None:
    """
    From a list of Digikey product results, return the cheapest one
    that has stock and is not obsolete.
    Mirrors the Filter* JS nodes from the original n8n workflow.
    """
    if not products:
        return None

    cleaned = []
    for product in products:
        variations = product.get("ProductVariations") or []
        unit_price = None
        if variations:
            pricing = variations[0].get("StandardPricing") or []
            if pricing:
                unit_price = pricing[0].get("UnitPrice")

        qty_available = product.get("QuantityAvailable", 0) or 0
        manufacturer_qty = product.get("ManufacturerPublicQuantity", 0) or 0
        status = (product.get("ProductStatus") or {}).get("Status", "")

        if status in ("Obsolete", "Discontinued at DigiKey"):
            continue
        if unit_price is None:
            continue

        try:
            price_num = float(unit_price)
        except (TypeError, ValueError):
            continue

        cleaned.append({
            "Manufacturer": (product.get("Manufacturer") or {}).get("Name"),
            "ManufacturerPartNumber": product.get("ManufacturerProductNumber"),
            "PartNumber": (
                variations[0].get("DigiKeyProductNumber") if variations else None
            ),
            "InStock": str(qty_available) if qty_available > 0 else None,
            "FactoryStock": str(manufacturer_qty) if manufacturer_qty > 0 else None,
            "UnitPrice": str(unit_price),
            "PriceNumber": price_num,
            "Currency": "EUR",
            "Supplier": "Digikey",
            "DatasheetUrl": product.get("DatasheetUrl"),
        })

    if not cleaned:
        return None

    # Prefer parts with InStock; fall back to all if none have stock
    in_stock = [p for p in cleaned if p["InStock"] is not None]
    pool = in_stock if in_stock else cleaned

    cheapest = min(pool, key=lambda p: p["PriceNumber"])
    cheapest.pop("PriceNumber", None)
    return cheapest
