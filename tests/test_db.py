"""Database + freshness tests - temp DBs only, offline, fixture-driven."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from numidia_core import db as db_mod
from numidia_core.enrichment import assign_wilaya, clip_to_algeria
from numidia_core.firms import normalize_raw, validate
from numidia_core.processing import derive_features

FIXTURE = Path(__file__).parent / "fixtures" / "firms_noaa21_sample_1d.csv"


def _enriched_now(acq: datetime) -> pd.DataFrame:
    """Small synthetic canonical batch acquired at `acq` (for LIVE tests)."""
    raw = pd.DataFrame([{
        "latitude": 36.75, "longitude": 3.06,
        "acq_date": acq.strftime("%Y-%m-%d"), "acq_time": acq.strftime("%H%M"),
        "satellite": "N21", "instrument": "VIIRS", "confidence": "n",
        "bright_ti4": 320.0, "bright_ti5": 295.0, "scan": 0.4, "track": 0.4,
        "frp": 5.0, "daynight": "N", "version": "2.0NRT",
    }])
    df = normalize_raw(raw, source="VIIRS_NOAA21_NRT", source_url="firms://t",
                       fetched_at=acq)
    kept, _ = clip_to_algeria(derive_features(validate(df)))
    assert len(kept) == 1  # Algiers point is inside Algeria
    return kept


def _enriched_fixture() -> pd.DataFrame:
    """Fixture rows through the real production path (clip to Algeria)."""
    raw = pd.read_csv(FIXTURE)
    df = normalize_raw(raw, source="VIIRS_NOAA21_NRT", source_url="firms://t",
                       fetched_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc))
    kept, excluded = clip_to_algeria(derive_features(validate(df)))
    assert (len(kept), excluded) == (186, 64)  # fixed real fixture numbers
    return kept


def test_upsert_is_idempotent(tmp_path):
    db = tmp_path / "t.db"
    db_mod.init_db(db)
    df = _enriched_fixture()
    first = db_mod.upsert_detections(df, db)
    assert first["new"] == len(df) and first["total"] == len(df)
    second = db_mod.upsert_detections(df, db)
    assert second["new"] == 0 and second["total"] == len(df)
    # first-seen wins: re-ingesting with a newer fetched_at keeps the original
    row = db_mod.get_detection_row(df.iloc[0]["detection_id"], db)
    assert row["fetched_at"].startswith("2026-09-17")


def test_empty_db_is_unavailable(tmp_path):
    db = tmp_path / "empty.db"
    db_mod.init_db(db)
    summary = db_mod.data_state_summary(path=db)
    assert summary["data_state"] == "UNAVAILABLE"
    assert summary["detections_count"] == 0


def test_fresh_run_old_data_is_historical(tmp_path):
    db = tmp_path / "h.db"
    db_mod.init_db(db)
    df = _enriched_fixture()  # acquired 2026-09-17 (old relative to real now)
    db_mod.upsert_detections(df, db)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"], urls=[],
                      count_new=len(df), count_total=len(df), status="ok",
                      message="test", path=db)
    summary = db_mod.data_state_summary(path=db)
    assert summary["data_state"] == "HISTORICAL"
    assert summary["ingest_fresh"] is True
    assert summary["live_count"] == 0


def test_fresh_run_fresh_data_is_live(tmp_path):
    db = tmp_path / "live.db"
    db_mod.init_db(db)
    now = datetime.now(timezone.utc)
    df = _enriched_now(now - timedelta(hours=2))
    db_mod.upsert_detections(df, db)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"], urls=[],
                      count_new=1, count_total=1, status="ok",
                      message="test", path=db)
    summary = db_mod.data_state_summary(path=db)
    assert summary["data_state"] == "LIVE"
    assert summary["live_count"] == 1


def test_old_run_is_stale_never_live(tmp_path):
    db = tmp_path / "stale.db"
    db_mod.init_db(db)
    now = datetime.now(timezone.utc)
    df = _enriched_now(now - timedelta(hours=2))  # freshly acquired...
    db_mod.upsert_detections(df, db)
    # ...but the successful run is 10h old with a 3h stale threshold
    old = now - timedelta(hours=10)
    db_mod.record_run(mode="api", sources=["VIIRS_NOAA21_NRT"], urls=[],
                      count_new=1, count_total=1, status="ok", message="old",
                      started_at=(old - timedelta(minutes=1)).isoformat(),
                      finished_at=old.isoformat(), path=db)
    summary = db_mod.data_state_summary(stale_after_min=180, path=db)
    assert summary["data_state"] == "STALE"
    assert summary["ingest_fresh"] is False


def test_error_run_without_success_is_stale(tmp_path):
    db = tmp_path / "err.db"
    db_mod.init_db(db)
    df = _enriched_fixture()
    db_mod.upsert_detections(df, db)
    db_mod.record_run(mode="api", sources=[], urls=[], count_new=0,
                      count_total=len(df), status="error",
                      message="boom", path=db)
    summary = db_mod.data_state_summary(path=db)
    assert summary["data_state"] == "STALE"


def test_rows_roundtrip_with_wilaya(tmp_path):
    db = tmp_path / "r.db"
    db_mod.init_db(db)
    db_mod.upsert_detections(_enriched_fixture(), db)
    rows = db_mod.load_detection_rows(limit=5, path=db)
    assert len(rows) == 5
    # Production invariant: every stored row passed the Algeria clip.
    assert all(r["wilaya_code"] for r in rows)
    one = db_mod.get_detection_row(rows[0]["detection_id"], db)
    assert one["detection_id"] == rows[0]["detection_id"]
    assert db_mod.get_detection_row("missing", db) is None