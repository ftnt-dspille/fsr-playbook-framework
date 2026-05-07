"""Push + run + env endpoints.

Subprocesses `python -m cli` from the existing FSRPlaybookYaml repo —
reuses all the tested push/run logic (idempotent push, --follow polling,
env rebuild). Streams live output through SSE for the run endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

from asyncio import create_subprocess_exec as _spawn
from asyncio.subprocess import PIPE, STDOUT
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"


router = APIRouter(prefix="/api", tags=["playbook"])


def _cli_cmd(*args: str) -> list[str]:
    return [sys.executable, "-W", "ignore::Warning", "-m", "cli", *args]


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(PYTHON_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    )
    # Belt-and-braces — even with -W, some libs print to stderr directly.
    env.setdefault("PYTHONWARNINGS", "ignore")
    return env


_NOISE_RE = re.compile(
    r"(InsecureRequestWarning|Unverified HTTPS request|"
    r"urllib3\.readthedocs\.io|warnings\.warn\()"
)


def _scrub(text: str) -> str:
    """Strip urllib3 self-signed-cert warning noise from CLI output."""
    if not text:
        return text
    if os.environ.get("FSR_SUPPRESS_INSECURE_WARNING", "true").lower() == "false":
        return text
    out: list[str] = []
    skip_next = False
    for line in text.splitlines():
        if _NOISE_RE.search(line):
            skip_next = True
            continue
        if skip_next:
            # The warning block is usually 2-3 lines; drop indented or
            # empty trailing lines that follow it.
            if line.startswith((" ", "\t")) or line.strip() == "":
                continue
            skip_next = False
        out.append(line)
    return "\n".join(out)


class PushIn(BaseModel):
    text: str
    mode: str = "replace"


class PushOut(BaseModel):
    ok: bool
    stdout: str
    stderr: str
    exit_code: int


@router.post("/playbook/push", response_model=PushOut)
def push(body: PushIn) -> PushOut:
    if body.mode not in ("replace", "create", "update", "upsert"):
        raise HTTPException(400, "mode must be replace|create|update|upsert")
    # Fail fast when FSR isn't configured — without this the user
    # waits for the 120 s subprocess timeout before getting feedback.
    try:
        from probes import _env  # type: ignore
        if not _env.get_config().is_live():
            return PushOut(
                ok=False,
                stdout="",
                stderr="FSR_BASE_URL / auth not configured in .env — "
                       "push has nothing to push to.",
                exit_code=2,
            )
    except Exception as e:
        return PushOut(
            ok=False, stdout="",
            stderr=f"FSR config probe failed: {type(e).__name__}: {e}",
            exit_code=2,
        )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(REPO_ROOT)
    ) as f:
        f.write(body.text)
        tmp_path = Path(f.name)
    try:
        proc = subprocess.run(
            _cli_cmd("push", str(tmp_path), "--mode", body.mode),
            cwd=str(REPO_ROOT),
            env=_cli_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return PushOut(
            ok=proc.returncode == 0,
            stdout=_scrub(proc.stdout),
            stderr=_scrub(proc.stderr),
            exit_code=proc.returncode,
        )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


class RunIn(BaseModel):
    name: str
    input: dict[str, Any] | None = None
    record: str | None = None
    timeout_seconds: int = 300


_TASK_ID_RE = re.compile(r"task[_ ]id[:\s=]+([0-9a-f-]{36})", re.IGNORECASE)


@router.post("/playbook/run")
async def run_playbook(body: RunIn) -> EventSourceResponse:
    args = ["run-playbook", body.name, "--follow"]
    if body.input:
        args += ["--input", json.dumps(body.input)]
    if body.record:
        args += ["--record", body.record]

    async def gen() -> AsyncIterator[dict[str, Any]]:
        proc = await _spawn(
            *_cli_cmd(*args),
            cwd=str(REPO_ROOT),
            env=_cli_env(),
            stdout=PIPE,
            stderr=STDOUT,
        )
        task_id: str | None = None
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if _NOISE_RE.search(line):
                    continue
                if task_id is None:
                    m = _TASK_ID_RE.search(line)
                    if m:
                        task_id = m.group(1)
                        yield {"event": "task_id", "data": json.dumps({"task_id": task_id})}
                yield {"event": "log", "data": json.dumps({"line": line})}
            try:
                rc = await asyncio.wait_for(proc.wait(), timeout=body.timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                rc = -1
                yield {"event": "error", "data": json.dumps({"message": "run timed out"})}
            yield {
                "event": "done",
                "data": json.dumps({"exit_code": rc, "task_id": task_id}),
            }
        finally:
            if proc.returncode is None:
                proc.kill()

    return EventSourceResponse(gen())


class EnvOut(BaseModel):
    ok: bool
    env: dict[str, Any] | None = None
    error: str | None = None


@router.get("/run/{pk}/env", response_model=EnvOut)
def run_env(pk: str) -> EnvOut:
    proc = subprocess.run(
        _cli_cmd("env", pk),
        cwd=str(REPO_ROOT),
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return EnvOut(ok=False, error=proc.stderr.strip() or "env lookup failed")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return EnvOut(ok=False, error=f"non-JSON output from `cli env`: {e}")
    return EnvOut(ok=True, env=data)
