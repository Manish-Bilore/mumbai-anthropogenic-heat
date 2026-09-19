"""Render a static 'Mumbai heat' poster (2040, hour ending 18:00) from the published tiles.

Used as the story page's explore panel and og:image. Pure rendering: no new numbers.
    python scripts/15_render_poster.py  ->  web/poster.png
"""
import gzip, math, pathlib
import numpy as np, mapbox_vector_tile as mvt
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
from pmtiles.reader import Reader, MmapSource, all_tiles
from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = next(p for p in [ROOT / "web/tiles/qf_years.pmtiles", ROOT / "docs/map/tiles/qf_years.pmtiles"] if p.exists())
FIELD, Z = "y2040_h17", 14
tr = Transformer.from_crs(4326, 32643, always_xy=True)

pts = {}
with open(SRC, "rb") as f:
    r = Reader(MmapSource(f))
    for (z, x, y), data in all_tiles(r.get_bytes):
        if z != Z:
            continue
        for ft in mvt.decode(gzip.decompress(data))["qf_years"]["features"]:
            g = ft["geometry"]
            ring = np.array(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0], float)
            w, h = np.ptp(ring[:, 0]), np.ptp(ring[:, 1])
            full = max(w, h)
            if min(w, h) < 0.9 * full:   # piece clipped at a tile edge; its twin elsewhere is whole
                continue
            cx, cy = (ring[:, 0].min() + ring[:, 0].max()) / 2, (ring[:, 1].min() + ring[:, 1].max()) / 2
            n = 2 ** z
            lon = (x + cx / 4096) / n * 360 - 180
            ty = (y + 1 - cy / 4096) / n
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty))))
            e, nn = tr.transform(lon, lat)
            k = (int(math.floor(e / 100)), int(math.floor(nn / 100)))  # grid centres sit on xx50 m
            pts[k] = max(pts.get(k, 0), float(ft["properties"].get(FIELD, 0)))

ks = np.array(list(pts.keys())); vs = np.array(list(pts.values()))
x0, y0 = ks.min(0); x1, y1 = ks.max(0)
S = 6  # pixels per 100 m cell
pad = 12
img = np.zeros(((y1 - y0 + 1 + 2 * pad) * S, (x1 - x0 + 1 + 2 * pad) * S, 3), np.uint8)
img[:] = (246, 243, 238)  # page background, light theme
stops = [(0, "#f6f3ee"), (0.5, "#fdf3d6"), (5, "#fbe3a0"), (15, "#f5c965"), (30, "#ec9340"),
         (50, "#d4572e"), (80, "#a8321f"), (150, "#5c1a14")]  # = RAMP_QF in web/heat.js
cmap = LinearSegmentedColormap.from_list("heat", [(v / 150, c) for v, c in stops])
for (i, j), v in zip(ks, vs):
    if v < 0.5:
        continue
    c = (np.array(cmap(min(v, 150) / 150)[:3]) * 255).astype(np.uint8)
    px = (i - x0 + pad) * S; py = (y1 - j + pad) * S
    img[py:py + S - 1, px:px + S - 1] = c   # 1 px gutter keeps the grid legible
out = ROOT / "web/poster.png"
Image.fromarray(img).save(out, optimize=True)
print(out, img.shape)
