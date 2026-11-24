# Backend

FastAPI application — serves the REST API and, in production, the built frontend as static files.

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

The Vite dev server (`npm run dev` in `../frontend`) proxies `/api` to this port automatically, so you never need to set `VITE_API_URL` locally.

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit your symbol-to-bucket mappings before starting. The file is read from the path in `CONFIG_PATH` (default: `./config.yaml` in dev, `/etc/investment-dashboard/config.yaml` in Docker).

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
  services/   # Business logic (allocation, CSV parsing, rebalancing)
tests/
  unit/         # Services, schemas and config loading
  integration/  # API endpoints via TestClient
```
