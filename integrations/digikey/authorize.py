"""
Digikey OAuth2 — Initial Authorization Script

Run this ONCE to get the first token pair (access + refresh).
After this, auth.py handles automatic refresh.

Usage:
  python integrations/digikey/authorize.py

Steps:
  1. Opens the Digikey authorization URL in your terminal.
  2. You open it in a browser, log in, and approve access.
  3. Digikey redirects to your redirect_uri with ?code=...
  4. Paste the full redirect URL here.
  5. The script exchanges the code for tokens and saves them.
"""

from __future__ import annotations

import asyncio
import os
import sys
import urllib.parse

import httpx

# Add project root to path so we can import from core/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.config import settings
from integrations.digikey.auth import (
    DIGIKEY_AUTH_URL,
    DIGIKEY_TOKEN_URL,
    save_initial_token,
)

REDIRECT_URI = "https://localhost"  # Must match what's registered in Digikey developer portal


def build_auth_url() -> str:
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": settings.DIGIKEY_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "manufacturing.catalog.products.v4.read",
    })
    return f"{DIGIKEY_AUTH_URL}?{params}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            DIGIKEY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.DIGIKEY_CLIENT_ID,
                "client_secret": settings.DIGIKEY_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise Exception(f"Token exchange failed: {response.status_code} {response.text}")

    return response.json()


async def main():
    auth_url = build_auth_url()
    print("\n=== Digikey OAuth2 Initial Authorization ===\n")
    print("1. Open this URL in your browser:\n")
    print(f"   {auth_url}\n")
    print("2. Log in and approve access.")
    print("3. You'll be redirected to a URL starting with https://localhost?code=...")
    print("4. Paste the FULL redirect URL below:\n")

    redirect_url = input("Redirect URL: ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        print("ERROR: Could not extract 'code' from URL.")
        sys.exit(1)

    print("\nExchanging code for tokens...")
    token_data = await exchange_code(code)
    save_initial_token(token_data)

    print("\n✅ Token saved to Supabase successfully.")
    print(f"   Access token expires in {token_data.get('expires_in', '?')} seconds.")
    print("   From now on, tokens refresh automatically.\n")


if __name__ == "__main__":
    asyncio.run(main())
