#!/usr/bin/env bash
# Start the Wealthfolio importer GUI.
# Wealthfolio must already be running. Configure its URL in wf-config.yml.
set -euo pipefail

GUI_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -f "$GUI_DIR/.env" ]]; then
  # shellcheck source=/dev/null
  source "$GUI_DIR/.env"
fi

if [[ -z "${IMAGE:-}" ]]; then
  echo "ERROR: IMAGE is not set. Copy .env.example to .env and set IMAGE." >&2
  exit 1
fi

mkdir -p "$GUI_DIR/data/input" "$GUI_DIR/data/converted" "$GUI_DIR/data/pushed"

if docker inspect wf-importer-gui &>/dev/null; then
  docker rm -f wf-importer-gui
fi

docker pull "$IMAGE"

docker run -d \
  --name wf-importer-gui \
  -p 23527:23527 \
  -v "$GUI_DIR/wf-config.yml:/app/wf-config.yml:ro" \
  -v "$GUI_DIR/data:/app/data" \
  "$IMAGE"

echo "Importer GUI: http://localhost:23527"
