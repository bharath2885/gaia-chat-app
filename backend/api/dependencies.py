"""FastAPI dependencies for session-based auth."""

from typing import Optional

from fastapi import Header, HTTPException, status

from backend.services.session_service import get_api_key_for_session
from backend.settings import Settings, get_settings


def require_session(
    x_session_id: Optional[str] = Header(default=None, alias="X-SESSION-ID"),
) -> str:
    """Validate the session header and return the stored Gaia API key."""

    if not x_session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-SESSION-ID header.",
        )
    api_key = get_api_key_for_session(x_session_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )
    return api_key
