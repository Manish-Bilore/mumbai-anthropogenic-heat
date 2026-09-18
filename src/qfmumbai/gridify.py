"""Aggregate per-building watts onto a regular grid -> W/m2."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

HOURS = 24


def make_grid(boundary: gpd.GeoDataFrame, cell_m: int, crs: str) -> gpd.GeoDataFrame:
    b = boundary.to_crs(crs)
    xmin, ymin, xmax, ymax = b.total_bounds
    xs = np.arange(np.floor(xmin / cell_m) * cell_m, xmax + cell_m, cell_m)
    ys = np.arange(np.floor(ymin / cell_m) * cell_m, ymax + cell_m, cell_m)
    cells, ids = [], []
    for i, x in enumerate(xs[:-1]):
        for j, y in enumerate(ys[:-1]):
            cells.append(box(x, y, x + cell_m, y + cell_m))
            ids.append(f"{i:04d}_{j:04d}")
    grid = gpd.GeoDataFrame({"cell_id": ids}, geometry=cells, crs=crs)
    keep = gpd.sjoin(grid, b[["geometry"]], how="inner", predicate="intersects")
    return grid.loc[grid.cell_id.isin(keep.cell_id)].reset_index(drop=True)


def aggregate(stock: gpd.GeoDataFrame, values_w: np.ndarray, grid: gpd.GeoDataFrame,
              prefix: str = "qf_h") -> gpd.GeoDataFrame:
    """values_w: (n_buildings, 24) watts. Returns grid with W/m2 columns."""
    pts = stock.copy()
    pts["geometry"] = stock.geometry.centroid
    joined = gpd.sjoin(pts[["geometry"]], grid[["cell_id", "geometry"]],
                       how="left", predicate="within")
    cell = joined["cell_id"].to_numpy()

    df = pd.DataFrame(values_w, columns=[f"{prefix}{h:02d}" for h in range(HOURS)])
    df["cell_id"] = cell
    summed = df.groupby("cell_id", dropna=True).sum()

    cell_area = grid.geometry.area.iloc[0]
    out = grid.merge(summed, on="cell_id", how="left").fillna(0.0)
    for h in range(HOURS):
        out[f"{prefix}{h:02d}"] = out[f"{prefix}{h:02d}"] / cell_area
    hcols = [f"{prefix}{h:02d}" for h in range(HOURS)]
    out["qf_mean"] = out[hcols].mean(axis=1)
    out["qf_peak"] = out[hcols].max(axis=1)
    out["peak_hour"] = out[hcols].values.argmax(axis=1)
    return out
