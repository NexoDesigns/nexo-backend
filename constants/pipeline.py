"""
Pipeline phase constants.

Single source of truth for the active phase order and related tuning values.
When adding/removing/reordering a phase, change it here — services/n8n_service.py
and routers/pipeline.py both read PHASE_ORDER from this module.
"""

# ── Active phase order ──────────────────────────────────────────────────────
# ic_naming_agent is intentionally absent: its work now happens inside
# architecture_agent's own n8n workflow. The pipeline_phases DB row is kept
# (not deleted) for historical phase_runs FK safety, but routers/pipeline.py
# filters the API response to this list, so it no longer appears in the UI.

# This is super important, it is used in endpoints to get info from supabase.
PHASE_ORDER = [
    "research",
    "ic_selection",
    "architecture_agent",
    "passive_components",
    "component_selection",
    "netlist",
]

# ── architecture-editor hand-off link ───────────────────────────────────────
EDITOR_LINK_PHASE_ID = "architecture_agent"
EDITOR_LINK_TTL_SECONDS = 8 * 60 * 60  # 8 hours — one engineering work session
