"""``auth_events`` table — the append-only authentication audit log."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from leadgen.db.base import Base, utcnow

EVENT_TYPES = (
    "setup_completed",
    "login_success",
    "login_failure",
    "logout",
    "account_locked",
    "password_changed",
    "password_reset",
    "recovery_code_regenerated",
    "user_created",
    "user_disabled",
    "user_enabled",
)

_EVENT_TYPE_SQL = "event_type IN (" + ", ".join(f"'{event_type}'" for event_type in EVENT_TYPES) + ")"


class AuthEvent(Base):
    """One recorded authentication event. Never updated, only inserted."""

    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Kept for failures against usernames that do not exist.
    username_attempted: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Column is named "metadata"; the attribute cannot be (reserved by DeclarativeBase).
    event_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(_EVENT_TYPE_SQL, name="event_type_valid"),
        Index("ix_auth_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_auth_events_event_type_created_at", "event_type", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuthEvent {self.event_type!r} user_id={self.user_id!r}>"
