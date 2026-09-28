"""FastAPI dependencies: cookie → session → user, plus the WebSocket handshake."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, WebSocket
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from leadgen import config
from leadgen.auth.csrf import origin_is_allowed
from leadgen.auth.service import AuthService, AuthenticatedSession, RequestContext
from leadgen.db.models import ROLE_ADMIN, User
from leadgen.db.session import get_db

UNAUTHENTICATED_DETAIL = "Authentication required."
FORBIDDEN_DETAIL = "Administrator privileges required."

WS_POLICY_VIOLATION = 1008


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """A service bound to this request's database session."""
    return AuthService(db)


def request_context(request: Request) -> RequestContext:
    """Client address and user agent, recorded on sessions and audit events."""
    return RequestContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def current_session(request: Request, service: AuthService = Depends(get_auth_service)) -> AuthenticatedSession:
    """The signed-in session, or 401 when the cookie is missing/invalid."""
    authenticated = service.authenticate(request.cookies.get(config.SESSION_COOKIE_NAME))
    if authenticated is None:
        raise HTTPException(status_code=401, detail=UNAUTHENTICATED_DETAIL)
    return authenticated


def require_user(authenticated: AuthenticatedSession = Depends(current_session)) -> User:
    """Any signed-in, enabled account."""
    return authenticated.user


def require_admin(user: User = Depends(require_user)) -> User:
    """A signed-in administrator."""
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail=FORBIDDEN_DETAIL)
    return user


async def authenticate_websocket(websocket: WebSocket, service: AuthService) -> Optional[User]:
    """Origin + cookie check for a WebSocket handshake.

    The socket is accepted first and then closed with 1008, because an ASGI
    server turns a close issued before ``accept()`` into a plain 403 handshake
    rejection instead of the policy-violation close code.
    """
    token = None
    if origin_is_allowed(websocket.headers.get("origin")):
        token = websocket.cookies.get(config.SESSION_COOKIE_NAME)
    authenticated = await run_in_threadpool(service.authenticate, token) if token else None

    await websocket.accept()
    if authenticated is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return None
    return authenticated.user
