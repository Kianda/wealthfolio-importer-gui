#!/usr/bin/env bash
# Build and optionally push the wealthfolio-importer-gui Docker image.
#
# Usage:
#   bash build.sh          # build only
#   PUSH=1 bash build.sh   # build + push
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -f "$DIR/.env" ]]; then
  # shellcheck source=/dev/null
  source "$DIR/.env"
fi

if [[ -z "${IMAGE:-}" ]]; then
  echo "ERROR: IMAGE is not set. Copy .env.example to .env and set IMAGE." >&2
  exit 1
fi

echo "Building $IMAGE…"
docker build -t "$IMAGE" "$DIR"

if [ "${PUSH:-0}" = "1" ]; then
  echo "Pushing $IMAGE…"
  docker push "$IMAGE"
fi

echo "Done: $IMAGE"
