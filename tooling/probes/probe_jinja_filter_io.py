"""probe_jinja_filter_io -- prove what every Jinja filter accepts and returns, live.

    make jinja-probe INSTANCE=<pyfsr instance alias>
    FSR_ENV_FILE=<env> PYTHONPATH=. .venv/bin/python -m tooling.probes.probe_jinja_filter_io

For every filter in ``jinja_macros`` (populated from the box's own registry by
``make jinja-export`` + ``probe_jinja_backend``) this renders real templates on
a FortiSOAR through ``POST /api/wf/api/jinja-editor/`` -- the same engine a
running playbook uses -- and stores one ``jinja_filter_probes`` row per case:
the exact template, the input, whether it rendered, the Python output type
(``type_debug``), a preview of the value, or the error.

Cases:
  * input matrix -- str, int, float, bool, list, dict, None piped into the
    filter with no arguments, for every filter whose extra parameters are all
    optional. A failure is evidence too: it is how "accepts list, not str" is
    proven rather than guessed.
  * curated -- ``jinja_filter_cases.yaml``: required-argument filters and
    behaviour worth pinning.

The rows are the evidence behind docs/JINJA_FILTERS.md and the baseline that
``make jinja-verify`` replays against a box.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .common import DB_PATH, open_db

CASES_FILE = Path(__file__).with_name("jinja_filter_cases.yaml")
INPUT_MATRIX: dict[str, Any] = {
    "str": "Hello World",
    "int": 3,
    "float": 2.5,
    "bool": True,
    "list": [3, 1, 2],
    "dict": {"b": 2, "a": 1},
    "none": None,
}
# Leading parameters FortiSOAR / Jinja inject; never supplied by the template.
_INJECTED = {"context", "eval_ctx", "environment", "env", "ctx"}
_INJECTED_ANNOTATIONS = ("EvalContext", "Context", "Environment")
# Filters that only make sense as their own probe or have side effects.
_NEVER_AUTO = {"type_debug", "mandatory", "comment"}


def _pytype(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def extra_params(parameters_json: str | None) -> list[dict] | None:
    """Parameters after the injected context args and the piped value."""
    if not parameters_json:
        return None
    params = json.loads(parameters_json)
    i = 0
    while i < len(params) and (
        params[i].get("name") in _INJECTED
        or any(a in str(params[i].get("annotation") or "") for a in _INJECTED_ANNOTATIONS)
    ):
        i += 1
    return params[i + 1:]  # drop the piped value


def needs_args(parameters_json: str | None) -> bool:
    extra = extra_params(parameters_json)
    if extra is None:
        return False
    return any(
        p.get("default") is None and p.get("kind") in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")
        for p in extra
    )


def template_for(name: str, args: str) -> str:
    call = f"value | {name}({args})" if args else f"value | {name}"
    # Render the type and a bounded preview in one round trip.
    return ("{{ {'t': (" + call + ") | type_debug, "
            "'v': ((" + call + ") | string)[:200]} | to_json }}")


def cases_for(name: str, parameters_json: str | None, curated: dict) -> list[dict]:
    out: list[dict] = []
    if name not in _NEVER_AUTO and not needs_args(parameters_json):
        for label, value in INPUT_MATRIX.items():
            out.append({"case_id": f"input:{label}", "input": value, "args": ""})
    for i, c in enumerate(curated.get(name) or [], 1):
        out.append({"case_id": f"curated:{i}", "input": c.get("input"), "args": c.get("args") or "",
                    "ctx": c.get("ctx")})
    return out


_ADDR = re.compile(r" at 0x[0-9a-f]+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _stable(preview: str) -> str:
    """Drop what changes per run or per box: object addresses, record UUIDs."""
    return _UUID.sub("<uuid>", _ADDR.sub("", preview))


def _parse(raw: str) -> Any:
    """The editor hands back a native value, which pyfsr stringifies with Python
    quoting; JSON-shaped output still parses as JSON."""
    for load in (json.loads, ast.literal_eval):
        try:
            return load(raw)
        except (ValueError, SyntaxError):
            continue
    return raw


def render_case(client, name: str, case: dict) -> dict:
    tpl = template_for(name, case["args"])
    values = {"value": case["input"]}
    if case.get("ctx") is not None:
        values["ctx"] = case["ctx"]
    row = {"filter_name": name, "case_id": case["case_id"], "template": tpl,
           "input_json": json.dumps(case["input"]), "input_type": _pytype(case["input"]),
           "ok": 0, "output_type": None, "output_preview": None, "error": None}
    try:
        raw = client.playbooks.render_jinja(tpl, values)
        parsed = _parse(raw)
        if isinstance(parsed, dict) and set(parsed) >= {"t", "v"}:
            row.update(ok=1, output_type=parsed["t"], output_preview=_stable(str(parsed["v"]))[:200])
        else:
            row["error"] = f"unexpected render result: {raw[:300]}"
    except Exception as e:  # noqa: BLE001 -- the error IS the evidence
        row["error"] = f"{type(e).__name__}: {e}"[:300]
    return row


def probe(client, conn: sqlite3.Connection, fsr_build: str, only: set[str] | None = None,
          workers: int = 2) -> dict[str, int]:
    curated = yaml.safe_load(CASES_FILE.read_text()) or {}
    filters = conn.execute("SELECT name, parameters_json FROM jinja_macros ORDER BY name").fetchall()
    jobs = [(name, c) for name, pj in filters if not only or name in only
            for c in cases_for(name, pj, curated)]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda j: render_case(client, *j), jobs))
    names = {n for n, _ in jobs}
    conn.executemany("DELETE FROM jinja_filter_probes WHERE filter_name = ?", [(n,) for n in names])
    conn.executemany(
        "INSERT OR REPLACE INTO jinja_filter_probes (filter_name, case_id, template, input_json, "
        "input_type, ok, output_type, output_preview, error, fsr_build, probed_at) "
        "VALUES (:filter_name, :case_id, :template, :input_json, :input_type, :ok, :output_type, "
        ":output_preview, :error, :fsr_build, :probed_at)",
        [dict(r, fsr_build=fsr_build, probed_at=now) for r in rows],
    )
    conn.commit()
    return {"filters": len(names), "cases": len(rows), "ok": sum(r["ok"] for r in rows),
            "untested": len([n for n, pj in filters if not cases_for(n, pj, curated)])}


def main(argv: list[str] | None = None) -> int:
    import warnings

    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", required=True, help="pyfsr instance alias (API login + SSH for the build stamp)")
    ap.add_argument("--only", help="comma-separated filter names")
    ap.add_argument("--workers", type=int, default=2,
                    help="parallel renders (default 2: 8 exhausted cyops-auth's DB pool on 8.0.0)")
    args = ap.parse_args(argv)
    from pyfsr.instances import InstanceRegistry

    from tooling.jinja_export import fsr_build

    reg = InstanceRegistry.load()
    client = reg.client(args.instance)
    try:
        build = fsr_build(reg.transport(args.instance))
    except Exception:  # noqa: BLE001 -- no SSH profile: fall back to the export's stamp
        meta = json.loads((DB_PATH.parent / "incoming" / "filters.json").read_text()).get("_meta", {})
        build = meta.get("fsr_build", "unknown")
    conn = open_db()
    stats = probe(client, conn, build, set(args.only.split(",")) if args.only else None, args.workers)
    print(f"[probe_jinja_filter_io] {build}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
