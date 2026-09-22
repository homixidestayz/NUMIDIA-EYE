"""Production worker CLI - runs the real ingestion pipeline into the app DB.

Usage:
    python -m numidia_worker.cli fetch              # scheduled/CI/manual run
    python -m numidia_worker.cli fetch --mode archive   # explicit backfill/test
    python -m numidia_worker.cli process --input <audit csv>  # reprocess
    python -m numidia_worker.cli verify             # honest AI readiness

Exit 0 on success, 2 when the source is unavailable (never fabricates data).
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from numidia_core import db as db_mod
from numidia_core import firms as firms_mod
from numidia_core import pipeline as pipeline_mod
from numidia_core import storage
from numidia_core.config import DB_PATH, INGEST_DAY, INGEST_MODE


def cmd_fetch(args: argparse.Namespace) -> int:
    summary = pipeline_mod.run_ingest(
        db_path=args.db, map_key=args.map_key, mode=args.mode,
        day=args.day, audit=not args.no_audit,
    )
    storage.write_status_sidecar("latest", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["status"] == "ok" else 2


def cmd_process(args: argparse.Namespace) -> int:
    raw = storage.load_raw_snapshot(args.input)
    if raw is None:
        print("[UNAVAILABLE] no audit snapshot found to process", file=sys.stderr)
        return 2
    if "detection_id" in raw.columns:
        frame = raw.copy()  # already-canonical audit snapshot
        source_note = "audit snapshot (canonical)"
    else:
        frame = firms_mod.normalize_raw(
            raw, source="FIRMS", source_url=None, fetched_at=None,
        )
        source_note = "raw FIRMS CSV"
    counts = pipeline_mod.process_frame(frame, args.db)
    print(f"[OK] reprocessed {source_note}: "
          f"{counts['new']} new / {counts['total']} stored")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    print(json.dumps(pipeline_mod.verification_status(), indent=2))
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    db_mod.init_db(args.db)
    for run in db_mod.latest_runs(limit=args.limit, path=args.db):
        print(json.dumps(run, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="numidia_worker", description="NUMIDIA EYE production ingestion")
    parser.add_argument("--db", default=None,
                        help=f"application DB path (default: {DB_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("fetch", help="run the full ingestion pipeline once")
    pf.add_argument("--map-key", default=None,
                    help="FIRMS MAP_KEY (default: FIRMS_MAP_KEY env, server-side)")
    pf.add_argument("--mode", choices=["api", "archive"], default=None,
                    help=f"ingestion mode (default: {INGEST_MODE}; "
                         "'api' needs the key, 'archive' is explicit backfill)")
    pf.add_argument("--day", type=int, default=None,
                    help=f"1 = last 24h, 2 = last 48h (default: {INGEST_DAY})")
    pf.add_argument("--no-audit", action="store_true",
                    help="skip writing the audit snapshot CSV")
    pf.set_defaults(func=cmd_fetch)

    pp = sub.add_parser("process", help="reprocess an audit snapshot into the DB")
    pp.add_argument("--input", default=None,
                    help="audit CSV path (default: latest snapshot)")
    pp.set_defaults(func=cmd_process)

    pv = sub.add_parser("verify", help="report honest AI verifier readiness")
    pv.set_defaults(func=cmd_verify)

    pr = sub.add_parser("runs", help="show recent ingest runs from the DB")
    pr.add_argument("--limit", type=int, default=5)
    pr.set_defaults(func=cmd_runs)

    args = parser.parse_args(argv)
    if args.mode is None:
        args.mode = INGEST_MODE
    if args.day is None:
        args.day = INGEST_DAY
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
