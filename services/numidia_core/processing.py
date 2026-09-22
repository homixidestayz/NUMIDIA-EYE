"""Real feature derivation from real detections.

No labels, no AI here — only physics-based features computed from the actual
FIRMS/VIIRS fields (brightness temperatures, FRP, time-of-day). These are the
features a later trained verifier model will consume. Nothing is invented:
if a raw field is missing the corresponding feature is left as NaN.
"""
from __future__ import annotations

import pandas as pd


def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add f_* features derived from the canonical detection frame."""
    out = df.copy()

    # Thermal contrast: I4 - I5 brightness temperature (K). A fire stand-out
    # signal in VIIRS data. Only if both bands are present in the real data.
    if {"bright_ti4", "bright_ti5"}.issubset(out.columns):
        out["f_bt_diff"] = out["bright_ti4"] - out["bright_ti5"]

    # Fire Radiative Power (MW) -- real value from FIRMS.
    out["f_frp"] = out["frp"]

    # Normalized confidence 0..1 (from FIRMS h/n/l or 0-100).
    out["f_confidence"] = out["confidence"]

    # Time-of-day / season context from the real acquisition timestamp.
    if "acq_datetime" in out.columns:
        ts = pd.to_datetime(out["acq_datetime"], utc=True)
        out["f_hour_utc"] = ts.dt.hour + ts.dt.minute / 60.0
        out["f_month"] = ts.dt.month
        out["f_doy"] = ts.dt.dayofyear

    # Day / night flag (FIRMS 'D'/'N'), as binary.
    if "daynight" in out.columns:
        out["f_daynight"] = (
            out["daynight"].astype(str).str.upper().str[0].eq("D")
        ).astype(int)

    # A row with neither thermal nor radiative power is not a usable fire
    # observation; drop it rather than invent values.
    if {"f_bt_diff", "f_frp"}.issubset(out.columns):
        keep = out["f_bt_diff"].notna() | out["f_frp"].notna()
        out = out[keep].reset_index(drop=True)

    return out