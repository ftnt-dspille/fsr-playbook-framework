"""docs/JINJA_FILTERS.md must match what the reference DB generates (never hand-edited)."""
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_jinja_filters_doc_is_regenerated():
    r = subprocess.run([sys.executable, "-m", "tooling.store.export_jinja_reference", "--check"],
                       cwd=_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or "docs/JINJA_FILTERS.md is stale: run `make jinja-docs`"
