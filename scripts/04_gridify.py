"""Per-building watts -> 100 m grid of W/m2, plus GeoJSON for tiling."""
import _bootstrap  # noqa: F401
import numpy as np

from qfmumbai.config import Config
from qfmumbai.gridify import aggregate, make_grid
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.logging_utils import get_logger
from qfmumbai.benchmark import summary


def main():
    cfg = Config.load()
    log = get_logger("04_grid", cfg)

    loads = read_vector(cfg.path("loads"))
    wards = read_vector(cfg.path("wards_raw"))

    grid = make_grid(wards, cfg["grid"]["cell_m"], cfg["crs"]["working"])
    log.info("grid: %d cells of %d m", len(grid), cfg["grid"]["cell_m"])

    values = loads[[f"qf_h{h:02d}" for h in range(24)]].to_numpy(float)
    out = aggregate(loads, values, grid)

    s = summary(out, cfg)
    log.info("model mean %.2f W/m2 (Sailor %.2f) | peak %.2f W/m2 at %02d:00 (Sailor %.2f at 16:00)",
             s["model_mean_wm2"], s["sailor_mean_wm2"], s["model_peak_wm2"],
             s["model_peak_hour"], s["sailor_peak_wm2"])

    write_vector(out, cfg.path("grid"))
    write_vector(out.to_crs(cfg["crs"]["output"]), cfg.path("grid_geojson"))
    log.info("wrote grid parquet + geojson")


if __name__ == "__main__":
    main()
