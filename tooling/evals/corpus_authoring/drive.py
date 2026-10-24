"""Drive one authoring task through Claude Code (`claude -p`) + the toolkit MCP.

Claude Code runs on the Claude subscription and picks the fsr-agentic-toolkit
MCP tools from its catalog exactly as a customer's agent would -- this is the
representative path for "can the toolkit let an agent author this playbook".

Credentials come from the environment (FSR_BASE_URL, FSR_API_KEY; the toolkit
executable from FSR_TOOLKIT_EXE or beside FSR_PYTHON, else PATH). The MCP server
is given a unique name and --strict-mcp-config so a user-level MCP config never
leaks in (a known claude -p hazard). The authored YAML is taken from the last
tool call that carried `yaml_text` (build_playbook / verify_playbook /
compile_playbook_yaml / publish_playbook), falling back to the last ```yaml
fence in the final message.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

SERVER = "fsrtk"
_ALLOWED = f"mcp__{SERVER}__*"

PREAMBLE = (
    "You are authoring a FortiSOAR playbook for a user. Use the FortiSOAR "
    "toolkit MCP tools available to you (prefer the workflows -- orient to "
    "learn the box, then build_playbook to author and gate the YAML). Do NOT "
    "publish or deploy anything to the box. When you are done, output the "
    "FINAL playbook YAML in a single ```yaml fenced block as your last message.\n\n"
    "Task:\n"
)

_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)
_YAML_TOOLS = ("build_playbook", "verify_playbook", "compile_playbook_yaml",
               "publish_playbook", "repair_playbook")


def _toolkit_exe() -> str:
    exe = os.environ.get("FSR_TOOLKIT_EXE")
    if exe and Path(exe).exists():
        return exe
    py = os.environ.get("FSR_PYTHON")
    if py:
        cand = Path(py).parent / "fsr-agentic-toolkit"
        if cand.exists():
            return str(cand)
    found = shutil.which("fsr-agentic-toolkit")
    if not found:
        raise SystemExit("no fsr-agentic-toolkit on PATH; set FSR_TOOLKIT_EXE or FSR_PYTHON")
    return found


def _mcp_config(work: Path) -> Path:
    server = {
        "command": _toolkit_exe(),
        "args": ["mcp"],
        "env": {
            # a nonexistent instances file forces use of the FSR_* env, not an alias
            "PYFSR_INSTANCES": str(work / "no-instances.toml"),
            "FSR_BASE_URL": os.environ["FSR_BASE_URL"],
            "FSR_API_KEY": os.environ["FSR_API_KEY"],
            "FSR_VERIFY_SSL": os.environ.get("FSR_VERIFY_SSL", "false"),
            "FSR_SUPPRESS_INSECURE_WARNINGS": "true",
        },
    }
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


def _extract_yaml(events: list[dict]) -> tuple[str, list[str]]:
    """Authored YAML + the ordered list of toolkit tool names called."""
    last_yaml = ""
    tool_names: list[str] = []
    final_text = ""
    for ev in events:
        for b in (ev.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name = str(b.get("name", "")).replace(f"mcp__{SERVER}__", "")
                tool_names.append(name)
                if name in _YAML_TOOLS:
                    y = (b.get("input") or {}).get("yaml_text")
                    if isinstance(y, str) and y.strip():
                        last_yaml = y
            elif b.get("type") == "text":
                final_text = b.get("text") or final_text
        if ev.get("type") == "result" and ev.get("result"):
            final_text = str(ev["result"])
    # Prefer the last YAML a tool actually received; else a fence in the answer.
    if last_yaml:
        return last_yaml, tool_names
    fences = _YAML_FENCE.findall(final_text or "")
    return (fences[-1] if fences else ""), tool_names


def drive_task(task: dict, work: Path, model: str = "claude-sonnet-5-5",
               timeout: int = 1800) -> dict:
    """Run one task; return {id, authored_yaml, tools, rc, stderr_tail}."""
    work.mkdir(parents=True, exist_ok=True)
    cfg = _mcp_config(work)
    cmd = ["claude", "-p", PREAMBLE + task["spec"], "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(cfg), "--strict-mcp-config",
           "--allowedTools", _ALLOWED]
    proc = subprocess.run(cmd, cwd=work, text=True, capture_output=True, timeout=timeout)
    events = _events(proc.stdout)
    (work / f"{task['id']}.transcript.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events))
    yaml_text, tools = _extract_yaml(events)
    return {
        "id": task["id"],
        "authored_yaml": yaml_text,
        "tools": tools,
        "used_build_playbook": "build_playbook" in tools,
        "rc": proc.returncode,
        "stderr_tail": proc.stderr[-1500:],
    }
