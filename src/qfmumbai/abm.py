"""AC adoption: who gets an AC at a given city-wide penetration level.

Rule (placeholder, uncalibrated):
    score = income_weight * income_rank + peer_weight * neighbour_adoption_share
Buildings are ranked by score and adopted until the household-weighted
penetration target is met. Peer share is computed on the previous level's
outcome, which makes the sweep path-dependent in the same way adoption is.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd


def neighbour_share(stock: gpd.GeoDataFrame, adopted: np.ndarray, radius_m: float) -> np.ndarray:
    """Share of neighbours within radius_m that have adopted. KD-tree on centroids
    so this stays tractable at 10^5-10^6 buildings."""
    from scipy.spatial import cKDTree

    pts = np.c_[stock.geometry.centroid.x.to_numpy(), stock.geometry.centroid.y.to_numpy()]
    tree = cKDTree(pts)
    counts = tree.query_ball_point(pts, r=radius_m, return_length=True)
    # sum of adopted neighbours via a second tree pass on adopters only
    adopters = pts[adopted.astype(bool)]
    if len(adopters) == 0:
        return np.zeros(len(stock), dtype=np.float32)
    atree = cKDTree(adopters)
    hits = atree.query_ball_point(pts, r=radius_m, return_length=True)
    return (hits / np.maximum(counts, 1)).astype(np.float32)


def adopt(stock: gpd.GeoDataFrame, cfg, penetration: float,
          previous: np.ndarray | None = None, rng=None) -> np.ndarray:
    """Returns a 0/1 adoption vector over residential buildings (others = 0)."""
    rng = rng or np.random.default_rng(cfg["run"]["seed"])
    res = stock["is_residential"].to_numpy()
    n = len(stock)

    income_rank = stock["income_band"].rank(pct=True).to_numpy(float)
    if previous is None:
        peer = np.zeros(n, dtype=float)
    else:
        peer = neighbour_share(stock, previous, cfg["abm"]["peer_radius_m"])

    score = (cfg["abm"]["income_weight"] * income_rank
             + cfg["abm"]["peer_weight"] * peer
             + rng.normal(0, 0.02, n))
    score = np.where(res, score, -np.inf)

    hh = stock["households"].to_numpy(float)
    target = penetration * hh[res].sum()
    order = np.argsort(-score)
    adopted = np.zeros(n, dtype=np.int8)
    cum = 0.0
    for i in order:
        if not res[i] or cum >= target:
            break
        adopted[i] = 1
        cum += hh[i]
    return adopted
