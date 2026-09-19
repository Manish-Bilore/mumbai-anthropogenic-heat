"""Per-building watts -> 100 m grid of W/m2, plus GeoJSON for tiling."""
import _bootstrap  # noqa: F401
import numpy as np

from qfmumbai.config import Config, ROOT
from qfmumbai.gridify import aggregate, make_grid
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.logging_utils import get_logger
from qfmumbai.benchmark import summary
from qfmumbai.qf_other import metabolic_heat, vehicle_heat


def main():
    cfg = Config.load()
    log = get_logger("04_grid", cfg)

    loads = read_vector(cfg.path("loads"))
    wards = read_vector(cfg.path("wards_raw"))

    grid = make_grid(wards, cfg["grid"]["cell_m"], cfg["crs"]["working"])
    log.info("grid: %d cells of %d m", len(grid), cfg["grid"]["cell_m"])

    values = loads[[f"qf_h{h:02d}" for h in range(24)]].to_numpy(float)

    met = metabolic_heat(loads, cfg)
    log.info("metabolism: %.0f MW mean, %.0f MW peak",
             met.sum(axis=0).mean()/1e6, met.sum(axis=0).max()/1e6)
    values = values + met

    out = aggregate(loads, values, grid)
    out["has_building"] = (out[[f'qf_h{h:02d}' for h in range(24)]].abs().sum(axis=1) > 0.01)

    roads_path = ROOT / cfg.get_in("vehicles.roads_file", "")
    if roads_path.exists():
        import geopandas as gpd
        roads = gpd.read_file(roads_path)
        veh = vehicle_heat(out, roads, cfg)
        for h in range(24):
            out[f"qf_h{h:02d}"] = out[f"qf_h{h:02d}"] + veh[:, h]
        log.info("vehicles: mean %.2f W/m2 over built cells", veh[veh.sum(axis=1) > 0].mean())
    else:
        log.warning("no roads file at %s -> vehicle term skipped", roads_path)

    hcols = [f"qf_h{h:02d}" for h in range(24)]
    out["qf_mean"] = out[hcols].mean(axis=1)
    out["qf_peak"] = out[hcols].max(axis=1)
    out["peak_hour"] = out[hcols].values.argmax(axis=1)

    s = summary(out, cfg)
    log.info("model mean %.2f W/m2 (Sailor %.2f) | peak %.2f W/m2 at %02d:00 (Sailor %.2f at 16:00)",
             s["model_mean_wm2"], s["sailor_mean_wm2"], s["model_peak_wm2"],
             s["model_peak_hour"], s["sailor_peak_wm2"])

    write_vector(out, cfg.path("grid"))
    write_vector(out.to_crs(cfg["crs"]["output"]), cfg.path("grid_geojson"))
    log.info("wrote grid parquet + geojson")


if __name__ == "__main__":
    main()
