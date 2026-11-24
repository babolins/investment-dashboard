# Backend

FastAPI application — serves the REST API and, in production, the built frontend as static files.

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`. To run the backend and frontend together with one command, use `../run.sh` (see the root README).

If built frontend assets are present, uvicorn serves them too, so one process is the whole app. It looks in `STATIC_DIR`, then `./static` (the Docker layout), then `../frontend/dist`.

The Vite dev server (`npm run dev` in `../frontend`) proxies `/api` to this port automatically, so you never need to set `VITE_API_URL` locally.

## Configuration

Categories and symbol assignments live in a YAML config, read from the first of `CONFIG_PATH`, `/etc/investment-dashboard/config.yaml`, `./config.yaml`, then `./config.example.yaml`. The API edits it in place (`app/services/config_store.py`, comment-preserving via ruamel.yaml); when running from the example, edits go to a new `./config.yaml` instead. See `config.example.yaml` for the format.

## Tests

```bash
uv run pytest
```

Unit tests cover the services; integration tests exercise the API through FastAPI's `TestClient`.

## Checks

```bash
uv run ruff check app tests
uv run ruff format --check app tests   # `uv run ruff format app tests` to fix
uv run pyright
```

## Project layout

```
app/
  api/        # FastAPI routers (holdings, rebalance, config) and shared dependencies (deps.py)
  models/     # Pydantic schemas and config models
  services/   # Business logic (allocation, CSV parsing, rebalancing) and the config store
tests/
  unit/         # Services, schemas and config loading
  integration/  # API endpoints via TestClient
```
