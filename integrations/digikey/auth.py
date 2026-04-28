"""
Digikey OAuth2 Authentication — Client Credentials Flow

Uses client_id + client_secret to get tokens automatically.
No browser authorization needed. Token is cached in Supabase
and refreshed automatically before each API call.

Token storage schema (tool_credentials table):
  CREATE TABLE IF NOT EXISTS tool_credentials (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from core.config import settings
from core.supabase import get_supabase

DIGIKEY_TOKEN_KEY = "digikey_oauth2"
DIGIKEY_TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"


class DigikeyAuthError(Exception):
    pass


def _load_token() -> Optional[dict]:
    """Load stored token from Supabase."""
    supabase = get_supabase()
    try:
        result = (
            supabase.table("tool_credentials")
            .select("value")
            .eq("key", DIGIKEY_TOKEN_KEY)
            .single()
            .execute()
        )
        return result.data["value"] if result.data else None
    except Exception:
        return None


def _save_token(token_data: dict) -> None:
    """Persist token to Supabase."""
    supabase = get_supabase()
    supabase.table("tool_credentials").upsert({
        "key": DIGIKEY_TOKEN_KEY,
        "value": token_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def _is_expired(token_data: dict, buffer_seconds: int = 120) -> bool:
    """Return True if the token expires within buffer_seconds."""
    expires_at = token_data.get("expires_at", 0)
    return time.time() >= (expires_at - buffer_seconds)


async def _fetch_token() -> dict:
    """Fetch a new access token using client credentials."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DIGIKEY_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.DIGIKEY_CLIENT_ID,
                "client_secret": settings.DIGIKEY_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise DigikeyAuthError(
            f"Token fetch failed: {response.status_code} {response.text}"
        )

    data = response.json()
    data["expires_at"] = time.time() + int(data.get("expires_in", 1800))
    return data


async def get_access_token() -> str:
    """
    Return a valid Digikey access token, fetching a new one if expired.
    Uses client credentials flow — no user authorization needed.
    """
    token_data = _load_token()

    if not token_data or _is_expired(token_data):
        token_data = await _fetch_token()
        _save_token(token_data)

    return token_data["access_token"]
