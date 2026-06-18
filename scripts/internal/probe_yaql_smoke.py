"""Read-only smoke test for YAQL filter availability via the jinja-editor render endpoint.

Plan:
  POST /api/wf/api/jinja-editor/  template={{ value | yaql("$") }}  values={value: [...]}
Confirms whether `yaql` is exposed as a Jinja filter and what the call shape looks like.
Does NOT modify FSR state.
"""
from __future__ import annotations
import json
import sys
import urllib3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tooling"))

urllib3.disable_warnings()
from probes._env import get_client  # noqa: E402

YAQL_PROBES = [
    # (label, template, values)
    ("identity", "{{ value | yaql('$') }}", {"value": [1, 2, 3]}),
    ("where", "{{ value | yaql('$.where($ > 1)') }}", {"value": [1, 2, 3]}),
    ("select", "{{ value | yaql('$.select($ * 2)') }}", {"value": [1, 2, 3]}),
    ("len", "{{ value | yaql('$.len()') }}", {"value": [1, 2, 3]}),
    ("dict-pluck", "{{ value | yaql('$.select($.name)') }}",
     {"value": [{"name": "a"}, {"name": "b"}]}),
    ("type_debug after yaql", "{{ value | yaql('$.where($ > 1)') | type_debug }}",
     {"value": [1, 2, 3]}),
]

RENDER_PATH = "/api/wf/api/jinja-editor/?format=json"


def main() -> int:
    c = get_client()
    if c is None:
        print("no live env", file=sys.stderr)
        return 2
    print(f"YAQL smoke against {c.base_url}{RENDER_PATH}\n")
    print(f"{'label':<24} {'ok':<4} output")
    print("-" * 80)
    for label, tmpl, vals in YAQL_PROBES:
        try:
            r = c.post(RENDER_PATH, data={"template": tmpl, "values": vals})
            if isinstance(r, dict):
                out = r.get("result", r)
            else:
                out = r
            out_s = json.dumps(out)[:120] if not isinstance(out, str) else out[:120]
            print(f"{label:<24} OK   {out_s}")
        except Exception as e:  # noqa: BLE001
            print(f"{label:<24} FAIL {repr(e)[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
