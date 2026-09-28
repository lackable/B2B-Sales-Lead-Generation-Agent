"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from leadgen.db.models.auth_event import EVENT_TYPES, AuthEvent
from leadgen.db.models.auth_session import AuthSession
from leadgen.db.models.user import ROLE_ADMIN, ROLE_USER, ROLES, User

__all__ = [
    "AuthEvent",
    "AuthSession",
    "EVENT_TYPES",
    "ROLE_ADMIN",
    "ROLE_USER",
    "ROLES",
    "User",
]
