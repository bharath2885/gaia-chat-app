"""In-memory session store keyed by session ID → API key."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

_sessions: Dict[str, Tuple[str, datetime]] = {}


def create_session(api_key: str, ttl_minutes: int = 60) -> str:
    session_id = uuid.uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    _sessions[session_id] = (api_key, expires)
    return session_id


def get_api_key_for_session(session_id: str) -> Optional[str]:
    entry = _sessions.get(session_id)
    if not entry:
        return None
    api_key, expires = entry
    if datetime.now(timezone.utc) > expires:
        _sessions.pop(session_id, None)
        return None
    return api_key


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def cleanup_expired() -> int:
    now = datetime.now(timezone.utc)
    expired = [sid for sid, (_, exp) in _sessions.items() if now > exp]
    for sid in expired:
        del _sessions[sid]
    return len(expired)
