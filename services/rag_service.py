"""
RAG Service

Converts a text query into an embedding and retrieves the most
semantically similar document chunks from pgvector.

Phase-specific query construction: each pipeline phase needs context
about different aspects of the design, so we build targeted queries
rather than using the raw user input as-is.
"""

from typing import Any, Optional

from core.supabase import get_supabase
from services.embedding_service import get_embedding

# Default number of chunks to retrieve per RAG query
DEFAULT_TOP_K = 5

# Phase-specific query templates.
# These guide the semantic search toward the most relevant information
# for each stage of the electronics design pipeline.
PHASE_QUERY_TEMPLATES = {
    "research": (
        "circuit design concept {main_function} {output_voltage}V {max_current}A "
        "topology reference schematic"
    ),
    "ic_selection": (
        "integrated circuit IC {main_function} switching converter "
        "{output_voltage}V {max_current}A datasheet specifications"
    ),
    "component_selection": (
        "passive components inductor capacitor resistor {main_function} "
        "buck converter BOM manufacturer"
    ),
    "netlist": (
        "netlist schematic connections pinout {main_function} "
        "{output_voltage}V circuit implementation"
    ),
}


def _build_phase_query(
    phase_id: str,
    requirements: Optional[dict],
    custom_inputs: Optional[dict],
) -> str:
    """
    Build a targeted search query for the given phase.
    Falls back to a generic query if requirements are missing.
    """
    template = PHASE_QUERY_TEMPLATES.get(phase_id, "{main_function} electronics design")

    # Extract values from requirements, with safe defaults
    req = requirements or {}
    params = {
        "main_function": req.get("main_function", "power conversion"),
        "output_voltage": req.get("output_voltage", ""),
        "max_current": req.get("max_current", ""),
        "input_voltage_min": req.get("input_voltage_min", ""),
        "input_voltage_max": req.get("input_voltage_max", ""),
        "temperature_range": req.get("temperature_range", ""),
    }

    query = template.format(**params).strip()

    # Append any custom input context that might help narrow the search
    if custom_inputs:
        extra = " ".join(str(v) for v in custom_inputs.values() if v)
        if extra:
            query = f"{query} {extra}"

    return query


async def search(
    query: str,
    project_id: Optional[str] = None,
    type_filter: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """
    Semantic search over document_chunks.

    Args:
        query: Natural language search query.
        project_id: If provided, includes both project-specific and global docs.
                    If None, searches all docs.
        type_filter: Optional document type filter ('datasheet', 'project_output', etc.)
        top_k: Number of results to return.

    Returns:
        List of chunk dicts with fields: id, document_id, content, similarity, metadata.
    """
    embedding = await get_embedding(query)

    supabase = get_supabase()

    rpc_params: dict[str, Any] = {
        "query_embedding": embedding,
        "match_count": top_k,
    }
    if project_id:
        rpc_params["filter_project_id"] = project_id
    if type_filter:
        rpc_params["filter_type"] = type_filter

    result = supabase.rpc("search_documents", rpc_params).execute()
    return result.data or []


async def build_rag_context_for_phase(
    phase_id: str,
    project_id: str,
    requirements: Optional[dict],
    custom_inputs: Optional[dict],
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """
    High-level function used by n8n_service.py.
    Builds a phase-specific query and returns structured RAG context.

    Returns a dict that is serialized into the n8n payload as 'rag_context'.
    The structure is intentionally verbose so n8n prompts can reference
    individual chunks with their similarity scores.
    """
    query = _build_phase_query(phase_id, requirements, custom_inputs)

    try:
        chunks = await search(
            query=query,
            project_id=project_id,
            top_k=top_k,
        )
    except Exception as e:
        # RAG failure must never block a pipeline execution.
        # Log the error and return empty context.
        import logging
        logging.getLogger(__name__).warning(
            f"RAG search failed for phase={phase_id} project={project_id}: {e}. "
            "Proceeding without RAG context."
        )
        chunks = []

    return {
        "query": query,
        "retrieved_chunks": chunks,
        "total_retrieved": len(chunks),
    }