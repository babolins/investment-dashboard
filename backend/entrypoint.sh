#!/bin/sh
set -e

CONFIG_DIR="/etc/investment-dashboard"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "No config.yaml found — initialising from example config at $CONFIG_FILE"
    cp /app/config.example.yaml "$CONFIG_FILE"
fi

exec "$@"
