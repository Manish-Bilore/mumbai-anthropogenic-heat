"""Ward population -> buildings -> households -> income band."""
import _bootstrap  # noqa: F401
import pandas as pd

from qfmumbai.config import Config
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.logging_utils import get_logger
from qfmumbai.population import assign_population


def main():
    cfg = Config.load()
    log = get_logger("02_population", cfg)

    stock = read_vector(cfg.path("stock"))
    ward_pop = pd.read_csv(cfg.path("ward_population"))

    rr_path = cfg.path("rr_rates")
    if rr_path.exists():
        rr = pd.read_csv(rr_path)
        stock = stock.merge(rr, on="ward", how="left")
        log.info("joined ready-reckoner rates as income proxy")
    else:
        log.warning("no ready-reckoner file; falling back to dwelling-area proxy for income")

    out = assign_population(stock, ward_pop, cfg)
    log.info("allocated population: %.0f (ward input total %.0f)",
             out["population"].sum(), ward_pop["population_mid2023"].sum())
    log.info("households: %.0f | mean AC saturation (hh-weighted): %.3f",
             out["households"].sum(),
             (out["ac_saturation_base"] * out["households"]).sum() / max(out["households"].sum(), 1))
    log.info("income band counts:\n%s", out["income_band"].value_counts().sort_index().to_string())

    p = write_vector(out, cfg.path("stock_pop"))
    log.info("wrote %s", p)


if __name__ == "__main__":
    main()
