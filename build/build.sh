#!/usr/bin/env bash
# Build the wf-importer-gui Docker image and optionally push to DockerHub.
#
# Usage:
#   bash build/build.sh                  # build only
#   PUSH=1 bash build/build.sh           # build + push
set -euo pipefail

BUILD_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$BUILD_DIR/.." && pwd)"

if [[ -f "$REPO_DIR/.env" ]]; then
  # shellcheck source=/dev/null
  source "$REPO_DIR/.env"
fi

if [[ -z "${IMAGE:-}" ]]; then
  echo "ERROR: IMAGE is not set. Copy .env.example to .env and set IMAGE." >&2
  exit 1
fi

echo "Building $IMAGE…"
docker build \
  -t "$IMAGE" \
  -f "$BUILD_DIR/Dockerfile" \
  "$REPO_DIR"

if [ "${PUSH:-0}" = "1" ]; then
  echo "Pushing $IMAGE…"
  docker push "$IMAGE"
fi

echo "Done: $IMAGE"
