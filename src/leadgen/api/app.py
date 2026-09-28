"""
FastAPI application factory for the Agent Pipeline orchestrator.

Run it from the repo root with::

    uvicorn leadgen.api.app:app --reload

The endpoints are split by domain under ``leadgen.api.routers``; shared runtime
state lives in ``leadgen.api.state`` and subprocess/SSE plumbing in
``leadgen.api.runner``.

Every route except ``/health`` and ``/auth/*`` requires a session cookie, and the
auth database is migrated to ``head`` on startup.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from leadgen import config
from leadgen.api.routers import (
    admin,
    auth,
    exports,
    health,
    hunter,
    linkedin,
    shortlister,
    ws,
)
from leadgen.auth.csrf import OriginCheckMiddleware
from leadgen.auth.dependencies import require_user
from leadgen.auth.errors import AuthError
from leadgen.auth.service import AuthService
from leadgen.db import migrate as db_migrate
from leadgen.db.session import session_scope


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the runtime directories, migrate the auth database, sweep old sessions."""
    config.ensure_runtime_dirs()
    if config.DB_AUTO_MIGRATE:
        db_migrate.upgrade_database()

    try:
        with session_scope() as db:
            AuthService(db).purge_sessions()
    except SQLAlchemyError as exc:
        # Cleanup must never stop the API from serving.
        print(f"[WARN] Could not purge expired sessions: {exc}", flush=True)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with CORS, CSRF protection and every domain router."""
    app = FastAPI(title="Agent Pipeline API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it wraps CORS: unsafe cross-origin calls are rejected first.
    app.add_middleware(OriginCheckMiddleware)

    @app.exception_handler(AuthError)
    async def _auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    # Public surface: liveness plus the login/setup/recovery flows.
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)

    # Everything below requires a session cookie.
    app.include_router(shortlister.router, dependencies=[Depends(require_user)])
    app.include_router(linkedin.router, dependencies=[Depends(require_user)])
    app.include_router(hunter.router, dependencies=[Depends(require_user)])
    app.include_router(exports.router, dependencies=[Depends(require_user)])

    # WebSockets check the cookie and Origin inside the handshake handler.
    app.include_router(ws.router)

    return app


app = create_app()
