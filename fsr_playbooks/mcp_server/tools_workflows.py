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


@mcp.tool()
def orient(goal: str = "", modules: list[str] | None = None) -> dict[str, Any]:
    """What this box has for a goal, in one call: each named module's real field
    names and picklist values, whether the caller can read it (and if not, which
    break: unpublished, role or team, with the fix), and the connectors that are
    configured and healthy, with the actions matching the goal. Call it before
    writing a playbook or records against modules you have not read."""
    from fsr_playbooks.workflows.orient import orient as _run
    return _run(goal=goal, modules=modules).to_tool()


@mcp.tool()
def provision_module(module: str, label: str = "", plural: str = "",
                     fields: list[dict] | None = None, roles: list[str] | None = None,
                     probe_record: dict | None = None,
                     check_only: bool = False) -> dict[str, Any]:
    """Create a module and leave it usable: create, publish (only when nothing
    else is staged), grant the role(s) (default Full App Permissions), then prove
    the caller can read and create records there. check_only=true writes nothing
    and names which break a module has (unpublished, role, team) and the fix."""
    from fsr_playbooks.workflows.provision import provision_module as _run
    return _run(module, label=label, plural=plural, fields=fields, roles=roles,
                probe_record=probe_record, check_only=check_only).to_tool()


@mcp.tool()
def repair_playbook(follow_up: str, yaml_text: str) -> dict[str, Any]:
    """Fix a playbook from a debug_run diagnosis. Pass the debug_run result id as
    follow_up and the playbook YAML. Root causes with a mechanical fix are fixed
    and the YAML re-validated (returned in data.yaml); the rest are listed as
    needing a hand edit. Pushing the fix is a separate, approval-carded call."""
    from fsr_playbooks.workflows.repair import repair_playbook as _run
    return _run(follow_up, yaml_text).to_tool()


@mcp.tool()
def investigate_alert(iri: str) -> dict[str, Any]:
    """Gather an alert's evidence: read the record, pull its indicators, and list
    the enrichment lookups configured here for each (as next calls). It does not
    judge: run the lookups, then emit the verdict card, which carries the same
    result shape."""
    from fsr_playbooks.workflows.investigate import investigate_alert as _run
    return _run(iri).to_tool()


@mcp.tool()
def build_playbook(goal: str, yaml_text: str = "",
                   modules: list[str] | None = None) -> dict[str, Any]:
    """Orient on the modules a playbook touches, then gate the draft YAML with
    verify_playbook and hand back the next calls (push, approval-carded, then
    verify_effect on a test record). Without yaml_text it returns the facts to
    write the draft from."""
    from fsr_playbooks.workflows.build import build_playbook as _run
    return _run(goal, yaml_text=yaml_text, modules=modules).to_tool()
