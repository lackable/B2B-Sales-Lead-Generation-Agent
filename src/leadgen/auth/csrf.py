"""Origin checks for state-changing requests and the WebSocket handshake.

``SameSite=Lax`` already keeps the cookie off cross-site POSTs; this is the
defence-in-depth layer that also covers the WebSocket handshake, which browsers
do not restrict through cookie attributes.
"""

from typing import Optional, Sequence

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from leadgen import config

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

REJECTED_DETAIL = "Cross-origin request rejected."


def _normalize(origin: Optional[str]) -> Optional[str]:
    if not origin or origin.strip().lower() == "null":
        return None
    return origin.strip().rstrip("/").lower()


def origin_is_allowed(origin: Optional[str], allowed_origins: Optional[Sequence[str]] = None) -> bool:
    """True when ``origin`` may perform an unsafe request.

    A missing ``Origin`` header is allowed: browsers always send it for
    cross-origin and unsafe same-site requests, so its absence means the caller
    is not a browser and CSRF does not apply.
    """
    candidate = _normalize(origin)
    if candidate is None:
        return True
    allowed = config.CORS_ALLOWED_ORIGINS if allowed_origins is None else allowed_origins
    return candidate in {normalized for normalized in (_normalize(item) for item in allowed) if normalized}


class OriginCheckMiddleware:
    """Reject unsafe cross-origin calls before they reach a route."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("method") in UNSAFE_METHODS:
            origin = Headers(scope=scope).get("origin")
            if not origin_is_allowed(origin):
                response = JSONResponse({"detail": REJECTED_DETAIL}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
