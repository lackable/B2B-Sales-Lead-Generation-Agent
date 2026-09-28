"""Persistence helper for the ``auth_events`` audit log."""

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from leadgen.db.models.auth_event import AuthEvent


def record(
    db: Session,
    *,
    event_type: str,
    user_id: Optional[str] = None,
    username_attempted: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuthEvent:
    """Append one audit event. ``metadata`` is stored as a JSON string."""
    event = AuthEvent(
        user_id=user_id,
        username_attempted=username_attempted,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=json.dumps(metadata) if metadata else None,
    )
    db.add(event)
    db.flush()
    return event
