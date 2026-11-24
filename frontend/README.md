# Frontend

Svelte 5 + TypeScript + Vite single-page application.

## Development

```bash
npm install
npm run dev
```

Runs at `http://localhost:5173`. Requests to `/api` and `/health` are proxied to the backend at `http://localhost:8000` (configured in `vite.config.ts`). Start the backend first.

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

Type-checks with svelte-check, then builds. Outputs to `dist/`. In production this directory is copied into the Docker image and served directly by FastAPI — there is no separate nginx container.

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
