# Frontend

Svelte 5 + TypeScript + Vite single-page application.

## Development

```bash
npm install
npm run dev
```

Runs at `http://localhost:5173`. Requests to `/api` are proxied to the backend at `http://localhost:8000` (configured in `vite.config.ts`). Start the backend first, or run `../run.sh` from here to start both together.

## Checks

```bash
npm run lint          # ESLint
npm run format:check  # Prettier (`npm run format` to fix)
npm run check         # svelte-check (types + a11y)
npm test              # Vitest + Testing Library (jsdom); `npm run test:watch` to watch
```

## Build

```bash
npm run build
```

Type-checks with svelte-check, then builds. Outputs to `dist/`. FastAPI serves this directory directly (no nginx): the Docker image copies it in, and a local `uvicorn` picks up `frontend/dist` on its own. `../run.sh prod` builds the frontend and starts that single server.

## Project layout

```
src/
  components/   # Svelte components (*.svelte) and their tests
  lib/          # Pure TypeScript logic (formatting, buckets, targets), unit tested
  services/     # API client (api.ts)
  types/        # Shared TypeScript types
  styles/       # Global CSS
  test/         # Shared test fixtures
```
