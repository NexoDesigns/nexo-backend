"""
Normative suggestion service.

Two-step approach:
  1. Tag-filter: fetch normative documents whose metadata.applicable_industries
     or metadata.applicable_countries overlaps with the project context.
  2. LLM ranking: POST the candidates + project context to an n8n webhook that
     uses a GPT mini agent to rank them and return relevance + reasoning.
     If N8N_NORMATIVES_SUGGEST_WEBHOOK_URL is not configured, falls back to
     returning the tag-filtered candidates without ranking.
"""

from typing import Any

import httpx

from core.config import settings
from core.supabase import get_supabase


async def suggest_normatives(project_id: str) -> list[dict[str, Any]]:
    """
    Returns a ranked list of normative suggestions for the given project.
    Each item is a dict with keys: document_id, name, metadata, relevance, reason.
    """
    supabase = get_supabase()
    print("called normatives/suggest")
    # ── Step 1: Load project normative context ────────────────────────────────
    project_result = (
        supabase.table("projects")
        .select(
            "normative_industry, normative_client_type, normative_user_age_range, "
            "normative_target_countries, normative_extra_context"
        )
        .eq("id", project_id)
        .single()
        .execute()
    )
    if not project_result.data:
        print("ERROR: project result.data is empty")
        raise ValueError(f"Project {project_id} not found")

    project = project_result.data
    industry = project.get("normative_industry") or ""
    countries = project.get("normative_target_countries") or []

    # ── Step 2: Fetch all ingested normative documents ────────────────────────
    docs_result = (
        supabase.table("documents")
        .select("id, name, metadata")
        .eq("type", "normative")
        .is_("project_id", "null")
        .eq("embedding_status", "done")
        .execute()
    )
    all_normatives = docs_result.data or []
    print("all normatives:", all_normatives)
    if not all_normatives:
        print("all normatives is EMPTY!!")
        return []

    # ── Step 3: Tag-filter ────────────────────────────────────────────────────
    def _matches(doc: dict) -> bool:
        meta = doc.get("metadata") or {}
        raw_industries = meta.get("applicable_industries") or []
        raw_countries = meta.get("applicable_countries") or []
        doc_industries = [raw_industries] if isinstance(raw_industries, str) else raw_industries
        doc_countries = [raw_countries] if isinstance(raw_countries, str) else raw_countries
        industry_match = not industry or industry in doc_industries
        country_match = (
            not doc_countries          # empty = global, always include
            or not countries           # project has no country filter
            or bool(set(countries) & set(doc_countries))
        )
        return industry_match or country_match

    candidates = [d for d in all_normatives if _matches(d)] or all_normatives
    print("candidates:", candidates)

    # ── Step 4: LLM ranking via n8n ───────────────────────────────────────────
    if not settings.N8N_NORMATIVES_SUGGEST_WEBHOOK_URL:
        return [
            {
                "document_id": d["id"],
                "name": d["name"],
                "metadata": d.get("metadata"),
                "relevance": None,
                "reason": None,
            }
            for d in candidates
        ]
    
    print("executing n8n")
    n8n_payload = {
        "project_context": {
            "industry": project.get("normative_industry"),
            "client_type": project.get("normative_client_type"),
            "user_age_range": project.get("normative_user_age_range"),
            "target_countries": project.get("normative_target_countries"),
            "extra_context": project.get("normative_extra_context"),
        },
        "candidates": [
            {
                "document_id": d["id"],
                "name": d["name"],
                "scope_summary": (d.get("metadata") or {}).get("scope_summary"),
                "standard_code": (d.get("metadata") or {}).get("standard_code"),
                "applicable_industries": (d.get("metadata") or {}).get("applicable_industries"),
                "applicable_countries": (d.get("metadata") or {}).get("applicable_countries"),
            }
            for d in candidates
        ],
    }
    print("llamando a n8n...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            settings.N8N_NORMATIVES_SUGGEST_WEBHOOK_URL,
            json=n8n_payload,
            headers={"X-N8N-Secret": settings.N8N_WEBHOOK_SECRET},
        )
        response.raise_for_status()
        ranked: list[dict] = response.json()  # [{ document_id, relevance, reason }, ...]

    print("respuesta del n8n:", ranked)
    # Merge n8n ranking with full doc data
    doc_map = {d["id"]: d for d in candidates}
    suggestions = []
    for item in ranked:
        doc_id = item.get("document_id")
        doc = doc_map.get(doc_id)
        if doc:
            suggestions.append({
                "document_id": doc_id,
                "name": doc["name"],
                "metadata": doc.get("metadata"),
                "relevance": item.get("relevance"),
                "reason": item.get("reason"),
            })
    return suggestions
