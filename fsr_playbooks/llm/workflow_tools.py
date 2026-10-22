"""The agent workflow tool names and tiers, in one place.

Each is one multi-step tool returning a WorkflowResult
(``fsr_playbooks.workflows``). ``llm.tools`` registers them; dependency-free so
anything can import the names.
"""
from __future__ import annotations

# name -> static tier. Reads are tier 1; provision_module writes schema, grants
# a role and publishes, so it is approval-carded.
WORKFLOW_TIERS: dict[str, int] = {
    "debug_run": 1,
    "verify_effect": 1,
    "orient": 1,
    "provision_module": 3,
    "repair_playbook": 1,  # edits a draft; pushing it is a separate carded call
    "investigate_alert": 1,
    "build_playbook": 1,  # gates a draft; pushing it is a separate carded call
}

WORKFLOW_TOOLS: tuple[str, ...] = tuple(WORKFLOW_TIERS)
