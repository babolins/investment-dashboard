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

## Stack

| Layer      | Technology                                                                          |
| ---------- | ----------------------------------------------------------------------------------- |
| Backend    | Python 3.12 · FastAPI · Pydantic v2                                                 |
| Frontend   | Svelte 5 · TypeScript · Vite (chart is hand-drawn SVG)                              |
| Packaging  | `uv` (backend) · `npm` (frontend)                                                   |
| Quality    | ruff, pyright, pytest (backend) · ESLint, Prettier, svelte-check, Vitest (frontend) |
| Deployment | Docker (single container, self-hosted)                                              |

## Quarterly Workflow

1. In Fidelity, go to **Accounts & Trade → Portfolio → Positions** and click **Download** to export a CSV.
2. Drop the CSV on the **Upload Portfolio** card (or click it to browse).
3. Review the **Holdings** table and the **Asset Allocation** chart. Any holding marked unassigned (a new purchase, say) needs a category: click its category pill and assign it.
4. In the **Rebalance Calculator**, enter the **Investment Amount** and check the targets. Each category's target is a **% of parent**, and each level must add up to 100%. The form starts from each category's default target. Changes you make here last for the session only; to change a default, edit the category under **Categories**.
5. Click **Calculate Buy Guidance**. Buy the amount shown for each category's buy symbol. **Post-trade Allocation** shows where the portfolio will end up.

---

## Getting started (development)

### 1. Install the prerequisites

| Tool                                                       | Version                        | Used for                                                                              |
| ---------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------- |
| [Git](https://git-scm.com/)                                | any                            | Cloning the repo                                                                      |
| [uv](https://docs.astral.sh/uv/)                           | ≥ 0.4                          | Backend dependencies and Python. uv downloads Python 3.12 itself if you don't have it |
| [Node.js](https://nodejs.org/) with npm                    | ≥ 24.15 (see [.nvmrc](.nvmrc)) | Frontend dependencies, dev server and build                                           |
| [Docker](https://docs.docker.com/get-docker/) with Compose | any                            | Deployment only; not needed for development                                           |

On macOS with [Homebrew](https://brew.sh/): `brew install uv node@24`. On other platforms, use the uv installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and install Node 24 from [nodejs.org](https://nodejs.org/) or with a version manager. With [nvm](https://github.com/nvm-sh/nvm) or [fnm](https://github.com/Schniz/fnm), run `nvm use` / `fnm use` in the repo root to pick up the version in `.nvmrc`.

### 2. Clone and install dependencies

```bash
git clone https://github.com/babolins/investment-dashboard.git
cd investment-dashboard
(cd backend && uv sync)      # creates backend/.venv (installs Python 3.12 if needed)
(cd frontend && npm ci)      # installs frontend/node_modules from the lockfile
```

### 3. Run it

```bash
./run.sh                     # open http://localhost:5173
```

With no `config.yaml` of your own, the app starts from the bundled example categories. See [Configuration](#configuration) below.

### 4. Build the frontend

```bash
cd frontend && npm run build # type-checks, then writes the production bundle to frontend/dist/
```

The backend serves `frontend/dist/` automatically when it exists, so after a build `cd backend && uv run uvicorn app.main:app` serves the whole app on http://localhost:8000. `./run.sh prod` does both steps for you.

### 5. Before you push

Run the [checks](#checks) below. CI runs the same ones.

### Dev container (optional)

The repo includes a VS Code [dev container](.devcontainer/) that ships uv, Python 3.12 and Node 24, and installs both sets of dependencies when the container is created. In VS Code, run **Dev Containers: Reopen in Container**, then go straight to step 3. The container is set up as a sandbox for Claude Code: outbound network is limited to an allowlist and pushing to GitHub is blocked, so push from your host.

## Development

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
