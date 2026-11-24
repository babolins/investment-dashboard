"""
FastAPI application entry point.
"""

from __future__ import annotations

import logging
import os
import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import config as config_router
from app.api import holdings, rebalance
from app.services.config_store import (
    ConfigError,
    ConfigWriteError,
    ConflictError,
    NotFoundError,
)

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
_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Errors raised by the config store and rebalance engine.  Starlette picks the
# handler of the closest class, so the subclasses win over ConfigError.
# ---------------------------------------------------------------------------
def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(NotFoundError)
def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return _json_error(404, str(exc))


@app.exception_handler(ConflictError)
def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
    return _json_error(409, str(exc))


@app.exception_handler(ConfigError)
def _invalid_config(_: Request, exc: ConfigError) -> JSONResponse:
    return _json_error(422, str(exc))


@app.exception_handler(ConfigWriteError)
def _config_not_writable(_: Request, exc: ConfigWriteError) -> JSONResponse:
    return _json_error(500, str(exc))


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
# Static frontend — only active when built assets are found, so one uvicorn
# process serves both the API and the UI.  Looked up in order:
#   STATIC_DIR            explicit override
#   backend/static        the Docker image layout
#   frontend/dist         a repo checkout after `npm run build`
# The catch-all route serves index.html for client-side SPA routing.
# ---------------------------------------------------------------------------
_backend_dir = pathlib.Path(__file__).resolve().parent.parent


def _find_static_dir() -> pathlib.Path | None:
    if env := os.getenv("STATIC_DIR"):
        return pathlib.Path(env).resolve()
    for candidate in (_backend_dir / "static", _backend_dir.parent / "frontend" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


_static_dir = _find_static_dir()

if _static_dir is not None:
    logging.getLogger(__name__).info("Serving frontend from %s", _static_dir)
    _static_root = _static_dir
    app.mount("/assets", StaticFiles(directory=_static_root / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        # Unknown API routes should 404, not return the app shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (_static_root / full_path).resolve()
        # is_relative_to blocks "../" escapes out of the static directory.
        if candidate.is_relative_to(_static_root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_root / "index.html")
