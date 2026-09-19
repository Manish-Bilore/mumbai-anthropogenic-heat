"""Buildings -> floors, floor area, archetype, ward."""
import _bootstrap  # noqa: F401
from qfmumbai.config import Config
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.logging_utils import get_logger
from qfmumbai.stock import prepare_stock


def main():
    cfg = Config.load()
    log = get_logger("01_stock", cfg)

    buildings = read_vector(cfg.path("buildings_raw"))
    wards = read_vector(cfg.path("wards_raw"))
    log.info("read %d buildings, %d wards", len(buildings), len(wards))

    stock = prepare_stock(buildings, wards, cfg)
    unmatched = stock["ward"].isna()
    if unmatched.any():
        out_of_scope = stock[unmatched]
        log.warning("dropping %d buildings outside Greater Mumbai (%.1f%% of stock)",
                    int(unmatched.sum()), 100 * unmatched.mean())
        log.warning("their bbox (working CRS): %s",
                    [round(v) for v in out_of_scope.total_bounds])
        out_of_scope[["building_id", "geometry"]].to_parquet(
            cfg.path("stock").parent / "buildings_out_of_scope.parquet")
        stock = stock[~unmatched].copy()

    log.info("archetype counts:\n%s", stock["archetype"].value_counts().to_string())
    log.info("total floor area: %.2f km2", stock["floor_area_m2"].sum() / 1e6)
    log.info("mean floors: %.2f | max: %d", stock["floors"].mean(), stock["floors"].max())

    out = write_vector(stock, cfg.path("stock"))
    log.info("wrote %s", out)


if __name__ == "__main__":
    main()
