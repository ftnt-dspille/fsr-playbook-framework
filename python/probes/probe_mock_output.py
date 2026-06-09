"""Probe: validate that useMockOutput=true substitutes a step's mock_result
and that downstream steps see the mocked value.

Pushes examples/probe_mock_output.yaml (a tiny start → connector → set_variable
chain whose connector targets recorded-future, which is unconfigured on the
dev FSR), triggers it with --mock, then reads the run env and asserts the
set_variable's stamped fields match the embedded mock_result payload.

Without --mock, the connector step would fail with a no-config error — so a
green run is itself partial proof that mocking fired. The downstream
set_variable assertion is the conclusive check that the mocked payload was
actually exposed to subsequent steps.

Usage:
    python -m probes.probe_mock_output

Requires .env with FSR_BASE_URL + auth. Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from probes import _env

REPO = Path(__file__).resolve().parents[2]
YAML_PATH = REPO / "examples" / "probe_mock_output.yaml"
PB_NAME = "FSRPB Probe Mock"
COLL_NAME = "FSRPB Probe Mock Output"

EXPECTED_MARKER = "fsrpb-mock-probe-OK"
EXPECTED_COUNT = 2
EXPECTED_FIRST_NAME = "alpha"

TERMINAL = {"finished", "failed", "terminated", "skipped",
            "finished_with_error", "rejected"}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    cfg = _env.get_config()
    if not cfg.is_live():
        _log("FSR_BASE_URL / auth not configured in .env — cannot run live probe")
        return 2
    client = _env.get_client()

    # 1. Compile + push
    _log(f"compiling {YAML_PATH.name}")
    sys.path.insert(0, str(REPO / "python"))
    from fsr_core.compiler import compile_yaml
    db_path = REPO / "store" / "fsr_reference.db"
    r = compile_yaml(YAML_PATH.read_text(), db_path)
    if not r.ok:
        _log(f"compile failed: {[e.to_dict() for e in r.errors]}")
        return 1

    _log("pushing to FSR (mode=replace)")
    import subprocess
    push = subprocess.run(
        [sys.executable, "-m", "cli", "push", str(YAML_PATH), "--mode", "replace"],
        cwd=str(REPO / "python"), capture_output=True, text=True,
    )
    if push.returncode != 0:
        _log(f"push failed:\n{push.stderr}")
        return 1
    push_out = (push.stderr + "\n" + push.stdout).strip()
    _log(push_out.splitlines()[-1])

    # 2. Parse workflow uuid out of the push output (the `playbooks/<uuid>`
    # URL line). Avoids a separate /api/3/workflows list call which 400s
    # on this FSR build when filtered by name.
    import re
    m = re.search(r"/playbooks/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", push_out)
    if not m:
        _log(f"could not parse workflow uuid from push output:\n{push_out[-500:]}")
        return 1
    wf_uuid = m.group(1)
    _log(f"workflow uuid: {wf_uuid[:8]}…")

    # 3. Trigger with useMockOutput=true
    _log("triggering with useMockOutput=true / globalMock=true")
    body = {
        "input": {},
        "request": {"data": {}},
        # globalMock MUST be false — with it true, IngestBulkFeed (and likely
        # other custom handlers) ignore mock_result and run live anyway.
        # useMockOutput=true alone is what makes mock_result apply uniformly.
        "useMockOutput": True,
        "globalMock": False,
    }
    tr = client.session.post(
        client.base_url + f"/api/triggers/1/notrigger/{wf_uuid}",
        json=body, verify=client.verify_ssl,
    )
    if tr.status_code >= 400:
        _log(f"trigger failed: HTTP {tr.status_code}\n{tr.text[:300]}")
        return 1
    trig_resp = tr.json() or {}
    _log(f"trigger response: {json.dumps(trig_resp)[:300]}")
    task_id = trig_resp.get("task_id")
    if not task_id:
        _log("no task_id returned from trigger")
        return 1
    _log(f"task_id: {task_id}")

    # 4. Poll for completion
    poll_url = (client.base_url + "/api/wf/api/workflows/"
                f"?task_id={task_id}"
                "&format=json&limit=5&offset=0&ordering=-modified")
    deadline = time.time() + 120
    final = None
    last_status = ""
    while time.time() < deadline:
        pr = client.session.get(poll_url, verify=client.verify_ssl)
        members = (pr.json() or {}).get("hydra:member") or []
        if members:
            status = members[0].get("status")
            if status != last_status:
                _log(f"  status: {status}  ({int(time.time() - (deadline - 120))}s)")
                last_status = status
            if status in TERMINAL:
                final = members[0]
                break
        time.sleep(2)
    if not final:
        _log(f"timeout waiting for terminal status (last seen: {last_status!r})")
        return 1
    if final.get("status") != "finished":
        _log(f"run did not finish cleanly: status={final.get('status')!r}")
        # show step diagnostics so we can see which step blew up
        pk_url = final.get("@id") or ""
        if pk_url:
            full = client.session.get(client.base_url + "/api" + pk_url
                                      + "?step_detail=true",
                                      verify=client.verify_ssl).json()
            for s in full.get("steps") or []:
                _log(f"  - {s.get('name')}: status={s.get('status')!r} result={str(s.get('result'))[:200]}")
        return 1
    _log(f"run status: {final.get('status')}")

    # 5. Fetch run env and assert
    pk_url = final.get("@id") or ""
    full = client.session.get(client.base_url + "/api" + pk_url
                              + "?step_detail=true",
                              verify=client.verify_ssl).json()
    env_obj = full.get("env") or {}
    _log(f"top-level env keys: {sorted(env_obj.keys())}")

    failures: list[str] = []
    if env_obj.get("mocked_marker") != EXPECTED_MARKER:
        failures.append(
            f"mocked_marker: got {env_obj.get('mocked_marker')!r}, "
            f"expected {EXPECTED_MARKER!r}"
        )
    # set_variable values may serialize as strings; coerce for the count check.
    raw_count = env_obj.get("mocked_count")
    try:
        count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        count = None
    if count != EXPECTED_COUNT:
        failures.append(
            f"mocked_count: got {raw_count!r}, expected {EXPECTED_COUNT}"
        )
    if env_obj.get("mocked_first_name") != EXPECTED_FIRST_NAME:
        failures.append(
            f"mocked_first_name: got {env_obj.get('mocked_first_name')!r}, "
            f"expected {EXPECTED_FIRST_NAME!r}"
        )

    if failures:
        _log("ASSERTION FAILED:")
        for f in failures:
            _log(f"  {f}")
        # Dump the Capture step's result for debugging.
        for s in full.get("steps") or []:
            if s.get("name") == "Capture mock":
                _log(f"Capture mock result: {json.dumps(s.get('result'), indent=2)[:800]}")
        return 1

    _log("PASS — mocked_result was substituted and downstream set_variable saw it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
