"""Non-building anthropogenic heat: metabolism and vehicles.

Metabolism : population already allocated to buildings, at a sleeping/awake
             rate following the residential occupancy schedule.
Vehicles   : OSM road length per grid cell x traffic density x energy per metre.
             Sailor et al. use 3605 J/m at 9.5 km/l; India's two-wheeler-heavy
             fleet is lighter, so the default here is lower and is a placeholder.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

HOURS = 24


def metabolic_heat(stock: pd.DataFrame, cfg) -> np.ndarray:
    """(n_buildings, 24) watts of human metabolic heat."""
    occ = np.asarray(cfg["schedules"]["residential_occupancy"], dtype=float)
    w_sleep = float(cfg.get_in("metabolism.watts_sleeping", 70.0))
    w_awake = float(cfg.get_in("metabolism.watts_awake", 140.0))
    rate = w_sleep + (w_awake - w_sleep) * (1.0 - occ)   # high occupancy at night = asleep
    pop = stock["population"].to_numpy(float)
    return (pop[:, None] * rate[None, :]).astype(np.float32)


CLASS_WEIGHT = {"motorway": 5.0, "trunk": 4.0, "primary": 3.0,
                "secondary": 2.0, "tertiary": 1.5, "residential": 1.0,
                "unclassified": 1.0, "service": 0.5}


def _weight(tag: str) -> float:
    tag = str(tag).lower()
    for key, w in CLASS_WEIGHT.items():
        if key in tag:
            return w
    return 1.0


CLASS_WEIGHT = {"motorway": 5.0, "trunk": 4.0, "primary": 3.0,
                "secondary": 2.0, "tertiary": 1.5, "residential": 1.0,
                "unclassified": 1.0, "service": 0.5}


def _weight(tag: str) -> float:
    tag = str(tag).lower()
    for key, w in CLASS_WEIGHT.items():
        if key in tag:
            return w
    return 1.0


def vehicle_heat(grid: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, cfg) -> np.ndarray:
    """(n_cells, 24) W/m2 from traffic.

    City-wide daily vehicle-kilometres are distributed across cells in proportion
    to class-weighted road length, converted to heat at j_per_m, then shaped by
    the traffic profile. Total vehicle-km is the parameter to calibrate against
    CTS survey data; road-class weights are a placeholder for traffic volume.
    """
    prof = np.asarray(cfg["schedules"]["traffic"], dtype=float)
    j_per_m = float(cfg.get_in("vehicles.joules_per_metre", 2200.0))
    total_vkm = float(cfg.get_in("vehicles.daily_vehicle_km_total", 8.0e7))

    roads = roads.to_crs(grid.crs).copy()
    tag_col = "highway" if "highway" in roads.columns else None
    roads["w"] = roads[tag_col].map(_weight) if tag_col else 1.0

    inter = gpd.overlay(roads[["w", "geometry"]], grid[["cell_id", "geometry"]],
                        how="intersection")
    inter["wlen"] = inter.geometry.length * inter["w"]
    wlen = (inter.groupby("cell_id")["wlen"].sum()
                 .reindex(grid["cell_id"]).fillna(0.0).to_numpy())

    share = wlen / wlen.sum() if wlen.sum() > 0 else wlen
    daily_j = share * total_vkm * 1000.0 * j_per_m
    hourly_w = (daily_j[:, None] * prof[None, :] / prof.sum()) * 24.0 / 86400.0
    return (hourly_w / grid.geometry.area.iloc[0]).astype(np.float32)
