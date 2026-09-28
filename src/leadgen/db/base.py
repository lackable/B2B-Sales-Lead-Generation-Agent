"""Declarative base, constraint naming conventions and shared column helpers."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic migrations reproducible and let
# SQLite batch-mode ALTERs drop/recreate the right constraints.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Naive UTC timestamp — SQLite stores datetimes without an offset."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid() -> str:
    """Primary keys are UUID4 strings so they are not guessable."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base; importing it registers nothing on its own."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """``created_at`` / ``updated_at`` pair maintained in UTC."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
