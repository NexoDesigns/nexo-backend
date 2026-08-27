"""
JWT extraction from Supabase Auth tokens.
MVP approach: decode without signature verification to extract user_id.
When scaling to SaaS, replace with full RS256 verification against Supabase public key.
"""

import base64
import json
import time
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt as pyjwt

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_jwt_payload(token: str) -> dict:
    """
    Decode the JWT payload without verifying the signature.
    Supabase JWTs are HS256 signed — verification requires the JWT secret,
    which lives server-side in Supabase. For this MVP we trust the token
    structurally and extract the subject (user_id).
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")

        # JWT uses base64url encoding without padding
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency. Extracts user_id (sub claim) from the Bearer token.
    Use as: user_id: str = Depends(get_current_user_id)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_jwt_payload(credentials.credentials)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Basic expiration check
    import time
    exp = payload.get("exp")
    if exp and time.time() > exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


def get_current_user_id_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(default=None),
) -> str:
    """
    FastAPI dependency for service-to-service calls (e.g. n8n).
    Accepts either:
      - X-Api-Key header with the configured N8N_SERVICE_API_KEY (static, never expires)
      - Bearer JWT (standard user auth)
    """
    from core.config import settings

    if x_api_key is not None:
        if not settings.N8N_SERVICE_API_KEY or x_api_key != settings.N8N_SERVICE_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        if not settings.N8N_SERVICE_USER_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="N8N_SERVICE_USER_ID not configured",
            )
        return settings.N8N_SERVICE_USER_ID

    return get_current_user_id(credentials)


# ── architecture-editor hand-off link ───────────────────────────────────────
#
# The System Diagram App (architecture-editor) is a separate static site
# (embedded in an iframe or opened in its own tab) that calls this backend
# cross-origin. Forwarding the user's real Supabase session JWT to it would
# expose a long-lived, broad-scope credential in a URL. Instead we mint a
# short-lived, narrowly-scoped token — signed with our own secret, which
# (unlike the Supabase token path above) this backend DOES verify — good for
# exactly one project/phase/run combination.

def mint_editor_link_token(user_id: str, project_id: str, run_id: str) -> tuple[str, int]:
    """Sign a short-lived token scoped to one architecture_agent run. Returns (token, expires_at epoch seconds)."""
    from core.config import settings
    from constants.pipeline import EDITOR_LINK_PHASE_ID, EDITOR_LINK_TTL_SECONDS

    now = int(time.time())
    exp = now + EDITOR_LINK_TTL_SECONDS
    payload = {
        "sub": user_id,
        "project_id": project_id,
        "phase_id": EDITOR_LINK_PHASE_ID,
        "run_id": run_id,
        "iat": now,
        "exp": exp,
    }
    token = pyjwt.encode(payload, settings.EDITOR_LINK_SECRET, algorithm="HS256")
    return token, exp


def _verify_editor_link_token(token: str, project_id: str, run_id: str) -> Optional[str]:
    """Verify a hand-off token's signature and scope. Returns the user_id on success, None if it isn't one of ours."""
    from core.config import settings

    try:
        payload = pyjwt.decode(token, settings.EDITOR_LINK_SECRET, algorithms=["HS256"])
    except pyjwt.InvalidTokenError:
        return None  # not our token (e.g. a real Supabase JWT) — caller falls back

    if payload.get("project_id") != project_id or payload.get("run_id") != run_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token not valid for this run")
    return payload.get("sub")


def get_user_id_for_run(
    project_id: str,
    run_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency for endpoints architecture-editor calls directly.
    Accepts either a normal Supabase bearer token (nexo-frontend) or an
    editor-link token scoped to this exact project_id/run_id (architecture-editor).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scoped_user_id = _verify_editor_link_token(credentials.credentials, project_id, run_id)
    if scoped_user_id:
        return scoped_user_id

    return get_current_user_id(credentials)