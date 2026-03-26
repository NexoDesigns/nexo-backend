"""
JWT extraction from Supabase Auth tokens.
MVP approach: decode without signature verification to extract user_id.
When scaling to SaaS, replace with full RS256 verification against Supabase public key.
"""

import base64
import json
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer()


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