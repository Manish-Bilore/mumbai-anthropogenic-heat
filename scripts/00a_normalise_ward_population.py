"""BMC ward-population export -> pipeline schema.
Input : data/raw/mumbai_ward_population_bmc.csv  (Region, Ward, Population)
Output: data/raw/mumbai_ward_population_2023.csv (ward, zone, population_mid2023, zone_area_km2)
"""
import _bootstrap  # noqa: F401

import pandas as pd

from qfmumbai.config import Config, ROOT
from qfmumbai.logging_utils import get_logger

ZONE = {"CITY": ("City", 72.02),
        "WESTERN": ("Western Suburbs", 232.55),
        "EASTERN": ("Eastern Suburbs", 178.57)}


def main():
    cfg = Config.load()
    log = get_logger("00a_wardpop", cfg)

    src = ROOT / "data" / "raw" / "mumbai_ward_population_bmc.csv"
    df = pd.read_csv(src)

    df["Ward"] = df["Ward"].astype(str).str.replace(r"\s+", "", regex=True).str.upper()
    df["Region"] = df["Region"].astype(str).str.strip().str.upper()
    df = df[~df["Ward"].eq("TOTAL")].copy()

    df["zone"] = df["Region"].map(lambda r: ZONE[r][0])
    df["zone_area_km2"] = df["Region"].map(lambda r: ZONE[r][1])

    out = (df.rename(columns={"Ward": "ward", "Population": "population_mid2023"})
             [["ward", "zone", "population_mid2023", "zone_area_km2"]])

    assert len(out) == 24, f"expected 24 wards, got {len(out)}"
    log.info("total population %s across %d wards",
             f"{out.population_mid2023.sum():,}", len(out))
    log.info("ward codes: %s", ", ".join(out["ward"]))

    dst = ROOT / "data" / "raw" / "mumbai_ward_population_2023.csv"
    out.to_csv(dst, index=False)
    log.info("wrote %s", dst)


if __name__ == "__main__":
    main()
