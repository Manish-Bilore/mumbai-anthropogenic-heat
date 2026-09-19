#!/usr/bin/env bash
# Post-render: copy the MapLibre viewer + PMTiles into the rendered site.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/docs/map"
cp -r "$ROOT/web/." "$ROOT/docs/map/"
echo "copied web/ -> docs/map/ ($(du -sh "$ROOT/docs/map" | cut -f1))"
