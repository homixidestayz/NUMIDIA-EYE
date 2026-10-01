"""--day-range tests for pull-history (synthetic fixtures, no network).

Pins the multi-date split contract: one deterministic file per
(date, source), never a merged multi-date file, never a date outside the
requested range, and existing files never rewritten.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from numidia_ml import cli as C
from numidia_core import firms as F

SECRET = "TEST-SECRET-KEY-12345"


def _raw(dates: list[str], src: str = "VIIRS_SNPP_SP") -> pd.DataFrame:
    rows = []
    for di, d in enumerate(dates):
        for i in range(2):
            rows.append({
                "latitude": 31.7 + 0.001 * i + 0.01 * di,
                "longitude": 6.05 + 0.001 * i,
                "bright_ti4": 320.0 + i, "bright_ti5": 295.0,
                "scan": 0.4, "track": 0.4,
                "acq_date": d, "acq_time": "1230",
                "satellite": "N", "instrument": "VIIRS", "confidence": "n",
                "version": "2.0", "frp": 5.0 + i, "daynight": "D", "type": 0,
            })
    df = pd.DataFrame(rows)
    df["_firms_source"] = src
    df["_firms_url"] = F.nrt_url(SECRET, src, 1, date=dates[0])
    return df


def _args(tmp_path, **over):
    base = {"start": "2024-01-01", "end": "2024-01-05",
            "sources": "VIIRS_SNPP_SP", "map_key": SECRET,
            "out": str(tmp_path), "manifest_name": "m.json",
            "skip_existing": True, "forbid_nrt": True,
            "run_id": "r", "day_range": 1}
    base.update(over)
    return type("NS", (), base)()


@pytest.fixture()
def fake5(monkeypatch):
    """DAY_RANGE=5 returns 5 dates; the last call may return fewer."""
    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        src = (sources or ["VIIRS_SNPP_SP"])[0]
        from datetime import date as _d, timedelta
        d0 = _d.fromisoformat(date)
        n = day if date == "2024-01-01" else 1   # only the first chunk is full
        return _raw([(d0 + timedelta(days=i)).isoformat() for i in range(n)], src)
    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    return _fake


# ------------------------------------------------------- 1. default day_range=1
def test_default_day_range_is_one(monkeypatch, tmp_path):
    seen = []
    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        seen.append(day)
        return _raw([date])
    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    C.cmd_pull_history(_args(tmp_path, end="2024-01-03"))
    assert seen == [1, 1, 1], "default must issue one request per date"


def test_day_range_one_writes_one_file_per_date(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "fetch_nrt_area",
                        lambda map_key=None, sources=None, day=1, date=None, bbox=None:
                        _raw([date]))
    C.cmd_pull_history(_args(tmp_path, end="2024-01-03"))
    assert sorted(p.name for p in tmp_path.glob("*.parquet")) == [
        "2024-01-01_VIIRS_SNPP_SP.parquet",
        "2024-01-02_VIIRS_SNPP_SP.parquet",
        "2024-01-03_VIIRS_SNPP_SP.parquet"]


# ------------------------------------------------------- 2. explicit day_range=5
def test_day_range_five_splits_into_five_files(fake5, tmp_path):
    rc = C.cmd_pull_history(_args(tmp_path, day_range=5))
    assert rc == 0
    names = sorted(p.name for p in tmp_path.glob("*.parquet"))
    assert names == [f"2024-01-0{i}_VIIRS_SNPP_SP.parquet" for i in range(1, 6)]


def test_each_file_contains_exactly_one_date(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    for p in tmp_path.glob("*.parquet"):
        df = pd.read_parquet(p)
        assert set(df["acq_date"].astype(str)) == {p.name[:10]}, \
            f"{p.name} mixes acquisition dates"


def test_day_range_five_uses_fewer_requests(fake5, tmp_path):
    """5 days / 5-day chunks = 1 chunk x 1 source = 1 request, 5 files."""
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["requests_made"] == 1
    assert m["day_range"] == 5
    assert len(m["files"]) == 5


def test_day_range_five_collapses_a_ten_day_span(monkeypatch, tmp_path):
    """10 days at day_range=5 costs 2 requests, versus 10 at day_range=1."""
    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        from datetime import date as _d, timedelta
        d0 = _d.fromisoformat(date)
        return _raw([(d0 + timedelta(days=i)).isoformat() for i in range(day)])
    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    C.cmd_pull_history(_args(tmp_path, day_range=5, end="2024-01-10"))
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["requests_made"] == 2
    assert len(m["files"]) == 10


def test_request_passes_day_range_to_client(monkeypatch, tmp_path):
    seen = []
    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        seen.append((day, date))
        return _raw([date])
    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    C.cmd_pull_history(_args(tmp_path, day_range=5, end="2024-01-05"))
    assert all(d == 5 for d, _ in seen)


# ------------------------------------------------------- 3. invalid day ranges
@pytest.mark.parametrize("bad", [0, -1, 6, 99])
def test_invalid_day_range_refused(tmp_path, bad, capsys):
    rc = C.cmd_pull_history(_args(tmp_path, day_range=bad))
    assert rc == 2
    assert "day-range must be 1..5" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.parquet"))


def test_end_before_start_refused(tmp_path, capsys):
    rc = C.cmd_pull_history(_args(tmp_path, start="2024-01-05", end="2024-01-01"))
    assert rc == 2
    assert "--end must be >= --start" in capsys.readouterr().out


# ------------------------------------------------------- 4. no merging of dates
def test_no_merged_multi_date_file(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    for p in tmp_path.glob("*.parquet"):
        assert len(pd.read_parquet(p)["acq_date"].astype(str).unique()) == 1


# ------------------------------------------------------- 5. final partial window
def test_dates_after_end_are_not_archived(monkeypatch, tmp_path):
    """A 5-day chunk starting near --end must not spill past it."""
    def _fake(map_key=None, sources=None, day=1, date=None, bbox=None):
        return _raw(["2024-01-04", "2024-01-05", "2024-01-06", "2024-01-07"])
    monkeypatch.setattr(F, "fetch_nrt_area", _fake)
    C.cmd_pull_history(_args(tmp_path, day_range=5, start="2024-01-04", end="2024-01-05"))
    names = sorted(p.name for p in tmp_path.glob("*.parquet"))
    assert names == ["2024-01-04_VIIRS_SNPP_SP.parquet",
                     "2024-01-05_VIIRS_SNPP_SP.parquet"]
    m = json.loads((tmp_path / "m.json").read_text())
    assert {d["date"] for d in m["dates_outside_requested_range"]} == {
        "2024-01-06", "2024-01-07"}
    assert m["date_coverage"]["max"] == "2024-01-05"


# ------------------------------------------------------- 6. skip-existing
def test_skip_existing_leaves_file_untouched(fake5, tmp_path):
    dest = tmp_path / "2024-01-03_VIIRS_SNPP_SP.parquet"
    dest.write_bytes(b"PRE-EXISTING")
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    assert dest.read_bytes() == b"PRE-EXISTING", "existing file was rewritten"
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["skipped_existing"] == 1
    assert "2024-01-03_VIIRS_SNPP_SP.parquet" not in m["files"]


def test_fully_covered_chunk_costs_no_request(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["requests_made"] == 0
    assert m["chunks_fully_skipped"] >= 1


# ------------------------------------------------------- 7. source guards hold
@pytest.mark.parametrize("bad", ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT",
                                 "VIIRS_NOAA21_NRT", "MODIS_SP"])
def test_forbid_nrt_still_applies_with_day_range(tmp_path, bad, capsys):
    rc = C.cmd_pull_history(_args(tmp_path, sources=bad, day_range=5))
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().out


# ------------------------------------------------------- 8. manifest provenance
def test_manifest_records_day_range_and_provenance(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    m = json.loads((tmp_path / "m.json").read_text())
    for k in ("run_id", "day_range", "requests_made", "chunks_fully_skipped",
              "skipped_existing", "rows", "failures", "files",
              "date_coverage", "sources", "filename_pattern"):
        assert k in m, f"missing {k}"
    assert m["day_range"] == 5
    assert m["rows"] == 10            # 5 dates x 2 rows
    assert all("written" in c for c in m["calls"] if c.get("status") == "ok")


def test_resumed_run_preserves_prior_provenance(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    C.cmd_pull_history(_args(tmp_path, day_range=5, start="2024-02-01",
                             end="2024-02-05", run_id="r2"))
    m = json.loads((tmp_path / "m.json").read_text())
    assert "runs" in m and len(m["runs"]) == 2
    assert m["runs"][0]["run_id"] == "r"
    assert m["runs"][1]["run_id"] == "r2"
    assert "2024-01-01_VIIRS_SNPP_SP.parquet" in m["files"], \
        "earlier run's files must survive the merge"


# ------------------------------------------------------- 9. safety invariants
def test_credentials_absent_with_day_range(fake5, tmp_path):
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    assert SECRET not in (tmp_path / "m.json").read_text()
    for p in tmp_path.glob("*.parquet"):
        df = pd.read_parquet(p)
        assert df["source_url"].map(lambda u: SECRET not in str(u)).all()


def test_non_finite_fails_closed_with_day_range(monkeypatch, tmp_path):
    def _bad(map_key=None, sources=None, day=1, date=None, bbox=None):
        raw = _raw([date])
        raw.loc[0, "frp"] = float("inf")
        return raw
    monkeypatch.setattr(F, "fetch_nrt_area", _bad)
    C.cmd_pull_history(_args(tmp_path, day_range=5))
    assert not list(tmp_path.glob("*.parquet"))
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["rejected_frames"] >= 1