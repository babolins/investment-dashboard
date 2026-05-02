# Frontend

React 18 + TypeScript + Vite single-page application.

## Development

```bash
npm install
npm run dev
```

Runs at `http://localhost:5173`. Requests to `/api` and `/health` are proxied to the backend at `http://localhost:8000` (configured in `vite.config.ts`). Start the backend first.

## Build

```bash
npm run build
```

Outputs to `dist/`. In production this directory is copied into the Docker image and served directly by FastAPI — there is no separate nginx container.

## Project layout

```
src/
  components/   # UI components (chart, table, forms)
  services/     # API client (api.ts)
  types/        # Shared TypeScript types
```

