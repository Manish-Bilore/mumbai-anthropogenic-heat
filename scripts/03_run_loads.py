"""Hourly base load, cooling load and waste heat per building (baseline AC fractions)."""
import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from qfmumbai.config import Config
from qfmumbai.io_utils import read_vector, write_vector
from qfmumbai.loads import assemble
from qfmumbai.logging_utils import get_logger


def main():
    cfg = Config.load()
    log = get_logger("03_loads", cfg)

    stock = read_vector(cfg.path("stock_pop"))
    weather = pd.read_csv(cfg.path("weather"))
    log.info("weather: min %.1f C, max %.1f C", weather.temp_c.min(), weather.temp_c.max())

    res = assemble(stock, cfg, weather)

    out = stock.copy()
    out["ac_fraction"] = res["ac_fraction"]
    for h in range(24):
        out[f"qf_h{h:02d}"] = res["qf_w"][:, h]
        out[f"el_h{h:02d}"] = res["electricity_w"][:, h]

    city_mw = res["electricity_w"].sum(axis=0) / 1e6
    qf_mw = res["qf_w"].sum(axis=0) / 1e6
    log.info("city electricity: peak %.0f MW at hour %d, daily mean %.0f MW",
             city_mw.max(), int(city_mw.argmax()) + 1, city_mw.mean())
    log.info("city waste heat: peak %.0f MW, cooling share of electricity %.1f%%",
             qf_mw.max(), 100 * res["e_ac"].sum() / max(res["electricity_w"].sum(), 1))

    p = write_vector(out, cfg.path("loads"))
    log.info("wrote %s", p)


if __name__ == "__main__":
    main()
