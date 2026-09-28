"""Persistence layer: SQLAlchemy 2.0 models, repositories and Alembic migrations.

This package knows nothing about authentication policy — it only stores and
retrieves rows. ``leadgen.auth`` imports ``leadgen.db``; the reverse must never
happen.
"""
