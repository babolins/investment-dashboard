#!/usr/bin/env bash
# Run the whole app with one command.
#
#   ./run.sh         dev: FastAPI (auto-reload) + Vite (hot reload).
#                    Open http://localhost:5173. Vite proxies /api to the backend.
#   ./run.sh prod    Build the frontend, then serve the API and UI from a single
#                    uvicorn process on http://localhost:8000 (HOST/PORT to override).
#
# Ctrl-C stops everything. In dev, if either server exits, the other is stopped too.
set -euo pipefail
cd "$(dirname "$0")"

[ -d frontend/node_modules ] || (cd frontend && npm ci)

case "${1:-dev}" in
  dev)
    # Job control puts each server in its own process group, so cleanup can
    # signal the whole tree (npm -> vite, uv -> uvicorn -> reloader worker).
    set -m
    (cd backend && exec uv run uvicorn app.main:app --reload --port 8000) &
    backend_pid=$!
    (cd frontend && exec npm run dev) &
    frontend_pid=$!
    trap 'kill -TERM -- "-$backend_pid" "-$frontend_pid" 2>/dev/null || true' EXIT
    # Without these, a signal kills bash outright and the EXIT trap never runs.
    trap 'exit 130' INT
    trap 'exit 143' TERM

    # Portable stand-in for `wait -n` (macOS ships bash 3.2).
    while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
      sleep 1
    done
    ;;
  prod)
    (cd frontend && npm run build)
    cd backend
    exec uv run uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
    ;;
  *)
    echo "usage: $0 [dev|prod]" >&2
    exit 1
    ;;
esac
