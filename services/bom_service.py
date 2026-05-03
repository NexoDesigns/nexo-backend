"""
BOM Service — runs build_bom() on a component_selection output and persists the result.
Used as a background task from both the n8n callback and the manual recheck endpoint.
"""

import logging

from integrations.components.bom import build_bom
from core.supabase import get_supabase

logger = logging.getLogger(__name__)


async def run_component_bom(run_id: str, output_payload: dict) -> None:
    """
    Extract passive components from a component_selection output_payload,
    run the full BOM pipeline (Digikey search + availability check),
    and persist the result to phase_runs.bom_result.
    """
    try:
        data = output_payload
        if isinstance(data, list):
            data = data[0] if data else {}
        components = (data.get("designcomponents") or {}).get("components") or []
        if not components:
            logger.info(f"BOM check skipped for run {run_id}: no components in output")
            return
        bom_result = await build_bom(components)
        supabase = get_supabase()
        supabase.table("phase_runs").update({"bom_result": bom_result}).eq("id", run_id).execute()
        logger.info(
            f"BOM check completed for run {run_id}: "
            f"{bom_result['summary']['available_count']}/{bom_result['summary']['total_parts']} available"
        )
    except Exception as e:
        logger.warning(f"BOM check failed for run {run_id}: {e}")
