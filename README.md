# Investment Portfolio Rebalancer

A self-hosted quarterly portfolio rebalancing tool that ingests a Fidelity CSV export, displays your current holdings and allocation, and computes how much to invest in **VTI**, **VXUS**, and **BND** each quarter.

## Features

- Upload a Fidelity portfolio CSV snapshot
- View holdings table: symbol, quantity, current value, total gain/loss, % of account
- Allocation pie chart grouped by VTI / VXUS / BND buckets
- YAML-configurable security mappings (direct, fractional, and excluded symbols)
- Rebalance calculator: enter investment amount + target allocation → buy guidance in dollars and % of investment

## Non-goals (v1)

- No historical snapshot storage
- No brokerage order execution
- No live price fetching
- No multi-user authentication
- No tax optimization

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · FastAPI · Pydantic v2 |
| Frontend | React 18 · TypeScript · Vite · Recharts |
| Packaging | `uv` (backend) · `npm` (frontend) |
| Deployment | Docker (single container, self-hosted) |

## Quarterly Workflow

1. Export portfolio CSV from Fidelity ("Positions" → "Download").
2. Upload CSV on the dashboard.
3. Review the holdings table and allocation chart.
4. Enter your intended investment amount and target allocation weights.
5. Follow the buy guidance for VTI / VXUS / BND.

---

## Development

### Prerequisites

- [uv](https://github.com/astral-sh/uv) ≥ 0.4
- Node.js ≥ 20 and npm ≥ 10
- Docker + Docker Compose (for deployment)

### Configuration

Copy `backend/config.example.yaml` to `backend/config.yaml` and edit your security-to-bucket mappings before starting the backend. See [backend/config.example.yaml](backend/config.example.yaml) for a fully annotated example.

### Run the backend

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Run the frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs at `http://localhost:5173` and proxies `/api` requests to the backend automatically.

### Run backend tests

```bash
cd backend
uv run pytest -v
```

### Lint

```bash
cd backend && uv run ruff check app/ tests/
cd frontend && npm run build  # TypeScript type-check included
```

---

## Deployment

### Build and start

```bash
# Requires backend/config.yaml — copy from the example if needed
cp backend/config.example.yaml backend/config.yaml

docker compose up -d --build
```

The container serves both the API and the built React frontend on a single port (default `8000`). There is no separate nginx container.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Host port to bind |
| `CONFIG_PATH` | `/etc/investment-dashboard/config.yaml` | Path to config inside the container |
| `APP_ENV` | `production` | Application environment |
| `VITE_API_URL` | _(empty)_ | Set at build time if the API is on a different host; leave empty for same-origin `/api` routing |
| `COMPOSE_NETWORK` | `investment-dashboard` | Docker network name |

### Reverse proxy (optional)

The container exposes a single HTTP service on `PORT`. Point a reverse proxy (e.g. Nginx Proxy Manager) directly at it for TLS termination:

```
app.your-domain  →  app:8000
```

### Stop

```bash
docker compose down
```

