"""
Digikey OAuth2 Authentication

Manages the OAuth2 token lifecycle:
- Initial authorization flow (one-time, via CLI script)
- Automatic token refresh before each API call
- Token persistence in Supabase (table: tool_credentials)

Token storage schema (tool_credentials table):
  CREATE TABLE tool_credentials (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

Run this SQL once in Supabase to create the table:
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
DIGIKEY_AUTH_URL = "https://api.digikey.com/v1/oauth2/authorize"


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


async def _refresh_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a new access token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DIGIKEY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.DIGIKEY_CLIENT_ID,
                "client_secret": settings.DIGIKEY_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise DigikeyAuthError(
            f"Token refresh failed: {response.status_code} {response.text}"
        )

    data = response.json()
    data["expires_at"] = time.time() + int(data.get("expires_in", 1800))
    return data


async def get_access_token() -> str:
    """
    Return a valid Digikey access token, refreshing if necessary.
    Raises DigikeyAuthError if no token is stored (run authorize.py first).
    """
    token_data = _load_token()
    if not token_data:
        raise DigikeyAuthError(
            "No Digikey token found. Run: python integrations/digikey/authorize.py"
        )

    if _is_expired(token_data):
        refresh = token_data.get("refresh_token")
        if not refresh:
            raise DigikeyAuthError(
                "Token expired and no refresh_token available. Re-authorize."
            )
        token_data = await _refresh_token(refresh)
        _save_token(token_data)

    return token_data["access_token"]


def save_initial_token(token_data: dict) -> None:
    """Called once by authorize.py after the initial OAuth2 flow."""
    token_data["expires_at"] = time.time() + int(token_data.get("expires_in", 1800))
    _save_token(token_data)
