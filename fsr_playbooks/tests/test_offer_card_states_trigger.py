"""The offer card says what starts the playbook, in plain words.

Live (analyst sim): "runs when an alert is created" was built as a manual
Execute button twice. The card listed the steps but never the trigger, so the
analyst approved it. The trigger is read from the playbook's own trigger step
(structure), never from the request's wording.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from fsr_playbooks.mcp_server.tools_emit import _trigger_summary  # noqa: E402


def _pb(trigger: str) -> str:
    return ("collection: C\nplaybooks:\n  - name: P\n    steps:\n"
            f"      - {trigger}\n      - {{name: Done, type: end}}\n")


@pytest.mark.parametrize("trigger,label", [
    ("{name: S, type: start_on_create, module: alerts, next: Done}",
     "Runs automatically when an alert is created"),
    ("{name: S, type: start_on_update, module: incidents, next: Done, "
     "when: {logic: AND, filters: [{field: severity, operator: changed}]}}",
     "Runs automatically when an incident is updated and matches its conditions"),
    ("{name: S, type: start, module: alerts, button_label: Check IP, next: Done}",
     'Runs when an analyst clicks "Check IP" on an alert'),
    ("{name: S, type: start, module: threat_intel_feeds, next: Done}",
     "Runs when an analyst starts it on a threat intel feed"),
])
def test_the_trigger_reads_as_the_analyst_would_say_it(trigger, label):
    t = _trigger_summary(_pb(trigger))
    assert t["label"] == label
    assert t.get("manual", False) == trigger.startswith("{name: S, type: start,")


def test_no_trigger_step_means_no_claim():
    assert _trigger_summary("collection: C\nplaybooks:\n  - name: P\n    steps: []\n") is None
