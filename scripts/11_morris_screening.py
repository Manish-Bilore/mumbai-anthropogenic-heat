"""Morris screening of the ABM's behavioural coefficients.

Which parameters actually move the answer? Run this BEFORE spending effort
calibrating anything: parameters with a low mu* are not worth fitting.

Fast mode (default): Qf is computed as total building + metabolic watts over the
built floor-cell area, skipping the grid aggregation, so a full 2026-2040 run
costs about a second. Absolute Qf is therefore slightly different from the
gridded pipeline; the sensitivity ranking is unaffected.

Outputs
  data/processed/abm_morris.csv      mu*, mu, sigma per parameter and per output
  figures/abm_morris.png
"""
import _bootstrap  # noqa: F401

import argparse
import copy

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from SALib.analyze import morris as morris_analyze
from SALib.sample import morris as morris_sample

from qfmumbai.abm_dynamic import afford_index, agent_discomfort, build_agents, step, stock_saturation
from qfmumbai.config import Config, ROOT
from qfmumbai.io_utils import read_vector, write_table
from qfmumbai.loads import assemble
from qfmumbai.logging_utils import get_logger
from qfmumbai.qf_other import metabolic_heat
from qfmumbai.thermal import apply_operation, apply_operation_cached

# name -> (config path, low, high)
PARAMS = {
    "b0":              ("abm_dynamic.b0", -3.5, -1.0),
    "b_afford":        ("abm_dynamic.b_afford", 0.5, 3.5),
    "b_discomfort":    ("abm_dynamic.b_discomfort", 0.2, 3.0),
    "b_peer":          ("abm_dynamic.b_peer", 0.0, 3.5),
    "p_cap":           ("abm_dynamic.p_cap", 0.10, 0.45),
    "income_growth":   ("abm_dynamic.income_growth_pa", 0.02, 0.08),
    "price_decline":   ("abm_dynamic.ac_price_decline_pa", 0.00, 0.05),
    "feedback_k":      ("abm_dynamic.feedback_k", 0.0, 0.10),
}


def set_in(cfg: dict, dotted: str, value) -> None:
    node = cfg
    keys = dotted.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = float(value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=int, default=None, help="Morris r")
    args = ap.parse_args()

    cfg0 = Config.load()
    log = get_logger("11_morris", cfg0)
    r = args.trajectories or int(cfg0.get_in("ensemble.sensitivity_trajectories", 10))

    stock = read_vector(cfg0.path("stock_pop"))
    weather = pd.read_csv(cfg0.path("weather"))
    res = stock["is_residential"].to_numpy()

    # built floor-cell area proxy: one 100 m cell per occupied cell footprint
    cell_m = float(cfg0["grid"]["cell_m"])
    cx = np.floor(stock.geometry.centroid.x / cell_m).astype(int)
    cy = np.floor(stock.geometry.centroid.y / cell_m).astype(int)
    built_area = len(set(zip(cx.tolist(), cy.tolist()))) * cell_m ** 2
    log.info("built area proxy: %.1f km2 | %d parameters | r=%d", built_area / 1e6, len(PARAMS), r)

    problem = {"num_vars": len(PARAMS), "names": list(PARAMS),
               "bounds": [[lo, hi] for (_, lo, hi) in PARAMS.values()]}
    X = morris_sample.sample(problem, N=r, num_levels=4)
    log.info("running %d model evaluations", len(X))

    y0 = int(cfg0["abm_dynamic"]["year_start"])
    y1 = int(cfg0["abm_dynamic"]["year_end"])

    def run(sample) -> tuple:
        cfg = Config(copy.deepcopy(dict(cfg0)))
        for name, v in zip(problem["names"], sample):
            set_in(cfg, PARAMS[name][0], v)

        rng = np.random.default_rng(cfg0["run"]["seed"])
        ag = build_agents(stock, cfg)
        state = apply_operation(stock, cfg, weather, 0.0)
        disc_ref = float(np.median(state.loc[res, "discomfort_dh"]))

        def qf_mean(st, dt, sat):
            w = weather.copy(); w["temp_c"] = w["temp_c"] + dt
            tmp = st.copy(); tmp["ac_saturation_base"] = sat
            out = assemble(tmp, cfg, w, penetration=None)
            tot = out["qf_w"] + metabolic_heat(st, cfg)
            return float(tot.sum(axis=0).mean() / built_area)

        qf_base = qf_mean(state, 0.0, stock_saturation(ag, stock))
        delta_t = 0.0
        for year in range(y0, y1 + 1):
            if year > y0:
                state = apply_operation_cached(stock, cfg, weather, delta_t)
                step(ag, cfg, rng, afford_index(cfg, year, y0),
                     agent_discomfort(state, ag), disc_ref)
            q = qf_mean(state, delta_t, stock_saturation(ag, stock))
            delta_t = float(cfg["abm_dynamic"]["feedback_k"]) * (q - qf_base)
        return ag.penetration, q, delta_t

    out = np.array([run(x) for x in X])
    log.info("penetration range across samples: %.1f%% - %.1f%%",
             100 * out[:, 0].min(), 100 * out[:, 0].max())

    rows = []
    for j, label in enumerate(["penetration_2040", "qf_2040_wm2", "delta_t_2040"]):
        Si = morris_analyze.analyze(problem, X, out[:, j], num_levels=4)
        for i, name in enumerate(problem["names"]):
            rows.append(dict(output=label, parameter=name, mu_star=Si["mu_star"][i],
                             mu=Si["mu"][i], sigma=Si["sigma"][i]))
    res_df = pd.DataFrame(rows)
    write_table(res_df, ROOT / "data" / "processed" / "abm_morris.csv")

    for label, g in res_df.groupby("output"):
        top = g.sort_values("mu_star", ascending=False)
        log.info("%s | ranked by mu*: %s", label,
                 ", ".join(f"{t.parameter}={t.mu_star:.3g}" for t in top.itertuples()))

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, (label, g) in zip(axes, res_df.groupby("output")):
        g = g.sort_values("mu_star")
        ax.barh(g.parameter, g.mu_star, color="#f2a541")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("$\\mu^*$")
        ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "abm_morris.png", dpi=150)
    log.info("wrote figures/abm_morris.png")


if __name__ == "__main__":
    main()
