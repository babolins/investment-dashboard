"""
FastAPI application entry point.
"""

from __future__ import annotations

import logging
import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import holdings, rebalance, config as config_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Investment Portfolio Rebalancer",
    description="Quarterly portfolio allocation analysis and rebalancing tool.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — only needed when the Vite dev server (localhost:5173) talks to the
# backend directly.  In production the frontend is served from the same origin
# so CORS is not required, but the middleware is kept for dev convenience.
# Override ALLOWED_ORIGINS to restrict origins in production if desired.
# ---------------------------------------------------------------------------
_origins_env = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
)
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(holdings.router, prefix="/api")
app.include_router(rebalance.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static frontend — only active when the built assets are present (production).
# The catch-all route serves index.html for client-side SPA routing.
# ---------------------------------------------------------------------------
_static_dir = pathlib.Path(__file__).parent.parent / "static"

if _static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        candidate = _static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_dir / "index.html")
