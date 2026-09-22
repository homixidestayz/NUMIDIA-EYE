"""Ingestion & processing CLI.

Usage:
    python -m numidia_worker.cli fetch              # real FIRMS/VIIRS -> raw snapshot
    python -m numidia_worker.cli process            # raw snapshot -> derived features

Failures are reported honestly (exit code 2 + UNAVAILABLE status sidecar);
we never substitute invented data for a failed source.
"""
from __future__ import annotations

import argparse
import sys

from numidia_core import firms as firms_mod
from numidia_core import storage
from numidia_core.config import PROCESSED_DIR
from numidia_core.processing import derive_features


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        df, meta = firms_mod.fetch_detections(map_key=args.map_key, mode=args.mode, day=args.day)
    except Exception as exc:  # noqa: BLE001 - report, don't fabricate
        storage.write_status_sidecar(
            "latest",
            {"firms": "UNAVAILABLE", "message": f"FIRMS fetch failed: {exc}", "rows": 0},
        )
        print(f"[UNAVAILABLE] FIRMS fetch failed: {exc}", file=sys.stderr)
        return 2

    path = storage.save_canonical_snapshot(df, name=args.out)
    sidecar = {
        "firms": "CONNECTED",
        "mode": meta["mode"],
        "source": meta["source"],
        "sources": meta["sources"],
        "fetched_at": meta["fetched_at"].isoformat(),
        "rows": meta["count"],
        "snapshot": str(path),
    }
    storage.write_status_sidecar("latest", sidecar)
    print(f"[OK] {meta['count']} real detections -> {path}")
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    raw = storage.load_raw_snapshot(args.input)
    if raw is None:
        storage.write_status_sidecar(
            "latest", {"firms": "UNAVAILABLE", "message": "no raw snapshot found", "rows": 0}
        )
        print("[UNAVAILABLE] no raw FIRMS snapshot found to process", file=sys.stderr)
        return 2

    if "detection_id" in raw.columns:
        # Already-canonical snapshot (produced by `fetch`); keep its per-source
        # provenance and go straight to validation + features.
        df = firms_mod.validate(raw.copy())
    else:
        # Raw FIRMS CSV (committed sample): normalize with explicit provenance,
        # preserving whatever source/date info the raw rows carry.
        src = "FIRMS"
        if "satellite" in raw.columns and len(raw):
            sat0 = str(raw["satellite"].iloc[0])
            if "NOAA21" in sat0 or sat0 == "N21":
                src = "VIIRS_NOAA21_NRT"
        fetched_at = None
        if "fetched_at" in raw.columns and len(raw):
            fetched_at = raw["fetched_at"].dropna().iloc[0]
        df = firms_mod.normalize_raw(
            raw, source=src,
            source_url=None, fetched_at=fetched_at,
        )
        df = firms_mod.validate(df)

    features = derive_features(df)
    sidecar = {
        "firms": "CONNECTED",
        "input": str(args.input or storage.latest_raw_snapshot()),
        "detections": len(df),
        "feature_columns": [c for c in features.columns if c.startswith("f_")],
    }
    out = storage.save_processed(features, name=args.name, sidecar=sidecar)
    print(f"[OK] {len(features)} detections with {len(sidecar['feature_columns'])} features -> {out['csv']}")
    print(f"      {out['parquet']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="numidia_worker", description="NUMIDIA EYE ingestion/processing")
    sub = parser.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("fetch", help="fetch real FIRMS/VIIRS detections (needs FIRMS_MAP_KEY for NRT API)")
    pf.add_argument("--map-key", default=None, help="FIRMS MAP_KEY (falls back to FIRMS_MAP_KEY env)")
    pf.add_argument("--mode", choices=["auto", "api", "archive"], default="auto")
    pf.add_argument("--day", type=int, default=1, choices=[1, 2], help="1 = last 24h, 2 = last 48h")
    pf.add_argument("--out", default="viirs_algeria_24h.csv")
    pf.set_defaults(func=cmd_fetch)

    pp = sub.add_parser("process", help="derive real features from a raw snapshot into data/processed/")
    pp.add_argument("--input", default=None, help="raw CSV path (default: latest snapshot)")
    pp.add_argument("--name", default="firms_features")
    pp.set_defaults(func=cmd_process)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())