"""Reading/writing spatial tables. Accepts parquet, gpkg, geojson, shp."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


def read_vector(path: str | Path) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"missing input: {path}")
    if path.suffix == ".parquet":
        return gpd.read_parquet(path)
    return gpd.read_file(path)


def write_vector(gdf: gpd.GeoDataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        gdf.to_parquet(path)
    elif path.suffix == ".geojson":
        gdf.to_file(path, driver="GeoJSON")
    else:
        gdf.to_file(path)
    return path


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
    return path


def require_columns(df: pd.DataFrame, cols, label: str = "table") -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"{label} is missing required columns: {missing}")
