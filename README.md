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

No config setup is needed for a quick test — if no `config.yaml` is found, the backend falls back to `config.example.yaml` automatically.

### Frontend development (optional)

In production the React app is compiled into the Docker image and served directly by FastAPI. For local frontend development with hot reload, run the Vite dev server in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` requests to the backend at `localhost:8000` automatically.

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
docker compose up -d --build
```

The container serves both the API and the built React frontend on a single port. There is no separate nginx container.

On first start, the entrypoint script automatically initialises `./etc-investment-dashboard/config.yaml` from the bundled example config if the file does not already exist. Edit that file to customise your security mappings; it is preserved across container restarts and image updates.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `/etc/investment-dashboard/config.yaml` | Path to config inside the container |
| `CONFIG_VOLUME` | `./etc-investment-dashboard` | Path to the config volume on the local filesystem |
| `APP_ENV` | `production` | Application environment |
| `VITE_API_URL` | _(empty)_ | Set at build time if the API is on a different host; leave empty for same-origin `/api` routing |
| `COMPOSE_NETWORK` | `investment-dashboard` | Docker network name |

### Stop

```bash
docker compose down
```

