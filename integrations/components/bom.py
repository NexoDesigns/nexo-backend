"""
BOM Builder — orchestrates the full 3-part component selection pipeline.

Part 1: Search passives by category in Digikey
Part 2: Check availability of all part numbers (ICs + found passives) in Mouser+Digikey
Part 3: Merge into final BOM

Entry point: build_bom()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.components.availability import check_availability
from integrations.components.classifier import classify
from integrations.components import digikey_queries as dq
from integrations.digikey.client import keyword_search, filter_and_pick_cheapest

logger = logging.getLogger(__name__)


async def _search_digikey_batch(
    searches: list[dict],
    component_refs: list[str],
    concurrency: int = 5,
) -> list[dict | None]:
    """
    Run a batch of Digikey searches, one per component, with concurrency limit.
    Returns list of cheapest picks (or None if not found), in same order as input.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def search_one(body: dict) -> dict | None:
        async with semaphore:
            try:
                result = await keyword_search(body)
                products = result.get("Products") or []
                return filter_and_pick_cheapest(products)
            except Exception as e:
                logger.warning(f"Digikey search failed: {e}")
                return None

    return await asyncio.gather(*[search_one(s) for s in searches])


async def _search_passives(
    classified: dict[str, list[dict]],
) -> dict[str, list[dict | None]]:
    """
    Run Digikey category searches for all passive component groups in parallel.
    Returns dict of group_name → list of found parts (None = not found).
    """
    tasks: dict[str, tuple[list[dict], list[dict]]] = {}

    mapping = {
        "resistors": (dq.build_resistor_searches, classified["resistors"]),
        "shunt_resistors": (dq.build_shunt_searches, classified["shunt_resistors"]),
        "capacitors": (dq.build_capacitor_searches, classified["capacitors"]),
        "electrolytic_capacitors": (dq.build_electrolytic_searches, classified["electrolytic_capacitors"]),
        "inductors": (dq.build_inductor_searches, classified["inductors"]),
        "fuses": (dq.build_fuse_searches, classified["fuses"]),
        "tvs_diodes": (dq.build_tvs_searches, classified["tvs_diodes"]),
        "diodes": (dq.build_diode_searches, classified["diodes"]),
        "zeners": (dq.build_zener_searches, classified["zeners"]),
        "mosfets": (dq.build_mosfet_searches, classified["mosfets"]),
        "transformers": (dq.build_transformer_searches, classified["transformers"]),
        "connectors": (dq.build_connector_searches, classified["connectors"]),
    }

    results: dict[str, list[dict | None]] = {}

    for group, (builder_fn, components) in mapping.items():
        if not components:
            results[group] = []
            continue
        searches = builder_fn(components)
        found = await _search_digikey_batch(searches, [c.get("ref", "") for c in components])
        results[group] = found

    return results


def _merge_passives_with_refs(
    classified: dict[str, list[dict]],
    found: dict[str, list[dict | None]],
) -> list[dict]:
    """
    Merge Digikey search results back with the original component refs.
    Returns a flat list of components with real part numbers where found.
    """
    merged = []

    group_order = [
        "resistors", "shunt_resistors", "capacitors", "electrolytic_capacitors",
        "inductors", "fuses", "tvs_diodes", "diodes", "zeners",
        "mosfets", "transformers", "connectors",
    ]

    for group in group_order:
        components = classified.get(group, [])
        results = found.get(group, [])

        for comp, result in zip(components, results):
            if result and result.get("ManufacturerPartNumber"):
                merged.append({
                    **comp,
                    "ManufacturerPartNumber": result["ManufacturerPartNumber"],
                    "PartNumber": result.get("PartNumber"),
                    "UnitPrice": result.get("UnitPrice"),
                    "Supplier": result.get("Supplier"),
                    "InStock": result.get("InStock"),
                    "FactoryStock": result.get("FactoryStock"),
                    "DatasheetUrl": result.get("DatasheetUrl"),
                })
            else:
                # Keep original component even if no part was found
                merged.append({**comp, "ManufacturerPartNumber": None})

    return merged


def _extract_ic_part_numbers(components: list[dict]) -> list[str]:
    """Extract MPNs of ICs (refs starting with U) that have real part numbers."""
    return [
        c["partNumber"]
        for c in components
        if (c.get("ref") or "").upper().startswith("U")
        and c.get("partNumber")
        and c["partNumber"].lower() not in (
            "resistor", "capacitor", "inductor", "fuse", "tvs diode",
            "diode", "zener diode", "mosfet", "transformer", "connector",
            "shunt resistor",
        )
    ]


async def build_bom(
    components: list[dict],
) -> dict[str, Any]:
    """
    Full pipeline entry point.

    Args:
        components: Raw component list from the agent (mixed ICs + passives).

    Returns:
        {
          "available": [...],    # components confirmed available (with price/supplier)
          "unavailable": [...],  # components not found or out of stock
          "summary": {...}       # counts by group
        }
    """
    # Step 1: Classify passives
    classified = classify(components)

    # Step 2: Search passives by category in Digikey
    logger.info("Searching passives in Digikey...")
    found_passives = await _search_passives(classified)

    # Step 3: Merge passives with their real part numbers
    passives_with_mpns = _merge_passives_with_refs(classified, found_passives)

    # Step 4: Collect all MPNs to verify (ICs + found passives)
    ic_mpns = _extract_ic_part_numbers(components)
    passive_mpns = [
        p["ManufacturerPartNumber"]
        for p in passives_with_mpns
        if p.get("ManufacturerPartNumber")
    ]
    all_mpns = list(dict.fromkeys(ic_mpns + passive_mpns))  # dedup, preserve order

    # Step 5: Check availability of all MPNs in Mouser + Digikey
    logger.info(f"Checking availability for {len(all_mpns)} part numbers...")
    available_parts, unavailable_parts = await check_availability(all_mpns)

    # Step 6: Enrich available parts with ref info from original component list
    ref_map = {c.get("partNumber"): c.get("ref") for c in components}
    for part in available_parts:
        mpn = part.get("ManufacturerPartNumber")
        if mpn and mpn in ref_map:
            part["ref"] = ref_map[mpn]

    return {
        "available": available_parts,
        "unavailable": unavailable_parts,
        "summary": {
            "total_parts": len(all_mpns),
            "available_count": len(available_parts),
            "unavailable_count": len(unavailable_parts),
            "passive_groups": {
                group: len(comps) for group, comps in classified.items() if comps
            },
        },
    }
