"""Daily Tmax/Tmin record -> one typical pre-monsoon day at hourly resolution.

Selection: median Tmax across April-May of the last N years; Tmin = median of the
same window. Expansion: Parton & Logan (1981) - sine from sunrise to sunset with a
lag on Tmax, exponential decay overnight.
Output: data/raw/weather_typical_day.csv (hour, temp_c)
"""
import _bootstrap  # noqa: F401

import argparse

import numpy as np
import pandas as pd

from qfmumbai.config import Config, ROOT
from qfmumbai.logging_utils import get_logger

SUNRISE, SUNSET = 6.2, 19.0     # Mumbai, early May
LAG_A, DECAY_B = 1.86, 2.2      # Parton-Logan coefficients


def diurnal(tmax: float, tmin: float) -> np.ndarray:
    hours = np.arange(24) + 0.5
    day_len = SUNSET - SUNRISE
    night_len = 24 - day_len
    t_sunset = (tmax - tmin) * np.sin(np.pi * day_len / (day_len + 2 * LAG_A)) + tmin

    out = np.empty(24)
    for i, h in enumerate(hours):
        if SUNRISE <= h <= SUNSET:
            out[i] = (tmax - tmin) * np.sin(np.pi * (h - SUNRISE) / (day_len + 2 * LAG_A)) + tmin
        else:
            dt = h - SUNSET if h > SUNSET else h + 24 - SUNSET
            out[i] = tmin + (t_sunset - tmin) * np.exp(-DECAY_B * dt / night_len)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--from-year", type=int, default=None,
                    help="ignore records before this year (source change in 2020)")
    ap.add_argument("--months", type=int, nargs="+", default=[4, 5])
    args = ap.parse_args()

    cfg = Config.load()
    log = get_logger("00c_weather", cfg)

    src = ROOT / "data" / "raw" / "mumbai_daily_temperature_1951_2024.csv"
    df = pd.read_csv(src)
    raw = df["Date"].astype(str).str.strip()
    dt = pd.to_datetime(raw, format="%d-%m-%Y", errors="coerce")
    serial = pd.to_numeric(raw.where(dt.isna()), errors="coerce")
    dt = dt.fillna(pd.to_datetime(serial, unit="D", origin="1899-12-30"))
    dt = dt.fillna(pd.to_datetime(raw.where(dt.isna()), errors="coerce", dayfirst=True))
    log.info("dates: %d parsed, %d unparseable", int(dt.notna().sum()), int(dt.isna().sum()))
    df["Date"] = dt
    df = df[df["Date"].notna()]
    last = df["Date"].dt.year.max()
    start = args.from_year if args.from_year else last - args.years + 1
    sel = df[(df["Date"].dt.year >= start) & (df["Date"].dt.month.isin(args.months))].copy()
    log.info("window: %s-%s, months %s -> %d days", start, last, args.months, len(sel))

    for c in ("Temp Max", "Temp Min"):
        sel[c] = pd.to_numeric(sel[c], errors="coerce")
    n_bad = int(sel[["Temp Max", "Temp Min"]].isna().any(axis=1).sum())
    sel = sel.dropna(subset=["Temp Max", "Temp Min"])
    log.info("dropped %d days with non-numeric temperature; %d remain", n_bad, len(sel))
    tmax = float(sel["Temp Max"].median())
    tmin = float(sel["Temp Min"].median())
    log.info("median Tmax %.2f C | median Tmin %.2f C | mean DTR %.2f C",
             tmax, tmin, float((sel["Temp Max"] - sel["Temp Min"]).mean()))

    temps = diurnal(tmax, tmin)
    out = pd.DataFrame({"hour": np.arange(24), "temp_c": np.round(temps, 2)})
    log.info("hourly: min %.2f at %02d:00 | max %.2f at %02d:00 | hours above 24 C: %d",
             out.temp_c.min(), int(out.temp_c.idxmin()),
             out.temp_c.max(), int(out.temp_c.idxmax()), int((out.temp_c > 24).sum()))

    dst = ROOT / "data" / "raw" / "weather_typical_day.csv"
    out.to_csv(dst, index=False)
    log.info("wrote %s", dst)


if __name__ == "__main__":
    main()
