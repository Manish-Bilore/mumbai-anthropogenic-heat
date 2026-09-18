"""Ward population -> buildings -> households -> income band."""
from __future__ import annotations

import numpy as np
import pandas as pd


def assign_population(stock: pd.DataFrame, ward_pop: pd.DataFrame, cfg, rng=None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(cfg["run"]["seed"])
    df = stock.copy()
    ward_pop = ward_pop.rename(columns=str.lower)
    if "population_mid2023" not in ward_pop.columns:
        raise KeyError("ward population file needs a 'population_mid2023' column")

    res = df["is_residential"]
    share = df["floor_area_m2"].where(res, 0.0)
    ward_total = share.groupby(df["ward"]).transform("sum").replace(0, np.nan)
    pop_lookup = dict(zip(ward_pop["ward"], ward_pop["population_mid2023"]))
    df["ward_population"] = df["ward"].map(pop_lookup)
    df["population"] = (share / ward_total * df["ward_population"]).fillna(0.0)

    occ = {a: p.get("occupants", cfg["population"]["household_size_default"])
           for a, p in cfg["archetypes"].items()}
    hh_size = df["archetype"].map(occ).fillna(cfg["population"]["household_size_default"])
    df["household_size"] = hh_size
    df["households"] = np.where(res, np.maximum(df["population"] / hh_size, 0.0), 0.0)

    df["income_band"] = _income_band(df, cfg, rng)
    sat = cfg["income"]["ac_saturation_by_band"]
    df["ac_saturation_base"] = df["income_band"].map(sat).fillna(0.0).astype(float)
    return df


def _income_band(df: pd.DataFrame, cfg, rng) -> pd.Series:
    """Proxy: ready-reckoner rate if joined upstream, else dwelling area per household."""
    n_bands = int(cfg["income"]["bands"])
    if "rr_rate" in df.columns and df["rr_rate"].notna().any():
        metric = df["rr_rate"]
    else:
        metric = df["floor_area_m2"] / df["households"].replace(0, np.nan)
    band = pd.Series(np.nan, index=df.index)
    valid = metric.notna() & np.isfinite(metric)
    if valid.any():
        band.loc[valid] = pd.qcut(metric[valid].rank(method="first"), n_bands,
                                  labels=False, duplicates="drop")
    band = band.fillna(0)
    band = band.where(~df["is_slum"], cfg["income"]["slum_forced_band"])
    band = band.where(df["is_residential"], -1)   # -1 = not a residential agent
    return band.astype(int)
