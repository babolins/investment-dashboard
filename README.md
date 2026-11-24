# Investment Portfolio Rebalancer

A self-hosted quarterly portfolio rebalancing tool that ingests a Fidelity CSV export, groups your holdings into categories you define (e.g. US stocks, international, bonds), and computes how much to invest in each category's ETF each quarter.

## Features

- Upload a Fidelity portfolio CSV snapshot
- View holdings table: symbol, quantity, current value, total gain/loss, % of account
- Allocation donut chart grouped by category
- Categories managed in the UI: create, rename, set the ETF to buy and a default target, delete
- Click a holding's category pill to assign it to one or more categories (split by %), exclude it, or leave it unassigned
- Categories and assignments are saved to `config.yaml` (comments preserved); everything else — uploads, amounts, targets typed into the form — stays in the browser session
- Nest categories inside each other (e.g. Stocks → US / International) by drag & drop or a "Move to" menu; securities are assigned to the innermost categories
- Rebalance calculator: enter the investment amount and each level's split as "% of parent" (e.g. Stocks 60% → US 70%) — the app works out each category's share of the portfolio (42%) → buy guidance in dollars and % of investment

## Non-goals (v1)

- No historical snapshot storage (the config file is the only persisted state)
- No brokerage order execution
- No live price fetching
- No multi-user authentication
- No tax optimization

## Stack

| Layer      | Technology                                                                          |
| ---------- | ----------------------------------------------------------------------------------- |
| Backend    | Python 3.12 · FastAPI · Pydantic v2                                                 |
| Frontend   | Svelte 5 · TypeScript · Vite (chart is hand-drawn SVG)                              |
| Packaging  | `uv` (backend) · `npm` (frontend)                                                   |
| Quality    | ruff, pyright, pytest (backend) · ESLint, Prettier, svelte-check, Vitest (frontend) |
| Deployment | Docker (single container, self-hosted)                                              |

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
- Node.js ≥ 20.19 and npm ≥ 10
- Docker + Docker Compose (for deployment)

### Configuration

The backend reads its config from the first of: `CONFIG_PATH`, `/etc/investment-dashboard/config.yaml`, `backend/config.yaml`, then the bundled [backend/config.example.yaml](backend/config.example.yaml) (fully annotated). Edits made in the UI are written back to that file — or, when running from the example, to a new `backend/config.yaml`, so the tracked example is never modified.

You can manage categories and assignments entirely from the UI, or edit the YAML by hand. Older config files (with `primary_symbols` / `default_target_allocations`) are upgraded automatically; the file is rewritten in the new format on the first save.

### Run the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
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

### Checks

CI runs these on every push to `main` and every pull request (`.github/workflows/ci.yml`).

```bash
# Backend (from backend/)
uv run ruff check app tests
uv run ruff format --check app tests   # `uv run ruff format app tests` to fix
uv run pyright
uv run pytest

# Frontend (from frontend/)
npm run lint
npm run format:check                   # `npm run format` to fix
npm run check                          # svelte-check (types + a11y)
npm test
npm run build
```

---

## Deployment

### Build and start

```bash
# Requires backend/config.yaml — copy from the example if needed
cp backend/config.example.yaml backend/config.yaml

docker compose up -d --build
```

The container serves both the API and the built frontend on a single port (default `8000`). There is no separate nginx container.

`backend/config.yaml` is bind-mounted **writable** so category edits made in the UI persist across restarts. It must exist before the first `docker compose up` (otherwise Docker creates a directory in its place).

### Environment variables

| Variable          | Default                                 | Description                                                                                     |
| ----------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `PORT`            | `8000`                                  | Host port to bind                                                                               |
| `CONFIG_PATH`     | `/etc/investment-dashboard/config.yaml` | Path to config inside the container                                                             |
| `APP_ENV`         | `production`                            | Application environment                                                                         |
| `VITE_API_URL`    | _(empty)_                               | Set at build time if the API is on a different host; leave empty for same-origin `/api` routing |
| `COMPOSE_NETWORK` | `investment-dashboard`                  | Docker network name                                                                             |

### Reverse proxy (optional)

The container exposes a single HTTP service on `PORT`. Point a reverse proxy (e.g. Nginx Proxy Manager) directly at it for TLS termination:

```
app.your-domain  →  app:8000
```

### Stop

```bash
docker compose down
```
