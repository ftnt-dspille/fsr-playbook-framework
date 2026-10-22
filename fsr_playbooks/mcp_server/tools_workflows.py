"""MCP tools for the agent workflows (``fsr_playbooks.workflows``).

Thin wrappers: each calls the workflow function and returns its
WorkflowResult as the tool envelope. The CLI renders the same object.
"""
from __future__ import annotations

from typing import Any

from fsr_playbooks.mcp_server._shared import mcp


@mcp.tool()
def debug_run(playbook_or_id: str, yaml_text: str | None = None) -> dict[str, Any]:
    """Explain why a playbook run did what it did, with evidence.

    Give a playbook name (its latest failed run is used) or a run pk / task id.
    Returns findings that cite the run and its steps: the failing step and its
    error, and any step argument that does not render against the run's own
    vars (the first one is the likely root cause). Pass the result id to
    repair_playbook as follow_up to fix it.
    """
    from fsr_playbooks.workflows.debug import debug_run as _run
    return _run(playbook_or_id, yaml_text=yaml_text).to_tool()


@mcp.tool()
def verify_effect(module: str = "", uuid: str = "", fields: dict | None = None,
                  assertions: list[dict] | None = None) -> dict[str, Any]:
    """Read the box back after a write and report what actually changed.

    Either name a record (module + uuid) and the field values the write should
    have set, or pass assert_playbook_outcome-style assertions. Each expected
    value becomes a finding; any mismatch makes the result partial, naming the
    field. Use after create_record / update_record / run_playbook.
    """
    from fsr_playbooks.workflows.verify import verify_effect as _run
    return _run(module=module, uuid=uuid, fields=fields, assertions=assertions).to_tool()
