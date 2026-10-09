"""Re-derive wilaya assignment for detections already in the database.

`wilaya_code` / `wilaya_name` are written at INGEST time by `enrichment`, and
`upsert_detections` deliberately never overwrites an existing row ("first-seen
wins"). So when the bundled boundaries change, stored detections keep the
geography they were stamped with, while the map and every new ingest use the new
one. That produces two different answers to "which wilaya is this?" depending on
when you ask - and, given the 48 -> 69 correction, the stored answer is the wrong
one for every detection inside a promoted wilaya.

This recomputes the assignment from each detection's own lat/lon. It changes only
those two columns. It deliberately does NOT touch `ingest_runs`: re-deriving a
derived attribute is not a data acquisition, and recording it as one would make a
stale database look freshly ingested.

Detections whose coordinates fall outside every polygon keep NULL. That is the
correct answer for offshore and border points, not a failure to fix.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import enrichment
from .db import connect, resolve_db_path


def scan(db_path: Path | str | None = None, limit: Optional[int] = None) -> dict:
    """Report what would change, without writing. Use this before ``apply``."""
    path = resolve_db_path(db_path)
    sql = "SELECT detection_id, wilaya_code, wilaya_name FROM detections"
    params: tuple = ()
    if limit:
        sql += " LIMIT ?"
        params = (limit,)

    with connect(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    changed, unresolved = [], 0
    with connect(path) as conn:
        current = {r[0]: r for r in conn.execute(
            "SELECT detection_id, lat, lon FROM detections")}

    for detection_id, code, name in rows:
        row = current.get(detection_id)
        if row is None or row[1] is None or row[2] is None:
            unresolved += 1
            continue
        new = enrichment.lookup_wilaya(row[1], row[2])
        new_code = new.get("wilaya_code")
        new_name = new.get("wilaya_name")
        if new_code is None:
            unresolved += 1
            continue
        if str(new_code) != str(code) or new_name != name:
            changed.append({"detection_id": detection_id,
                            "from": [code, name], "to": [new_code, new_name]})

    return {"examined": len(rows), "would_change": len(changed),
            "outside_all_polygons": unresolved, "changes": changed}


def apply(db_path: Path | str | None = None, limit: Optional[int] = None) -> dict:
    """Rewrite wilaya_code / wilaya_name from stored coordinates."""
    path = resolve_db_path(db_path)
    sql = "SELECT detection_id, wilaya_code, wilaya_name, lat, lon FROM detections"
    params: tuple = ()
    if limit:
        sql += " LIMIT ?"
        params = (limit,)

    with connect(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    updates, unresolved = [], 0
    for detection_id, code, name, lat, lon in rows:
        if lat is None or lon is None:
            unresolved += 1
            continue
        new = enrichment.lookup_wilaya(lat, lon)
        new_code = new.get("wilaya_code")
        new_name = new.get("wilaya_name")
        if new_code is None:
            # Outside every polygon: record the honest absence rather than
            # leaving a stale parent wilaya behind.
            if code is not None:
                updates.append((None, None, detection_id))
            unresolved += 1
            continue
        if str(new_code) != str(code) or new_name != name:
            updates.append((new_code, new_name, detection_id))

    if updates:
        with connect(path) as conn:
            conn.executemany(
                "UPDATE detections SET wilaya_code = ?, wilaya_name = ? "
                "WHERE detection_id = ?", updates)

    return {"examined": len(rows), "updated": len(updates),
            "outside_all_polygons": unresolved}