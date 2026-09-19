"""Building stock: floors, floor area, archetype assignment, ward join."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

SNAP_M = 100.0   # snap near-boundary buildings to the nearest ward


def _floor_height(cfg, use_class: str) -> float:
    fh = cfg["stock"]["floor_height_m"]
    key = str(use_class).lower()
    if "residential" in key or "mixed" in key:
        return fh["residential"]
    if "industrial" in key:
        return fh["industrial"]
    if "commercial" in key or "retail" in key or "office" in key:
        return fh["commercial"]
    return fh["default"]


def prepare_stock(buildings: gpd.GeoDataFrame, wards: gpd.GeoDataFrame, cfg) -> gpd.GeoDataFrame:
    s = cfg["schema"]
    work_crs = cfg["crs"]["working"]

    gdf = buildings.to_crs(work_crs).copy()
    gdf = gdf.rename(columns={s["building_id"]: "building_id",
                              s["height"]: "height_m",
                              s["use_class"]: "use_class"})
    if s["slum_flag"] in gdf.columns:
        gdf = gdf.rename(columns={s["slum_flag"]: "is_slum"})
    else:
        gdf["is_slum"] = False
    gdf["is_slum"] = gdf["is_slum"].fillna(False).astype(bool)

    gdf["footprint_m2"] = gdf.geometry.area
    gdf["use_class"] = gdf["use_class"].fillna("unknown").astype(str).str.lower()

    fh = gdf["use_class"].map(lambda u: _floor_height(cfg, u))
    floors = np.ceil(gdf["height_m"].fillna(fh) / fh)
    gdf["floors"] = floors.clip(cfg["stock"]["min_floors"], cfg["stock"]["max_floors"]).astype(int)
    gdf["floor_area_m2"] = gdf["footprint_m2"] * gdf["floors"]

    gdf["archetype"] = _assign_archetype(gdf, cfg)
    gdf["is_residential"] = gdf["archetype"].str.startswith("res_")

    wards = wards.to_crs(work_crs)[["ward", "geometry"]]
    cent = gdf.copy()
    cent["geometry"] = gdf.geometry.centroid
    joined = gpd.sjoin(cent, wards, how="left", predicate="within")[["building_id", "ward"]]
    joined = joined.drop_duplicates("building_id")

    miss = joined["ward"].isna()
    if miss.any():
        ids = joined.loc[miss, "building_id"]
        near = gpd.sjoin_nearest(cent[cent.building_id.isin(ids)][["building_id", "geometry"]],
                                 wards, how="left", max_distance=SNAP_M, distance_col="_d")
        near = near.drop_duplicates("building_id")[["building_id", "ward"]]
        joined = joined.set_index("building_id")
        joined.update(near.set_index("building_id"))
        joined = joined.reset_index()

    gdf = gdf.merge(joined, on="building_id", how="left")

    keep = ["building_id", "ward", "use_class", "archetype", "is_residential", "is_slum",
            "height_m", "floors", "footprint_m2", "floor_area_m2", "geometry"]
    return gpd.GeoDataFrame(gdf[keep], geometry="geometry", crs=work_crs)


def _assign_archetype(gdf: pd.DataFrame, cfg) -> pd.Series:
    cmap = {k.lower(): v for k, v in cfg["stock"]["use_class_map"].items()}
    base = gdf["use_class"].map(cmap).fillna(cfg["stock"]["use_class_map"].get("unknown", "res_midrise"))

    rules = sorted(cfg["stock"]["residential_by_floors"], key=lambda r: r["max_floors"])
    res_mask = base.str.startswith("res_")
    refined = base.copy()
    for rule in reversed(rules):
        refined = refined.where(~(res_mask & (gdf["floors"] <= rule["max_floors"])), rule["archetype"])

    refined = refined.where(~gdf["is_slum"], cfg["stock"]["slum_archetype"])
    return refined
