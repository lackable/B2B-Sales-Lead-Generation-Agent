"""``users`` table — accounts, credentials and lockout bookkeeping."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column

from leadgen.db.base import Base, TimestampMixin, new_uuid

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)


class User(Base, TimestampMixin):
    """An account. Users are disabled (``is_active``), never hard-deleted."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    # NFKC + casefold form; UNIQUE enforces case-insensitive usernames.
    username_normalized: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_code_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_USER, server_default=ROLE_USER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (CheckConstraint("role IN ('admin', 'user')", name="role_valid"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.username!r} role={self.role!r} active={self.is_active}>"
