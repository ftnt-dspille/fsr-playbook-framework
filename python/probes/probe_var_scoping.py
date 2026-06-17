"""Phase 1a probe — variable scoping / lifetime (live).

STATIC_TYPE_FLOW_PLAN.md Phase 1a: the branch-local var-typer (Phase 2)
needs the engine's real scoping rules, not assumptions. This drives small
playbooks on the live box and reads back (via the force-fail channel — see
probe_set_variable_coercion) what a downstream step actually sees:

  A. predecessor visibility + sibling-arm isolation — a var set BEFORE a
     decision is visible on the taken arm; a var set ONLY on the sibling
     (untaken) arm is NOT.
  B. for_each `vars.item` lifetime — is the loop binding still readable in a
     step AFTER the for_each step, or only inside it?

Each probe ends in a code_snippet that raises, so FSR persists the prior
step results regardless of the instance's debug-logging setting.

Run:  PYTHONPATH=python:. .venv/bin/python -m probes.probe_var_scoping
"""
from __future__ import annotations

import json
import os
import time

from ._env import get_config  # noqa: F401  (kept for parity / future use)
from .common import REPO_ROOT
from .probe_set_variable_coercion import _Live, _ENGINE_KEYS, _TERMINAL

DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"
OUT_PATH = REPO_ROOT / "store" / "probe_results" / "var_scoping.json"


def _run_and_read(live: _Live, coll_name: str, yaml_src: str,
                  read_step: str) -> dict:
    """Push + trigger a collection, poll to terminal, return the named
    step's persisted `result` (user vars only). Cleans up the collection."""
    from fsr_playbooks.compiler import compile_yaml
    cres = compile_yaml(yaml_src, DB_PATH)
    if not cres.ok:
        errs = [getattr(e, "to_dict", lambda: e)() for e in (cres.errors or [])]
        return {"__error__": f"compile failed: {errs}"}
    coll = (cres.fsr_json.get("data") or [cres.fsr_json])[0]
    _, push = live.req("/api/3/workflow_collections", "POST", json=coll)
    wfs = (push or {}).get("workflows") or []
    if not wfs:
        return {"__error__": f"push returned no workflows: {str(push)[:200]}"}
    coll_uuid = (push or {}).get("uuid")
    wf_uuid = wfs[0].get("uuid")
    _, trig = live.req(f"/api/triggers/1/notrigger/{wf_uuid}", "POST",
                       json={"input": {}, "request": {"data": {}},
                             "useMockOutput": False, "globalMock": False})
    task_id = (trig or {}).get("task_id")
    result, status, run_pk = {}, "TIMEOUT", None
    deadline = time.time() + 120
    while time.time() < deadline:
        _, listing = live.req(
            "/api/wf/api/workflows/?format=json&limit=1&ordering=-modified"
            f"&task_id={task_id}&parent_wf__isnull=True", "GET")
        members = (listing or {}).get("hydra:member") or []
        if members:
            run = members[0]
            run_pk = (run.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
            status = run.get("status")
            if status in _TERMINAL:
                _, d = live.req(
                    f"/api/wf/api/workflows/{run_pk}/"
                    "?format=json&step_detail=true", "GET")
                step = next((s for s in (d or {}).get("steps") or []
                             if s.get("name") == read_step), {})
                result = step.get("result") or {}
                break
        time.sleep(2)
    if coll_uuid and os.environ.get("PROBE_NO_CLEANUP") != "1":
        live.req(f"/api/3/workflow_collections/{coll_uuid}?hardDelete=true",
                 "DELETE")
    user_vars = {k: v for k, v in result.items() if k not in _ENGINE_KEYS}
    return {"status": status, "run_pk": run_pk, "vars": user_vars}


# --- Probe A: predecessor visibility + sibling-arm isolation ---------------
# Decision condition is always-true, so the run takes the "Read On True" arm.
# "a" is set BEFORE the decision (should be visible); "only_false" is set only
# on the untaken Else arm (should be UNSET on the taken arm).
_PROBE_A = """
collection: __scope_a
visible: true
playbooks:
  - name: Scope A
    is_active: true
    steps:
      - name: start
        type: start
        next: Set Pre
      - name: Set Pre
        type: set_variable
        next: Decide
        vars:
          a: "alpha"
      - name: Decide
        type: decision
        conditions:
          - display: "yes"
            when: "{{ 1 == 1 }}"
            next: Read On True
          - display: Else
            default: true
            next: Set Only False
      - name: Read On True
        type: set_variable
        next: Boom
        vars:
          saw_a: "{{ vars.a | default('UNSET') }}"
          saw_only_false: "{{ vars.only_false | default('UNSET') }}"
      - name: Set Only False
        type: set_variable
        vars:
          only_false: "set_on_false_arm"
      - name: Boom
        type: code_snippet
        arguments:
          code: |
            raise Exception('force-fail to persist results')
"""


# --- Probe B: for_each vars.item lifetime ----------------------------------
# Loop a no-op code_snippet over a 2-element list, then in a LATER step read
# vars.item. If item is loop-scoped it should be UNSET after the loop; if it
# leaks it would hold the last element.
_PROBE_B = """
collection: __scope_b
visible: true
playbooks:
  - name: Scope B
    is_active: true
    steps:
      - name: start
        type: start
        next: Build List
      - name: Build List
        type: set_variable
        next: Loop
        vars:
          mylist:
            - "x1"
            - "x2"
      - name: Loop
        type: code_snippet
        next: After Loop
        for_each:
          item: "{{ vars.steps.Build_List.mylist }}"
          parallel: false
          condition: ""
        arguments:
          code: |
            print("iter")
      - name: After Loop
        type: set_variable
        next: Boom
        vars:
          item_after: "{{ vars.item | default('UNSET') }}"
      - name: Boom
        type: code_snippet
        arguments:
          code: |
            raise Exception('force-fail to persist results')
"""


def main() -> None:
    live = _Live()
    epoch = int(os.environ.get("PROBE_EPOCH") or time.time())

    findings = {}
    print("[scope A] predecessor visibility + sibling-arm isolation")
    a = _run_and_read(live, f"__scope_a_{epoch}",
                      _PROBE_A.replace("__scope_a", f"__scope_a_{epoch}"),
                      "Read On True")
    print(f"  {a}")
    findings["predecessor_and_sibling"] = a

    print("[scope B] for_each vars.item lifetime after the loop")
    b = _run_and_read(live, f"__scope_b_{epoch}",
                      _PROBE_B.replace("__scope_b", f"__scope_b_{epoch}"),
                      "After Loop")
    print(f"  {b}")
    findings["for_each_item_lifetime"] = b

    # Interpretation
    av = (a.get("vars") or {})
    print("\n=== interpretation ===")
    print(f"  predecessor var visible on taken arm : "
          f"saw_a={av.get('saw_a')!r} (expect 'alpha')")
    print(f"  sibling-arm var isolated            : "
          f"saw_only_false={av.get('saw_only_false')!r} (expect 'UNSET')")
    bv = (b.get("vars") or {})
    print(f"  for_each item after loop            : "
          f"item_after={bv.get('item_after')!r}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "probe": "var_scoping", "epoch": epoch, "base": live.base,
        "findings": findings,
    }, indent=2, default=str))
    print(f"\nsaved {OUT_PATH}")


if __name__ == "__main__":
    main()
