"""End-to-end live tests — push a playbook, fire it, assert it finished.

Marked `live`; deselect with `pytest -m "not live"` to skip when no
appliance is configured. The tests drive everything through the
`fsrpb` CLI (subprocess) so they double as a contract for the
public command surface.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
TOOLING_DIR = REPO / "tooling"


pytestmark = pytest.mark.live


@pytest.fixture(scope="session")
def env_configured():
    """Skip the whole module if .env credentials are absent."""
    env = REPO / ".env"
    if not env.exists():
        pytest.skip(f".env missing at {env}")
    text = env.read_text()
    if "FSR_BASE_URL" not in text or "FSR_PASSWORD" not in text:
        pytest.skip(".env does not contain FSR_BASE_URL / FSR_PASSWORD")


def fsrpb(*args: str, input_text: str | None = None) -> tuple[int, str, str]:
    """Run `fsrpb` (python -m cli) with the given args. Return (rc, stdout, stderr)."""
    cmd = [sys.executable, "-m", "cli", *args]
    proc = subprocess.run(
        cmd, cwd=TOOLING_DIR, input=input_text, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _push(yaml_path: Path) -> str:
    """Compile + push a playbook YAML; return the collection uuid prefix."""
    rc, out, err = fsrpb("push", str(yaml_path), "--mode", "replace")
    assert rc == 0, f"push failed:\nstdout={out}\nstderr={err}"
    # stderr ends with: "PURGE+POST <name> (N playbook(s)) uuid=<8-hex> mode=replace"
    m = re.search(r"uuid=([0-9a-f]{8})", err)
    assert m, f"no uuid in push output: {err!r}"
    return m.group(1)


def _run(name: str, *, score: str | None = None, timeout: int = 30) -> tuple[int, str]:
    """Fire a playbook with --follow; return (rc, final_status). rc=0 → finished."""
    args = ["run-playbook", name, "--follow", "--follow-timeout", str(timeout)]
    if score is not None:
        args += ["--input", json.dumps({"score": score})]
    rc, out, err = fsrpb(*args)
    final = "?"
    if out:
        # last `--follow` payload is a JSON record with a "status" key
        try:
            rec = json.loads(out.strip().splitlines()[-1] if "{" not in out.strip()
                             else _last_json_object(out))
            final = rec.get("status", "?")
        except Exception:  # noqa: BLE001
            final = "?"
    return rc, final


def _last_json_object(text: str) -> str:
    # crude: find the last {...} block in the output
    end = text.rfind("}")
    if end < 0:
        return "{}"
    depth = 0
    for i in range(end, -1, -1):
        ch = text[i]
        if ch == "}": depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                return text[i:end + 1]
    return "{}"


# ---------------------------------------------------------------------------
# Build-up tests: each stage adds one new piece. A failure isolates the cause.
# ---------------------------------------------------------------------------


def test_stage1_bare_set_variable(env_configured):
    """Smallest possible playbook: start → set_variable. Must finish."""
    yaml = EXAMPLES / "test_complex_e2e.yaml"
    _push(yaml)
    rc, status = _run("E2E - Compute Severity")
    assert rc == 0, f"expected exit 0 (finished), got rc={rc} status={status!r}"
    assert status == "finished", f"expected status=finished, got {status!r}"


def test_stage2_var_chain(env_configured):
    """Two set_variable steps where the second references the first's vars.

    Re-uses the same example file (it's currently at stage 3); checks that
    chaining works regardless of the input parameter being supplied.
    """
    rc, status = _run("E2E - Compute Severity", score="3")
    assert rc == 0
    assert status == "finished"


def test_stage3_input_param_jinja(env_configured):
    """Reading vars.input.params.<name> from a runtime input param."""
    rc, status = _run("E2E - Compute Severity", score="42")
    assert rc == 0
    assert status == "finished"


# ---------------------------------------------------------------------------
# Stage 4 — manual_input. Push, fire, find the pause, respond, assert
# the run resumes and reaches `finished`. Requires the canonical
# resume URL POST /api/wf/api/workflows/<wf_pk>/wfinput_resume/ with
# {input, step_iri, step_id, manual_input_id} body — the PUT path was
# a red herring (returns 200 but doesn't actually resume).
# ---------------------------------------------------------------------------


def test_stage4_manual_input_resume(env_configured):
    """Button-only manual input pause/resume cycle finishes cleanly.

    Drives the input cycle through pyfsr's typed ``manual_input`` / ``playbooks``
    APIs (list → answer → run_env), not hand-built URLs.
    """
    from probes import _env  # type: ignore  # noqa: PLC0415
    client = _env.get_client()

    yaml = EXAMPLES / "test_manual_input_e2e.yaml"
    _push(yaml)

    rc, out, err = fsrpb("run-playbook", "E2E - Manual Input")
    assert rc == 0, f"fire failed: {err}"
    m = re.search(r'"task_id":\s*"([0-9a-f-]+)"', out)
    assert m, f"no task_id in run-playbook output: {out!r}"
    task_id = m.group(1)

    pending_id = _wait_pending(client, "E2E test gate")
    assert pending_id is not None, "manual_input never paused (no 'E2E test gate')"

    # Button-only prompt: select the primary option, no input values.
    client.manual_input.answer(input_id=pending_id, option="Continue")

    env = _wait_finished(client, task_id)
    assert env is not None and env.status == "finished", \
        f"expected finished, got {env.status if env else None}"


# ---------------------------------------------------------------------------
# Stage 5 — manual_input authored in the FRIENDLY form (the F3 path): a
# MULTI-field prompt with a REQUIRED field. Asserts (a) the rendered form on
# the appliance is non-empty and carries every declared field with the right
# type + required flag (the exact regression F3 shipped silently), and (b) the
# responder's values flow into a downstream set_variable, read back out of the
# finished run's historical-steps. Pushes via the same friendly authoring that
# the parser hoist + resolver transform process end-to-end.
# ---------------------------------------------------------------------------


def _wait_pending(client, gate: str, *, tries: int = 8):
    """Poll pyfsr for the pending manual input whose prompt title is ``gate``.

    Returns the input ``id`` (or ``None``). Scope ``all`` because the prompt may
    be assigned to a team rather than the calling user.
    """
    import time
    for _ in range(tries):
        time.sleep(2)
        for mi in client.manual_input.list(assigned_to="all"):
            if mi.title == gate:
                return mi.id
    return None


def _wait_finished(client, task_id: str, *, tries: int = 20):
    """Poll ``playbooks.run_env(task_id)`` until the run is terminal.

    Returns the terminal :class:`~pyfsr.models.RunEnv` (status + per-step
    results), tolerating the transient 5xx the detail endpoint can throw right
    after a resume.
    """
    import time
    last = None
    for _ in range(tries):
        time.sleep(2)
        try:
            last = client.playbooks.run_env(task_id)
        except Exception:  # noqa: BLE001 - transient right after resume
            continue
        if last.status in ("finished", "failed", "terminated", "rejected",
                           "skipped", "finished_with_error"):
            return last
    return last


def test_stage5_manual_input_multi_field(env_configured):
    """Friendly multi-field prompt: form renders correctly + values flow through."""
    import time
    from probes import _env  # type: ignore  # noqa: PLC0415

    client = _env.get_client()
    # Step (b) below reads the set_variable result back out of the run record.
    # FortiSOAR only persists set_variable / jinja values when GLOBAL playbook
    # debug logging is on; ensure it so the value assertions are meaningful
    # regardless of the box's prior state.
    client.system_settings.set_playbook_debug_logging(True)

    yaml = EXAMPLES / "test_manual_input_multi_e2e.yaml"
    # `replace` purges-then-posts; on a fresh box the collection doesn't exist
    # yet so the purge DELETE 404s and aborts. Fall back to `create` the first
    # time, then `replace` keeps subsequent runs clean.
    rc, out, err = fsrpb("push", str(yaml), "--mode", "replace")
    if rc != 0 and "purge aborted" in err:
        rc, out, err = fsrpb("push", str(yaml), "--mode", "create")
    assert rc == 0, f"push failed:\nstdout={out}\nstderr={err}"

    rc, out, err = fsrpb("run-playbook", "E2E - Manual Input Multi")
    assert rc == 0, f"fire failed: {err}"
    m = re.search(r'"task_id":\s*"([0-9a-f-]+)"', out)
    assert m, f"no task_id in run-playbook output: {out!r}"
    task_id = m.group(1)

    # Wait for the manual_input pause (pyfsr typed listing).
    pending_id = _wait_pending(client, "E2E multi gate")
    assert pending_id is not None, "manual_input never paused (no 'E2E multi gate')"

    # (a) The rendered form on the appliance must carry all three declared fields
    # with the right type + required flag — the F3 assertion. A dropped `inputs:`
    # would surface here as an empty/short inputVariables list. Read it through
    # the typed pyfsr model: input["schema"] is a ManualInputSchema, its
    # inputVariables are ManualInputVariable objects.
    mi = client.manual_input.retrieve(pending_id)
    ivars = mi.input["schema"].inputVariables
    by_name = {v.name: v for v in ivars}
    assert set(by_name) == {"comment", "severity", "ticket_id"}, \
        f"rendered form fields wrong: {sorted(by_name)}"
    assert by_name["comment"].required is True, "comment should be required"
    assert by_name["comment"].formType == "textarea"
    assert by_name["severity"].required is True, "severity should be required"
    assert by_name["severity"].formType == "dynamicList", \
        f"severity should render as a select: {by_name['severity']!r}"
    assert by_name["severity"].options == ["Low", "Medium", "High"]
    assert by_name["ticket_id"].required is False, "ticket_id should be optional"

    # Respond with values for every field, including the required ones, through
    # the typed pyfsr API (resolves the option + numeric run id itself).
    sentinel = "TKT-E2E-7788"
    client.manual_input.answer(
        input_id=pending_id, option="Continue",
        inputs={"comment": "looks good", "severity": "High", "ticket_id": sentinel},
    )

    # (b) The responder's data must have reached the downstream set_variable.
    # With debug logging on, the run record persists each step's result; read it
    # via the typed run_env (Capture is the set_variable step). Poll until the
    # run is terminal AND the Capture result has populated (it lags the status
    # flip by a beat).
    cap_result = None
    env = None
    for _ in range(20):
        time.sleep(2)
        try:
            env = client.playbooks.run_env(task_id)
        except Exception:  # noqa: BLE001 - transient right after resume
            continue
        step = env.steps.get("Capture")
        if step and isinstance(step.result, dict) and step.result.get("got_severity"):
            cap_result = step.result
            break
        if env.status in ("failed", "terminated", "rejected", "finished_with_error"):
            break
    assert env is not None and env.status == "finished", \
        f"expected finished, got {env.status if env else None}"
    assert cap_result is not None, (
        "Capture step result never populated — is global playbook debug logging "
        "enabled? (the test sets it, but the appliance may override)")
    # The captured variables must equal exactly what the responder submitted.
    assert cap_result.get("got_severity") == "High", \
        f"got_severity mismatch: {cap_result!r}"
    assert cap_result.get("got_ticket") == sentinel, \
        f"got_ticket mismatch: {cap_result!r}"
    assert cap_result.get("got_comment") == "looks good", \
        f"got_comment mismatch: {cap_result!r}"
