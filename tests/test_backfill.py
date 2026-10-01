"""Backfill-archive tests - synthetic fixtures only (no network, no real data).

These protect the invariants of the historical FIRMS archive:
  * only reproducible VIIRS SP sources are accepted for a backfill
  * an existing parquet is skipped, never rewritten
  * the manifest is written under a NEW name and never clobbers an old one
  * filenames are deterministic
  * schema / coordinate / finiteness / duplicate anomalies are REPORTED
  * the FIRMS key never reaches a file, manifest, or log line
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from numidia_ml import cli as C
from numidia_core import firms as F

SECRET = "TEST-SECRET-KEY-12345"


def _raw(n: int = 3, lat: float = 31.7) -> pd.DataFrame:
    """Raw FIRMS-shaped payload as the Area API returns it."""
    return pd.DataFrame([{
        "latitude": lat + 0.001 * i, "longitude": 6.05 + 0.001 * i,
        "bright_ti4": 320.0 + i, "bright_ti5": 295.0, "scan": 0.4, "track": 0.4,
        "acq_date": "2024-01-15", "acq_time": f"123{i}",
        "satellite": "N", "instrument": "VIIRS", "confidence": "n",
        "version": "2.0", "frp": 5.0 + i, "daynight": "D", "type": 0,
    } for i in range(n)])


def _args(tmp_path: Path, **over):
    base = {
        "start": "2024-01-15", "end": "2024-01-15",
        "sources": "VIIRS_SNPP_SP", "map_key": SECRET,
        "out": str(tmp_path), "manifest_name": "manifest_run.json",
        "skip_existing": True, "forbid_nrt": True, "run_id": "test_run",
    }
    base.update(over)
    return type("NS", (), base)()


@pytest.fixture()
def fake_fetch(monkeypatch):
    """Patch the real network call; record every URL the code builds."""
    seen: list[str] = []

    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        src = (sources or ["VIIRS_SNPP_SP"])[0]
        url = F.nrt_url(map_key, src, day, bbox=bbox, date=date)
        seen.append(url)
        raw = _raw()
        raw["_firms_source"] = src
        raw["_firms_url"] = url
        return raw

    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    return seen


# ---------------------------------------------------------------- source guard
@pytest.mark.parametrize("bad", ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT",
                                 "VIIRS_NOAA21_NRT", "MODIS_SP", "MODIS_NRT"])
def test_forbid_nrt_refuses_non_sp_sources(tmp_path, bad, capsys):
    rc = C.cmd_pull_history(_args(tmp_path, sources=bad))
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.parquet"))


def test_sp_sources_are_accepted(tmp_path, fake_fetch):
    assert C.cmd_pull_history(_args(tmp_path)) == 0
    assert (tmp_path / "2024-01-15_VIIRS_SNPP_SP.parquet").exists()


# ---------------------------------------------------------------- filenames
def test_filename_is_deterministic(tmp_path, fake_fetch):
    C.cmd_pull_history(_args(tmp_path, sources="VIIRS_SNPP_SP,VIIRS_NOAA20_SP"))
    names = sorted(p.name for p in tmp_path.glob("*.parquet"))
    assert names == ["2024-01-15_VIIRS_NOAA20_SP.parquet",
                     "2024-01-15_VIIRS_SNPP_SP.parquet"]


# ---------------------------------------------------------------- archive safety
def test_skip_existing_does_not_rewrite(tmp_path, fake_fetch):
    dest = tmp_path / "2024-01-15_VIIRS_SNPP_SP.parquet"
    dest.write_bytes(b"PRE-EXISTING-BYTES")
    rc = C.cmd_pull_history(_args(tmp_path, skip_existing=True))
    assert rc == 2 or rc == 0
    assert dest.read_bytes() == b"PRE-EXISTING-BYTES", "existing file was rewritten"
    man = json.loads((tmp_path / "manifest_run.json").read_text())
    # A fully covered chunk is skipped without spending a request at all.
    assert man["requests_made"] == 0
    assert man["chunks_fully_skipped"] == 1
    assert man["files"] == []


def test_manifest_name_does_not_clobber_old_manifest(tmp_path, fake_fetch):
    old = tmp_path / "manifest.json"
    old.write_text('{"legacy": true}', encoding="utf-8")
    C.cmd_pull_history(_args(tmp_path, manifest_name="manifest_run2.json"))
    assert json.loads(old.read_text()) == {"legacy": True}
    assert (tmp_path / "manifest_run2.json").exists()


def test_manifest_records_provenance(tmp_path, fake_fetch):
    C.cmd_pull_history(_args(tmp_path))
    m = json.loads((tmp_path / "manifest_run.json").read_text())
    for k in ("run_id", "started_at", "finished_at", "start", "end", "sources",
              "source_type", "geographic_request", "schema", "files", "rows",
              "failures", "date_coverage", "filename_pattern"):
        assert k in m, f"manifest missing {k}"
    assert m["run_id"] == "test_run"
    assert m["schema"] == list(F.CANONICAL_COLUMNS)
    assert m["date_coverage"]["min"] == "2024-01-15"
    assert m["files"] == ["2024-01-15_VIIRS_SNPP_SP.parquet"]


def test_stored_frame_carries_all_live_v1_raw_fields(tmp_path, fake_fetch):
    C.cmd_pull_history(_args(tmp_path))
    df = pd.read_parquet(tmp_path / "2024-01-15_VIIRS_SNPP_SP.parquet")
    for c in C.HISTORY_LIVE_V1_RAW:
        assert c in df.columns, f"live-v1 raw field {c} missing from archive"
    assert df["bright_ti4"].notna().all()


# ---------------------------------------------------------------- validation
def test_validate_ok_frame():
    df = F.normalize_raw(_raw(), source="VIIRS_SNPP_SP", source_url="u",
                        fetched_at=pd.Timestamp("2024-01-15", tz="UTC").to_pydatetime())
    rep = C.validate_history_frame(df)
    assert rep["ok"] is True
    assert rep["rows"] == 3
    assert rep["bad_lat"] == 0 and rep["bad_lon"] == 0


def test_validate_reports_missing_columns():
    rep = C.validate_history_frame(pd.DataFrame({"lat": [1.0]}))
    assert rep["ok"] is False
    assert "detection_id" in rep["missing_columns"]


def test_validate_reports_bad_coordinates_and_nonfinite():
    df = F.normalize_raw(_raw(), source="VIIRS_SNPP_SP", source_url="u",
                        fetched_at=pd.Timestamp("2024-01-15", tz="UTC").to_pydatetime())
    df.loc[0, "lat"] = 999.0
    df.loc[1, "frp"] = float("inf")
    rep = C.validate_history_frame(df)
    assert rep["bad_lat"] == 1
    assert rep["non_finite"].get("frp") == 1
    assert rep["ok"] is False


def test_validate_reports_duplicate_ids_not_silently():
    df = F.normalize_raw(_raw(), source="VIIRS_SNPP_SP", source_url="u",
                        fetched_at=pd.Timestamp("2024-01-15", tz="UTC").to_pydatetime())
    rep = C.validate_history_frame(pd.concat([df, df], ignore_index=True))
    assert rep["duplicate_ids"] == 3


def test_all_null_live_v1_field_is_reported_but_rows_are_kept(tmp_path, monkeypatch):
    """normalize_raw back-fills absent columns as None. A payload that never
    carried bright_ti4 yields an all-null column: the real detections are kept
    (never silently discarded) and the anomaly must be reported."""
    def _no_ti4(map_key=None, sources=None, day=1, date=None, bbox=None):
        raw = _raw().drop(columns=["bright_ti4"])
        raw["_firms_source"] = "VIIRS_SNPP_SP"
        raw["_firms_url"] = F.nrt_url(map_key, "VIIRS_SNPP_SP", 1, date=date)
        return raw
    monkeypatch.setattr(F, "fetch_nrt_area", _no_ti4)
    rc = C.cmd_pull_history(_args(tmp_path))
    assert rc == 0
    assert (tmp_path / "2024-01-15_VIIRS_SNPP_SP.parquet").exists(), \
        "real detections must not be discarded"
    m = json.loads((tmp_path / "manifest_run.json").read_text())
    assert m["validation_warnings"], "all-null live-v1 field was not reported"
    assert "bright_ti4" in m["validation_warnings"][0]["all_null_live_v1_columns"]


def test_validation_rejection_prevents_write(tmp_path, monkeypatch):
    """A frame with a non-finite numeric fails closed and is not stored.

    (Impossible coordinates never reach the validator: the pre-existing
    firms.validate() bbox filter drops them first.)
    """
    def _bad(map_key=None, sources=None, day=1, date=None, bbox=None):
        raw = _raw()
        raw.loc[0, "frp"] = float("inf")       # survives validate(), unusable
        raw["_firms_source"] = "VIIRS_SNPP_SP"
        raw["_firms_url"] = F.nrt_url(map_key, "VIIRS_SNPP_SP", 1, date=date)
        return raw
    monkeypatch.setattr(F, "fetch_nrt_area", _bad)
    rc = C.cmd_pull_history(_args(tmp_path))
    assert not list(tmp_path.glob("*.parquet")), "invalid frame was stored"
    m = json.loads((tmp_path / "manifest_run.json").read_text())
    assert m["rejected_frames"] == 1
    assert rc == 2


# ---------------------------------------------------------------- redaction
def test_key_never_written_to_manifest_or_frame(tmp_path, fake_fetch):
    C.cmd_pull_history(_args(tmp_path))
    man_text = (tmp_path / "manifest_run.json").read_text()
    assert SECRET not in man_text
    df = pd.read_parquet(tmp_path / "2024-01-15_VIIRS_SNPP_SP.parquet")
    assert df["source_url"].map(lambda u: SECRET not in str(u)).all()
    assert df["source_url"].map(lambda u: "{FIRMS_MAP_KEY}" in str(u)).all()


def test_error_message_is_redacted(tmp_path, monkeypatch, capsys):
    def _boom(map_key=None, sources=None, day=1, date=None, bbox=None):
        raise RuntimeError(f"failed GET {F.nrt_url(map_key, 'VIIRS_SNPP_SP', 1, date=date)}")
    monkeypatch.setattr(F, "fetch_nrt_area", _boom)
    rc = C.cmd_pull_history(_args(tmp_path))
    out = capsys.readouterr().out
    assert SECRET not in out
    assert "{FIRMS_MAP_KEY}" in out
    assert rc == 2
    m = json.loads((tmp_path / "manifest_run.json").read_text())
    assert m["failures"] == 1
    assert SECRET not in json.dumps(m)