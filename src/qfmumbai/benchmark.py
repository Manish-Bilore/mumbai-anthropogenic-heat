"""Compare modelled Qf against the Sailor et al. (2015) extrapolation for Mumbai."""
from __future__ import annotations

import numpy as np
import pandas as pd

SAILOR_SUMMER_SHAPE = np.array(
    [0.25, 0.23, 0.25, 0.21, 0.22, 0.29, 0.53, 0.82, 0.87, 0.80, 0.80, 0.84,
     0.89, 0.89, 0.93, 1.00, 0.90, 0.78, 0.56, 0.48, 0.44, 0.41, 0.36, 0.30]
)


def city_profile(grid: pd.DataFrame, prefix: str = "qf_h") -> np.ndarray:
    cols = [f"{prefix}{h:02d}" for h in range(24)]
    return grid[cols].mean(axis=0).to_numpy()


def compare(grid: pd.DataFrame, cfg) -> pd.DataFrame:
    model = city_profile(grid)
    peak = float(cfg["benchmark"]["sailor_summer_peak_wm2"])
    sailor = SAILOR_SUMMER_SHAPE * peak
    return pd.DataFrame({
        "hour": np.arange(1, 25),
        "model_wm2": model,
        "sailor_wm2": sailor,
        "ratio": np.divide(model, sailor, out=np.zeros(24), where=sailor > 0),
    })


def summary(grid: pd.DataFrame, cfg) -> dict:
    model = city_profile(grid)
    return {
        "model_mean_wm2": float(model.mean()),
        "model_peak_wm2": float(model.max()),
        "model_peak_hour": int(model.argmax() + 1),
        "sailor_mean_wm2": float(cfg["benchmark"]["sailor_summer_mean_wm2"]),
        "sailor_peak_wm2": float(cfg["benchmark"]["sailor_summer_peak_wm2"]),
        "sailor_peak_hour": 16,
    }
