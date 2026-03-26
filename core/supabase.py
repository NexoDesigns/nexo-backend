"""
Supabase client — singleton pattern.

Using the service key (not the anon key) because all requests go through
FastAPI, which has already verified the user's JWT before reaching Supabase.
The service key bypasses RLS, which is fine for a single-tenant MVP.
When multi-tenancy is needed, switch to per-request clients with the user's JWT.
"""

from functools import lru_cache

from supabase import Client, create_client

from core.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """
    Returns a cached Supabase client.
    lru_cache(maxsize=1) ensures a single instance is reused across requests.
    FastAPI's Depends() calls this function; the result is cached at module level.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)