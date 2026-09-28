"""Persistence helpers for the ``users`` table — no authentication policy here."""

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadgen.db.base import utcnow
from leadgen.db.models.user import ROLE_USER, User


def count_users(db: Session) -> int:
    """Total number of accounts — drives the first-run setup gate."""
    return int(db.scalar(select(func.count()).select_from(User)) or 0)


def get_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.get(User, user_id)


def get_by_normalized_username(db: Session, username_normalized: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username_normalized == username_normalized))


def list_users(db: Session) -> Sequence[User]:
    return db.scalars(select(User).order_by(User.created_at, User.username)).all()


def create(
    db: Session,
    *,
    username: str,
    username_normalized: str,
    password_hash: str,
    recovery_code_hash: str,
    role: str = ROLE_USER,
    must_change_password: bool = False,
    created_by_id: Optional[str] = None,
) -> User:
    """Insert a new account and flush so ``user.id`` is populated."""
    now = utcnow()
    user = User(
        username=username,
        username_normalized=username_normalized,
        password_hash=password_hash,
        recovery_code_hash=recovery_code_hash,
        recovery_code_created_at=now,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
        failed_login_attempts=0,
        password_changed_at=now,
        created_by_id=created_by_id,
    )
    db.add(user)
    db.flush()
    return user
