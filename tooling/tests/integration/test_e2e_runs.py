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
PYTHON_DIR = REPO / "tooling"


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
        cmd, cwd=PYTHON_DIR, input=input_text, capture_output=True, text=True,
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
    """Manual input pause/resume cycle finishes cleanly."""
    import time
    yaml = EXAMPLES / "test_manual_input_e2e.yaml"
    _push(yaml)

    rc, out, err = fsrpb("run-playbook", "E2E - Manual Input")
    assert rc == 0, f"fire failed: {err}"
    m = re.search(r'"task_id":\s*"([0-9a-f-]+)"', out)
    assert m, f"no task_id in run-playbook output: {out!r}"
    task_id = m.group(1)

    # Wait briefly for the manual_input pause to register
    pending_id = None
    for _ in range(8):
        time.sleep(2)
        rc2, out2, _ = fsrpb("inputs", "list", "--json")
        items = json.loads(out2 or "[]")
        match = next((i for i in items if i.get("title") == "E2E test gate"), None)
        if match:
            pending_id = match["id"]
            break
    assert pending_id is not None, "manual_input never paused (no 'E2E test gate' in pendings)"

    rc3, _, err3 = fsrpb(
        "inputs", "respond", str(pending_id),
        "--option", "Continue", "--task-id", task_id,
    )
    assert rc3 == 0, f"respond failed: {err3}"

    # Poll until terminal
    final = "?"
    for _ in range(15):
        time.sleep(2)
        rc4, out4, _ = fsrpb("steps", task_id, "--json")
        # Use the workflows endpoint instead — steps endpoint shows audit
        # records that may lag; the run record is the source of truth.
        from probes import _env  # type: ignore  # noqa: PLC0415
        client = _env.get_client()
        r = client.session.get(
            client.base_url + f"/api/wf/api/workflows/?task_id={task_id}&format=json&limit=1",
            verify=client.verify_ssl,
        )
        recs = r.json().get("hydra:member", [])
        if recs:
            final = recs[0]["status"]
            if final in ("finished", "failed", "terminated", "rejected", "skipped",
                         "finished_with_error"):
                break
    assert final == "finished", f"expected finished, got {final}"
