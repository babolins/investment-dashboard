#!/usr/bin/env bash
# Runs as root via sudo. New named volumes are created root-owned; hand the
# dependency volumes to the vscode user. Takes no arguments on purpose: the
# paths are fixed so sudo access to this script can't be used for anything else.
set -euo pipefail

WS=/workspaces/investment-dashboard
for dir in "$WS/backend/.venv" "$WS/frontend/node_modules"; do
  # -h: never follow a symlink planted at the path
  chown -h vscode:vscode "$dir"
done
