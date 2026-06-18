"""probe_jinja — populate jinja_macros (filters) + jinja_context_vars.

Sources, in priority order:

  1. widget_constants — `widget-jinja-editor/widget/widgetAssets/js/constants/
     jinjaFilters.constants.js` (49 filters, comprehensive metadata). Loaded
     via a small Node helper because the file is an IIFE that expects a
     `window` global. Status `seen` only.

  2. live_api_render — for each filter, render a tiny `{{ value | filter }}`
     template via the FSR Jinja-render endpoint. The endpoint URL isn't
     documented; we discover it by trying a list of candidates with the
     widget's known call shape: POST { template, values }.

Trust ladder:
  - Filter cataloged from widget constants: `seen` via widget_constants.
  - Filter renders successfully on FSR: promoted to `tested_pass` via
    live_api_render.
  - Render endpoint itself: tested_pass via live_api_render once any filter
    succeeds through it.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import warnings
from pathlib import Path
from typing import Any

from . import _env
from .common import (
    probe_session,
    record_verification,
    wipe_probe_tables,
)

PROBE_NAME = "probe_jinja"

PLAYBOOK_GUIDE_PDF = (
    Path.home()
    / "Library/CloudStorage/OneDrive-FortinetCorpMain"
    / "Cloud_Documents/Documentation/FSOAR"
    / "FortiSOAR Playbooks Guide - FortiSOAR-7.6.1-Playbooks_Guide.pdf"
)
PLAYBOOK_GUIDE_FILTER_PAGES = (207, 214)  # comprehensive filter table

JINJA_FILTERS_JS = (
    Path.home()
    / "WebstormProjects"
    / "fortisoar-widget-harness"
    / "widgets-src"
    / "widget-jinja-editor"
    / "widget"
    / "widgetAssets"
    / "js"
    / "constants"
    / "jinjaFilters.constants.js"
)
EXTRACTOR_MJS = Path(__file__).with_name("_jinja_extract.mjs")

# Discovery candidates for the render endpoint. The widget calls
# `dynamicValueService.evaluateJinja({template, values})`; the actual HTTP
# path isn't visible in widget code. Probe these in order; first one that
# returns the expected output for `{{ "x" | upper }}` wins.
RENDER_CANDIDATES = [
    # Confirmed via FSR app.unmin.js (dynamicValueService.evaluateJinja):
    #   `WORKFLOW + "api/jinja-editor/?format=json"`
    # WORKFLOW prefix is `/api/wf/`, so the path is `/api/wf/api/jinja-editor/`.
    "/api/wf/api/jinja-editor/?format=json",
    "/api/wf/api/jinja-editor/",
    # Fallbacks in case the route differs by version:
    "/api/wf/jinja-editor/",
    "/api/wf/jinja/render",
    "/api/3/jinja-editor",
]

PROBE_TEMPLATE = "{{ value | upper }}"
PROBE_INPUT = {"value": "x"}
PROBE_EXPECTED = "X"


# ---------------- helpers ----------------

def _scalarize(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


def _signature_for(name: str, meta: dict) -> str:
    params = meta.get("parameters") or []
    parts = []
    for p in params:
        if not isinstance(p, dict):
            continue
        s = p.get("name") or "?"
        if p.get("type"):
            s += f": {p['type']}"
        parts.append(s)
    args = ", ".join(parts)
    return f"value | {name}({args})" if args else f"value | {name}"


# ---------------- catalog filters (widget) ----------------

def _load_filters_from_widget(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    if not JINJA_FILTERS_JS.exists():
        return 0, [f"missing {JINJA_FILTERS_JS}"]
    if not shutil.which("node"):
        return 0, ["node not on PATH; cannot evaluate constants file"]
    try:
        out = subprocess.run(
            ["node", str(EXTRACTOR_MJS), str(JINJA_FILTERS_JS)],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        return 0, [f"node extractor failed: {e.stderr.strip()[:300]}"]
    try:
        data = json.loads(out)
    except Exception as e:  # noqa: BLE001
        return 0, [f"extractor JSON parse failed: {e!r}"]

    filters = data.get("filters") or {}
    n = 0
    for name, meta in filters.items():
        if not isinstance(meta, dict):
            continue
        rv = meta.get("returnValue") or {}
        params = meta.get("parameters") or []
        # The widget's "example" usually shows what the filter consumes; we
        # don't have a structured input_type from the constants file, so leave
        # input_type_hint NULL for now. PDF source rarely has it either.
        out_declared = rv.get("type") if isinstance(rv, dict) else rv
        conn.execute(
            """INSERT OR REPLACE INTO jinja_macros
               (name, signature, returns, description, example,
                parameters_json, input_type_hint, output_type_declared,
                output_type_observed, aliases_csv)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL)""",
            (
                name,
                _signature_for(name, meta),
                _scalarize(out_declared),
                _scalarize(meta.get("documentation")),
                _scalarize(meta.get("example")),
                json.dumps(params) if isinstance(params, list) else None,
                _scalarize(out_declared),
            ),
        )
        record_verification(
            conn, kind="jinja_filter", key=name,
            method="widget_constants", status="seen",
            notes=f"category={meta.get('category')}",
        )
        n += 1
    return n, []


# ---------------- catalog filters (playbook guide PDF) ----------------

# Lines in the comprehensive table look like:
#   "    abs                  Absolute value of a number    jinja2_docs"
# Filter name is the first token, possibly with parens: "attr(x)", "batch(n)",
# "combine(dict_x,\nrecursive=False)" (multiline). We capture name only and let
# the description carry the args info — ingesting precise param shapes from
# the PDF is more brittle than it's worth; the live render verifies behavior.
_PDF_ROW = __import__("re").compile(
    r"^\s{4,6}([a-zA-Z][a-zA-Z0-9_]*)(?:\([^)]*\))?\s{2,}"
    r"(.+?)\s{2,}(jinja2(?:_docs)?|ansible(?:_ipaddr|\.netcommon)?|FortiSOAR)\s*$"
)


def _load_filters_from_pdf(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    if not PLAYBOOK_GUIDE_PDF.exists():
        return 0, [f"missing {PLAYBOOK_GUIDE_PDF}"]
    if not shutil.which("pdftotext"):
        return 0, ["pdftotext not on PATH; install poppler"]
    p1, p2 = PLAYBOOK_GUIDE_FILTER_PAGES
    try:
        text = subprocess.run(
            ["pdftotext", "-layout", "-f", str(p1), "-l", str(p2),
             str(PLAYBOOK_GUIDE_PDF), "-"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        return 0, [f"pdftotext failed: {e.stderr.strip()[:200]}"]

    n = 0
    for line in text.splitlines():
        m = _PDF_ROW.match(line)
        if not m:
            continue
        name, desc, source = m.group(1), m.group(2).strip(), m.group(3)
        # Skip the table header itself.
        if name.lower() == "filter":
            continue
        # Honor existing rows: don't clobber a richer widget_constants entry
        # with a sparse PDF row — only INSERT if name is new.
        existing = conn.execute(
            "SELECT 1 FROM jinja_macros WHERE name = ?", (name,),
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO jinja_macros (name, signature, returns, description, example)
                   VALUES (?, NULL, NULL, ?, NULL)""",
                (name, desc),
            )
        record_verification(
            conn, kind="jinja_filter", key=name,
            method="playbook_guide_pdf", status="seen",
            notes=f"source={source}",
        )
        n += 1
    return n, []


# ---------------- live render discovery + per-filter verify ----------------

def _try_render(client, path: str, template: str, values: dict) -> tuple[bool, str, Any]:
    """Returns (ok, raw_output_string, full_response).
    Treats both `{result: "X"}` and a raw string `"X"` as success patterns.
    """
    try:
        r = client.post(path, data={"template": template, "values": values})
    except Exception as e:  # noqa: BLE001
        return False, repr(e)[:200], None
    if isinstance(r, str):
        return True, r, r
    if isinstance(r, dict):
        for k in ("result", "output", "rendered", "value"):
            if isinstance(r.get(k), str):
                return True, r[k], r
        return True, json.dumps(r)[:200], r
    return False, f"unexpected type {type(r).__name__}", r


def _discover_endpoint(conn: sqlite3.Connection, client) -> str | None:
    """Try render candidates with PROBE_TEMPLATE; return the working path."""
    for path in RENDER_CANDIDATES:
        ok, raw, _ = _try_render(client, path, PROBE_TEMPLATE, PROBE_INPUT)
        if ok and PROBE_EXPECTED in raw:
            # Found it. Catalog the endpoint and confirm tested_pass.
            conn.execute(
                """INSERT OR IGNORE INTO api_endpoints
                   (path_pattern, http_method, service, source, summary, response_kind)
                   VALUES (?, 'POST', 'wf', 'manual',
                           'Jinja template render — discovered via probe_jinja',
                           'json')""",
                (path,),
            )
            record_verification(
                conn, kind="api_endpoint",
                key=f"POST {path}",
                method="live_api_render", status="tested_pass",
                notes=f"upper('x')='{raw[:30]}'",
            )
            return path
        # 404/route-not-found is the normal case — don't log.
    return None


def _verify_filter_renders(
    conn: sqlite3.Connection, client, render_path: str,
) -> tuple[int, int]:
    """For each cataloged filter, render `{{ value | <filter> | type_debug }}`
    so we capture both correctness AND the actual Python output type. Output
    types matter when piping (a generator vs list breaks downstream filters);
    we store them in jinja_macros.output_type_observed.

    Filters that need specific input (e.g. dictsort needs a dict, batch needs
    a linecount arg) fail here — that's information too: tested_fail rows
    record the error so agents know the limitation.
    """
    passed = failed = 0
    rows = conn.execute("SELECT name FROM jinja_macros").fetchall()
    for (name,) in rows:
        if not name:
            continue
        # type_debug at the end captures the output type of `value | <filter>`.
        # If the filter chain errors, raw will contain the API error message.
        ok, raw, _ = _try_render(
            client, render_path,
            template=f"{{{{ value | {name} | type_debug }}}}",
            values={"value": "Hello"},
        )
        success = ok and not raw.strip().lower().startswith(("apierror", "error", "{"))
        if success:
            observed_type = raw.strip()
            conn.execute(
                "UPDATE jinja_macros SET output_type_observed = ? WHERE name = ?",
                (observed_type, name),
            )
            record_verification(
                conn, kind="jinja_filter", key=name,
                method="live_api_render", status="tested_pass",
                notes=f"output_type={observed_type}",
            )
            passed += 1
        else:
            record_verification(
                conn, kind="jinja_filter", key=name,
                method="live_api_render", status="tested_fail",
                notes=f"out={raw[:80]}",
            )
            failed += 1
    return passed, failed


# ---------------- shape inference (no new calls) ----------------

import re as _re

# `do_replace() missing 2 required positional arguments: 'old' and 'new'`
# `do_attr() missing 1 required positional argument: 'name'`
# `sync_do_groupby() missing 1 required positional argument: 'attribute'`
_MISSING_ARGS_RE = _re.compile(
    r"missing\s+(\d+)\s+required\s+positional\s+arguments?:\s*(.+)"
)


def _parse_required_args(note: str) -> list[str] | None:
    """Pull required-positional arg names out of a Python TypeError message."""
    if not note:
        return None
    m = _MISSING_ARGS_RE.search(note)
    if not m:
        return None
    arg_str = m.group(2)
    # arg list looks like: 'a', 'b' and 'c'   |   'old' and 'new'   |   'name'
    return _re.findall(r"'([^']+)'", arg_str)


def _infer_param_shapes(conn: sqlite3.Connection) -> tuple[int, int]:
    """Backfill jinja_macros.parameters_json from existing verification notes.

    Two techniques, both zero-cost (data we already collected):
      (1) tested_fail with `missing N required positional arguments: 'a', 'b'`
          → those exact arg names go into parameters_json with required=True.
      (3) tested_pass with no extra args needed → parameters_json stays
          structurally empty (all optional / no positional required).

    We only fill rows that came from PDF (no widget-supplied parameters_json),
    so the rich widget metadata is never overwritten.
    """
    updated_required = updated_empty = 0
    rows = conn.execute(
        "SELECT name FROM jinja_macros WHERE parameters_json IS NULL OR parameters_json = ''"
    ).fetchall()
    for (name,) in rows:
        verifs = conn.execute(
            "SELECT status, notes FROM verifications "
            "WHERE kind='jinja_filter' AND key=? AND method='live_api_render' "
            "ORDER BY ts DESC LIMIT 1",
            (name,),
        ).fetchone()
        if not verifs:
            continue
        status, note = verifs[0], verifs[1] or ""

        if status == "tested_fail":
            args = _parse_required_args(note)
            if not args:
                continue
            params = [
                {"name": a, "kind": "POSITIONAL", "required": True, "source": "error_message"}
                for a in args
            ]
            conn.execute(
                "UPDATE jinja_macros SET parameters_json = ? WHERE name = ?",
                (json.dumps(params), name),
            )
            updated_required += 1
        elif status == "tested_pass":
            # No required positional args — leave detail-of-optional-args TBD
            # (would need backend introspection to know names + defaults).
            conn.execute(
                "UPDATE jinja_macros SET parameters_json = ? WHERE name = ?",
                (json.dumps([]), name),
            )
            updated_empty += 1
    return updated_required, updated_empty


# ---------------- entry ----------------

def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    sources = [JINJA_FILTERS_JS]

    with probe_session(PROBE_NAME, sources) as conn:
        wipe_probe_tables(conn, PROBE_NAME)
        conn.execute(
            "DELETE FROM verifications WHERE kind = 'jinja_filter'"
        )

        n_filters, errs = _load_filters_from_widget(conn)
        n_pdf, pdf_errs = _load_filters_from_pdf(conn)
        errs.extend(pdf_errs)
        passed = failed = 0
        endpoint: str | None = None
        if cfg.is_live() and n_filters:
            client = _env.get_client()
            endpoint = _discover_endpoint(conn, client)
            if endpoint:
                passed, failed = _verify_filter_renders(conn, client, endpoint)
            else:
                errs.append("render endpoint not discovered; tried "
                            f"{len(RENDER_CANDIDATES)} candidates")
        # Backfill parameter shapes from error messages — zero extra calls.
        inferred_required, inferred_empty = _infer_param_shapes(conn)

        notes = json.dumps({
            "widget_filters": n_filters,
            "pdf_filters": n_pdf,
            "render_endpoint": endpoint,
            "passed": passed, "failed": failed,
            "errors": errs[:10],
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] widget={n_filters}  pdf={n_pdf}  "
              f"endpoint={endpoint or '(not found)'}  "
              f"passed={passed}  failed={failed}  "
              f"shapes_inferred={inferred_required}+{inferred_empty}")
        for e in errs[:5]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
