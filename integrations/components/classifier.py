"""
Component Classifier

Mirrors the Search* (first set) JS nodes from the n8n workflow.
Given the full component list, splits them into typed groups for
the Digikey category search.

Component types recognised (matching the partNumber field values from the agent):
  resistor, shunt resistor, capacitor, inductor, fuse, tvs diode,
  diode, zener diode, mosfet, transformer, connector
"""

from __future__ import annotations

from typing import Any


def classify(components: list[dict]) -> dict[str, list[dict]]:
    """
    Split a flat component list into groups by type.
    ICs (ref starts with 'U') are excluded — they already have part numbers.

    Returns a dict:
      {
        "resistors": [...],
        "shunt_resistors": [...],
        "capacitors": [...],
        "electrolytic_capacitors": [...],
        "inductors": [...],
        "fuses": [...],
        "tvs_diodes": [...],
        "diodes": [...],
        "zeners": [...],
        "mosfets": [...],
        "transformers": [...],
        "connectors": [...],
      }
    """
    groups: dict[str, list[dict]] = {
        "resistors": [],
        "shunt_resistors": [],
        "capacitors": [],
        "electrolytic_capacitors": [],
        "inductors": [],
        "fuses": [],
        "tvs_diodes": [],
        "diodes": [],
        "zeners": [],
        "mosfets": [],
        "transformers": [],
        "connectors": [],
    }

    for comp in components:
        ref = (comp.get("ref") or "").upper()
        part_number = (comp.get("partNumber") or "").lower()

        # Skip ICs — they come with a real part number from the LLM agent
        if ref.startswith("U"):
            continue

        # Remove role/group — keep only technical fields + ref
        clean = {
            k: v for k, v in comp.items()
            if k not in ("role", "group")
        }

        if part_number == "shunt resistor":
            groups["shunt_resistors"].append(clean)
        elif part_number == "resistor":
            groups["resistors"].append(clean)
        elif part_number == "capacitor":
            cap_type = (comp.get("type") or "").lower()
            if "electrolytic" in cap_type:
                groups["electrolytic_capacitors"].append(clean)
            else:
                groups["capacitors"].append(clean)
        elif part_number == "inductor":
            groups["inductors"].append(clean)
        elif part_number == "fuse":
            groups["fuses"].append(clean)
        elif part_number == "tvs diode":
            groups["tvs_diodes"].append(clean)
        elif part_number == "diode":
            groups["diodes"].append(clean)
        elif part_number == "zener diode":
            groups["zeners"].append(clean)
        elif part_number == "mosfet":
            groups["mosfets"].append(clean)
        elif part_number == "transformer":
            groups["transformers"].append(clean)
        elif part_number == "connector":
            groups["connectors"].append(clean)

    return groups
