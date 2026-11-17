"""Drive one connector BUILD or FIX task through Claude Code + the connector toolkit MCP.

Mirrors corpus_authoring/drive.py, but the artifact is a connector DIRECTORY on
disk (info.json + operations.py + connector.py), not a YAML string: the agent
writes/edits files in its work dir and the grader reads that dir in place. So the
agent is given the file tools (Read/Write/Edit) alongside the toolkit MCP.

The connector toolkit is not pip-installed; its MCP server runs from an isolated
venv with mcp<2 (the shipped code uses the v1 FastMCP API) and the package on
PYTHONPATH. Point the driver at that venv + src via env:
  FSR_CONN_TOOLKIT_PY   python in a venv that has mcp<2 + the toolkit's deps
  FSR_CONN_TOOLKIT_SRC  parent dir of the `fsr_connector_toolkit` package
  FSR_CONN_TOOLKIT_DB   optional catalog.sqlite for lookup/search_corpus/audit
No FortiSOAR box is needed -- the toolkit reads connector dirs + a local corpus.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SERVER = "fsrconn"
_ALLOWED = f"mcp__{SERVER}__* Read Write Edit Glob Grep"

_BUILD_PREAMBLE = (
    "You are building a FortiSOAR connector for a user. A connector is a directory "
    "with info.json (metadata + operations + parameters), operations.py (a handler "
    "per operation plus a dispatch dict), and connector.py (a Connector subclass "
    "with execute() and check_health()). Use the connector toolkit MCP tools to "
    "look up what the target API expects before you write an operation. Write the "
    "three files into the connector directory given below. Do NOT install anything.\n\n"
    "Connector directory (write your files here): {conn_dir}\n\nTask:\n"
)

_FIX_PREAMBLE = (
    "You are fixing a broken FortiSOAR connector for a user. The connector is the "
    "directory given below; edit its files in place. Use the connector toolkit MCP "
    "tools (and read the files) to find and correct the problem. Do NOT install "
    "anything.\n\nConnector directory: {conn_dir}\n\nReported problem:\n"
)


def _toolkit_py() -> str:
    py = os.environ.get("FSR_CONN_TOOLKIT_PY")
    if not py or not Path(py).exists():
        raise SystemExit("set FSR_CONN_TOOLKIT_PY to a python with mcp<2 + the toolkit deps")
    return py


def _mcp_config(work: Path) -> Path:
    src = os.environ.get("FSR_CONN_TOOLKIT_SRC")
    if not src:
        raise SystemExit("set FSR_CONN_TOOLKIT_SRC to the parent dir of fsr_connector_toolkit")
    env = {"PYTHONPATH": src}
    db = os.environ.get("FSR_CONN_TOOLKIT_DB")
    if db:
        env["FSR_TOOLKIT_DB"] = db
    server = {"command": _toolkit_py(), "args": ["-m", "fsr_connector_toolkit.mcp"], "env": env}
    cfg = work / ".mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {SERVER: server}}, indent=2))
    return cfg


def _events(stdout: str) -> list[dict]:
    out = []
    for line in stdout.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _tools_used(events: list[dict]) -> list[str]:
    names: list[str] = []
    for ev in events:
        for b in (ev.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                names.append(str(b.get("name", "")).replace(f"mcp__{SERVER}__", ""))
    return names


def _run(prompt: str, conn_dir: Path, work: Path, model: str, timeout: int) -> dict:
    # Absolute --mcp-config: claude -p runs with cwd=work, so a relative path
    # resolves against work and vanishes -> claude loads no tools and the
    # scorecard silently reads 0 (a false negative). Same hazard as the
    # authoring driver.
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    conn_dir = Path(conn_dir).resolve()
    conn_dir.mkdir(parents=True, exist_ok=True)
    cfg = _mcp_config(work)
    cmd = ["claude", "-p", prompt, "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(cfg), "--strict-mcp-config",
           "--allowedTools", *_ALLOWED.split()]
    proc = subprocess.run(cmd, cwd=work, text=True, capture_output=True, timeout=timeout)
    events = _events(proc.stdout)
    (work / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    return {"connector_dir": str(conn_dir), "tools": _tools_used(events),
            "rc": proc.returncode, "stderr_tail": proc.stderr[-1500:]}


def drive_build(task: dict, work: Path, model: str = "claude-sonnet-5-5",
                timeout: int = 1800) -> dict:
    """task: {id, spec}. The agent writes a new connector into work/<id>/connector."""
    base = Path(work) / task["id"]
    conn_dir = base / "connector"
    prompt = _BUILD_PREAMBLE.format(conn_dir=conn_dir.resolve()) + task["spec"]
    out = _run(prompt, conn_dir, base, model, timeout)
    out["id"] = task["id"]
    return out


def drive_fix(task: dict, work: Path, model: str = "claude-sonnet-5-5",
              timeout: int = 1800) -> dict:
    """task: {id, spec, broken_dir}. The broken connector is copied into
    work/<id>/connector and the agent edits it in place."""
    import shutil
    base = Path(work) / task["id"]
    conn_dir = base / "connector"
    base.mkdir(parents=True, exist_ok=True)
    if conn_dir.exists():
        shutil.rmtree(conn_dir)
    shutil.copytree(task["broken_dir"], conn_dir)
    prompt = _FIX_PREAMBLE.format(conn_dir=conn_dir.resolve()) + task["spec"]
    out = _run(prompt, conn_dir, base, model, timeout)
    out["id"] = task["id"]
    return out
