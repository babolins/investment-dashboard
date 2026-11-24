#!/usr/bin/env bash
# Runs once when the container is created, before the firewall comes up.
set -euo pipefail

cd "$(dirname "$0")/.."

# Named volumes are created root-owned; hand them to the container user.
sudo /usr/local/bin/fix-volume-owners.sh

echo "==> Installing backend dependencies (uv)"
(cd backend && uv sync --frozen)

echo "==> Installing frontend dependencies (npm)"
(cd frontend && npm ci)

echo
echo "Dev container ready. Start the app with:"
echo "  backend:  cd backend && uv run uvicorn app.main:app --reload --port 8000"
echo "  frontend: cd frontend && npm run dev"
