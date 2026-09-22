"""Ground-truth loaders for the labeling pipeline. Every loader records
provenance (source URL, file SHA256, download/record counts); nothing is
invented, and a missing/corrupt source raises instead of yielding guesses.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd
from shapely.geometry import shape
from shapely.validation import make_valid

# Pinned EMSR533 final products (verified links from the activation page).
EMS_BASE_URL = (
    "https://cems-mapping-website.s3.eu-west-1.amazonaws.com"
    "/static/activations/EMSR533"
)
EMS_PRODUCTS = [
    {"file": "EMSR533_AOI01_DEL_PRODUCT_r1_RTP01_v2_vector.zip",
     "aoi": "AOI01-TiziOuzou", "product": "DEL_PRODUCT", "version": "v2",
     "delivery": "2021-08-16T08:24:01"},
    {"file": "EMSR533_AOI01_GRA_PRODUCT_r1_RTP01_v1_vector.zip",
     "aoi": "AOI01-TiziOuzou", "product": "GRA_PRODUCT", "version": "v1",
     "delivery": "2021-08-21T01:27:04"},
    {"file": "EMSR533_AOI02_DEL_PRODUCT_r1_RTP01_v1_vector.zip",
     "aoi": "AOI02-Aokas", "product": "DEL_PRODUCT", "version": "v1",
     "delivery": "2021-08-13T02:41:42"},
    {"file": "EMSR533_AOI02_GRA_PRODUCT_r1_RTP01_v1_vector.zip",
     "aoi": "AOI02-Aokas", "product": "GRA_PRODUCT", "version": "v1",
     "delivery": "2021-08-20T21:13:42"},
]
# Event window: activation reason reports fires since 2021-08-09 (-1d pad) and
# the last EMS delivery is 2021-08-21 (+1d pad).
EMS_EVENT_WINDOW = ("2021-08-08", "2021-08-22")

# Pinned annual gas-flare catalogs (verified links from the EOG product page).
VNF_BASE_URL = "https://eogdata.mines.edu/global_flare_data"
VNF_FILES = {
    2024: "VIIRS_Global_flaring_d.7_slope_0.029353_2024_v20240730_web_IDmatch.xlsx",
    2023: "VIIRS_Global_flaring_d.7_slope_0.029353_2023_v20230614_web_IDmatch.xlsx",
    2022: "VIIRS_Global_flaring_d.7_slope_0.029353_2022_v20230526_web.xlsx",
    2021: "VIIRS_Global_flaring_d.7_slope_0.029353_2021_web.xlsx",
    2020: "VIIRS_Global_flaring_d.7_slope_0.029353_2020_web_v1.xlsx",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_geojson_from_zip(zip_path: Path, suffix: str) -> list[dict]:
    """Read matching *.json members (EMS GeoJSON) straight from the zip."""
    out = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith(suffix):
                out.append((name, json.loads(zf.read(name).decode("utf-8"))))
    if not out:
        raise FileNotFoundError(f"no *{suffix} members in {zip_path.name}")
    return out


def load_ems_polygons(ems_dir: Path | str) -> tuple[list[dict], dict]:
    """Load confirmed burnt-area polygons from the 4 pinned EMSR533 products.

    Returns (polygons, stats) where each polygon is
    {geometry, aoi, product, version, delivery, notation, area_attr}.
    Only notation == 'Burnt area' is kept; invalid geometries are repaired
    with make_valid (counted) or dropped if still invalid (counted).
    """
    ems_dir = Path(ems_dir)
    polys, stats = [], {"products": 0, "features": 0, "kept": 0,
                        "repaired": 0, "dropped_invalid": 0, "skipped_notation": 0}
    for prod in EMS_PRODUCTS:
        path = ems_dir / prod["file"]
        if not path.exists():
            raise FileNotFoundError(f"missing ground truth file: {path}")
        with zipfile.ZipFile(path) as zf:
            members = [n for n in zf.namelist()
                       if "observedEventA" in n and n.endswith(".json")]
        if not members:
            raise FileNotFoundError(f"no observedEventA in {prod['file']}")
        stats["products"] += 1
        for member in members:
            with zipfile.ZipFile(path) as zf:
                gj = json.loads(zf.read(member).decode("utf-8"))
            for feat in gj.get("features", []):
                stats["features"] += 1
                props = feat.get("properties", {}) or {}
                if props.get("notation") != "Burnt area":
                    stats["skipped_notation"] += 1
                    continue
                try:
                    geom = shape(feat["geometry"])
                except (KeyError, ValueError, TypeError):
                    stats["dropped_invalid"] += 1
                    continue
                if not geom.is_valid:
                    geom = make_valid(geom)
                    if not geom.is_valid or geom.is_empty:
                        stats["dropped_invalid"] += 1
                        continue
                    stats["repaired"] += 1
                polys.append({
                    "geometry": geom,
                    "aoi": prod["aoi"],
                    "product": prod["product"],
                    "version": prod["version"],
                    "delivery": prod["delivery"],
                    "notation": props.get("notation"),
                    "area_attr": props.get("area"),
                    "ground_truth_id": f"EMSR533:{prod['aoi']}:{prod['product']}:{len(polys)}",
                })
                stats["kept"] += 1
    return polys, stats


def load_ems_aois(ems_dir: Path | str) -> list[dict]:
    """Load the EMS areas-of-interest (bounds the U1 uncertain rule)."""
    ems_dir = Path(ems_dir)
    aois = []
    for prod in EMS_PRODUCTS:
        if prod["product"] != "DEL_PRODUCT":
            continue  # one AOI polygon per AOI is enough
        path = ems_dir / prod["file"]
        with zipfile.ZipFile(path) as zf:
            members = [n for n in zf.namelist()
                       if "areaOfInterestA" in n and n.endswith(".json")]
        for member in members:
            with zipfile.ZipFile(path) as zf:
                gj = json.loads(zf.read(member).decode("utf-8"))
            for feat in gj.get("features", []):
                try:
                    geom = make_valid(shape(feat["geometry"]))
                except (KeyError, ValueError, TypeError):
                    continue
                if geom.is_empty:
                    continue
                aois.append({"geometry": geom, "aoi": prod["aoi"]})
    if not aois:
        raise FileNotFoundError("no areaOfInterestA polygons found in EMS zips")
    return aois


def _find_col(columns: list[str], *needles: str) -> str | None:
    lowered = {str(c).strip().lower(): str(c) for c in columns if c is not None}
    for needle in needles:
        for low, orig in lowered.items():
            if needle in low:
                return orig
    return None


def load_vnf_sites(xlsx_path: Path | str, year: int) -> tuple[pd.DataFrame, dict]:
    """Load Algeria gas-flare sites from one annual VNF catalog spreadsheet.

    Returns (sites, stats). All flare sheets (upstream + downstream) are kept
    with a sector column; both are industrial heat, i.e. confirmed non-fire.
    Raises when the file or the Algeria rows are missing.
    """
    import openpyxl

    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"missing ground truth file: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    frames = []
    for sheet in wb.sheetnames:
        if not sheet.lower().startswith("flare"):
            continue
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        df = pd.DataFrame(rows[1:], columns=header)
        col_country = _find_col(header, "country")
        col_lat = _find_col(header, "latitude")
        col_lon = _find_col(header, "longitude")
        if not (col_country and col_lat and col_lon):
            continue
        df = df[df[col_country].astype(str).str.strip().str.lower() == "algeria"].copy()
        if df.empty:
            continue
        df["sector"] = sheet
        df["catalog_year"] = year
        frames.append(df)
    if not frames:
        raise ValueError(f"no Algeria flare rows in {xlsx_path.name}")
    sites = pd.concat(frames, ignore_index=True)
    header = list(sites.columns)
    col_lat = _find_col(header, "latitude")
    col_lon = _find_col(header, "longitude")
    col_bcm = _find_col(header, "bcm")
    col_freq = _find_col(header, "detection freq")
    col_temp = _find_col(header, "avg temp")
    col_id = _find_col(header, "id 20", "idmy")
    out = pd.DataFrame({
        "site_id": [f"VNF:{year}:{i}" for i in range(len(sites))],
        "lat": pd.to_numeric(sites[col_lat], errors="coerce"),
        "lon": pd.to_numeric(sites[col_lon], errors="coerce"),
        "country": "Algeria",
        "catalog_year": year,
        "sector": sites["sector"],
        "bcm": pd.to_numeric(sites[col_bcm], errors="coerce") if col_bcm else None,
        "detection_freq": pd.to_numeric(sites[col_freq], errors="coerce") if col_freq else None,
        "avg_temp_k": pd.to_numeric(sites[col_temp], errors="coerce") if col_temp else None,
        "catalog_row_id": sites[col_id].astype(str) if col_id else None,
    })
    out = out.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    stats = {"file": xlsx_path.name, "year": year,
             "sheets_used": sorted({s for s in sites['sector'].unique()}),
             "algeria_sites": len(out)}
    return out, stats


def load_effis_shapezip(path: Path | str) -> tuple[object, dict]:
    """Load the EFFIS real-time burnt-area database (MODIS RDA polygons).

    Returns (geodataframe, stats). Raises when the file is missing or unreadable.
    Per-polygon date columns (if any) are reported, not assumed.
    """
    import geopandas as gpd

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"missing ground truth file: {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"EFFIS database is empty: {path.name}")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    date_like = [c for c in gdf.columns
                 if any(k in str(c).lower() for k in ("date", "start", "update", "year", "time"))]
    stats = {"file": path.name, "features": len(gdf),
             "columns": list(gdf.columns),
             "date_like_columns": date_like,
             "crs": str(gdf.crs)}
    return gdf, stats