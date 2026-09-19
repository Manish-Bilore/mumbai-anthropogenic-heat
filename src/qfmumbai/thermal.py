"""Indoor thermal state and AC operation behaviour.

Why this exists
---------------
Adoption is driven by discomfort, and discomfort is felt indoors. Using outdoor
CDH gives every household in the city the same stimulus, which throws away the
building stock. A tin-roofed chawl and a tower flat under identical weather do
not have the same indoor temperature, and the gap runs the wrong way against
ability to pay: the hottest dwellings belong to the households least able to
buy an AC.

Free-running indoor temperature
-------------------------------
Single-capacitance (1R1C) model per building, integrated hourly over a repeating
typical day until periodic:

    C dT_in/dt = UA_eff (T_out - T_in) + Q_solar + Q_internal

    C          thermal capacitance, J/K = capacitance_j_per_m2k x floor area
    UA_eff     fabric + infiltration conductance, boosted at night when the
               occupants open windows and T_out < T_in
    Q_solar    floor-area solar gain plus a roof term for low-rise dwellings,
               where roof area per dwelling is large (chawls, informal housing)
    Q_internal appliance heat, already computed by loads.base_power

Operation
---------
Ownership is a poor proxy for heat output: a household running one room for two
hours a night and one cooling the whole flat for ten differ fourfold in Qf. Two
behavioural variables are modelled:

    setpoint   higher for lower-income households (bill sensitivity, habituation)
    runtime    logistic in (T_in - setpoint), scaled by a bill-sensitivity factor
               that falls as consumption crosses tariff slabs

Both are read back by loads.cooling_demand through the per-building columns
`ac_setpoint_c` and `ac_runtime_mult`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .loads import base_power

HOURS = 24


# --------------------------------------------------------------------------
# free-running indoor temperature
# --------------------------------------------------------------------------

def _archetype_array(df: pd.DataFrame, cfg, block: str, key: str, default: float) -> np.ndarray:
    table = cfg.get_in(block, {}) or {}
    mapping = {a: float(table.get(a, {}).get(key, default)) for a in cfg["archetypes"]}
    return df["archetype"].map(mapping).fillna(default).to_numpy(float)


def free_running_indoor(df: pd.DataFrame, cfg, weather: pd.DataFrame,
                        delta_t: float = 0.0, spin_days: int = 5) -> np.ndarray:
    """(n_buildings, 24) indoor air temperature with no cooling, degrees C."""
    t_out = weather["temp_c"].to_numpy(float) + delta_t
    n = len(df)

    floor = df["floor_area_m2"].to_numpy(float)
    foot = df["footprint_m2"].to_numpy(float)

    # Free-running conductance is NOT the closed-window UA used for cooling load:
    # windows are open, so the ventilation term is much larger.
    u = df["archetype"].map({a: p_.get("u_value", 2.0) for a, p_ in cfg["archetypes"].items()}
                            ).fillna(2.0).to_numpy(float)
    ach = _archetype_array(df, cfg, "thermal.free_running_ach", "value", 5.0)
    storey_h = 3.0
    perim = 4.0 * np.sqrt(np.maximum(foot, 1.0))
    floors = df["floors"].to_numpy(float)
    envelope = perim * floors * storey_h + foot
    volume = foot * floors * storey_h
    ua_fabric = u * envelope
    ua_vent = 0.33 * ach * volume
    ua = ua_fabric + ua_vent

    cap = _archetype_array(df, cfg, "thermal.capacitance_j_per_m2k", "value", 120e3)
    cap = np.where(cap > 0, cap, 120e3)
    C = np.maximum(cap * floor, 1.0)

    vent_boost = float(cfg.get_in("thermal.night_ventilation_factor", 2.5))

    q_sol_floor = floor * float(cfg["cooling"]["solar_gain_w_per_m2_floor"])
    roof_w = _archetype_array(df, cfg, "thermal.roof_solar_w_per_m2", "value", 0.0)
    q_sol_roof = foot * roof_w
    day = np.zeros(HOURS)
    day[7:19] = 1.0
    q_sol = (q_sol_floor + q_sol_roof)[:, None] * day[None, :]

    q_int = base_power(df, cfg).astype(float)

    t_in = np.full(n, float(t_out.mean()))
    out = np.zeros((n, HOURS), dtype=np.float32)
    dt_s = 3600.0

    for d in range(spin_days):
        for h in range(HOURS):
            night = (h < 7) or (h >= 20)
            ua_h = np.where((t_out[h] < t_in) & night, ua_fabric + ua_vent * vent_boost, ua)
            dT = (ua_h * (t_out[h] - t_in) + q_sol[:, h] + q_int[:, h]) * dt_s / C
            t_in = t_in + np.clip(dT, -5.0, 5.0)     # clip guards stiff cells
            if d == spin_days - 1:
                out[:, h] = t_in
    return out


def discomfort_degree_hours(t_in: np.ndarray, cfg) -> np.ndarray:
    """Indoor degree-hours above the comfort threshold, scaled to a season."""
    thr = float(cfg.get_in("thermal.comfort_threshold_c", 28.0))
    days = float(cfg.get_in("abm_dynamic.cooling_season_days", 210))
    return np.clip(t_in - thr, 0.0, None).sum(axis=1) * days


# --------------------------------------------------------------------------
# operation behaviour
# --------------------------------------------------------------------------

def setpoints(df: pd.DataFrame, cfg) -> np.ndarray:
    """Chosen setpoint per building, from the income band."""
    table = cfg.get_in("operation.setpoint_by_band", {}) or {}
    default = float(cfg["cooling"]["setpoint_c"])
    band = df["income_band"].to_numpy()
    out = np.full(len(df), default, dtype=float)
    for b, v in table.items():
        out[band == int(b)] = float(v)
    return out


def runtime_multiplier(df: pd.DataFrame, cfg, t_in: np.ndarray, t_set: np.ndarray) -> np.ndarray:
    """Fraction of the hour the AC actually runs, per building (scalar per building).

    Logistic in mean indoor exceedance, damped by bill sensitivity: households in
    lower income bands run the unit fewer hours for the same discomfort because
    the marginal tariff slab bites harder.
    """
    c = cfg.get_in("operation", {}) or {}
    k = float(c.get("runtime_slope", 0.8))
    x0 = float(c.get("runtime_midpoint_k", 2.0))
    floor_frac = float(c.get("runtime_floor", 0.15))

    exceed = np.clip(t_in - t_set[:, None], 0.0, None).mean(axis=1)
    frac = 1.0 / (1.0 + np.exp(-k * (exceed - x0)))

    bill = cfg.get_in("operation.bill_sensitivity_by_band", {}) or {}
    band = df["income_band"].to_numpy()
    damp = np.ones(len(df), dtype=float)
    for b, v in bill.items():
        damp[band == int(b)] = float(v)

    return np.clip(floor_frac + (1.0 - floor_frac) * frac * damp, 0.0, 1.0)


_CACHE = {}


def apply_operation_cached(df, cfg, weather, delta_t=0.0, bin_k=0.05):
    """apply_operation, memoised on delta_t rounded to bin_k.

    The RC spin-up dominates runtime, and delta_t moves ~0.01 K per simulated
    year, so recomputing every year is wasted work. Binning at 0.05 K keeps the
    indoor state within a few hundredths of a degree of the exact solution.
    """
    key = round(float(delta_t) / bin_k)
    if key not in _CACHE:
        _CACHE[key] = apply_operation(df, cfg, weather, key * bin_k)
    return _CACHE[key]


def apply_operation(df: pd.DataFrame, cfg, weather: pd.DataFrame,
                    delta_t: float = 0.0) -> pd.DataFrame:
    """Attach ac_setpoint_c, ac_runtime_mult and indoor diagnostics to the stock."""
    t_in = free_running_indoor(df, cfg, weather, delta_t)
    t_set = setpoints(df, cfg)

    out = df.copy()
    out["t_in_mean_c"] = t_in.mean(axis=1)
    out["t_in_max_c"] = t_in.max(axis=1)
    out["discomfort_dh"] = discomfort_degree_hours(t_in, cfg)
    out["ac_setpoint_c"] = t_set
    out["ac_runtime_mult"] = runtime_multiplier(df, cfg, t_in, t_set)
    return out
