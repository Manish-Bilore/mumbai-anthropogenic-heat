"""Dynamic AC-adoption ABM: annual steps, stochastic adoption, heat feedback.

Outputs
  data/processed/abm_timeseries.csv        one row per simulated year
  data/processed/abm_sensitivity.csv       trajectories across feedback_k values
  data/processed/qf_grid_years.parquet     Qf grid for each snapshot year
  data/processed/qf_grid_years.geojson     same, for tiling
  figures/abm_trajectory.png

Run after 02_assign_population.py. Does not need 05_abm_sweep.py.
"""
import _bootstrap  # noqa: F401

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qfmumbai.abm_dynamic import (Agents, afford_index, build_agents,
                                  cooling_degree_hours, step, stock_saturation)
from qfmumbai.config import Config, ROOT
from qfmumbai.gridify import aggregate_fast, assign_cells, make_grid
from qfmumbai.io_utils import read_vector, write_table, write_vector
from qfmumbai.loads import assemble
from qfmumbai.logging_utils import get_logger
from qfmumbai.qf_other import metabolic_heat, vehicle_heat


def qf_for_year(stock, cfg, weather, delta_t, saturation, cell_ids, grid,
                veh=None, prefix="qf_h"):
    """Qf grid (W/m2) for the given AC saturation and temperature increment."""
    w = weather.copy()
    w["temp_c"] = w["temp_c"] + delta_t

    tmp = stock.copy()
    tmp["ac_saturation_base"] = saturation
    res = assemble(tmp, cfg, w, penetration=None)

    qf = res["qf_w"] + metabolic_heat(stock, cfg)
    g = aggregate_fast(cell_ids, qf, grid, prefix=prefix)
    cols = [f"{prefix}{h:02d}" for h in range(24)]
    if veh is not None:
        g[cols] = g[cols].to_numpy() + veh
    built = g[cols].abs().sum(axis=1) > 0.01
    profile = g.loc[built, cols].mean(axis=0).to_numpy()
    return g, profile, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensitivity", action="store_true",
                    help="also sweep feedback_k from the config list")
    args = ap.parse_args()

    cfg = Config.load()
    log = get_logger("09_abm_dynamic", cfg)
    c = cfg["abm_dynamic"]
    rng = np.random.default_rng(cfg["run"]["seed"])

    stock = read_vector(cfg.path("stock_pop"))
    weather = pd.read_csv(cfg.path("weather"))
    wards = read_vector(cfg.path("wards_raw"))
    grid = make_grid(wards, cfg["grid"]["cell_m"], cfg["crs"]["working"])
    cell_ids = assign_cells(stock, grid)
    log.info("grid %d cells | stock %d buildings", len(grid), len(stock))

    roads_path = ROOT / cfg.get_in("vehicles.roads_file", "")
    veh = None
    if roads_path.exists():
        import geopandas as gpd
        veh = vehicle_heat(grid, gpd.read_file(roads_path), cfg)
        log.info("vehicle heat loaded: mean %.2f W/m2", veh.mean())
    else:
        log.warning("no roads file -> vehicle term omitted")

    y0, y1 = int(c["year_start"]), int(c["year_end"])
    snaps = set(int(y) for y in c["snapshot_years"])

    def run(k_feedback: float, seed_offset: int = 0, collect_grids: bool = False):
        r = np.random.default_rng(cfg["run"]["seed"] + seed_offset)
        ag = build_agents(stock, cfg)
        cdh_ref = cooling_degree_hours(weather, cfg, 0.0)

        sat0 = stock_saturation(ag, stock)
        _, prof0, _ = qf_for_year(stock, cfg, weather, 0.0, sat0, cell_ids, grid, veh)
        qf_base = float(prof0.mean())

        delta_t, rows, grids = 0.0, [], {}
        for year in range(y0, y1 + 1):
            cdh = cooling_degree_hours(weather, cfg, delta_t)
            afford = afford_index(cfg, year, y0)
            if year > y0:
                step(ag, cfg, r, afford, cdh, cdh_ref)

            sat = stock_saturation(ag, stock)
            prefix = f"y{year}_h" if year in snaps else "qf_h"
            g, prof, res = qf_for_year(stock, cfg, weather, delta_t, sat,
                                       cell_ids, grid, veh, prefix=prefix)
            qf_mean = float(prof.mean())

            rows.append(dict(year=year, penetration=ag.penetration,
                             ac_households=int(ag.adopted.sum()),
                             afford=afford, delta_t=delta_t,
                             cdh=cdh, qf_mean_wm2=qf_mean, qf_peak_wm2=float(prof.max()),
                             qf_peak_hour=int(prof.argmax()) + 1,
                             elec_peak_mw=float(res["electricity_w"].sum(axis=0).max() / 1e6)))
            if collect_grids and year in snaps:
                grids[year] = g

            delta_t = k_feedback * (qf_mean - qf_base)

        return pd.DataFrame(rows), grids

    k = float(c["feedback_k"])
    log.info("main run: %d-%d, feedback_k=%.3f K per W/m2", y0, y1, k)
    ts, grids = run(k, collect_grids=True)

    for _, r in ts.iterrows():
        log.info("%d | AC %.1f%% (%.2fM hh) | dT %+.2f C | Qf %.2f W/m2 (peak %.2f @ %02d:00) | elec peak %.0f MW",
                 r.year, 100 * r.penetration, r.ac_households / 1e6, r.delta_t,
                 r.qf_mean_wm2, r.qf_peak_wm2, r.qf_peak_hour, r.elec_peak_mw)

    write_table(ts, ROOT / "data" / "processed" / "abm_timeseries.csv")

    merged = grid.copy()
    for year, g in grids.items():
        cols = [c_ for c_ in g.columns if c_.startswith(f"y{year}_")]
        merged = merged.merge(g[["cell_id"] + cols], on="cell_id", how="left")
    write_vector(merged, ROOT / "data" / "processed" / "qf_grid_years.parquet")
    write_vector(merged.to_crs(cfg["crs"]["output"]),
                 ROOT / "data" / "processed" / "qf_grid_years.geojson")
    log.info("wrote snapshot grids for %s", sorted(grids))

    sens = None
    if args.sensitivity:
        frames = []
        for i, kk in enumerate(c["feedback_k_sensitivity"]):
            t, _ = run(float(kk), seed_offset=i + 1)
            t["feedback_k"] = kk
            frames.append(t)
            log.info("k=%.3f -> %d penetration %.1f%%, dT %+.2f C, Qf %.2f W/m2",
                     kk, y1, 100 * t.penetration.iloc[-1], t.delta_t.iloc[-1],
                     t.qf_mean_wm2.iloc[-1])
        sens = pd.concat(frames, ignore_index=True)
        write_table(sens, ROOT / "data" / "processed" / "abm_sensitivity.csv")

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    axes[0].plot(ts.year, 100 * ts.penetration, lw=2, color="#d1495b")
    axes[0].set_ylabel("AC penetration (%)")
    axes[1].plot(ts.year, ts.qf_mean_wm2, lw=2, color="#f2a541")
    axes[1].set_ylabel("Q$_f$ mean, built cells (W m$^{-2}$)")
    axes[2].plot(ts.year, ts.delta_t, lw=2, color="#2f8f9d")
    axes[2].set_ylabel("feedback $\\Delta$T (K)")
    if sens is not None:
        for kk, grp in sens.groupby("feedback_k"):
            axes[0].plot(grp.year, 100 * grp.penetration, lw=1, alpha=0.5, ls="--")
    for a in axes:
        a.set_xlabel("year")
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "abm_trajectory.png", dpi=150)
    log.info("wrote figures/abm_trajectory.png")


if __name__ == "__main__":
    main()
