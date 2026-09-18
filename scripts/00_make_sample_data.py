"""Generate synthetic buildings/wards/weather so the pipeline runs end to end
before the real data lands. Writes to data/raw/ only if files are absent."""
import _bootstrap  # noqa: F401
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, box

from qfmumbai.config import Config, ROOT
from qfmumbai.logging_utils import get_logger


def main():
    cfg = Config.load()
    log = get_logger("00_sample", cfg)
    rng = np.random.default_rng(cfg["run"]["seed"])
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    # 3 fake wards, 2 km x 2 km each, in UTM 43N near Mumbai
    x0, y0, size = 280000, 2090000, 2000
    wards = gpd.GeoDataFrame(
        {"ward": ["X1", "X2", "X3"]},
        geometry=[box(x0 + i * size, y0, x0 + (i + 1) * size, y0 + size) for i in range(3)],
        crs=cfg["crs"]["working"],
    )

    rows, geoms = [], []
    n_per_ward = 800
    classes = ["residential", "residential", "residential", "commercial/retail", "office", "industrial"]
    for wi in range(3):
        for k in range(n_per_ward):
            cx = rng.uniform(x0 + wi * size + 50, x0 + (wi + 1) * size - 50)
            cy = rng.uniform(y0 + 50, y0 + size - 50)
            w = rng.uniform(6, 30)
            d = rng.uniform(6, 30)
            geoms.append(Polygon([(cx, cy), (cx + w, cy), (cx + w, cy + d), (cx, cy + d)]))
            uc = classes[rng.integers(0, len(classes))]
            slum = bool(rng.random() < 0.18 and uc == "residential")
            h = rng.uniform(3, 8) if slum else float(np.clip(rng.lognormal(2.6, 0.6), 3, 120))
            rows.append({"building_id": f"W{wi}_{k:05d}", "height_m": h,
                         "use_class": uc, "is_slum": slum})
    buildings = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs=cfg["crs"]["working"])

    hours = np.arange(24)
    temp = 29.5 + 4.5 * np.sin((hours - 9) / 24 * 2 * np.pi)   # peak ~15:00, min ~03:00
    weather = pd.DataFrame({"hour": hours, "temp_c": np.round(temp, 2)})

    pop = pd.DataFrame({"ward": ["X1", "X2", "X3"],
                        "zone": ["Sample"] * 3,
                        "population_mid2023": [180000, 240000, 120000]})

    targets = {
        raw / "buildings.parquet": lambda p: buildings.to_parquet(p),
        raw / "wards.gpkg": lambda p: wards.to_file(p, driver="GPKG"),
        raw / "weather_typical_day.csv": lambda p: weather.to_csv(p, index=False),
        raw / "mumbai_ward_population_2023.csv": lambda p: pop.to_csv(p, index=False),
    }
    for path, writer in targets.items():
        if path.exists():
            log.info("exists, skipping: %s", path.name)
            continue
        writer(path)
        log.info("wrote sample %s", path.name)
    log.info("sample stock: %d buildings across %d wards", len(buildings), len(wards))


if __name__ == "__main__":
    main()
