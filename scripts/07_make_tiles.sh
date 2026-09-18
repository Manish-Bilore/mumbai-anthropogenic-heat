#!/usr/bin/env bash
# Requires tippecanoe (brew install tippecanoe / apt install tippecanoe)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/web/tiles"

tippecanoe -o "$ROOT/web/tiles/qf_grid.pmtiles" \
  -l qf_grid -Z 9 -z 15 --drop-densest-as-needed --force \
  "$ROOT/data/processed/qf_grid_penetration.geojson"

echo "wrote web/tiles/qf_grid.pmtiles"
