"""Notebook validity tests - the cloud notebook must stay a correct, portable driver."""
from __future__ import annotations

import json
from pathlib import Path

NB = Path(__file__).resolve().parents[1] / "notebooks" / "numidia_cloud_train.ipynb"


def _nb() -> dict:
    return json.loads(NB.read_text(encoding="utf-8"))


def _sources(nb: dict) -> list[str]:
    return ["".join(c.get("source", [])) for c in nb["cells"]]


def test_notebook_is_valid_nbformat():
    nb = _nb()
    assert nb["nbformat"] == 4
    assert nb["metadata"]["kernelspec"]["language"] == "python"
    assert len(nb["cells"]) >= 6
    kinds = {c["cell_type"] for c in nb["cells"]}
    assert {"markdown", "code"} <= kinds


def test_notebook_covers_workflow():
    text = "\n".join(_sources(_nb()))
    for marker in ("git clone", "pip install", "manifest_v2",
                   "firms_labels_v2.csv", "numidia_ml.cli experiment",
                   "PYTHONPATH", "metrics.json", "config.json", "EXPERIMENTAL"):
        assert marker in text, f"notebook missing: {marker}"


def test_notebook_has_no_local_paths_or_secrets():
    text = "\n".join(_sources(_nb()))
    assert "C:\\" not in text and "C:/" not in text
    assert "FIRMS_MAP_KEY=" not in text
    assert "uv run" not in text  # uv does not exist on Colab/Kaggle


def test_notebook_code_cells_compile():
    nb = _nb()
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells
    for i, cell in enumerate(code_cells):
        body = "\n".join(
            line for line in "".join(cell.get("source", [])).splitlines()
            if not line.strip().startswith(("!", "%"))
        )
        compile(body, f"<cell {i}>", "exec")
