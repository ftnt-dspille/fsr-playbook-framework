"""Phase 4b probe — connector-param ingestion coercion (live).

STATIC_TYPE_FLOW_PLAN.md Open Q #2 / Phase 4b: when a value flows into a
connector op param, what python type does the connector actually receive,
and does the param's *widget type* (text vs integer vs json …) change that?

Mechanism: the fsr-playbook-builder connector ships a `visible:false`
diagnostic op `echo_param_types` that returns `type(value).__name__` for each
received param, with params declared at six widget types (text, textarea,
integer, decimal, checkbox, json). We call it via the SAME integration
execute path a playbook connector step uses (`/api/integration/execute/`),
sending an identical value into all six params at once, and read back the
received python type per widget.

Run:  PYTHONPATH=python .venv/bin/python -m probes.probe_param_ingestion
Env:  reuses FSR_BASE_URL / auth from .env (same as the other probes).
Output: prints the matrix + writes store/probe_results/param_ingestion_coercion.json.

Requires the connector deployed with `echo_param_types` (>= 0.3.122).
"""
from __future__ import annotations

import json
import sys

from ._env import get_config
from .common import REPO_ROOT

OUT_PATH = REPO_ROOT / "data" / "probe_results" / "param_ingestion_coercion.json"

WIDGETS = ["p_text", "p_textarea", "p_integer", "p_decimal",
           "p_checkbox", "p_json"]

# (label, value) — the same value is sent into every widget-typed param so we
# can compare what each widget receives. Mirrors the Phase 1b set_variable
# battery so the two matrices can be compared directly.
BATTERY: list[tuple[str, object]] = [
    ("str_123", "123"), ("int_123", 123),
    ("str_1p5", "1.5"), ("float_1p5", 1.5),
    ("str_true", "true"), ("bool_true", True),
    ("str_false", "false"), ("str_TRUE", "TRUE"),
    ("str_list", '["a","b"]'), ("nat_list", ["a", "b"]),
    ("str_obj", '{"k":1}'), ("nat_obj", {"k": 1}),
    ("str_null", "null"), ("str_hello", "hello"),
    ("str_007", "007"), ("str_date", "2026-06-06"),
]


def _live_execute():
    cfg = get_config()
    if not cfg.is_live():
        sys.exit("env not live: set FSR_BASE_URL + auth in .env")
    sys.path.insert(0, str(REPO_ROOT.parent / "ConnectorsV2"
                           / "fsr-playbook-builder" / "scripts"))
    from fsr_live import LiveFSR  # noqa: PLC0415
    fsr = LiveFSR.from_env()

    def run(params: dict) -> dict:
        r = fsr.execute("echo_param_types", params, timeout=60)
        return r.data if isinstance(r.data, dict) else {}

    return run


def main() -> None:
    run = _live_execute()
    matrix: dict[str, dict[str, str]] = {}
    for label, val in BATTERY:
        rec = (run({w: val for w in WIDGETS}) or {}).get("received") or {}
        matrix[label] = {w: rec.get(w, {}).get("py_type") for w in WIDGETS}

    hdr = "value".ljust(11) + "".join(
        w.replace("p_", "").ljust(10) for w in WIDGETS)
    print(hdr)
    print("-" * len(hdr))
    for label, _ in BATTERY:
        print(label.ljust(11) + "".join(
            str(matrix[label][w]).ljust(10) for w in WIDGETS))

    # widget-independence check: every widget received the same type per value?
    uniform = all(len(set(row.values())) == 1 for row in matrix.values())
    print(f"\nwidget-type independent (all columns equal per row): {uniform}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(
        {"widgets": WIDGETS, "matrix": matrix,
         "widget_type_independent": uniform}, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
