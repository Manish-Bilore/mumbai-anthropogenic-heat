"""Dynamic AC-adoption ABM, v2: indoor discomfort, operation behaviour, ensembles.

Differences from 09_abm_dynamic.py
  - adoption responds to INDOOR discomfort degree-hours per agent (1R1C model),
    not to a single city-wide outdoor CDH
  - AC-owning households choose a setpoint and an operating fraction, so Qf
    depends on how the unit is run, not only on whether it exists
  - runs N stochastic replicates and reports median with a 10-90 band

Outputs
  data/processed/abm2_timeseries.csv       median + quantiles per year
  data/processed/abm2_replicates.csv       every replicate, every year
  data/processed/abm2_thermal_wards.csv    indoor temp / discomfort by ward + band
  data/processed/qf_grid_years.parquet     snapshot grids (median replicate)
  data/processed/qf_grid_years.geojson
  figures/abm2_trajectory.png
"""
import _bootstrap  # noqa: F401

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qfmumbai.abm_dynamic import (afford_index, agent_discomfort, build_agents, step,
                                  stock_saturation)
from qfmumbai.config import Config, ROOT
from qfmumbai.gridify import aggregate_fast, assign_cells, make_grid
from qfmumbai.io_utils import read_vector, write_table, write_vector
from qfmumbai.loads import assemble
from qfmumbai.logging_utils import get_logger
from qfmumbai.qf_other import metabolic_heat, vehicle_heat
from qfmumbai.thermal import apply_operation, apply_operation_cached


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=None)
    ap.add_argument("--no-grids", action="store_true", help="skip snapshot grids (faster)")
    args = ap.parse_args()

    cfg = Config.load()
    log = get_logger("10_abm_ensemble", cfg)
    c = cfg["abm_dynamic"]
    n_rep = args.replicates or int(cfg.get_in("ensemble.replicates", 30))

    stock = read_vector(cfg.path("stock_pop"))
    weather = pd.read_csv(cfg.path("weather"))
    wards = read_vector(cfg.path("wards_raw"))
    grid = make_grid(wards, cfg["grid"]["cell_m"], cfg["crs"]["working"])
    cell_ids = assign_cells(stock, grid)

    roads_path = ROOT / cfg.get_in("vehicles.roads_file", "")
    veh = None
    if roads_path.exists():
        import geopandas as gpd
        veh = vehicle_heat(grid, gpd.read_file(roads_path), cfg)

    y0, y1 = int(c["year_start"]), int(c["year_end"])
    snaps = sorted(int(y) for y in c["snapshot_years"])
    k_fb = float(c["feedback_k"])

    # --- indoor thermal state at delta_t = 0: the baseline the agents live in ---
    base = apply_operation(stock, cfg, weather, 0.0)
    res = base["is_residential"]
    log.info("indoor temp by archetype (mean / max over the day):")
    for a, g in base[res].groupby("archetype"):
        log.info("   %-12s %.1f / %.1f C | discomfort %.0f Kh | setpoint %.1f | runtime %.2f",
                 a, g.t_in_mean_c.mean(), g.t_in_max_c.mean(), g.discomfort_dh.mean(),
                 g.ac_setpoint_c.mean(), g.ac_runtime_mult.mean())
    disc_ref = float(np.median(base.loc[res, "discomfort_dh"]))
    log.info("reference discomfort (median residential): %.0f Kh", disc_ref)

    ward_tbl = (base[res].groupby(["ward", "income_band"])
                .agg(t_in_mean=("t_in_mean_c", "mean"), t_in_max=("t_in_max_c", "mean"),
                     discomfort=("discomfort_dh", "mean"), households=("households", "sum"))
                .reset_index())
    write_table(ward_tbl, ROOT / "data" / "processed" / "abm2_thermal_wards.csv")

    def qf_of(state_stock, delta_t, sat, prefix="qf_h"):
        w = weather.copy()
        w["temp_c"] = w["temp_c"] + delta_t
        tmp = state_stock.copy()
        tmp["ac_saturation_base"] = sat
        r = assemble(tmp, cfg, w, penetration=None)
        qf = r["qf_w"] + metabolic_heat(state_stock, cfg)
        g = aggregate_fast(cell_ids, qf, grid, prefix=prefix)
        cols = [f"{prefix}{h:02d}" for h in range(24)]
        if veh is not None:
            g[cols] = g[cols].to_numpy() + veh
        built = g[cols].abs().sum(axis=1) > 0.01
        return g, g.loc[built, cols].mean(axis=0).to_numpy(), r

    def one_run(seed: int, keep_grids: bool):
        rng = np.random.default_rng(seed)
        ag = build_agents(stock, cfg)
        state = base
        _, prof0, _ = qf_of(state, 0.0, stock_saturation(ag, stock))
        qf_base = float(prof0.mean())

        delta_t, rows, grids = 0.0, [], {}
        for year in range(y0, y1 + 1):
            # agents re-read their indoor environment each year (it shifts with delta_t)
            if year > y0:
                state = apply_operation_cached(stock, cfg, weather, delta_t)
                disc = agent_discomfort(state, ag)
                step(ag, cfg, rng, afford_index(cfg, year, y0), disc, disc_ref)

            sat = stock_saturation(ag, stock)
            prefix = f"y{year}_h" if (keep_grids and year in snaps) else "qf_h"
            g, prof, r = qf_of(state, delta_t, sat, prefix)
            qf_mean = float(prof.mean())

            rows.append(dict(seed=seed, year=year, penetration=ag.penetration,
                             ac_households=int(ag.adopted.sum()), delta_t=delta_t,
                             qf_mean_wm2=qf_mean, qf_peak_wm2=float(prof.max()),
                             qf_peak_hour=int(prof.argmax()) + 1,
                             mean_runtime=float(state.loc[res, "ac_runtime_mult"].mean()),
                             elec_peak_mw=float(r["electricity_w"].sum(axis=0).max() / 1e6)))
            if keep_grids and year in snaps:
                grids[year] = g
            delta_t = k_fb * (qf_mean - qf_base)
        return pd.DataFrame(rows), grids

    log.info("running %d replicates, %d-%d, feedback_k=%.3f", n_rep, y0, y1, k_fb)
    frames, grids = [], {}
    for i in range(n_rep):
        keep = (i == 0) and not args.no_grids
        t, g = one_run(cfg["run"]["seed"] + i, keep)
        frames.append(t)
        if keep:
            grids = g
        if i == 0 or (i + 1) % 10 == 0:
            log.info("  replicate %d/%d: 2040 penetration %.1f%%, Qf %.2f W/m2",
                     i + 1, n_rep, 100 * t.penetration.iloc[-1], t.qf_mean_wm2.iloc[-1])

    reps = pd.concat(frames, ignore_index=True)
    write_table(reps, ROOT / "data" / "processed" / "abm2_replicates.csv")

    agg = (reps.groupby("year")
           .agg(pen_med=("penetration", "median"),
                pen_p10=("penetration", lambda s: s.quantile(0.10)),
                pen_p90=("penetration", lambda s: s.quantile(0.90)),
                qf_med=("qf_mean_wm2", "median"),
                qf_p10=("qf_mean_wm2", lambda s: s.quantile(0.10)),
                qf_p90=("qf_mean_wm2", lambda s: s.quantile(0.90)),
                peak_med=("qf_peak_wm2", "median"),
                dt_med=("delta_t", "median"),
                runtime_med=("mean_runtime", "median"),
                elec_med=("elec_peak_mw", "median")).reset_index())
    write_table(agg, ROOT / "data" / "processed" / "abm2_timeseries.csv")

    for _, r in agg.iterrows():
        log.info("%d | AC %.1f%% [%.1f-%.1f] | runtime %.2f | dT %+.2f C | Qf %.2f [%.2f-%.2f] | elec %.0f MW",
                 r.year, 100 * r.pen_med, 100 * r.pen_p10, 100 * r.pen_p90, r.runtime_med,
                 r.dt_med, r.qf_med, r.qf_p10, r.qf_p90, r.elec_med)

    if grids:
        merged = grid.copy()
        for year, g in grids.items():
            cols = [x for x in g.columns if x.startswith(f"y{year}_")]
            merged = merged.merge(g[["cell_id"] + cols], on="cell_id", how="left")
        write_vector(merged, ROOT / "data" / "processed" / "qf_grid_years.parquet")
        write_vector(merged.to_crs(cfg["crs"]["output"]),
                     ROOT / "data" / "processed" / "qf_grid_years.geojson")
        log.info("wrote snapshot grids %s", sorted(grids))

    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    ax[0].fill_between(agg.year, 100 * agg.pen_p10, 100 * agg.pen_p90, alpha=0.25, color="#d1495b")
    ax[0].plot(agg.year, 100 * agg.pen_med, lw=2, color="#d1495b")
    ax[0].set_ylabel("AC penetration (%)")
    ax[1].fill_between(agg.year, agg.qf_p10, agg.qf_p90, alpha=0.25, color="#f2a541")
    ax[1].plot(agg.year, agg.qf_med, lw=2, color="#f2a541")
    ax[1].set_ylabel("Q$_f$ mean, built cells (W m$^{-2}$)")
    ax[2].plot(agg.year, agg.dt_med, lw=2, color="#2f8f9d")
    ax[2].set_ylabel("feedback $\\Delta$T (K)")
    for a in ax:
        a.set_xlabel("year")
        a.grid(alpha=0.3)
    fig.suptitle(f"Mumbai AC adoption ABM, {n_rep} replicates (median, 10-90 band)", fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "abm2_trajectory.png", dpi=150)
    log.info("wrote figures/abm2_trajectory.png")


if __name__ == "__main__":
    main()
