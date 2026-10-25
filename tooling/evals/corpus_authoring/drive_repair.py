"""Drive one REPAIR task through Claude Code (`claude -p`) + the toolkit MCP.

Authoring-from-scratch is one skill; fixing a broken playbook is another. This
hands the agent a deliberately-broken playbook (from mutate.py) and asks it to
diagnose and FIX it with the toolkit's debug/verify/repair tools, then captures
the repaired YAML so repair_grade.py can score whether the injected defect was
actually removed and the structure preserved.

Same subscription path and MCP wiring as drive.py -- it reuses that module's
config/transcript/extraction helpers so the two drivers can never drift in how
they talk to the toolkit or read YAML back out of a run.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from tooling.evals.corpus_authoring import drive

REPAIR_PREAMBLE = (
    "A FortiSOAR playbook below is BROKEN -- it will not compile or run "
    "correctly. Use the FortiSOAR toolkit MCP tools available to you to "
    "diagnose the problem (debug_run / verify_playbook) and then FIX it "
    "(repair_playbook or by editing the YAML). Do NOT publish or deploy "
    "anything to the box. Preserve the playbook's original intent and "
    "structure -- change only what is needed to make it correct. When you are "
    "done, output the COMPLETE corrected playbook YAML in a single ```yaml "
    "fenced block as your last message.\n\nBroken playbook:\n```yaml\n"
)


def drive_repair(task: dict, defect: dict, work: Path,
                 model: str = "claude-sonnet-5-5", timeout: int = 1800) -> dict:
    """Run one repair; return {id, kind, repaired_yaml, tools, rc, stderr_tail}."""
    work.mkdir(parents=True, exist_ok=True)
    cfg = drive._mcp_config(work)
    prompt = REPAIR_PREAMBLE + defect["yaml"] + "\n```\n"
    cmd = ["claude", "-p", prompt, "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(cfg), "--strict-mcp-config",
           "--allowedTools", drive._ALLOWED]
    proc = subprocess.run(cmd, cwd=work, text=True, capture_output=True, timeout=timeout)
    events = drive._events(proc.stdout)
    tag = f"{task['id']}__{defect['kind']}"
    (work / f"{tag}.repair.transcript.jsonl").write_text(
        "\n".join(__import__("json").dumps(e) for e in events))
    repaired_yaml, tools = drive._extract_yaml(events)
    return {
        "id": task["id"],
        "kind": defect["kind"],
        "repaired_yaml": repaired_yaml,
        "tools": tools,
        "used_debug": any(t in tools for t in ("debug_run", "repair_playbook")),
        "used_verify": "verify_playbook" in tools,
        "rc": proc.returncode,
        "stderr_tail": proc.stderr[-1500:],
    }
