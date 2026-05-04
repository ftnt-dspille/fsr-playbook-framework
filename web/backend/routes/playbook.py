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
    return [sys.executable, "-m", "cli", *args]


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(PYTHON_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    )
    return env


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
            stdout=proc.stdout,
            stderr=proc.stderr,
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
