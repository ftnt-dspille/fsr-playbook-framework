"""CSV report builder for ``code_snippet`` playbook steps.

Stdlib-only (``csv`` + ``io``) so it imports under the code-snippet connector's
default import policy, and produces a single-cell-per-value CSV that an
``smtp`` ``send_email`` (``file_path``) or ``slack`` ``upload_file`` step can
attach unchanged.

Example -- in a reconciliation playbook, build a CSV of mismatches and hand the
path to a notification step::

    from fsr_playbooks.helpers import csv_report
    path = csv_report.write_csv(
        "/tmp/recon.csv",
        mismatches,
        columns=["serial", "field", "value_a", "value_b"],
    )
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


def _coerce(value: Any) -> str:
    """Render a step-var value as a single CSV cell (empty for ``None``)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _columns(rows: list[dict[str, Any]], columns: list[str] | None) -> list[str]:
    if columns:
        return list(columns)
    seen: dict[str, None] = {}
    for row in rows:
        for k in row:
            seen.setdefault(k, None)
    return list(seen)


def build_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Render ``rows`` (a list of dicts) as a CSV string.

    ``columns`` pins the column order; without it the union of keys in
    first-seen order is used. Missing values become empty cells and
    non-scalar values (lists/dicts) are JSON-encoded into a single cell so
    they never split across columns.
    """
    cols = _columns(rows, columns)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(cols)
    for row in rows:
        writer.writerow([_coerce(row.get(c)) for c in cols])
    return out.getvalue()


def write_csv(
    path: str | Path,
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> str:
    """Write ``rows`` as CSV to ``path`` (created/overwritten); return ``str(path)``.

    The returned path is what a notification step's attachment argument takes
    (e.g. SMTP ``send_email`` ``file_path`` or Slack ``upload_file`` ``file``).
    """
    text = build_csv(rows, columns=columns)
    p = Path(path)
    p.write_text(text, encoding="utf-8")
    return str(p)
