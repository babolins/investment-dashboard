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

### Run the app

One command starts everything:

```bash
./run.sh          # dev: open http://localhost:5173
./run.sh prod     # production build: open http://localhost:8000
```

- **`dev`** runs the FastAPI backend with auto-reload on port 8000 and the Vite dev server with hot reload on port 5173. Vite proxies `/api` to the backend. Ctrl-C stops both, and if either server exits, the other is stopped too.
- **`prod`** builds the frontend, then a single uvicorn process serves the API and the UI on one port (`HOST`/`PORT` override the default `127.0.0.1:8000`). This is the same setup the Docker image uses.

`frontend/node_modules` is installed on first run if missing; `uv run` keeps the backend environment in sync automatically. The API docs are at `http://localhost:8000/docs` in both modes.

<details>
<summary>Running the pieces by hand</summary>

```bash
cd backend && uv run uvicorn app.main:app --reload     # API on :8000
cd frontend && npm run dev                             # UI on :5173, proxies /api to :8000
```

The backend serves the built frontend whenever it finds one: `STATIC_DIR` if set, else `backend/static/` (the Docker layout), else `frontend/dist/` (after `npm run build`). So `npm run build` followed by uvicorn alone also gives you the whole app on :8000.

</details>

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
docker compose up -d --build
```

The container serves both the API and the built frontend on port `8000`. There is no separate nginx container. No host port is published: the compose network is external, so create it once (`docker network create investment-dashboard`) and point your reverse proxy at `app:8000`.

On first start, the entrypoint copies the bundled example config to `./etc-investment-dashboard/config.yaml` (or `$CONFIG_VOLUME/config.yaml`) if no config exists there yet. The directory is mounted **writable**, so category edits made in the UI are saved back to that file and persist across container restarts and image updates. You can also edit it by hand.

### Environment variables

| Variable          | Default                                 | Description                                                                                     |
| ----------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `CONFIG_PATH`     | `/etc/investment-dashboard/config.yaml` | Path to config inside the container                                                             |
| `CONFIG_VOLUME`   | `./etc-investment-dashboard`            | Host directory mounted at `/etc/investment-dashboard`                                           |
| `APP_ENV`         | `production`                            | Application environment                                                                         |
| `STATIC_DIR`      | _(auto)_                                | Directory of built frontend assets to serve; defaults to the bundled build                      |
| `VITE_API_URL`    | _(empty)_                               | Set at build time if the API is on a different host; leave empty for same-origin `/api` routing |
| `COMPOSE_NETWORK` | `investment-dashboard`                  | Docker network name                                                                             |

### Stop

```bash
docker compose down
```
