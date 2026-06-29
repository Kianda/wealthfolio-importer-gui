#!/usr/bin/env bash
set -euo pipefail
docker rm -f wf-importer-gui 2>/dev/null || true
echo "Stopped."
