"""Re-deriving stored geography when the boundaries change.

These tests pin the property that makes the operation safe: it rewrites ONLY the
derived wilaya columns, from each detection's own coordinates, and it never
touches ingest_runs (which would make a stale database look freshly ingested).

Also pinned: the reason a plain upsert cannot do this job. `upsert_detections`
documents "first-seen wins" and leaves existing rows untouched, which is correct
for acquisition and wrong for re-derivation.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from numidia_core import backfill, db as db_mod

# Every column in `detections` is NOT NULL and the insert is INSERT OR IGNORE,
# so a sparse frame is silently dropped rather than rejected. A fixture must
# therefore supply all 30 columns or it inserts nothing and the test passes for
# the wrong reason.
_BASE = {c: None for c in db_mod.DET_COLUMNS}
_BASE.update({
    "confidence_raw": "n", "bright_ti4": 320.0, "bright_ti5": 300.0,
    "scan": 0.4, "track": 1.0, "frp": 5.0, "daynight": "D", "version": "3.0",
    "type": 0, "source": "TEST", "source_url": "https://example.invalid",
    "f_bt_diff": 20.0, "f_frp": 0.5, "f_confidence": 0.6,
    "f_hour_utc": 10, "f_month": 10, "f_doy": 282, "f_daynight": 0,
})


def _row(detection_id: str, lat: float, lon: float) -> dict:
    row = dict(_BASE)
    row.update({"detection_id": detection_id, "lat": lat, "lon": lon,
                "acq_datetime": "2026-10-09T10:00:00Z", "acq_date": "2026-10-09",
                "acq_time": "10:00", "satellite": "N20", "instrument": "VIIRS",
                "confidence": "n", "fetched_at": "2026-10-09T10:05:00Z"})
    return row


POINTS = pd.DataFrame([
    # Algiers, Tizi Ouzou, In Salah - one capital from each reform era
    _row("d_alg", 36.7538, 3.0588),
    _row("d_tiz", 36.7118, 4.0458),
    _row("d_ins", 27.1936, 2.4675),
    # Open Mediterranean: must stay null rather than snapping to a neighbour
    _row("d_off", 20.0, 2.0),
])


@pytest.fixture
def db(tmp_path):
    path = db_mod.init_db(tmp_path / "t.db")
    db_mod.upsert_detections(POINTS, path=path)
    return path


def _rows(path):
    with sqlite3.connect(path) as con:
        return {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT detection_id, wilaya_code, wilaya_name FROM detections")}


def test_upsert_alone_cannot_correct_geography(db):
    """Why this module exists: first-seen wins means no re-derivation."""
    before = _rows(db)
    db_mod.upsert_detections(POINTS, path=db)
    assert _rows(db) == before, "a re-upsert must not be expected to rewrite anything"


def test_scan_reports_without_writing(db):
    # Stamp a deliberately wrong wilaya, as an old boundary set would have.
    with sqlite3.connect(db) as con:
        con.execute("UPDATE detections SET wilaya_code='11', wilaya_name='Stale'")

    report = backfill.scan(db)
    assert report["would_change"] >= 1
    assert report["changes"], "scan must list what it would do"
    assert _rows(db)["d_alg"] == ("11", "Stale"), "scan must not write"


def test_apply_rewrites_only_the_wilaya_columns(db):
    with sqlite3.connect(db) as con:
        con.execute("UPDATE detections SET wilaya_code='11', wilaya_name='Stale'")
        before_geom = dict(con.execute(
            "SELECT detection_id, lat FROM detections").fetchall())
        before_acq = dict(con.execute(
            "SELECT detection_id, acq_datetime FROM detections").fetchall())

    result = backfill.apply(db)
    assert result["updated"] >= 1

    after = _rows(db)
    assert after["d_alg"][1] == "Alger"
    assert after["d_tiz"][1] == "Tizi Ouzou"
    assert after["d_ins"][1] == "In Salah"   # a 2019 wilaya, was 'Tamanrasset'

    with sqlite3.connect(db) as con:
        assert dict(con.execute(
            "SELECT detection_id, lat FROM detections").fetchall()) == before_geom
        assert dict(con.execute(
            "SELECT detection_id, acq_datetime FROM detections").fetchall()) == before_acq


def test_points_outside_algeria_become_null_not_a_neighbour(db):
    with sqlite3.connect(db) as con:
        con.execute("UPDATE detections SET wilaya_code='11', wilaya_name='Stale' "
                    "WHERE detection_id='d_off'")

    backfill.apply(db)

    assert _rows(db)["d_off"] == (None, None), \
        "offshore must be honestly null, never snapped to a nearby wilaya"


def test_apply_does_not_touch_ingest_runs(db):
    db_mod.record_run(mode="test", sources=["T"], urls=["u"], count_new=4,
                      count_total=4, status="ok")
    with sqlite3.connect(db) as con:
        before = con.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]

    backfill.apply(db)

    with sqlite3.connect(db) as con:
        after = con.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
    assert after == before, \
        "re-deriving a derived attribute is not a data acquisition"


def test_coordinates_are_not_null_so_the_null_branch_is_unreachable(db):
    """Documents why backfill's defensive null check cannot fire via the DB.

    lat/lon are NOT NULL in the schema, so "a stored detection with no
    coordinates" cannot exist. The guard stays as defence in depth for a future
    schema change, but this test records that it is not currently exercisable
    rather than pretending otherwise.
    """
    with sqlite3.connect(db) as con:
        notnull = {r[1] for r in con.execute("PRAGMA table_info(detections)") if r[3]}
    assert {"lat", "lon"} <= notnull
    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(db) as con:
            con.execute("UPDATE detections SET lat=NULL WHERE detection_id='d_alg'")


def test_apply_is_idempotent(db):
    first = backfill.apply(db)
    second = backfill.apply(db)
    assert second["updated"] == 0, "a second run must find nothing left to change"
    assert first["examined"] == second["examined"]