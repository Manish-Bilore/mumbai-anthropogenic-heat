"""Build the income proxy from ASR locality rates.

Input : data/raw/rr_localities.csv  (locality, region, res_rate_sqft, res_rate_sqm,
                                      ward, ward_confidence, source)
Output: data/raw/ready_reckoner.csv (ward, rr_rate, n_localities, method)

Rules:
  - ward rate = median of its localities' residential rates (INR/sqm)
  - localities with a blank ward are reported and ignored
  - wards with no localities fall back to the median of all mapped wards, flagged
  - low-confidence mappings can be excluded with --min-confidence med|high
Re-run this after correcting any mapping in rr_localities.csv.
"""
import _bootstrap  # noqa: F401

import argparse

import pandas as pd

from qfmumbai.config import Config, ROOT
from qfmumbai.logging_utils import get_logger

RANK = {"low": 0, "med": 1, "high": 2}
WARDS = ["A", "B", "C", "D", "E", "F/S", "F/N", "G/S", "G/N", "H/E", "H/W", "K/E", "K/W",
         "P/S", "P/N", "R/S", "R/C", "R/N", "L", "M/E", "M/W", "N", "S", "T"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-confidence", choices=["low", "med", "high"], default="low")
    args = ap.parse_args()

    cfg = Config.load()
    log = get_logger("08_income", cfg)

    src = ROOT / "data" / "raw" / "rr_localities.csv"
    df = pd.read_csv(src)
    log.info("read %d localities from %s", len(df), src.name)

    unmapped = df[df["ward"].isna() | (df["ward"].astype(str).str.strip() == "")]
    if len(unmapped):
        log.warning("%d localities have no ward mapping: %s",
                    len(unmapped), ", ".join(unmapped["locality"].head(15)))

    keep = df["ward_confidence"].map(RANK).fillna(0) >= RANK[args.min_confidence]
    use = df[keep & df["ward"].notna()].copy()
    log.info("using %d localities at confidence >= %s", len(use), args.min_confidence)

    agg = (use.groupby("ward")["res_rate_sqm"]
              .agg(rr_rate="median", n_localities="size")
              .reindex(WARDS))

    fallback = agg["rr_rate"].median()
    missing = agg["rr_rate"].isna()
    if missing.any():
        log.warning("no localities for wards: %s -> filled with city median %.0f",
                    ", ".join(agg.index[missing]), fallback)
    agg["method"] = ["median_of_localities" if not m else "city_median_fallback" for m in missing]
    agg["rr_rate"] = agg["rr_rate"].fillna(fallback).round().astype(int)
    agg["n_localities"] = agg["n_localities"].fillna(0).astype(int)

    out = ROOT / "data" / "raw" / "ready_reckoner.csv"
    agg.reset_index(names="ward").to_csv(out, index=False)

    spread = agg["rr_rate"].max() / agg["rr_rate"].min()
    log.info("ward rates: min %s (%s), max %s (%s), spread %.1fx",
             f"{agg['rr_rate'].min():,}", agg["rr_rate"].idxmin(),
             f"{agg['rr_rate'].max():,}", agg["rr_rate"].idxmax(), spread)
    log.info("wrote %s", out)


if __name__ == "__main__":
    main()
