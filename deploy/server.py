"""Production wrapper: NUMIDIA API + static dashboard on one origin.

Keeps the repository untouched: imports the app factory from the repo,
serves apps/site at /, and injects window.NUMIDIA_API_BASE so the
dashboard talks to this same origin instead of 127.0.0.1:8010.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from numidia_api.app import build_app

REPO = Path(os.environ.get("NUMIDIA_REPO", "/app/repo"))
SITE = REPO / "apps" / "site"

app: FastAPI = build_app()

_raw_index = (SITE / "index.html").read_text(encoding="utf-8")
_inject = '<script>window.NUMIDIA_API_BASE = location.origin;</script>\n'
if "<script src=\"./site.js\">" in _raw_index:
    _patched_index = _raw_index.replace(
        '<script src="./site.js">', _inject + '<script src="./site.js">', 1
    )
else:  # fallback: inject right after <body>
    _patched_index = _raw_index.replace("<body>", "<body>\n" + _inject, 1)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    return _patched_index


app.mount("/", StaticFiles(directory=str(SITE), html=False), name="site")
