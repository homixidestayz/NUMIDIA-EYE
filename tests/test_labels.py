"""Labeling-engine tests - fully synthetic fixtures (no network, no real data).

These pin the v1 rules: fire inside polygon+window, night+flare negatives,
uncertain bands, conflicts, dedup, and persistence flags.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from shapely.geometry import box

from numidia_ml import labels as L


def _det(rows: list[dict]) -> pd.DataFrame:
    base = {"satellite": "N21", "instrument": "VIIRS", "confidence": 0.6,
            "confidence_raw": "n", "bright_ti4": 320.0, "bright_ti5": 295.0,
            "scan": 0.4, "track": 0.4, "frp": 5.0, "version": "2.0NRT",
            "source": "VIIRS_SNPP_NRT", "source_url": "t",
            "fetched_at": datetime(2021, 8, 12, tzinfo=timezone.utc)}
    return pd.DataFrame([{**base, **r} for r in rows])


def _burnt():
    return [{"geometry": box(4.0, 36.5, 4.5, 36.8), "start": "2021-08-08",
             "end": "2021-08-22", "gt_id": "EMSR533:AOI01-TiziOuzou:DEL_PRODUCT:0",
             "source": "P1-EMSR533"}]


def _aois():
    return [{"geometry": box(3.9, 36.4, 4.6, 36.9), "aoi": "AOI-X",
             "start": "2021-08-08", "end": "2021-08-22"}]


def _sites(persistent: bool = True):
    return pd.DataFrame([{
        "site_id": "VNF:1", "lat": 28.0, "lon": 9.0, "country": "Algeria",
        "catalog_year": 2021, "sector": "flare upstream", "bcm": 1.0,
        "detection_freq": 0.9, "avg_temp_k": 1800.0, "catalog_row_id": "7",
        "years_seen": 3 if persistent else 1,
        "persistent": persistent}])


def test_haversine_sanity():
    import numpy as np
    d = L.haversine_m(np.array([36.75]), np.array([3.06]), 35.70, -0.64)
    assert 300_000 < d[0] < 420_000  # Algiers-Oran ~360 km


def test_fire_inside_polygon_window():
    df = _det([{"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
                "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
                "detection_id": "a"}])
    lab, exc, c = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["positive"] == 1 and c["excluded"] == 0
    assert lab.iloc[0]["label_source"] == "P1-EMSR533"
    assert lab.iloc[0]["ground_truth_id"] == "EMSR533:AOI01-TiziOuzou:DEL_PRODUCT:0"


def test_fire_outside_window_is_not_fire():
    df = _det([{"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-10-25T01:00:00Z",
                "acq_date": "2021-10-25", "acq_time": "0100", "daynight": "N",
                "detection_id": "b"}])
    lab, exc, c = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["positive"] == 0
    # two months past the window -> beyond U3 -> excluded, not forced
    assert c["excluded"] == 1


def test_u3_near_window_is_uncertain():
    df = _det([{"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-25T01:00:00Z",
                "acq_date": "2021-08-25", "acq_time": "0100", "daynight": "N",
                "detection_id": "c"}])
    lab, exc, c = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["uncertain"] == 1
    assert "U3" in lab.iloc[0]["label_source"]


def test_night_flare_is_nonfire_day_is_uncertain():
    rows = [
        {"lat": 28.0, "lon": 9.0, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "night"},
        {"lat": 28.0, "lon": 9.0, "acq_datetime": "2021-08-12T13:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "1300", "daynight": "D",
         "detection_id": "day"},
    ]
    lab, exc, c = L.build_dataset(_det(rows), burnt=[], aois=[],
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["negative"] == 1 and c["uncertain"] == 1
    neg = lab[lab["label"] == "non-fire"].iloc[0]
    assert neg["label_source"] == "N1-flare" and neg["match_distance_m"] == 0.0


def test_nonpersistent_site_gives_no_negative():
    df = _det([{"lat": 28.0, "lon": 9.0, "acq_datetime": "2021-08-12T01:00:00Z",
                "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
                "detection_id": "np"}])
    lab, exc, c = L.build_dataset(df, burnt=[], aois=[],
                                  flare_sites=_sites(persistent=False),
                                  flare_catalog_year=2021)
    assert c["negative"] == 0 and c["excluded"] == 1


def test_u1_in_aoi_outside_polygon():
    df = _det([{"lat": 36.45, "lon": 3.95, "acq_datetime": "2021-08-12T01:00:00Z",
                "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
                "detection_id": "u1"}])
    lab, exc, c = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["uncertain"] == 1
    assert lab.iloc[0]["label_source"] == "U1-in-AOI-outside-polygon"


def test_conflict_is_uncertain_and_counted():
    df = _det([{"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
                "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
                "detection_id": "cf"}])
    sites = _sites()
    sites.at[0, "lat"] = 36.6
    sites.at[0, "lon"] = 4.2
    lab, exc, c = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                  flare_sites=sites, flare_catalog_year=2021)
    assert c["conflicts"] == 1 and c["uncertain"] == 1 and c["positive"] == 0


def test_dedup_keeps_max_frp():
    rows = [
        {"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "d1", "frp": 5.0},
        {"lat": 36.6001, "lon": 4.2001, "acq_datetime": "2021-08-12T03:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0300", "daynight": "N",
         "detection_id": "d2", "frp": 9.0},
    ]
    lab, exc, c = L.build_dataset(_det(rows), burnt=_burnt(), aois=_aois(),
                                  flare_sites=_sites(), flare_catalog_year=2021)
    assert c["duplicates"] == 1 and len(lab) == 1
    assert lab.iloc[0]["frp"] == 9.0


def test_mark_persistent_flags():
    import pandas as pd
    a = pd.DataFrame([{"lat": 28.0, "lon": 9.0}])
    b = pd.DataFrame([{"lat": 28.0, "lon": 9.0}, {"lat": 30.0, "lon": 5.0}])
    out = L.mark_persistent({2020: a, 2021: b})
    assert len(out) == 2
    assert bool(out[out["lat"] == 28.0].iloc[0]["persistent"]) is True
    assert bool(out[out["lat"] == 30.0].iloc[0]["persistent"]) is False


def test_nrt_url_exact_order_and_date():
    from numidia_core import firms as F
    url = F.nrt_url("K", "VIIRS_SNPP_NRT", 1, date="2021-08-12")
    assert url == ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/K/"
                   "VIIRS_SNPP_NRT/-9.0,18.0,12.0,38.0/1/2021-08-12")
    url2 = F.nrt_url("K", "VIIRS_SNPP_NRT", 2)
    assert url2.endswith("/VIIRS_SNPP_NRT/-9.0,18.0,12.0,38.0/2")
    try:
        F.nrt_url("K", "VIIRS_SNPP_NRT", 1, date="12-08-2021")
        raise AssertionError("bad date accepted")
    except ValueError:
        pass

def test_event_id_and_split_assignment():
    df = _det([
        {"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "e1"},
    ])
    lab, _, _ = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                flare_sites=_sites(), flare_catalog_year=2021)
    lab["cohort"] = "2021"
    lab = L.assign_split(L.add_event_id(lab))
    assert lab.iloc[0]["event_id"].startswith("EMSR533:")
    assert lab.iloc[0]["split"] == "train"


def test_val_event_goes_to_validation():
    df = _det([
        {"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "e2"},
    ])
    lab, _, _ = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                flare_sites=_sites(), flare_catalog_year=2021)
    lab["cohort"] = "2021"
    lab = L.add_event_id(lab)
    lab.at[0, "event_id"] = L.VAL_EVENT
    lab = L.assign_split(lab)
    assert lab.iloc[0]["split"] == "val"


def test_verify_dataset_passes_on_clean_build():
    df = _det([
        {"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "v1"},
        {"lat": 28.0, "lon": 9.0, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "v2"},
    ])
    lab, _, _ = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                flare_sites=_sites(), flare_catalog_year=2021)
    lab["cohort"] = "2021"
    lab = L.assign_split(L.add_event_id(lab))
    checks = L.verify_dataset(lab, {"v1", "v2"}, {"VNF:1"})
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]


def test_verify_dataset_catches_untraced_row():
    df = _det([
        {"lat": 36.6, "lon": 4.2, "acq_datetime": "2021-08-12T01:00:00Z",
         "acq_date": "2021-08-12", "acq_time": "0100", "daynight": "N",
         "detection_id": "ghost"},
    ])
    lab, _, _ = L.build_dataset(df, burnt=_burnt(), aois=_aois(),
                                flare_sites=_sites(), flare_catalog_year=2021)
    lab["cohort"] = "2021"
    lab = L.assign_split(L.add_event_id(lab))
    checks = L.verify_dataset(lab, {"something-else"}, {"VNF:1"})
    by_name = {c["check"]: c for c in checks}
    v5 = [c for c in checks if c["check"].startswith("V5")][0]
    assert v5["ok"] is False

def test_strat_band_split():
    import pandas as pd
    df = pd.DataFrame({"lat": [36.0, 33.9, 28.0]})
    out = L.add_strat_band(df)
    assert out["strat_lat_band"].tolist() == ["north", "south", "south"]


def test_assign_folds_balances_classes():
    import pandas as pd
    rows = ([{"wilaya_name": "N1", "event_id": "EV-N1", "split": "train", "label": "fire"}] * 6
            + [{"wilaya_name": "N2", "event_id": "EV-N2", "split": "train", "label": "fire"}] * 6
            + [{"wilaya_name": "S1", "event_id": "EV-S1", "split": "train", "label": "non-fire"}] * 6
            + [{"wilaya_name": "S2", "event_id": "EV-S2", "split": "train", "label": "non-fire"}] * 6)
    out = L.assign_folds(pd.DataFrame(rows), k=2)
    for f in ("0", "1"):
        sub = out[out["fold"] == f]
        assert (sub["label"] == "fire").sum() > 0, f"fold {f} has no fire rows"
        assert (sub["label"] == "non-fire").sum() > 0, f"fold {f} has no non-fire rows"
    assert (out.groupby("wilaya_name")["fold"].nunique() == 1).all()


def test_assign_folds_wilaya_pure():
    import pandas as pd
    rows = []
    for i, w in enumerate(["A", "A", "B", "C", "D", "E", "F"]):
        rows.append({"wilaya_name": w, "event_id": f"EV-{w}-{i}",
                     "split": "train", "label": "fire"})
    rows.append({"wilaya_name": "A", "event_id": "EV-X",
                 "split": "val", "label": "fire"})
    df = pd.DataFrame(rows)
    out = L.assign_folds(df, k=3)
    tr = out[out["split"] == "train"]
    assert tr["fold"].notna().all()
    assert (tr.groupby("wilaya_name")["fold"].nunique() == 1).all()
    assert out.loc[out["split"] != "train", "fold"].isna().all()
    assert set(tr["fold"].unique()) <= {"0", "1", "2"}


def test_assign_folds_merges_event_sharing_wilayas():
    import pandas as pd
    df = pd.DataFrame([
        {"wilaya_name": "A", "event_id": "EV-1", "split": "train", "label": "fire"},
        {"wilaya_name": "B", "event_id": "EV-1", "split": "train", "label": "fire"},
        {"wilaya_name": "C", "event_id": "EV-2", "split": "train", "label": "fire"},
    ])
    out = L.assign_folds(df, k=5)
    fa = out.loc[out["wilaya_name"] == "A", "fold"].iloc[0]
    fb = out.loc[out["wilaya_name"] == "B", "fold"].iloc[0]
    assert fa == fb  # shared event keeps wilayas in one fold


def test_feature_contract_bans_location_and_time():
    for banned in ("lat", "lon", "wilaya_name", "daynight", "f_hour_utc",
                   "acq_date", "detection_id", "source"):
        assert banned in L.BANNED_FEATURES, banned
        assert banned not in L.MODEL_FEATURES_V1, banned
    for feat in ("bright_ti4", "bright_ti5", "f_bt_diff", "frp", "confidence"):
        assert feat in L.MODEL_FEATURES_V1, feat


def test_verify_v2_catches_fold_leak():
    import pandas as pd
    df = pd.DataFrame([
        {"wilaya_name": "A", "event_id": "EV-1", "split": "train",
         "label": "fire", "fold": "0", "strat_lat_band": "north",
         "bright_ti4": 330.0, "bright_ti5": 300.0, "f_bt_diff": 30.0,
         "frp": 5.0, "f_frp": 5.0, "confidence": 0.6, "f_confidence": 0.6,
         "scan": 0.4, "track": 0.4, "satellite": "N", "type": "0"},
        {"wilaya_name": "A", "event_id": "EV-1", "split": "train",
         "label": "fire", "fold": "1", "strat_lat_band": "north",
         "bright_ti4": 331.0, "bright_ti5": 301.0, "f_bt_diff": 30.0,
         "frp": 6.0, "f_frp": 6.0, "confidence": 0.6, "f_confidence": 0.6,
         "scan": 0.4, "track": 0.4, "satellite": "N", "type": "0"},
    ])
    checks = L.verify_v2(df)
    by_name = {c["check"][:4]: c for c in checks}
    assert by_name["V8a:"]["ok"] is False  # wilaya A spans folds 0 and 1
    assert by_name["V8b:"]["ok"] is False  # event EV-1 spans folds
    assert by_name["V9: "]["ok"] is True
    assert by_name["V10:"]["ok"] is True
