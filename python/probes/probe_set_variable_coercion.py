"""Phase 1b probe — set_variable type-creation / auto-coercion matrix (live).

STATIC_TYPE_FLOW_PLAN.md Phase 1: the static var-typer must reproduce the
engine's *actual* set_variable coercion rule, not assume it. This probe
drives a throwaway playbook that `set_variable`s a battery of literal forms
(quoted strings, bare YAML scalars, Jinja expressions) on the live box, then
reads the finished run's `env` dict — which holds each var's actual
post-coercion value. The JSON type of each env value (number / string /
bool / array / object / null) is the evidence: it shows whether
set_variable ran `json.loads` on the input and what survived.

Run:  PYTHONPATH=python .venv/bin/python -m probes.probe_set_variable_coercion
Env:  reuses FSR_BASE_URL / FSR_PORT / FSR_USERNAME+PASSWORD (or FSR_API_TOKEN)
      from .env (same as the other probes).

Output: prints the matrix and writes store/probe_results/set_variable_coercion.json.
Cleans up the throwaway collection (hardDelete) unless PROBE_NO_CLEANUP=1.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from ._env import get_config
from .common import REPO_ROOT

DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"
OUT_PATH = REPO_ROOT / "store" / "probe_results" / "set_variable_coercion.json"


# --------------------------------------------------------------------------
# The literal battery. Each entry is (var_name, yaml_value_literal, note).
# yaml_value_literal is inserted verbatim into the YAML `vars:` mapping, so
# quoting matters: `"123"` is a string input, `123` is a YAML int, etc.
# --------------------------------------------------------------------------
BATTERY: list[tuple[str, str, str]] = [
    # --- quoted strings: tests engine json.loads coercion of text input ---
    ("s_false_cap", '"False"', 'string "False" (capitalized)'),
    ("s_true_cap", '"True"', 'string "True" (capitalized)'),
    ("s_false_lc", '"false"', 'string "false" (lowercase)'),
    ("s_true_lc", '"true"', 'string "true" (lowercase)'),
    ("s_int", '"123"', 'string "123"'),
    ("s_zero", '"0"', 'string "0"'),
    ("s_neg", '"-7"', 'string "-7"'),
    ("s_leadzero", '"007"', 'string "007" (leading zero)'),
    ("s_float", '"1.5"', 'string "1.5"'),
    ("s_hex", '"0x1f"', 'string "0x1f"'),
    ("s_list", '"[\\"a\\", \\"b\\"]"', 'string JSON array'),
    ("s_obj", '"{\\"k\\": 1}"', 'string JSON object'),
    ("s_null", '"null"', 'string "null"'),
    ("s_none", '"None"', 'string "None" (python repr)'),
    ("s_empty", '""', 'empty string'),
    ("s_date", '"2026-06-06"', 'string ISO date'),
    ("s_iso", '"2026-06-06T12:00:00Z"', 'string ISO timestamp'),
    ("s_word", '"hello"', 'plain word (json.loads should fail)'),
    # --- bare YAML scalars: tests whether native JSON types survive ---
    ("y_bool", "false", "bare YAML bool false"),
    ("y_int", "42", "bare YAML int"),
    ("y_float", "3.14", "bare YAML float"),
    # --- Jinja expressions: tests render-then-coerce interaction ---
    ("j_false", '"{{ false }}"', "Jinja {{ false }}"),
    ("j_int", '"{{ 1 + 2 }}"', "Jinja arithmetic"),
    ("j_list", '"{{ [1, 2, 3] }}"', "Jinja list literal"),
    ("j_str_int", '"{{ \'123\' }}"', "Jinja string literal '123'"),
    # --- rule-refinement edge cases ---
    ("s_TRUE_uc", '"TRUE"', 'string "TRUE" (all caps)'),
    ("s_yes", '"yes"', 'string "yes" (YAML bool?)'),
    ("s_sci", '"1e3"', 'string "1e3" (scientific)'),
    ("s_float0", '"1.0"', 'string "1.0"'),
    ("s_ws_int", '" 123 "', 'string " 123 " (whitespace-padded)'),
    ("s_comma_num", '"1,000"', 'string "1,000" (thousands sep)'),
    ("s_bad_json", '"[1, 2"', 'string "[1, 2" (malformed JSON)'),
    ("s_tilde", '"~"', 'string "~" (YAML null token)'),
]


def _build_yaml(coll_name: str) -> str:
    # FSR only persists step results when a run FAILS (success-path step
    # results + env are dropped server-side). So the playbook deliberately
    # raises in a trailing code_snippet AFTER the set_variable; the failed
    # run then exposes the Set Literals step's coerced output. (Same trick
    # the connector uses to read agent-op results — see auto-memory
    # fsr_agent_proxied_execute_async / the B3 force-fail saga.)
    lines = [
        f"collection: {coll_name}",
        "description: Throwaway set_variable coercion probe (safe to purge).",
        "visible: true",
        "",
        "playbooks:",
        "  - name: Coercion Probe",
        "    is_active: true",
        "    steps:",
        "      - name: start",
        "        type: start",
        "        next: Set Literals",
        "",
        "      - name: Set Literals",
        "        type: set_variable",
        "        next: Boom",
        "        vars:",
    ]
    for name, literal, _note in BATTERY:
        lines.append(f"          {name}: {literal}")
    lines += [
        "",
        "      - name: Boom",
        "        type: code_snippet",
        "        arguments:",
        "          code: |",
        "            raise Exception('force-fail to persist set_variable results')",
    ]
    return "\n".join(lines) + "\n"


# Engine-injected keys that show up in the set_variable step result
# alongside the user vars — excluded from the matrix.
_ENGINE_KEYS = {"debug", "input", "request", "task_id", "result",
                "resources", "currentUser", "auth_info", "globalMock",
                "useMockOutput", "mockPlaybookId", "last_run_at"}


# --------------------------------------------------------------------------
# Minimal live client (auth + req), modeled on scripts/probe_fsr.py:FSR.
# --------------------------------------------------------------------------
class _Live:
    def __init__(self) -> None:
        cfg = get_config()
        if not cfg.is_live():
            sys.exit("env not live: set FSR_BASE_URL + auth in .env")
        base = cfg.base_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "https://" + base
        if cfg.port and not re.search(r":\d+$", base.split("//", 1)[-1]):
            base = f"{base}:{cfg.port}"
        self.base = base
        self.verify = cfg.verify_ssl
        if not self.verify:
            import urllib3
            urllib3.disable_warnings()
        self.s = requests.Session()
        self.s.headers["Authorization"] = self._auth(cfg)
        self.s.headers["Content-Type"] = "application/json"

    def _auth(self, cfg) -> str:
        if cfg.api_key:
            scheme = os.environ.get("FSR_AUTH_SCHEME", "API-KEY")
            # API keys are sent as-is by pyfsr; try bearer-less first.
            return f"{cfg.api_key}"
        r = requests.post(f"{self.base}/auth/authenticate",
                          json={"credentials": {"loginid": cfg.username,
                                                "password": cfg.password}},
                          verify=self.verify, timeout=30)
        if not r.ok:
            sys.exit(f"auth failed {r.status_code}: {r.text[:300]}")
        tok = r.json().get("token")
        if not tok:
            sys.exit(f"auth ok but no token: {r.json()!r}")
        return f"Bearer {tok}"

    def req(self, path: str, method: str = "GET", **kw):
        url = path if path.startswith("http") else f"{self.base}{path}"
        r = self.s.request(method, url, verify=self.verify, timeout=60, **kw)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"__nonjson__": r.text[:2000]}


_TERMINAL = {"finished", "failed", "terminated", "finished_with_error",
             "rejected"}


def _poll_result(live: _Live, task_id, timeout_s: int = 120):
    """Poll until the run reaches a terminal status, then return
    (run_pk, status, set_variable_step_result). The coerced vars live in
    the Set Literals step's `result` on the FAILED run."""
    deadline = time.time() + timeout_s
    run_pk = None
    while time.time() < deadline:
        _, listing = live.req(
            "/api/wf/api/workflows/?format=json&limit=1&ordering=-modified"
            f"&task_id={task_id}&parent_wf__isnull=True", "GET")
        members = (listing or {}).get("hydra:member") or []
        if members:
            run = members[0]
            run_pk = (run.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
            if run.get("status") in _TERMINAL:
                _, d = live.req(
                    f"/api/wf/api/workflows/{run_pk}/"
                    "?format=json&step_detail=true", "GET")
                sl = next((s for s in (d or {}).get("steps") or []
                           if s.get("name") == "Set Literals"), {})
                return run_pk, run.get("status"), sl.get("result") or {}
        time.sleep(2)
    return run_pk, "TIMEOUT", {}


def _json_type(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def main() -> None:
    from fsr_core.compiler import compile_yaml

    epoch = int(os.environ.get("PROBE_EPOCH") or time.time())
    coll_name = f"__svcoerce_{epoch}"
    src = _build_yaml(coll_name)

    cres = compile_yaml(src, DB_PATH)
    if not cres.ok:
        errs = [getattr(e, "to_dict", lambda: e)() for e in (cres.errors or [])]
        sys.exit(f"probe playbook failed to compile: {errs}")
    wj = cres.fsr_json
    collection = (wj.get("data") or [wj])[0]

    live = _Live()
    print(f"[set_variable coercion] pushing collection {coll_name}")
    c, push = live.req("/api/3/workflow_collections", "POST", json=collection)
    wfs = (push or {}).get("workflows") or []
    if not wfs:
        sys.exit(f"push returned no workflows ({c}): {str(push)[:300]}")
    coll_uuid = (push or {}).get("uuid")
    wf_uuid = wfs[0].get("uuid")

    c, trig = live.req(f"/api/triggers/1/notrigger/{wf_uuid}", "POST",
                       json={"input": {}, "request": {"data": {}},
                             "useMockOutput": False, "globalMock": False})
    task_id = (trig or {}).get("task_id")
    print(f"  triggered wf={wf_uuid} task_id={task_id}")
    run_pk, status, coerced = _poll_result(live, task_id)
    user_vars = {k: v for k, v in coerced.items() if k not in _ENGINE_KEYS}
    print(f"  run {run_pk} -> {status}; {len(user_vars)} user vars captured")

    rows = []
    for name, literal, note in BATTERY:
        present = name in user_vars
        val = user_vars.get(name)
        rows.append({
            "var": name, "input_yaml": literal, "note": note,
            "present": present,
            "runtime_type": _json_type(val) if present else "ABSENT",
            "runtime_value": val,
        })

    # Pretty print
    print(f"\n{'var':<14}{'input':<26}{'-> runtime_type':<18}value")
    print("-" * 90)
    for r in rows:
        print(f"{r['var']:<14}{r['input_yaml']:<26}"
              f"{r['runtime_type']:<18}{r['runtime_value']!r}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "probe": "set_variable_coercion",
        "epoch": epoch,
        "base": live.base,
        "run_pk": run_pk, "status": status,
        "rows": rows,
        "raw_step_result": coerced,
    }, indent=2, default=str))
    print(f"\nsaved {OUT_PATH}")

    if os.environ.get("PROBE_NO_CLEANUP") != "1" and coll_uuid:
        cc, _ = live.req(
            f"/api/3/workflow_collections/{coll_uuid}?hardDelete=true", "DELETE")
        print(f"  cleanup collection {coll_uuid} -> {cc}")


if __name__ == "__main__":
    main()
