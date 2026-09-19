"""Clean raw wards + buildings (+ typology) into the pipeline schema."""
import _bootstrap  # noqa: F401

import geopandas as gpd
import pandas as pd

from qfmumbai.config import Config, ROOT
from qfmumbai.logging_utils import get_logger

RAW = ROOT / "data" / "raw"


def attach_typology(b: gpd.GeoDataFrame, log) -> gpd.GeoDataFrame:
    path = RAW / "mumbai_typology.gpkg"
    if not path.exists():
        log.warning("no typology file -> use_class = unknown")
        b["use_class"] = "unknown"
        return b

    t = gpd.read_file(path)
    log.info("typology cols: %s (%d rows)", t.columns.tolist(), len(t))

    label_col = next((c for c in t.columns
                      if c.lower() in {"typology_label", "typology", "use_class", "label"}), None)
    if label_col is None:
        raise KeyError("no typology label column found")

    id_col = next((c for c in t.columns if c.lower() in {"id", "building_id"}), None)
    if id_col is not None:
        t[id_col] = t[id_col].astype(str)
        b = b.merge(t[[id_col, label_col]].rename(columns={id_col: "building_id"}),
                    on="building_id", how="left")
        log.info("typology joined by id")
    else:
        pts = b.copy()
        pts["geometry"] = b.geometry.centroid
        j = gpd.sjoin(pts[["building_id", "geometry"]], t[[label_col, "geometry"]],
                      how="left", predicate="within")
        b = b.merge(j[["building_id", label_col]].drop_duplicates("building_id"),
                    on="building_id", how="left")
        log.info("typology joined spatially")

    b["use_class"] = (b[label_col].astype(str).str.strip().str.lower()
                      .replace({"nan": "unknown", "none": "unknown"}))
    matched = (b["use_class"] != "unknown").mean()
    log.info("typology matched for %.1f%% of buildings", 100 * matched)
    log.info("use_class counts: %s", b["use_class"].value_counts().head(12).to_dict())
    return b.drop(columns=[label_col])


def main():
    cfg = Config.load()
    log = get_logger("00b_normalise", cfg)

    w = gpd.read_file(RAW / "wards.gpkg")
    w["ward"] = w["Name"].astype(str).str.strip().str.replace(r"\s+", "", regex=True).str.upper()
    w = w[["ward", "geometry"]]
    assert w["ward"].is_unique and len(w) == 24
    w.to_file(RAW / "wards_clean.gpkg", driver="GPKG")
    log.info("wards: %d", len(w))

    b = gpd.read_file(RAW / "buildings.gpkg")
    b = b.rename(columns={"id": "building_id", "height": "height_m"})
    b["building_id"] = b["building_id"].astype(str)
    log.info("buildings read: %d | crs %s", len(b), b.crs)

    b = attach_typology(b, log)
    if "is_slum" not in b.columns:
        b["is_slum"] = False
        log.warning("no slum layer -> res_slum archetype unused; income override inactive")

    bad = b["height_m"].isna() | (b["height_m"] <= 0)
    med = b.loc[~bad, "height_m"].median()
    b.loc[bad, "height_m"] = med
    log.info("height: invalid %d | median %.1f m | p99 %.1f m",
             int(bad.sum()), med, b["height_m"].quantile(0.99))

    out = RAW / "buildings_clean.parquet"
    b[["building_id", "height_m", "use_class", "is_slum", "geometry"]].to_parquet(out)
    log.info("wrote %s (%d buildings)", out, len(b))


if __name__ == "__main__":
    main()
