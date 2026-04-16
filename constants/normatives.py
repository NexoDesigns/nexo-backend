"""
Normative field constants.

Single source of truth for all string values used in normative context fields.
When adding or renaming values, change them here only.

These are NOT enforced as DB enums — the DB columns are TEXT/TEXT[].
These constants are used for:
  - Tag-filter logic in normative_service.py
  - API documentation / schema descriptions
  - Future: GET /normatives/options endpoint for frontend dropdowns
"""

# ── Industry ──────────────────────────────────────────────────────────────────
INDUSTRY_CONSUMER_ELECTRONICS = "consumer_electronics"
INDUSTRY_MEDICAL               = "medical"
INDUSTRY_AUTOMOTIVE            = "automotive"
INDUSTRY_INDUSTRIAL            = "industrial"
INDUSTRY_TELECOM               = "telecom"

ALL_INDUSTRIES: list[str] = [
    INDUSTRY_CONSUMER_ELECTRONICS,
    INDUSTRY_MEDICAL,
    INDUSTRY_AUTOMOTIVE,
    INDUSTRY_INDUSTRIAL,
    INDUSTRY_TELECOM,
]

# ── Client / user type ────────────────────────────────────────────────────────
CLIENT_TYPE_CONSUMER     = "consumer"
CLIENT_TYPE_PROFESSIONAL = "professional"
CLIENT_TYPE_CHILD        = "child"

ALL_CLIENT_TYPES: list[str] = [
    CLIENT_TYPE_CONSUMER,
    CLIENT_TYPE_PROFESSIONAL,
    CLIENT_TYPE_CHILD,
]

# ── User age range ────────────────────────────────────────────────────────────
AGE_RANGE_ADULT_ONLY = "adult_only"
AGE_RANGE_ALL_AGES   = "all_ages"
AGE_RANGE_CHILDREN   = "children"

ALL_AGE_RANGES: list[str] = [
    AGE_RANGE_ADULT_ONLY,
    AGE_RANGE_ALL_AGES,
    AGE_RANGE_CHILDREN,
]

# ── Selection source (for project_normatives table) ───────────────────────────
SELECTION_SOURCE_MANUAL              = "manual"
SELECTION_SOURCE_SUGGESTED_CONFIRMED = "suggested_confirmed"

ALL_SELECTION_SOURCES: list[str] = [
    SELECTION_SOURCE_MANUAL,
    SELECTION_SOURCE_SUGGESTED_CONFIRMED,
]
