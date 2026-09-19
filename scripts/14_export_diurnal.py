"""Derive city-mean diurnal Q_f curves per snapshot year from the published PMTiles.

Reads web/tiles/qf_years.pmtiles (or docs/map/tiles/ if web/tiles is absent), decodes
every z14 tile, de-duplicates 100 m cells split across tile boundaries (identical
96-value property vectors), and writes web/diurnal.json for the story page and viewer.

Field hNN in the tiles is 0-indexed. It lines up one-for-one with hour NN+1 of
benchmark_sailor.csv (1..24), i.e. hNN is the hour ENDING (NN+1):00. The viewer labels
hours that way, so the 'peak at 18:00' in the text is field h17.

    pip install pmtiles mapbox-vector-tile
    python scripts/14_export_diurnal.py
"""
import gzip
import json
import pathlib

import mapbox_vector_tile as mvt
import numpy as np
import pandas as pd
from pmtiles.reader import MmapSource, Reader, all_tiles

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = next(p for p in [ROOT / "web/tiles/qf_years.pmtiles",
                       ROOT / "docs/map/tiles/qf_years.pmtiles"] if p.exists())
YEARS = [2026, 2030, 2035, 2040]
Z = 14

with open(SRC, "rb") as f:
    r = Reader(MmapSource(f))
    cells = set()
    for (z, _x, _y), data in all_tiles(r.get_bytes):
        if z != Z:
            continue
        for ft in mvt.decode(gzip.decompress(data))["qf_years"]["features"]:
            p = ft["properties"]
            cells.add(tuple(round(float(p.get(f"y{y}_h{h:02d}", 0)), 3)
                            for y in YEARS for h in range(24)))

A = np.array(sorted(cells)).reshape(len(cells), len(YEARS), 24)
bm = pd.read_csv(ROOT / "data/processed/benchmark_sailor.csv").sort_values("hour")

out = {
    "note": ("Unweighted mean over mapped 100 m cells, recomputed from the published tiles. "
             "Runs ~2 W/m2 above the series.json built-cell mean; shape is the point."),
    "hour_convention": "index i = hour ending (i+1):00 IST",
    "n_cells": int(len(cells)),
    "years": YEARS,
    "city_mean": {str(y): [round(float(v), 2) for v in A[:, i, :].mean(0)]
                  for i, y in enumerate(YEARS)},
    "sailor": [round(float(v), 2) for v in bm.sailor_wm2],
    "p90_peak": {str(y): round(float(np.percentile(A[:, i, 17], 90)), 1)
                 for i, y in enumerate(YEARS)},
}
dst = ROOT / "web/diurnal.json"
dst.write_text(json.dumps(out, indent=1))
print(f"{len(cells):,} cells -> {dst.relative_to(ROOT)}")
