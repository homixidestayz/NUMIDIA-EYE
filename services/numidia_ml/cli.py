"""Labeling-pipeline CLI. Two steps, both auditable:

    python -m numidia_ml.cli pull-history --start 2021-08-08 --end 2021-08-22
    python -m numidia_ml.cli build

pull-history uses the keyed NRT API with explicit DATEs (history use only;
production ingestion is untouched). build assembles the labeled dataset +
dataset report from ground truth + history + live-DB rows (read-only).
No model is trained or registered here.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
assert (REPO_ROOT / "pyproject.toml").exists(), f"bad REPO_ROOT: {REPO_ROOT}"
DEFAULT_HISTORY = REPO_ROOT / "data" / "labels" / "firms_history"
DEFAULT_GT = REPO_ROOT / "data" / "labels" / "ground_truth"
DEFAULT_OUT = REPO_ROOT / "data" / "labels"
DEFAULT_REPORT = REPO_ROOT / "docs" / "dataset-report-v1.md"


def _daterange(start: str, end: str):
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if e < s:
        raise ValueError("end must be >= start")
    d = s
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)


def cmd_pull_history(args: argparse.Namespace) -> int:
    from numidia_core import firms as firms_mod
    from numidia_core.config import FIRMS_MAP_KEY

    key = (args.map_key or FIRMS_MAP_KEY).strip()
    if not key:
        print("[UNAVAILABLE] FIRMS_MAP_KEY required for history pulls", flush=True)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    manifest = {"start": args.start, "end": args.end, "sources": sources,
                "calls": [], "rows": 0, "failures": 0}
    fetched_at = datetime.now(timezone.utc)
    for day in _daterange(args.start, args.end):
        for src in sources:
            call = {"date": day, "source": src}
            try:
                raw = firms_mod.fetch_nrt_area(map_key=key, sources=[src],
                                               day=1, date=day)
            except Exception as exc:  # noqa: BLE001 - record, continue
                call["status"] = "error"
                call["message"] = firms_mod.redact_key_from_text(str(exc), key)[:300]
                manifest["failures"] += 1
                manifest["calls"].append(call)
                print(f"[{day} {src}] ERROR {call['message']}", flush=True)
                continue
            if raw.empty:
                call["status"] = "empty"
                manifest["calls"].append(call)
                print(f"[{day} {src}] empty", flush=True)
                continue
            norm = firms_mod.normalize_raw(
                raw.drop(columns=["_firms_source", "_firms_url"]),
                source=src,
                source_url=firms_mod.redact_url(raw["_firms_url"].iloc[0], key),
                fetched_at=fetched_at)
            norm = firms_mod.validate(norm)
            dest = out / f"{day}_{src}.parquet"
            norm.to_parquet(dest, index=False)
            call["status"] = "ok"
            call["rows"] = len(norm)
            call["file"] = dest.name
            manifest["rows"] += len(norm)
            manifest["calls"].append(call)
            print(f"[{day} {src}] {len(norm)} rows -> {dest.name}", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"[OK] {manifest['rows']} history rows, "
          f"{manifest['failures']} failures (recorded, not hidden)")
    return 0 if manifest["rows"] else 2


def _load_history_frames(history_dir: Path) -> pd.DataFrame:
    files = sorted(history_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no history parquet in {history_dir} "
                                "(run pull-history first)")
    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    for col in ("acq_datetime", "fetched_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    return df


def _effis_items(gdf, stats_sink: dict) -> list[dict]:
    """DZ polygons with per-polygon windows; unusable rows counted, not guessed."""
    from shapely.validation import make_valid

    dz = gdf[gdf["COUNTRY"] == "DZ"].copy()
    stats_sink["effis_dz_features"] = len(dz)
    items = []
    no_date = 0
    repaired = 0
    dropped = 0
    end_fallback = 0
    for i, row in dz.iterrows():
        start = pd.to_datetime(row.get("FIREDATE"), utc=True, errors="coerce")
        end = pd.to_datetime(row.get("FINALDATE"), utc=True, errors="coerce")
        if pd.isna(end):
            end = pd.to_datetime(row.get("LASTUPDATE"), utc=True, errors="coerce")
            if pd.notna(end):
                end_fallback += 1
        if pd.isna(start):
            no_date += 1
            continue
        if pd.isna(end):
            end = start
            end_fallback += 1
        try:
            geom = row["geometry"]
            if geom is None or geom.is_empty:
                dropped += 1
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
                if not geom.is_valid or geom.is_empty:
                    dropped += 1
                    continue
                repaired += 1
        except (AttributeError, TypeError, ValueError):
            dropped += 1
            continue
        items.append({
            "geometry": geom,
            "start": (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "end": (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "gt_id": f"EFFIS:DZ:{row.get('id', i)}",
            "source": "P2-EFFIS",
        })
    stats_sink["effis_missing_date"] = no_date
    stats_sink["effis_repaired"] = repaired
    stats_sink["effis_dropped"] = dropped
    stats_sink["effis_end_fallback"] = end_fallback
    stats_sink["effis_polygons"] = len(items)
    return items


def cmd_build(args: argparse.Namespace) -> int:
    from numidia_core import db as db_mod
    from numidia_core.config import DB_PATH
    from numidia_core.enrichment import clip_to_algeria
    from numidia_core.processing import derive_features
    from numidia_ml import ground_truth as gt
    from numidia_ml import labels as L
    from numidia_ml import report as R

    history_dir = Path(args.history)
    gt_dir = Path(args.ground_truth)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"rules_version": L.RULES_VERSION,
                      "generated_at": datetime.now(timezone.utc).isoformat()}
    try:
        git_bin = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
        manifest["code_commit"] = subprocess.check_output(
            [git_bin, "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
            text=True).strip()
    except (subprocess.SubprocessError, OSError):
        manifest["code_commit"] = "unknown"
    gt_manifest = []

    # ---- P1: EMSR533 ----------------------------------------------------
    ems_polys, ems_stats = gt.load_ems_polygons(gt_dir / "emsr533")
    ems_aois = gt.load_ems_aois(gt_dir / "emsr533")
    manifest.update({f"ems_{k}": v for k, v in ems_stats.items()})
    for prod in gt.EMS_PRODUCTS:
        gt_manifest.append({
            "key": f"P1-EMSR533:{prod['aoi']}:{prod['product']}",
            "type": "Copernicus EMS Rapid Mapping burnt-area polygons (human-validated)",
            "records": sum(1 for p in ems_polys if p["aoi"] == prod["aoi"]
                           and p["product"] == prod["product"]),
            "url": f"{gt.EMS_BASE_URL}/{prod['file']}",
            "sha256": gt.sha256_file(gt_dir / "emsr533" / prod["file"]),
        })
    burnt = [{"geometry": p["geometry"], "start": gt.EMS_EVENT_WINDOW[0],
              "end": gt.EMS_EVENT_WINDOW[1], "gt_id": p["ground_truth_id"],
              "source": "P1-EMSR533"} for p in ems_polys]
    aois = [{"geometry": a["geometry"], "aoi": a["aoi"],
             "start": gt.EMS_EVENT_WINDOW[0], "end": gt.EMS_EVENT_WINDOW[1]}
            for a in ems_aois]
    print(f"[P1] {len(burnt)} burnt polygons, {len(aois)} AOIs", flush=True)

    # ---- N1/N2: VNF flare catalogs --------------------------------------
    sites_by_year: dict[int, pd.DataFrame] = {}
    for year, fname in sorted(gt.VNF_FILES.items()):
        local = gt_dir / "vnf" / f"flare_{year}.xlsx"  # saved under short name
        sites, stats = gt.load_vnf_sites(local, year)
        sites_by_year[year] = sites
        gt_manifest.append({
            "key": f"N1-VNF:{year}",
            "type": "EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry)",
            "records": stats["algeria_sites"],
            "url": f"{gt.VNF_BASE_URL}/{fname}",
            "sha256": gt.sha256_file(gt_dir / "vnf" / f"flare_{year}.xlsx"),
        })
    manifest["vnf_sites"] = len(sites_by_year[max(sites_by_year)])
    print(f"[N1] {manifest['vnf_sites']} Algeria flare sites "
          f"({max(sites_by_year)} catalog)", flush=True)

    # ---- P2: EFFIS -------------------------------------------------------
    effis_zip = gt_dir / "effis" / args.effis_file
    gdf, effis_stats = gt.load_effis_shapezip(effis_zip)
    effis_sink: dict = {}
    effis_items = _effis_items(gdf, effis_sink)
    manifest.update(effis_sink)
    gt_manifest.append({
        "key": "P2-EFFIS:2026-season-MODIS",
        "type": "EFFIS Rapid Damage Assessment burnt-area DB (MODIS, WFS SHAPEZIP)",
        "records": effis_stats["features"],
        "url": ("https://maps.effis.emergency.copernicus.eu/effis?service=WFS"
                "&request=getfeature&typename=ms:modis.ba.poly&version=1.1.0"
                "&outputformat=SHAPEZIP"),
        "sha256": gt.sha256_file(effis_zip),
    })
    burnt.extend(effis_items)
    print(f"[P2] {len(effis_items)} DZ polygons with usable dates "
          f"(of {effis_stats['features']} WFS features)", flush=True)

    # ---- FIRMS inputs: history (2021) + live DB (2026), read-only --------
    hist = _load_history_frames(history_dir)
    hist = clip_to_algeria(derive_features(hist))[0]
    manifest["firms_history"] = (
        f"{args.history}: {len(hist)} rows after features+Algeria clip")
    live_rows = db_mod.load_detection_rows(
        limit=100000, path=args.db or DB_PATH)
    live = pd.DataFrame(live_rows)
    for col in ("acq_datetime", "fetched_at"):
        if col in live.columns:
            live[col] = pd.to_datetime(live[col], utc=True)
    manifest["firms_live"] = f"{args.db or DB_PATH}: {len(live)} rows (read-only)"
    print(f"[FIRMS] history {len(hist)} + live {len(live)} rows", flush=True)

    # ---- per-cohort labeling (catalog year must precede detection year) --
    hist["acq_year"] = pd.to_datetime(hist["acq_datetime"], utc=True).dt.year
    hist2021 = hist[hist["acq_year"] == 2021].copy()
    hist2026 = hist[hist["acq_year"] == 2026].copy()
    det2026 = pd.concat([hist2026, live], ignore_index=True) if not hist2026.empty else live
    manifest["firms_history_split"] = (
        f"2021: {len(hist2021)} rows; 2026: {len(hist2026)} rows; "
        f"other years ignored: {len(hist) - len(hist2021) - len(hist2026)} rows")
    cohorts = [
        ("2021", hist2021, {2020: sites_by_year[2020], 2021: sites_by_year[2021]}, 2021),
        ("2026", det2026, {y: sites_by_year[y] for y in (2021, 2022, 2023, 2024)}, 2024),
    ]
    all_labeled, all_excluded, total = [], [], None
    all_persistent_ids: set = set()
    for name, det, sy, cat_year in cohorts:
        if det.empty:
            continue
        persistent = L.mark_persistent(sy)
        all_persistent_ids.update(persistent["site_id"].tolist())
        manifest[f"vnf_persistent_{name}"] = (
            f"{int(persistent['persistent'].sum())}/{len(persistent)} sites")
        lab, exc, counts = L.build_dataset(
            det, burnt=burnt, aois=aois, flare_sites=persistent,
            flare_catalog_year=cat_year)
        lab["cohort"] = name
        exc["cohort"] = name
        all_labeled.append(lab)
        all_excluded.append(exc)
        print(f"[{name}] +{counts['positive']}/-{counts['negative']}/"
              f"~{counts['uncertain']}/x{counts['excluded']}/"
              f"dup{counts['duplicates']}", flush=True)
        if total is None:
            total = dict(counts)
        else:
            for k in ("input", "positive", "negative", "uncertain", "excluded",
                      "labeled", "duplicates", "conflicts", "fire_pre_dedup",
                      "nonfire_pre_dedup", "uncertain_pre_dedup"):
                total[k] = total.get(k, 0) + counts.get(k, 0)
    if not all_labeled:
        print("[ERROR] no cohorts produced labels", flush=True)
        return 2
    labeled = pd.concat(all_labeled, ignore_index=True)
    excluded = pd.concat(all_excluded, ignore_index=True)
    labeled = L.add_event_id(labeled)
    labeled = L.assign_split(labeled)

    # ---- publication verification gate (fail loudly, write nothing) ------
    input_ids = set(hist["detection_id"].tolist()) | set(live["detection_id"].tolist())
    verification = L.verify_dataset(labeled, input_ids, all_persistent_ids)
    print("--- verification ---", flush=True)
    failed = 0
    for v in verification:
        mark = "PASS" if v["ok"] else "FAIL"
        if not v["ok"]:
            failed += 1
        print(f"[{mark}] {v['check']} :: {v['detail']}", flush=True)
    if failed:
        print(f"[ERROR] {failed} verification check(s) failed - "
              f"dataset NOT written", flush=True)
        return 2

    split_counts = labeled.groupby(["split", "label"]).size().to_dict()
    cohort_table = labeled.groupby(["cohort", "label"]).size().reset_index(name="count")
    ems_matches = int((labeled["label_source"] == "P1-EMSR533").sum())
    effis_matches = int((labeled["label_source"] == "P2-EFFIS").sum())
    vnf_matches = int((labeled["label_source"] == "N1-flare").sum())
    flare_ref = labeled[labeled["ground_truth_id"].str.startswith("VNF", na=False)]
    distinct_flare_sites = int(
        flare_ref[["ground_truth_id"]].drop_duplicates().shape[0])
    manifest["splits"] = {f"{s}/{l}": int(c) for (s, l), c in split_counts.items()}
    manifest["verification"] = verification

    dataset_path = out_dir / "firms_labels_v1.csv"
    excluded_path = out_dir / "firms_excluded_v1.csv"
    labeled.to_csv(dataset_path, index=False)
    excluded.to_csv(excluded_path, index=False)
    manifest["ground_truth"] = gt_manifest
    manifest["counts"] = total
    manifest["dataset"] = str(dataset_path)
    manifest["dataset_rows"] = len(labeled)
    manifest["dataset_sha256"] = gt.sha256_file(dataset_path)
    (out_dir / "manifest_v1.json").write_text(
        json.dumps(manifest, indent=2, default=str))

    rules = {"version": L.RULES_VERSION,
             "flare_radius_m": L.FLARE_RADIUS_M,
             "flare_ring_m": L.FLARE_RING_M,
             "site_persist_m": L.SITE_PERSIST_M,
             "u3_days": L.U3_DAYS,
             "dedup_decimals": L.DEDUP_DECIMALS}
    R.write_report(Path(args.report), counts=total, manifest=manifest,
                   labeled=labeled, rules=rules, split_counts=split_counts,
                   cohort_table=cohort_table, verification=verification,
                   ems_matches=ems_matches, effis_matches=effis_matches,
                   vnf_matches=vnf_matches,
                   distinct_flare_sites=distinct_flare_sites,
                   excluded_reasons=excluded["exclude_reason"].value_counts().to_dict())
    print(f"[OK] {len(labeled)} labeled + {len(excluded)} excluded -> {dataset_path}")
    print(f"     report -> {args.report}")
    return 0


def _daterange_str(df: pd.DataFrame, label: str) -> str:
    ts = pd.to_datetime(df.loc[df["label"] == label, "acq_datetime"], utc=True)
    return f"{ts.min().date()} … {ts.max().date()}"


def cmd_experiment(args: argparse.Namespace) -> int:
    from numidia_ml import experiment as E
    from numidia_ml import ground_truth as gt

    ds = Path(args.dataset)
    if not ds.exists():
        print(f"[ERROR] dataset not found: {ds}", flush=True)
        return 2
    sha = gt.sha256_file(ds)
    record = E.run_experiment(ds, Path(args.out), sha)
    E.write_experiment_report(args.report, record)
    t = record["test_once"]
    print(f"[OK] experiment {record['experiment']} model={record['model']} "
          f"thr={t['threshold']}", flush=True)
    print(f"     test ROC-AUC={t['roc_auc']:.4f} PR-AUC={t['pr_auc']:.4f} "
          f"F1={t['f1']:.4f} Brier={t['brier']:.4f}", flush=True)
    print(f"     artifacts -> {args.out} | report -> {args.report}")
    print("     NOT REGISTERED: live API still returns 503 AI_UNAVAILABLE.")
    return 0


def cmd_verify_artifact(args: argparse.Namespace) -> int:
    """Verify a candidate artifact against the dataset (read-only, no registration)."""
    from numidia_ml import verify_artifact as V

    result = V.verify_artifact(args.artifact, args.dataset, args.metrics, tol=args.tol)
    print("--- verify-artifact ---", flush=True)
    for c in result["checks"]:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['check']} :: {c['detail']}", flush=True)
    if result["pass"]:
        print("[OK] candidate eligible for review (registration still requires approval).")
        return 0
    print("[ERROR] candidate FAILED verification - do not register.", flush=True)
    return 2


def cmd_audit(args: argparse.Namespace) -> int:
    """Bias audit. Reads v1 read-only; proves immutability via SHA before/after."""
    from numidia_ml import audit as A
    from numidia_ml import ground_truth as gt

    ds = Path(args.dataset)
    sha_before = gt.sha256_file(ds)
    lab = pd.read_csv(ds)
    two = lab[lab["label"].isin(("fire", "non-fire"))].copy()
    two["lat"] = pd.to_numeric(two["lat"], errors="coerce")
    two["lon"] = pd.to_numeric(two["lon"], errors="coerce")
    for c in ("frp", "bright_ti4", "bright_ti5", "f_bt_diff"):
        two[c] = pd.to_numeric(two[c], errors="coerce")

    y = (two["label"] == "fire").astype(int).to_numpy()
    stats = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "dataset": ds.name,
        "dataset_sha": sha_before,
        "rules_version": two["rules_version"].iloc[0] if len(two) else "?",
        "lat": A.distribution_summary(two, "lat"),
        "lon": A.distribution_summary(two, "lon"),
        "frp": A.distribution_summary(two, "frp"),
        "bt4": A.distribution_summary(two, "bright_ti4"),
        "bt5": A.distribution_summary(two, "bright_ti5"),
        "btdiff": A.distribution_summary(two, "f_bt_diff"),
        "overlap_lat": round(A.histogram_overlap(two, "lat"), 4),
        "overlap_lon": round(A.histogram_overlap(two, "lon"), 4),
        "overlap_frp": round(A.histogram_overlap(two, "frp"), 4),
        "overlap_btdiff": round(A.histogram_overlap(two, "f_bt_diff"), 4),
        "wilaya_table": {w: {"fire": int(r["fire"]), "non-fire": int(r["non-fire"]),
                             "total": int(r["total"]), "fire_rate": float(r["fire_rate"])}
                         for w, r in A.crosstab(two, "wilaya_name").iterrows()},
        "wilaya_lookup": {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in A.wilaya_lookup_accuracy(two).items()},
        "daynight_ct": A.crosstab(two, "daynight")[["fire", "non-fire"]].to_dict(),
        "sat_ct": A.crosstab(two, "satellite")[["fire", "non-fire"]].to_dict(),
        "fire_dates": _daterange_str(two, "fire"),
        "nonfire_dates": _daterange_str(two, "non-fire"),
        "thresholds": {
            "latitude": A.best_single_threshold(two["lat"].to_numpy(), y),
            "longitude": A.best_single_threshold(two["lon"].to_numpy(), y),
            "frp": A.best_single_threshold(two["frp"].to_numpy(), y),
            "band_difference": A.best_single_threshold(two["f_bt_diff"].to_numpy(), y),
        },
        "geo_baseline": A.geo_baseline_test_performance(lab),
    }

    sites_by_year: dict[int, pd.DataFrame] = {}
    for year, fname in sorted(gt.VNF_FILES.items()):
        sites, _ = gt.load_vnf_sites(Path(args.ground_truth) / "vnf" / f"flare_{year}.xlsx", year)
        sites_by_year[year] = sites
    north = A.northern_flare_analysis(sites_by_year, lab)
    stats.update({
        "north_cut": north["north_lat_cut"],
        "north_persistent": north["persistent_north_sites"],
        "north_total": north["persistent_total"],
        "north_matched": north["north_matched_sites"],
        "north_sites": north["north_sites"],
    })

    n_south_neg = int(((two["label"] == "non-fire") & (two["lat"] < A.NORTH_LAT)).sum())
    n_north_neg = int(((two["label"] == "non-fire") & (two["lat"] >= A.NORTH_LAT)).sum())
    n_north_fire = int(((two["label"] == "fire") & (two["lat"] >= A.NORTH_LAT)).sum())
    proposal = {
        "hard_negatives": (
            "H1 — Northern persistent VNF sites (measured above): "
            f"{north['persistent_north_sites']} persistent sites at/above "
            f"{north['north_lat_cut']}°N, of which {north['north_matched_sites']} "
            f"already anchor dataset rows. Dataset today holds {n_north_neg} "
            f"northern negatives vs {n_south_neg} southern negatives against "
            f"{n_north_fire} northern fires. H1 is real, committed ground truth "
            "in the confusing latitude band — the immediate hard-negative pool. "
            "Required before training: per-site review confirming each northern "
            "site is industrial (sector + imagery), then stratify/upsample them "
            "so the model cannot trade latitude for physics.\n"
            "H2 — N2-style manual curation of northern industrial heat (cement "
            "works, power stations, refinery flares with operator-confirmed "
            "events): coordinates + event dates + imagery review, admitted "
            "per-site like N2. Not downloaded — field/literature work, no ETA.\n"
            "REJECTED: labeling 'no ground truth' northern detections as "
            "negative; EFFIS unburned-area inversion; agricultural burns "
            "(combustion — at best uncertain); any threshold-derived labels."
        ),
        "split": (
            "Revise to a dual-axis design (v2 dataset fields: split stays, rule "
            "changes): (a) TIME axis — keep the 2026 forward holdout as test; "
            "(b) GEOGRAPHY axis — within 2021, geo-grouped K-fold by event "
            "(EMSR533 AOI01 vs AOI02 plus EFFIS-2021 polygon groups) for model "
            "selection, replacing single-AOI02 validation; (c) REPORTING axis — "
            "every metric stratified by latitude band (≥34°N vs <34°N) and by "
            "day/night, so geo-cheating is visible even if aggregate scores "
            "look good; (d) FEATURE RULE — raw lat/lon and wilaya identifiers "
            "are banned from model inputs (stratification-only); verification "
            "V2 extends to assert train/val/test event disjointness per fold."
        ),
        "verdict": (
            "v1 is NOT suitable for training as-is: the negative class is "
            "geographically isolated by construction, and the measured "
            "baseline proves coordinates alone separate the classes "
            "(lat/lon-only logistic regression: 0.975 accuracy, 0.975 AUC on "
            "the 2026 forward-time test; single latitude threshold: 97.9%; "
            "wilaya lookup: 98.9%). Any model with location features would "
            "learn the map, not fire physics. A second, independent shortcut "
            "exists: every non-fire row is nighttime by construction while "
            "fires are day+night, so day/night must also be stratified at "
            "evaluation, never trusted as a feature. v1 REMAINS the approved "
            "immutable evidence base; training waits on v2 with H1 "
            "verified+stratified, the coordinate ban, and the dual-axis split."
        ),
        "data_needs": (
            "1. H1 per-site industrial confirmation (sector + imagery) for the "
            "northern persistent VNF sites, committed as data/labels/north_sites_review.csv. "
            "2. H2 northern industrial-heat curation (manual, no ETA). "
            "3. 2022–2025 positives via EFFIS DATA REQUEST FORM / EMS archive "
            "query (manual). 4. P3 commune-level curation for event validation. "
            "5. v2 dataset build implementing the revised split + stratification "
            "fields. None of these invent labels; all extend ground truth."
        ),
    }
    A.write_audit_report(args.report, stats=stats, proposal=proposal)
    sha_after = gt.sha256_file(ds)
    print(f"[OK] audit -> {args.report}")
    print(f"     v1 immutable: {sha_before == sha_after} (sha {sha_before[:12]}…)")
    return 0 if sha_before == sha_after else 2


def cmd_build_v2(args: argparse.Namespace) -> int:
    """V2 assembly: v1 rules + 2022/2023 cohorts + folds + feature contract.

    v1 files are never modified (read-only inputs where reused). New outputs:
    firms_labels_v2.csv, firms_excluded_v2.csv, manifest_v2.json,
    docs/dataset-report-v2.md. No model training here.
    """
    from numidia_core import db as db_mod
    from numidia_core.config import DB_PATH
    from numidia_core.enrichment import clip_to_algeria
    from numidia_core.processing import derive_features
    from numidia_ml import ground_truth as gt
    from numidia_ml import labels as L
    from numidia_ml import report as R

    history_dir = Path(args.history)
    gt_dir = Path(args.ground_truth)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"dataset_version": "v2",
                      "rules_version": L.RULES_VERSION,
                      "generated_at": datetime.now(timezone.utc).isoformat()}
    try:
        git_bin = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
        manifest["code_commit"] = subprocess.check_output(
            [git_bin, "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
            text=True).strip()
    except (subprocess.SubprocessError, OSError):
        manifest["code_commit"] = "unknown"
    gt_manifest = []

    ems_polys, ems_stats = gt.load_ems_polygons(gt_dir / "emsr533")
    ems_aois = gt.load_ems_aois(gt_dir / "emsr533")
    manifest.update({f"ems_{k}": v for k, v in ems_stats.items()})
    for prod in gt.EMS_PRODUCTS:
        gt_manifest.append({
            "key": f"P1-EMSR533:{prod['aoi']}:{prod['product']}",
            "type": "Copernicus EMS Rapid Mapping burnt-area polygons (human-validated)",
            "records": sum(1 for p in ems_polys if p["aoi"] == prod["aoi"]
                           and p["product"] == prod["product"]),
            "url": f"{gt.EMS_BASE_URL}/{prod['file']}",
            "sha256": gt.sha256_file(gt_dir / "emsr533" / prod["file"]),
        })
    burnt = [{"geometry": p["geometry"], "start": gt.EMS_EVENT_WINDOW[0],
              "end": gt.EMS_EVENT_WINDOW[1], "gt_id": p["ground_truth_id"],
              "source": "P1-EMSR533"} for p in ems_polys]
    aois = [{"geometry": a["geometry"], "aoi": a["aoi"],
             "start": gt.EMS_EVENT_WINDOW[0], "end": gt.EMS_EVENT_WINDOW[1]}
            for a in ems_aois]
    print(f"[P1] {len(burnt)} burnt polygons, {len(aois)} AOIs", flush=True)

    sites_by_year: dict[int, pd.DataFrame] = {}
    for year, fname in sorted(gt.VNF_FILES.items()):
        local = gt_dir / "vnf" / f"flare_{year}.xlsx"
        sites, stats = gt.load_vnf_sites(local, year)
        sites_by_year[year] = sites
        gt_manifest.append({
            "key": f"N1-VNF:{year}",
            "type": "EOG VIIRS Nightfire annual gas-flare survey (SWIR pyrometry)",
            "records": stats["algeria_sites"],
            "url": f"{gt.VNF_BASE_URL}/{fname}",
            "sha256": gt.sha256_file(local),
        })
    manifest["vnf_sites"] = len(sites_by_year[max(sites_by_year)])
    print(f"[N1] {manifest['vnf_sites']} Algeria flare sites "
          f"({max(sites_by_year)} catalog)", flush=True)

    effis_zip = gt_dir / "effis" / args.effis_file
    gdf, effis_stats = gt.load_effis_shapezip(effis_zip)
    effis_sink: dict = {}
    effis_items = _effis_items(gdf, effis_sink)
    manifest.update(effis_sink)
    gt_manifest.append({
        "key": "P2-EFFIS:MODIS-seasonal (2016-2026 as published)",
        "type": "EFFIS Rapid Damage Assessment burnt-area DB (MODIS, WFS SHAPEZIP)",
        "records": effis_stats["features"],
        "url": ("https://maps.effis.emergency.copernicus.eu/effis?service=WFS"
                "&request=getfeature&typename=ms:modis.ba.poly&version=1.1.0"
                "&outputformat=SHAPEZIP"),
        "sha256": gt.sha256_file(effis_zip),
    })
    burnt.extend(effis_items)
    print(f"[P2] {len(effis_items)} DZ polygons with usable dates "
          f"(of {effis_stats['features']} WFS features)", flush=True)

    # ---- H1 review: suitable northern hard-negative sites -----------------
    review = pd.read_csv(args.review)
    suitable = set(review.loc[review["suitable_hard_negative"].astype(str).str.lower() == "yes",
                              "site_id"].tolist())
    manifest["h1_review"] = {
        "file": str(args.review),
        "sites_reviewed": len(review),
        "confirmed_suitable": len(suitable),
        "unconfirmed": int((review["confirmation_status"] != "CONFIRMED").sum()),
    }
    print(f"[H1] {len(suitable)}/{len(review)} northern sites confirmed suitable",
          flush=True)

    # ---- FIRMS inputs ------------------------------------------------------
    hist = _load_history_frames(history_dir)
    hist = clip_to_algeria(derive_features(hist))[0]
    hist["acq_year"] = pd.to_datetime(hist["acq_datetime"], utc=True).dt.year
    live_rows = db_mod.load_detection_rows(limit=100000, path=args.db or DB_PATH)
    live = pd.DataFrame(live_rows)
    for col in ("acq_datetime", "fetched_at"):
        if col in live.columns:
            live[col] = pd.to_datetime(live[col], utc=True)
    print(f"[FIRMS] history {len(hist)} + live {len(live)} rows", flush=True)

    det2026 = pd.concat([hist[hist["acq_year"] == 2026], live], ignore_index=True)
    cohorts = []
    for det_year in (2021, 2022, 2023):
        part = hist[hist["acq_year"] == det_year].copy()
        use = {y: sites_by_year[y] for y in sorted(sites_by_year) if y <= det_year}
        cohorts.append((str(det_year), part, use, max(use)))
    cohorts.append(("2026", det2026,
                    {y: sites_by_year[y] for y in (2021, 2022, 2023, 2024)}, 2024))
    manifest["firms_history_split"] = "; ".join(
        f"{name}: {len(part)} rows" for name, part, _, _ in cohorts)

    all_labeled, all_excluded, total = [], [], None
    all_persistent_ids: set = set()
    for name, det, sy, cat_year in cohorts:
        if det.empty:
            print(f"[{name}] no rows - skipped", flush=True)
            continue
        persistent = L.mark_persistent(sy)
        all_persistent_ids.update(persistent["site_id"].tolist())
        manifest[f"vnf_persistent_{name}"] = (
            f"{int(persistent['persistent'].sum())}/{len(persistent)} sites")
        lab, exc, counts = L.build_dataset(
            det, burnt=burnt, aois=aois, flare_sites=persistent,
            flare_catalog_year=cat_year)
        lab["cohort"] = name
        exc["cohort"] = name
        all_labeled.append(lab)
        all_excluded.append(exc)
        print(f"[{name}] +{counts['positive']}/-{counts['negative']}/"
              f"~{counts['uncertain']}/x{counts['excluded']}/"
              f"dup{counts['duplicates']}", flush=True)
        if total is None:
            total = dict(counts)
        else:
            for k in ("input", "positive", "negative", "uncertain", "excluded",
                      "labeled", "duplicates", "conflicts", "fire_pre_dedup",
                      "nonfire_pre_dedup", "uncertain_pre_dedup"):
                total[k] = total.get(k, 0) + counts.get(k, 0)
    if not all_labeled:
        print("[ERROR] no cohorts produced labels", flush=True)
        return 2
    labeled = pd.concat(all_labeled, ignore_index=True)
    excluded = pd.concat(all_excluded, ignore_index=True)
    labeled = L.add_event_id(labeled)
    labeled = L.assign_split(labeled)
    labeled = L.add_strat_band(labeled)
    excluded = L.add_strat_band(excluded)
    labeled = L.assign_folds(labeled, k=5)

    input_ids = set(hist["detection_id"].tolist()) | set(live["detection_id"].tolist())
    verification = L.verify_dataset(labeled, input_ids, all_persistent_ids)
    verification.extend(L.verify_v2(labeled))
    print("--- verification ---", flush=True)
    failed = 0
    for v in verification:
        mark = "PASS" if v["ok"] else "FAIL"
        if not v["ok"]:
            failed += 1
        print(f"[{mark}] {v['check']} :: {v['detail']}", flush=True)
    if failed:
        print(f"[ERROR] {failed} verification check(s) failed - "
              f"dataset NOT written", flush=True)
        return 2

    # ---- hard-negative + stratification summaries --------------------------
    h1_ref = labeled[labeled["ground_truth_id"].isin(suitable)]
    hard_neg = h1_ref[h1_ref["label"] == "non-fire"]
    manifest["hard_negatives_h1"] = {
        "suitable_sites": len(suitable),
        "distinct_suitable_matched": int(h1_ref["ground_truth_id"].nunique()),
        "rows_at_suitable": int(len(h1_ref)),
        "nonfire_at_suitable": int(len(hard_neg)),
    }
    split_counts = labeled.groupby(["split", "label"]).size().to_dict()
    cohort_table = labeled.groupby(["cohort", "label"]).size().reset_index(name="count")
    fold_table = labeled[labeled["split"] == "train"].groupby(["fold", "label"]).size().reset_index(name="count")
    band_table = labeled.groupby(["strat_lat_band", "label"]).size().reset_index(name="count")
    daynight_table = labeled.groupby([
        labeled["daynight"].astype(str).str.upper().str[0], "label"]).size().reset_index(name="count")
    sat_table = labeled.groupby(["satellite", "label"]).size().reset_index(name="count")

    dataset_path = out_dir / "firms_labels_v2.csv"
    excluded_path = out_dir / "firms_excluded_v2.csv"
    labeled.to_csv(dataset_path, index=False)
    excluded.to_csv(excluded_path, index=False)
    manifest["ground_truth"] = gt_manifest
    manifest["counts"] = total
    v1_path = out_dir / "firms_labels_v1.csv"
    if v1_path.exists():
        manifest["v1_sha256"] = gt.sha256_file(v1_path)
    manifest["dataset"] = str(dataset_path)
    manifest["dataset_rows"] = len(labeled)
    manifest["dataset_sha256"] = gt.sha256_file(dataset_path)
    manifest["model_features_v1"] = L.MODEL_FEATURES_V1
    manifest["banned_features"] = L.BANNED_FEATURES
    manifest["splits"] = {f"{s}/{l}": int(c) for (s, l), c in split_counts.items()}
    manifest["verification"] = verification
    (out_dir / "manifest_v2.json").write_text(
        json.dumps(manifest, indent=2, default=str))

    rules = {"version": L.RULES_VERSION,
             "flare_radius_m": L.FLARE_RADIUS_M,
             "flare_ring_m": L.FLARE_RING_M,
             "site_persist_m": L.SITE_PERSIST_M,
             "u3_days": L.U3_DAYS,
             "dedup_decimals": L.DEDUP_DECIMALS}
    R.write_report_v2(
        Path(args.report), counts=total, manifest=manifest, labeled=labeled,
        rules=rules, split_counts=split_counts, cohort_table=cohort_table,
        fold_table=fold_table, band_table=band_table,
        daynight_table=daynight_table, sat_table=sat_table,
        verification=verification,
        ems_matches=int((labeled["label_source"] == "P1-EMSR533").sum()),
        effis_matches=int((labeled["label_source"] == "P2-EFFIS").sum()),
        vnf_matches=int((labeled["label_source"] == "N1-flare").sum()),
        distinct_flare_sites=int(
            labeled[labeled["ground_truth_id"].str.startswith("VNF", na=False)]
            ["ground_truth_id"].nunique()),
        excluded_reasons=excluded["exclude_reason"].value_counts().to_dict())
    print(f"[OK] v2: {len(labeled)} labeled + {len(excluded)} excluded -> {dataset_path}")
    print(f"     report -> {args.report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="numidia_ml", description="NUMIDIA verifier labeling pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    ph = sub.add_parser("pull-history",
                        help="pull dated FIRMS NRT windows (history use only)")
    ph.add_argument("--start", required=True, help="YYYY-MM-DD")
    ph.add_argument("--end", required=True, help="YYYY-MM-DD")
    ph.add_argument("--sources", default="VIIRS_SNPP_SP,VIIRS_NOAA20_SP",
                    help="FIRMS sources (history pulls use _SP archive products; "
                         "verified: _NRT serves recent dates only)")
    ph.add_argument("--map-key", default=None)
    ph.add_argument("--out", default=str(DEFAULT_HISTORY))
    ph.set_defaults(func=cmd_pull_history)

    pb = sub.add_parser("build", help="assemble labeled dataset + report")
    pb.add_argument("--history", default=str(DEFAULT_HISTORY))
    pb.add_argument("--ground-truth", default=str(DEFAULT_GT))
    pb.add_argument("--effis-file",
                    default="effis_burnt_areas_current season_WFS.zip")
    pb.add_argument("--db", default=None, help="live DB path (read-only)")
    pb.add_argument("--out", default=str(DEFAULT_OUT))
    pb.add_argument("--report", default=str(DEFAULT_REPORT))
    pb.set_defaults(func=cmd_build)

    pv2 = sub.add_parser("build-v2", help="assemble v2 dataset (folds, bans, H1, 2022/23 cohorts)")
    pv2.add_argument("--history", default=str(DEFAULT_HISTORY))
    pv2.add_argument("--ground-truth", default=str(DEFAULT_GT))
    pv2.add_argument("--effis-file",
                     default="effis_burnt_areas_current season_WFS.zip")
    pv2.add_argument("--review", default=str(DEFAULT_OUT / "north_sites_review.csv"))
    pv2.add_argument("--db", default=None, help="live DB path (read-only)")
    pv2.add_argument("--out", default=str(DEFAULT_OUT))
    pv2.add_argument("--report", default=str(REPO_ROOT / "docs" / "dataset-report-v2.md"))
    pv2.set_defaults(func=cmd_build_v2)

    pa = sub.add_parser("audit", help="dataset-bias audit (analysis only, v1 read-only)")
    pa.add_argument("--dataset", default=str(DEFAULT_OUT / "firms_labels_v1.csv"))
    pa.add_argument("--ground-truth", default=str(DEFAULT_GT))
    pa.add_argument("--report", default=str(REPO_ROOT / "docs" / "bias-audit-v1.md"))
    pa.set_defaults(func=cmd_audit)

    px = sub.add_parser("experiment",
                        help="first model experiment (local artifact, never registered)")
    px.add_argument("--dataset", default=str(DEFAULT_OUT / "firms_labels_v2.csv"))
    px.add_argument("--out", default=str(REPO_ROOT / "services" / "ml" / "models" / "exp_v1"))
    px.add_argument("--report", default=str(REPO_ROOT / "docs" / "model-experiment-v1.md"))
    px.set_defaults(func=cmd_experiment)

    pv = sub.add_parser("verify-artifact",
                        help="verify a candidate artifact (read-only, never registers)")
    pv.add_argument("--artifact", required=True, help="candidate .joblib pipeline")
    pv.add_argument("--dataset", default=str(DEFAULT_OUT / "firms_labels_v2.csv"))
    pv.add_argument("--metrics", default=None, help="metrics.json recorded with the artifact")
    pv.add_argument("--tol", type=float, default=1e-4)
    pv.set_defaults(func=cmd_verify_artifact)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
