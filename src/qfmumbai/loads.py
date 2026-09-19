"""Hourly electricity demand and waste heat for one typical day.

Decomposition (see README):
    P_base(t)  = appliance stock x schedule           [residential]
                 base_w_per_m2 x floor area x schedule [non-residential]
    Q_cool(t)  = UA (T_out - T_set) + Q_solar + Q_internal, clipped at >= 0
    E_ac(t)    = Q_cool / COP, capped at rated capacity, scaled by AC fraction
    Q_f(t)     = P_base(t) + Q_cool(t) + E_ac(t)      [energy balance of the box]
                 i.e. base electricity (1:1) + condenser rejection Q_cool(1+1/COP)
All quantities in watts per building unless stated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HOURS = 24


def _sched(cfg, name: str) -> np.ndarray:
    arr = np.asarray(cfg["schedules"][name], dtype=float)
    if arr.size != HOURS:
        raise ValueError(f"schedule {name} must have 24 values, got {arr.size}")
    return arr


def base_power(df: pd.DataFrame, cfg) -> np.ndarray:
    """(n_buildings, 24) watts of non-cooling electricity."""
    res_s = _sched(cfg, "residential_base")
    com_s = _sched(cfg, "commercial_base")
    n = len(df)
    out = np.zeros((n, HOURS), dtype=np.float32)

    for arch, params in cfg["archetypes"].items():
        mask = (df["archetype"] == arch).to_numpy()
        if not mask.any():
            continue
        if arch.startswith("res_"):
            watts_per_dwelling = float(sum(params.get("appliances", {}).values()))
            per_building = df.loc[mask, "households"].to_numpy() * watts_per_dwelling
            out[mask] = per_building[:, None] * res_s[None, :]
        else:
            density = float(params.get("base_w_per_m2", 20.0))
            per_building = df.loc[mask, "floor_area_m2"].to_numpy() * density
            out[mask] = per_building[:, None] * com_s[None, :]
    return out


def ua_values(df: pd.DataFrame, cfg) -> np.ndarray:
    """Envelope + infiltration conductance, W/K per building."""
    u = df["archetype"].map({a: p.get("u_value", 2.0) for a, p in cfg["archetypes"].items()}).to_numpy(float)
    ach = df["archetype"].map({a: p.get("ach", 1.0) for a, p in cfg["archetypes"].items()}).to_numpy(float)

    footprint = df["footprint_m2"].to_numpy(float)
    floors = df["floors"].to_numpy(float)
    storey_h = 3.0
    perimeter = 4.0 * np.sqrt(np.maximum(footprint, 1.0))          # square-plan approximation
    envelope = perimeter * floors * storey_h + footprint           # walls + roof
    volume = footprint * floors * storey_h

    ua_fabric = u * envelope
    ua_infil = 0.33 * ach * volume                                 # 0.33 Wh/m3K
    return (ua_fabric + ua_infil).astype(np.float32)


def cooling_demand(df: pd.DataFrame, cfg, weather: pd.DataFrame, ac_fraction: np.ndarray) -> dict:
    """Returns dict of (n,24) arrays: q_cool_th (W thermal), e_ac (W electric)."""
    t_out = weather["temp_c"].to_numpy(float)
    if t_out.size != HOURS:
        raise ValueError("weather file must have 24 hourly rows")
    cop = float(cfg["cooling"]["cop"])
    if "ac_setpoint_c" in df.columns:
        t_set = df["ac_setpoint_c"].to_numpy(float)[:, None]
    else:
        t_set = np.full((len(df), 1), float(cfg["cooling"]["setpoint_c"]))

    ua = ua_values(df, cfg)[:, None]                                # (n,1)
    dT = np.clip(t_out[None, :] - t_set, 0.0, None)                 # (n,24)

    solar_density = float(cfg["cooling"]["solar_gain_w_per_m2_floor"])
    day = np.zeros(HOURS); day[7:19] = 1.0
    q_sol = (df["floor_area_m2"].to_numpy(float)[:, None] * solar_density) * day[None, :]

    q_int = base_power(df, cfg) * float(cfg["cooling"]["internal_gain_fraction"])

    occ = np.where(df["is_residential"].to_numpy()[:, None],
                   _sched(cfg, "residential_occupancy")[None, :],
                   _sched(cfg, "commercial_occupancy")[None, :])

    q_cool = (ua * dT + q_sol + q_int) * occ
    q_cool = np.clip(q_cool, 0.0, None)

    cap = df["archetype"].map(
        {a: p.get("ac_capacity_w_th", 5300.0) for a, p in cfg["archetypes"].items()}
    ).fillna(5300.0).to_numpy(float)
    units = np.where(df["is_residential"].to_numpy(), df["households"].to_numpy(float), 1.0)
    # non-residential: scale capacity with floor area (crude), residential: per dwelling
    cap_total = np.where(df["is_residential"].to_numpy(),
                         cap * np.maximum(units, 1.0),
                         df["floor_area_m2"].to_numpy(float) * 100.0)      # 100 W/m2 installed
    q_cool = np.minimum(q_cool, cap_total[:, None])

    if "ac_runtime_mult" in df.columns:
        q_cool = q_cool * df["ac_runtime_mult"].to_numpy(float)[:, None]

    q_cool = q_cool * ac_fraction[:, None]
    e_ac = q_cool / cop
    return {"q_cool_th": q_cool.astype(np.float32), "e_ac": e_ac.astype(np.float32)}


def ac_fraction(df: pd.DataFrame, cfg, penetration: float | None = None, rng=None) -> np.ndarray:
    """Per-building AC fraction. Residential comes from income band (or ABM override),
    non-residential from the fixed archetype value."""
    rng = rng or np.random.default_rng(cfg["run"]["seed"])
    frac = df["archetype"].map(
        {a: p.get("ac_fraction_fixed", 0.0) for a, p in cfg["archetypes"].items()}
    ).fillna(0.0).to_numpy(dtype=float, copy=True)

    res = df["is_residential"].to_numpy()
    base = df["ac_saturation_base"].to_numpy(float)
    if penetration is None:
        frac[res] = base[res]
        return frac

    # rescale the income-based profile so the household-weighted mean hits `penetration`
    hh = df["households"].to_numpy(float)
    w = hh[res]
    current = np.average(base[res], weights=w) if w.sum() > 0 else 0.0
    scale = penetration / current if current > 0 else 0.0
    frac[res] = np.clip(base[res] * scale, 0.0, 1.0)
    return frac


def assemble(df: pd.DataFrame, cfg, weather: pd.DataFrame, penetration=None, rng=None) -> dict:
    """Full hourly result set for one AC penetration level."""
    fr = ac_fraction(df, cfg, penetration, rng)
    p_base = base_power(df, cfg)
    cool = cooling_demand(df, cfg, weather, fr)

    elec = p_base + cool["e_ac"]
    q_f = p_base + cool["q_cool_th"] + cool["e_ac"]      # = base + Q_cool(1 + 1/COP)
    return {"ac_fraction": fr, "p_base": p_base, "e_ac": cool["e_ac"],
            "q_cool_th": cool["q_cool_th"], "electricity_w": elec, "qf_w": q_f}
