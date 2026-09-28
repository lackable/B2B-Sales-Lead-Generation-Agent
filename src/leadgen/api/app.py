"""
FastAPI application factory for the Agent Pipeline orchestrator.

Run it from the repo root with::

    uvicorn leadgen.api.app:app --reload

The endpoints are split by domain under ``leadgen.api.routers``; shared runtime
state lives in ``leadgen.api.state`` and subprocess/SSE plumbing in
``leadgen.api.runner``.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from leadgen import config
from leadgen.api.routers import (
    exports,
    health,
    hunter,
    linkedin,
    shortlister,
    ws,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the gitignored runtime directories before serving requests."""
    config.ensure_runtime_dirs()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with CORS and every domain router registered."""
    app = FastAPI(title="Agent Pipeline API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(shortlister.router)
    app.include_router(linkedin.router)
    app.include_router(hunter.router)
    app.include_router(exports.router)
    app.include_router(ws.router)

    return app


app = create_app()
