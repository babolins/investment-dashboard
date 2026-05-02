# Backend

FastAPI application — serves the REST API and, in production, the built React frontend as static files.

## Development

```bash
uv sync
uv run fastapi dev app/main.py
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

The Vite dev server (`npm run dev` in `../frontend`) proxies `/api` to this port automatically, so you never need to set `VITE_API_URL` locally.

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit your symbol-to-bucket mappings before starting. The file is read from the path in `CONFIG_PATH` (default: `./config.yaml` in dev, `/etc/investment-dashboard/config.yaml` in Docker).

## Tests

```bash
uv run pytest -v
```

## Lint

```bash
uv run ruff check app/ tests/
```

## Project layout

```
app/
  api/        # FastAPI routers (holdings, rebalance, config)
  models/     # Pydantic schemas and config models
  services/   # Business logic (allocation, CSV parsing, rebalancing)
tests/
  unit/       # Unit tests for services
  integration/
```
