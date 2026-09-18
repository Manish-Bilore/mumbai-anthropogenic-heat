"""Sweep AC penetration levels; recompute Qf for each; write one grid file."""
import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from qfmumbai.abm import adopt
from qfmumbai.config import Config
from qfmumbai.gridify import aggregate, make_grid
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.loads import assemble
from qfmumbai.logging_utils import get_logger


def main():
    cfg = Config.load()
    log = get_logger("05_abm", cfg)
    rng = np.random.default_rng(cfg["run"]["seed"])

    stock = read_vector(cfg.path("stock_pop"))
    weather = pd.read_csv(cfg.path("weather"))
    wards = read_vector(cfg.path("wards_raw"))
    grid = make_grid(wards, cfg["grid"]["cell_m"], cfg["crs"]["working"])

    merged = grid.copy()
    previous = None
    for level in cfg["abm"]["penetration_levels"]:
        adopted = adopt(stock, cfg, level, previous, rng)
        previous = adopted

        tmp = stock.copy()
        # adopted buildings run their income-band saturation; others none
        tmp["ac_saturation_base"] = np.where(adopted == 1, tmp["ac_saturation_base"], 0.0)
        res = assemble(tmp, cfg, weather, penetration=None)

        tag = f"p{int(level * 100):02d}"
        g = aggregate(stock, res["qf_w"], grid, prefix=f"{tag}_h")
        cols = [c for c in g.columns if c.startswith(tag)] + ["qf_mean", "qf_peak"]
        g = g.rename(columns={"qf_mean": f"{tag}_mean", "qf_peak": f"{tag}_peak"})
        merged = merged.merge(
            g[["cell_id"] + [c for c in g.columns if c.startswith(tag)]],
            on="cell_id", how="left")

        adopted_hh = stock.loc[adopted == 1, "households"].sum()
        city_mean = g[f"{tag}_mean"].mean()
        res_cells = g.loc[g[f"{tag}_mean"] > 0, f"{tag}_peak"].mean()
        log.info("penetration %.0f%%: %d buildings adopt, %.0f households | "
                 "city mean Qf %.2f W/m2 | mean cell peak %.2f W/m2",
                 level * 100, int(adopted.sum()), adopted_hh, city_mean, res_cells)

    write_vector(merged, cfg.path("abm"))
    write_vector(merged.to_crs(cfg["crs"]["output"]), cfg.path("abm_geojson"))
    log.info("wrote penetration sweep grid")


if __name__ == "__main__":
    main()
