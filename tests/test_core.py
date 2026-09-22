"""Core engine tests - offline, using the TEST FIXTURE (never production data).

Fixture: tests/fixtures/firms_noaa21_sample_1d.csv - 250 real FIRMS rows kept
solely for automated testing. Production code must never read it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from numidia_core.config import ALGERIA_BBOX
from numidia_core.enrichment import clip_to_algeria, lookup_wilaya
from numidia_core.firms import confidence_to_num, normalize_raw, redact_url, validate
from numidia_core.processing import derive_features

FIXTURE = Path(__file__).parent / "fixtures" / "firms_noaa21_sample_1d.csv"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _normalized() -> pd.DataFrame:
    raw = pd.read_csv(FIXTURE)
    df = normalize_raw(raw, source="VIIRS_NOAA21_NRT", source_url="firms://test",
                       fetched_at=NOW)
    return validate(df)


def test_fixture_is_real_and_complete():
    raw = pd.read_csv(FIXTURE)
    assert len(raw) == 250
    assert (raw["satellite"] == "N21").all()
    assert (raw["instrument"] == "VIIRS").all()


def test_normalize_full_schema():
    df = _normalized()
    assert len(df) == 250
    expected = {
        "detection_id", "lat", "lon", "acq_datetime", "acq_date", "acq_time",
        "satellite", "instrument", "confidence", "confidence_raw", "bright_ti4",
        "bright_ti5", "scan", "track", "frp", "daynight", "version", "source",
        "source_url", "fetched_at",
    }
    assert expected <= set(df.columns)


def test_detection_ids_unique():
    df = _normalized()
    assert df["detection_id"].nunique() == len(df)


def test_confidence_mapping():
    df = _normalized()
    assert set(df["confidence_raw"].dropna().unique()) <= {"h", "n", "l"}
    n_rows = df[df["confidence_raw"] == "n"]
    if len(n_rows):
        assert (n_rows["confidence"] == 0.6).all()
    assert confidence_to_num("high") == 1.0
    assert confidence_to_num("l") == 0.2
    assert confidence_to_num(75) == 0.75
    assert confidence_to_num("garbage") is None


def test_bbox_validation():
    df = _normalized()
    assert df["lat"].between(ALGERIA_BBOX["lat_min"], ALGERIA_BBOX["lat_max"]).all()
    assert df["lon"].between(ALGERIA_BBOX["lon_min"], ALGERIA_BBOX["lon_max"]).all()


def test_acq_datetime_parsed_utc():
    df = _normalized()
    ts = pd.to_datetime(df["acq_datetime"], utc=True)
    assert ts.dt.tz is not None
    assert (ts.dt.date == pd.Timestamp("2026-09-17").date()).all()


def test_provenance_present():
    df = _normalized()
    assert (df["source"] == "VIIRS_NOAA21_NRT").all()
    assert (df["fetched_at"] == NOW).all()
    assert df["source_url"].notna().all()


def test_key_redaction():
    url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/SECRETKEY123/VIIRS_NOAA21_NRT/1/-9,18,12,38"
    redacted = redact_url(url, "SECRETKEY123")
    assert "SECRETKEY123" not in redacted
    assert "{FIRMS_MAP_KEY}" in redacted
    assert redact_url(None, "SECRETKEY123") is None


def test_derive_features_real():
    df = _normalized()
    feats = derive_features(df)
    assert len(feats) == len(df)
    r0 = feats.iloc[0]
    assert abs(r0["f_bt_diff"] - (r0["bright_ti4"] - r0["bright_ti5"])) < 1e-9
    assert set(feats["f_month"].dropna()) <= {8, 9, 10, 11, 12}
    assert set(feats["f_daynight"].dropna().unique()) <= {0, 1}


def test_wilaya_enrichment_real():
    df = _normalized()
    kept, excluded = clip_to_algeria(derive_features(df))
    # The FIRMS bbox necessarily over-covers Algeria (neighbors +
    # Mediterranean): 64/250 fixture rows are genuinely out-of-country and
    # are excluded with a recorded count - never served as Algerian.
    assert len(kept) == 186
    assert excluded == 64
    assert kept["wilaya_code"].notna().all()
    assert kept["wilaya_code"].str.match(r"^\d{1,2}$").all()
    # Spot check: a known inland point resolves (Algiers area -> 16).
    hit = lookup_wilaya(36.75, 3.06)
    assert hit["wilaya_code"] == "16"