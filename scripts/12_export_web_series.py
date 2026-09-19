"""Export the ABM trajectory to web/series.json so the viewer stops hardcoding numbers.

Reads  data/processed/abm2_timeseries.csv  (+ abm2_thermal_wards.csv if present)
Writes web/series.json
"""
import _bootstrap  # noqa: F401

import json

import pandas as pd

from qfmumbai.config import Config, ROOT
from qfmumbai.io_utils import read_vector
from qfmumbai.logging_utils import get_logger


def main():
    cfg = Config.load()
    log = get_logger("12_web_series", cfg)

    ts = pd.read_csv(ROOT / "data" / "processed" / "abm2_timeseries.csv").set_index("year")
    stock = read_vector(cfg.path("stock_pop"))
    hh_total = float(stock.loc[stock.is_residential, "households"].sum())

    years = [int(y) for y in cfg["abm_dynamic"]["snapshot_years"]]
    series = {}
    for y in years:
        if y not in ts.index:
            log.warning("year %d missing from timeseries", y)
            continue
        r = ts.loc[y]
        series[str(y)] = dict(
            pen=round(100 * float(r.pen_med), 1),
            hh=round(float(r.pen_med) * hh_total / 1e6, 2),
            qf=round(float(r.qf_med), 2),
            peak=round(float(r.peak_med), 2),
            dt=round(float(r.dt_med), 2),
            mw=int(round(float(r.elec_med))),
            runtime=round(float(r.runtime_med), 2),
        )

    payload = {
        "years": years,
        "series": series,
        "meta": {
            "config_hash": cfg.hash,
            "households_total": int(hh_total),
            "feedback_k": float(cfg["abm_dynamic"]["feedback_k"]),
            "note": "uncalibrated prototype; see README known-wrong list",
        },
    }

    thermal = ROOT / "data" / "processed" / "abm2_thermal_wards.csv"
    if thermal.exists():
        t = pd.read_csv(thermal)
        by_band = (t.groupby("income_band")
                    .apply(lambda g: pd.Series({
                        "t_in_mean": (g.t_in_mean * g.households).sum() / max(g.households.sum(), 1),
                        "discomfort": (g.discomfort * g.households).sum() / max(g.households.sum(), 1),
                    }), include_groups=False)
                    .round(1).reset_index())
        payload["thermal_by_band"] = by_band.to_dict(orient="records")

    out = ROOT / "web" / "series.json"
    out.write_text(json.dumps(payload, indent=2))
    log.info("wrote %s for years %s", out, years)
    for y, v in series.items():
        log.info("  %s: AC %.1f%% (%.2fM hh) | Qf %.2f | peak %.2f | dT %+.2f | %d MW",
                 y, v["pen"], v["hh"], v["qf"], v["peak"], v["dt"], v["mw"])


if __name__ == "__main__":
    main()
