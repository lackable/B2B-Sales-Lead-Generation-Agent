"""Persistence helpers for the ``auth_sessions`` table."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from leadgen.db.base import utcnow
from leadgen.db.models.auth_session import AuthSession


def create(
    db: Session,
    *,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuthSession:
    """Insert a session row and flush so ``session.id`` is populated."""
    now = utcnow()
    session = AuthSession(
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    db.flush()
    return session


def get_by_token_hash(db: Session, token_hash: str) -> Optional[AuthSession]:
    return db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))


def revoke(db: Session, session: AuthSession, *, reason: str, when: Optional[datetime] = None) -> None:
    if session.revoked_at is None:
        session.revoked_at = when or utcnow()
        session.revoked_reason = reason
        db.flush()


def revoke_all_for_user(
    db: Session,
    user_id: str,
    *,
    reason: str,
    except_session_id: Optional[str] = None,
    when: Optional[datetime] = None,
) -> int:
    """Revoke every live session of a user; returns how many rows changed."""
    now = when or utcnow()
    stmt = (
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )
    if except_session_id is not None:
        stmt = stmt.where(AuthSession.id != except_session_id)
    result = db.execute(stmt)
    db.flush()
    return int(result.rowcount or 0)


def purge(db: Session, *, now: Optional[datetime] = None, revoked_grace_hours: int = 24) -> int:
    """Delete expired sessions and revoked ones older than the grace period."""
    moment = now or utcnow()
    result = db.execute(
        delete(AuthSession).where(
            or_(
                AuthSession.expires_at < moment,
                AuthSession.revoked_at.is_not(None) & (AuthSession.revoked_at < moment - timedelta(hours=revoked_grace_hours)),
            )
        )
    )
    db.flush()
    return int(result.rowcount or 0)
