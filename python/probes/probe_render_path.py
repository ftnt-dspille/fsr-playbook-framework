"""Render-path probe — capture how FSR actually executes for_each,
break_loop, and step-level conditions, and save the resulting run
envs as fixtures so the simulator can be tested against real
behavior without a live FSR.

Each scenario:
  1. Synthesises a tiny playbook that exercises one construct.
  2. Pushes it (replace mode), captures the workflow UUID.
  3. Triggers it via /api/triggers/1/notrigger/<uuid>.
  4. Polls the run to terminal status.
  5. Pulls the full run env via `?step_detail=true`.
  6. Writes a fixture JSON under
     ``python/tests/fixtures/render_path_probe/<scenario>.json`` with
     the playbook YAML, the run status, the env, and per-step results.
  7. Best-effort cleans up the probe collection.

Usage:
    python -m probes.probe_render_path
    python -m probes.probe_render_path --scenario for_each_break_loop
    python -m probes.probe_render_path --keep    # leave on FSR for debug

Requires `.env` with FSR_BASE_URL + auth, same as the other probes.

The fixtures this writes are consumed by
``python/tests/test_render_path_fixtures.py``. Tests skip cleanly when
the fixtures are absent — re-run this probe whenever a new construct
needs covering or when FSR semantics may have shifted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

from probes import _env  # noqa: E402

FIXTURE_DIR = REPO / "python" / "tests" / "fixtures" / "render_path_probe"
COLL_NAME = "FSRPB Render Path Probe"
TERMINAL = {"finished", "failed", "terminated", "skipped",
            "finished_with_error", "rejected"}


# ---------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    pb_name: str  # playbook to TRIGGER (parent for workflow_reference scenarios)
    description: str
    yaml: str  # full collection YAML (may contain multiple playbooks)


def _wrap(pb_name: str, description: str, steps_yaml: str) -> str:
    """Wrap a per-scenario steps body in the probe's collection +
    playbook envelope. We keep each scenario's playbook name unique
    so the resolver's deterministic uuid5 doesn't collide."""
    return textwrap.dedent(f"""\
        collection: "{COLL_NAME}"
        description: "render-path probe collection"
        playbooks:
          - name: "{pb_name}"
            description: "{description}"
            is_active: true
            steps:
        """) + textwrap.indent(steps_yaml, "      ")


def _wrap_ref(parent_name: str, child_name: str,
              parent_desc: str, parent_steps: str,
              child_steps: str,
              child_params: list[str] | None = None) -> str:
    """Wrap a workflow_reference scenario as a 2-playbook collection
    (child + parent). Child must come first so the parser's
    `target: <name>` lookup resolves at parse time."""
    header = (
        f'collection: "{COLL_NAME}"\n'
        f'description: "render-path probe collection"\n'
        f'playbooks:\n'
    )
    params_line = (f'    parameters: {list(child_params)}\n'
                   if child_params else '')
    child_block = (
        f'  - name: "{child_name}"\n'
        f'    description: "child for {parent_name}"\n'
        f'    is_active: true\n'
        + params_line
        + f'    steps:\n'
        + textwrap.indent(child_steps, "      ")
    )
    parent_block = (
        f'  - name: "{parent_name}"\n'
        f'    description: "{parent_desc}"\n'
        f'    is_active: true\n'
        f'    steps:\n'
        + textwrap.indent(parent_steps, "      ")
    )
    return header + child_block + parent_block


SCENARIOS: list[Scenario] = [
    # 1. for_each over a literal list, sequential. Captures whether
    #    vars.steps.<set_var_step> ends up holding the LAST iteration
    #    or all iterations or something else.
    Scenario(
        name="for_each_sequential_list",
        pb_name="rp_for_each_seq",
        description="for_each over [10,20,30], sequential, set_variable inside",
        yaml=_wrap(
            "rp_for_each_seq",
            "for_each sequential",
            textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: set_variable
                for_each:
                  item: "{{ [10, 20, 30] }}"
                  parallel: false
                vars:
                  current: "{{ vars.item }}"
                  doubled: "{{ vars.item * 2 }}"
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
                  loop_current: "{{ vars.steps.Loop.current }}"
            """),
        ),
    ),

    # 2. for_each parallel. Same body, parallel: true. Confirms whether
    #    parallel changes vars.steps.<step> shape.
    Scenario(
        name="for_each_parallel_list",
        pb_name="rp_for_each_par",
        description="for_each over [10,20,30], parallel, set_variable inside",
        yaml=_wrap(
            "rp_for_each_par",
            "for_each parallel",
            textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: set_variable
                for_each:
                  item: "{{ [10, 20, 30] }}"
                  parallel: true
                vars:
                  current: "{{ vars.item }}"
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
            """),
        ),
    ),

    # 3. for_each with break_loop. Iterates [1..5]; break when item==3.
    #    Captures how many iterations actually executed.
    Scenario(
        name="for_each_break_loop",
        pb_name="rp_for_each_brk",
        description="for_each with break_loop on item==3",
        yaml=_wrap(
            "rp_for_each_brk",
            "for_each break_loop",
            textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: set_variable
                for_each:
                  item: "{{ [1, 2, 3, 4, 5] }}"
                  parallel: false
                  break_loop: "{{ vars.item == 3 }}"
                vars:
                  current: "{{ vars.item }}"
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
                  loop_current: "{{ vars.steps.Loop.current }}"
            """),
        ),
    ),

    # 4. Empty for_each list. What does vars.steps.<step> look like?
    Scenario(
        name="for_each_empty_list",
        pb_name="rp_for_each_empty",
        description="for_each over an empty list",
        yaml=_wrap(
            "rp_for_each_empty",
            "for_each empty",
            textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: set_variable
                for_each:
                  item: "{{ [] }}"
                  parallel: false
                vars:
                  current: "{{ vars.item }}"
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
            """),
        ),
    ),

    # ---- WorkflowReference scenarios ---------------------------------

    # R1. Sync ref, basic. Child sets a var; parent reads it back via
    #     vars.steps.<ref_step>. Confirms the documented "child's
    #     set_variables propagate into parent" rule.
    Scenario(
        name="ref_sync_basic",
        pb_name="rp_ref_sync_parent",
        description="sync workflow_reference, child sets var, parent reads it",
        yaml=_wrap_ref(
            parent_name="rp_ref_sync_parent",
            child_name="rp_ref_sync_child",
            parent_desc="parent calls child sync, reads vars.steps.<ref>",
            parent_steps=textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Call"
              - name: "Call"
                type: workflow_reference
                arguments:
                  target: rp_ref_sync_child
                  apply_async: false
                  pass_parent_env: false
                  pass_input_record: false
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  child_product: "{{ vars.steps.Call.product }}"
                  child_seen:    "{{ vars.steps.Call }}"
            """),
            child_steps=textwrap.dedent("""\
              - name: "ChildStart"
                type: start
                next: "Compute"
              - name: "Compute"
                type: set_variable
                vars:
                  product: 42
                  child_marker: "ran"
            """),
        ),
    ),

    # R2. Sync ref WITH arguments. Parent passes a literal; child
    #     uses vars.input.params.<key> to compute.
    Scenario(
        name="ref_with_arguments",
        pb_name="rp_ref_args_parent",
        description="sync ref passing arguments to child",
        yaml=_wrap_ref(
            parent_name="rp_ref_args_parent",
            child_name="rp_ref_args_child",
            parent_desc="parent passes arguments.base=7",
            parent_steps=textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Call"
              - name: "Call"
                type: workflow_reference
                arguments:
                  target: rp_ref_args_child
                  arguments:
                    base: 7
                  apply_async: false
                  pass_parent_env: false
                  pass_input_record: false
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  product:  "{{ vars.steps.Call.product }}"
                  echoed:   "{{ vars.steps.Call.base_echoed }}"
            """),
            child_steps=textwrap.dedent("""\
              - name: "ChildStart"
                type: start
                next: "Compute"
              - name: "Compute"
                type: set_variable
                vars:
                  base_echoed: "{{ vars.input.params.base }}"
                  product:     "{{ (vars.input.params.base | int) * 10 }}"
            """),
            child_params=["base"],
        ),
    ),

    # R3. Sync ref with `pass_parent_env: true`. Child should see and
    #     potentially mutate parent vars. Captures whether the parent
    #     reflects the child's writes after return.
    Scenario(
        name="ref_pass_parent_env_true",
        pb_name="rp_ref_envT_parent",
        description="ref with pass_parent_env=true; check var inheritance",
        yaml=_wrap_ref(
            parent_name="rp_ref_envT_parent",
            child_name="rp_ref_envT_child",
            parent_desc="parent sets var, child reads + writes, parent reads back",
            parent_steps=textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "SetParentVar"
              - name: "SetParentVar"
                type: set_variable
                vars:
                  parent_marker: "from_parent"
                next: "Call"
              - name: "Call"
                type: workflow_reference
                arguments:
                  target: rp_ref_envT_child
                  apply_async: false
                  pass_parent_env: true
                  pass_input_record: false
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  saw_child_write: "{{ vars.child_marker | default('UNSET') }}"
                  child_step_view: "{{ vars.steps.Call }}"
            """),
            child_steps=textwrap.dedent("""\
              - name: "ChildStart"
                type: start
                next: "Echo"
              - name: "Echo"
                type: set_variable
                vars:
                  child_marker:    "from_child"
                  saw_parent:      "{{ vars.parent_marker | default('NONE') }}"
            """),
        ),
    ),

    # R4. Ref inside a for_each. 624 corpus rows do this — capture
    #     what vars.steps.<ref_loop> looks like after iteration.
    Scenario(
        name="ref_inside_for_each",
        pb_name="rp_ref_loop_parent",
        description="for_each over ref calls; capture per-iteration outputs",
        yaml=_wrap_ref(
            parent_name="rp_ref_loop_parent",
            child_name="rp_ref_loop_child",
            parent_desc="parent calls child once per item",
            parent_steps=textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: workflow_reference
                for_each:
                  item: "{{ [1, 2, 3] }}"
                  parallel: false
                arguments:
                  target: rp_ref_loop_child
                  arguments:
                    n: "{{ vars.item }}"
                  apply_async: false
                  pass_parent_env: false
                  pass_input_record: false
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
                  loop_count: "{{ vars.steps.Loop | length }}"
            """),
            child_steps=textwrap.dedent("""\
              - name: "ChildStart"
                type: start
                next: "Compute"
              - name: "Compute"
                type: set_variable
                vars:
                  squared: "{{ (vars.input.params.n | int) ** 2 }}"
            """),
            child_params=["n"],
        ),
    ),

    # 5. for_each.condition — per-iteration filter. Iterate
    #    [1,2,3,4,5] but only execute the body when item is even.
    #    Captures whether the result list contains all 5 entries
    #    (with skipped-iteration placeholders) or just the matching 2.
    Scenario(
        name="for_each_condition_filter",
        pb_name="rp_for_each_cond",
        description="for_each.condition filtering even items only",
        yaml=_wrap(
            "rp_for_each_cond",
            "for_each per-iteration condition",
            textwrap.dedent("""\
              - name: "Trigger"
                type: start
                next: "Loop"
              - name: "Loop"
                type: set_variable
                for_each:
                  item: "{{ [1, 2, 3, 4, 5] }}"
                  parallel: false
                  condition: "{{ vars.item % 2 == 0 }}"
                vars:
                  current: "{{ vars.item }}"
                next: "Capture"
              - name: "Capture"
                type: set_variable
                vars:
                  loop_seen: "{{ vars.steps.Loop }}"
                  loop_count: "{{ vars.steps.Loop | length }}"
            """),
        ),
    ),
]


# ---------------------------------------------------------------------
# Execution helpers (push, trigger, poll, capture)
# ---------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _push(yaml_text: str) -> dict[str, str]:
    """Push a scenario YAML; return ``{playbook_name: uuid}`` for
    every workflow created. Push output lines look like
    ``✓ <name>: https://<host>/playbooks/<uuid>``.
    """
    tmp = REPO / ".probe_render_path_tmp.yaml"
    tmp.write_text(yaml_text)
    try:
        push = subprocess.run(
            [sys.executable, "-m", "cli", "push", str(tmp),
             "--mode", "replace"],
            cwd=str(REPO / "python"), capture_output=True, text=True,
        )
    finally:
        tmp.unlink(missing_ok=True)
    if push.returncode != 0:
        raise RuntimeError(f"push failed:\n{push.stderr}\n{push.stdout}")
    out = push.stderr + "\n" + push.stdout
    pairs: dict[str, str] = {}
    for m in re.finditer(r"✓\s+(\S+):\s*https?://\S+/playbooks/"
                         r"([0-9a-f-]{36})", out):
        pairs[m.group(1)] = m.group(2)
    if not pairs:
        # Fall back to the first uuid in the output for backwards
        # compatibility with older push output formats.
        m = re.search(r"/playbooks/([0-9a-f-]{36})", out)
        if not m:
            raise RuntimeError(f"could not parse workflow uuids:\n{out[-400:]}")
        pairs["__first__"] = m.group(1)
    return pairs


def _trigger_and_capture(client, wf_uuid: str,
                         timeout_s: int = 90) -> dict:
    """Trigger by UUID, poll to terminal, return the full run dict
    (env + per-step results)."""
    body = {"input": {}, "request": {"data": {}},
            "useMockOutput": False, "globalMock": False}
    tr = client.session.post(
        client.base_url + f"/api/triggers/1/notrigger/{wf_uuid}",
        json=body, verify=client.verify_ssl, timeout=30,
    )
    if tr.status_code >= 400:
        raise RuntimeError(f"trigger HTTP {tr.status_code}: {tr.text[:300]}")
    task_id = (tr.json() or {}).get("task_id")
    if not task_id:
        raise RuntimeError("trigger returned no task_id")

    # Scope the poll to the TOP-LEVEL run for this template. Without
    # `parent_wf__isnull=True` a workflow_reference scenario surfaces
    # the CHILD run (it shares the task_id and finishes most recently)
    # so we'd miss the parent's env entirely. Verified 2026-05-08 via
    # ref_sync_basic capturing rp_ref_sync_child instead of _parent.
    parent_iri = f"/api/3/workflows/{wf_uuid}"
    poll = (client.base_url + "/api/wf/api/workflows/"
            f"?task_id={task_id}&template_iri={parent_iri}"
            f"&parent_wf__isnull=True"
            f"&format=json&limit=1&ordering=-modified")
    deadline = time.time() + timeout_s
    final = None
    last_status = ""
    while time.time() < deadline:
        r = client.session.get(poll, verify=client.verify_ssl, timeout=15)
        members = (r.json() or {}).get("hydra:member") or []
        if members:
            status = members[0].get("status", "")
            if status != last_status:
                _log(f"  status: {status}")
                last_status = status
            if status in TERMINAL:
                final = members[0]
                break
        time.sleep(2)
    if not final:
        raise RuntimeError(f"timeout; last status={last_status!r}")

    # Pull the full run with per-step env + result.
    full = client.session.get(
        client.base_url + "/api" + final.get("@id", "")
        + "?step_detail=true",
        verify=client.verify_ssl, timeout=30,
    ).json()
    return full


def _purge(client) -> None:
    """Best-effort cleanup of the probe collection + its workflows."""
    try:
        r = client.session.get(
            client.base_url + "/api/3/workflow_collections"
            f"?name={COLL_NAME}&$limit=10",
            verify=client.verify_ssl, timeout=15,
        )
        ids = [c["uuid"] for c in (r.json() or {}).get("hydra:member", [])
               if c.get("uuid")]
        if ids:
            client.session.delete(
                client.base_url + "/api/3/delete/workflow_collections"
                "?$hardDelete=true",
                json={"ids": ids},
                verify=client.verify_ssl, timeout=15,
            )
        # sweep orphan workflows by name prefix
        wr = client.session.get(
            client.base_url + "/api/3/workflows"
            "?name${startswith}=rp_&$limit=50",
            verify=client.verify_ssl, timeout=15,
        )
        wids = [w["uuid"] for w in (wr.json() or {}).get("hydra:member", [])
                if w.get("uuid")]
        if wids:
            client.session.delete(
                client.base_url + "/api/3/delete/workflows"
                "?$hardDelete=true",
                json={"ids": wids}, verify=client.verify_ssl, timeout=15,
            )
    except Exception as exc:  # noqa: BLE001
        _log(f"purge: {exc}")


# ---------------------------------------------------------------------
# Per-scenario runner + fixture writer
# ---------------------------------------------------------------------

def _save_fixture(scenario: Scenario, run: dict) -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    fixture = {
        "scenario": scenario.name,
        "playbook_name": scenario.pb_name,
        "description": scenario.description,
        "yaml": scenario.yaml,
        "run_status": run.get("status"),
        "env": run.get("env") or {},
        "steps": [
            {
                "name": s.get("name"),
                "type_name": (s.get("step_type") or {}).get("name")
                              if isinstance(s.get("step_type"), dict)
                              else s.get("type"),
                "status": s.get("status"),
                "result": s.get("result"),
            }
            for s in (run.get("steps") or [])
        ],
    }
    path = FIXTURE_DIR / f"{scenario.name}.json"
    path.write_text(json.dumps(fixture, indent=2, default=str))
    return path


def run_one(client, scenario: Scenario) -> tuple[bool, str]:
    _log(f"\n=== {scenario.name} ===")
    try:
        uuids = _push(scenario.yaml)
        # Pick the playbook to trigger. For multi-playbook collections
        # (workflow_reference scenarios), we explicitly trigger the
        # parent (scenario.pb_name).
        wf_uuid = uuids.get(scenario.pb_name)
        if wf_uuid is None:
            wf_uuid = next(iter(uuids.values()))
        _log(f"  trigger uuid: {wf_uuid[:8]}… ({scenario.pb_name})")
        if len(uuids) > 1:
            _log(f"  also pushed: {[n for n in uuids if n != scenario.pb_name]}")
        run = _trigger_and_capture(client, wf_uuid)
        path = _save_fixture(scenario, run)
        _log(f"  saved → {path.relative_to(REPO)}")
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario",
                    help="run only the named scenario (default: all)")
    ap.add_argument("--keep", action="store_true",
                    help="leave the probe collection on FSR after run")
    args = ap.parse_args()

    cfg = _env.get_config()
    if not cfg.is_live():
        _log("FSR_BASE_URL / auth not configured — see .env")
        return 2
    client = _env.get_client()

    targets = SCENARIOS
    if args.scenario:
        targets = [s for s in SCENARIOS if s.name == args.scenario]
        if not targets:
            _log(f"unknown scenario: {args.scenario}")
            _log("known: " + ", ".join(s.name for s in SCENARIOS))
            return 2

    failures: list[tuple[str, str]] = []
    try:
        for sc in targets:
            ok, msg = run_one(client, sc)
            if not ok:
                failures.append((sc.name, msg))
    finally:
        if not args.keep:
            _log("\npurging probe collection")
            _purge(client)

    _log(f"\n{len(targets) - len(failures)}/{len(targets)} scenarios ok")
    for name, msg in failures:
        _log(f"  FAIL {name}: {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
