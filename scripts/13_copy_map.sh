#!/usr/bin/env bash
# Post-render: publish the hand-built pages into the rendered site.
#   web/        -> docs/map/     (viewer, heat.css/js, series.json, diurnal.json, poster.png, tiles)
#   story/      -> docs/         (scroll story replaces Quarto's root; the Quarto overview is overview.html)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/docs/map"
cp -r "$ROOT/web/." "$ROOT/docs/map/"
cp "$ROOT/story/index.html" "$ROOT/docs/index.html"
touch "$ROOT/docs/.nojekyll"
echo "copied web/ -> docs/map/ ($(du -sh "$ROOT/docs/map" | cut -f1)); story -> docs/index.html"
