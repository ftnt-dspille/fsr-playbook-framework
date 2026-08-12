"""Regression: run-vs-author redirect at the dispatch boundary.

When the analyst asks to *run* an already-deployed playbook by name, models
(esp. gpt-4.1-mini) reliably mis-route to an authoring tool: they call
`verify_playbook(yaml_text="", playbook="<Name>")` -- a `playbook` NAME with no
YAML to author. Live on 8.0 this was 0/3: every "run the playbook <name>" turn
picked verify_playbook and fabricated/blank-parsed YAML instead of run_playbook.

The fix is language-agnostic -- it keys on the tool-CALL SHAPE (blank yaml_text +
a playbook name), never on the analyst's words -- so it works no matter what
language the request was phrased in.

The redirect is FORCING, not advisory: a tool_result that merely *tells* the
model to call run_playbook is unreliable (gpt-4.1-mini reads it and wanders back
into authoring). dispatch() re-dispatches run_playbook itself, through the same
tier gate, and tags the result `_redirected_from`. Model compliance stops
mattering. The advisory `run_not_author` envelope survives only as the fallback
for a registry with no run_playbook in it.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import tools as tools_mod
from fsr_playbooks.llm.tools import _AUTHORING_YAML_TOOLS, REGISTRY, ToolSpec, dispatch


@pytest.fixture
def spy_verify(monkeypatch):
    """Register a throwaway verify_playbook that records whether it ran."""
    ran: list = []

    def _fn(yaml_text="", playbook=None, **kw):
        ran.append({"yaml_text": yaml_text, "playbook": playbook})
        return {"ok": True, "ready_to_push": True}

    spec = ToolSpec(
        name="verify_playbook",
        description="test-only verify_playbook",
        input_schema={"type": "object", "properties": {}},
        fn=_fn,
        tier=0,
    )
    monkeypatch.setitem(REGISTRY, "verify_playbook", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "verify_playbook", 0)
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)
    yield ran


@pytest.fixture
def spy_run(monkeypatch):
    """Stub run_playbook at tier 0 so the forcing redirect is observable without
    the tier-3 approval envelope standing in the way."""
    ran: list = []

    def _fn(playbook=None, **kw):
        ran.append({"playbook": playbook, **kw})
        return {"ok": True, "status": "finished"}

    spec = ToolSpec(
        name="run_playbook",
        description="test-only run_playbook",
        input_schema={"type": "object", "properties": {}},
        fn=_fn,
        tier=0,
    )
    monkeypatch.setitem(REGISTRY, "run_playbook", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "run_playbook", 0)
    yield ran


def test_blank_yaml_plus_playbook_name_forces_the_run(spy_verify, spy_run):
    """verify_playbook with a name but no YAML → run_playbook actually runs,
    with the name carried over; the authoring tool never executes."""
    out = dispatch("verify_playbook", {"yaml_text": "", "playbook": "Get Latest NIST-NVD CVE Details"})
    assert out.get("_redirected_from") == "verify_playbook"
    assert spy_run == [{"playbook": "Get Latest NIST-NVD CVE Details"}]
    assert spy_verify == [], "verify_playbook must NOT execute on a run request"


def test_redirect_still_passes_through_the_tier_gate(spy_verify):
    """With the REAL run_playbook (tier 3), the redirect yields the approval
    envelope -- forcing the route must not force execution past the gate."""
    out = dispatch("verify_playbook", {"yaml_text": "", "playbook": "Get Latest NIST-NVD CVE Details"})
    assert out.get("_redirected_from") == "verify_playbook"
    assert out.get("pending_approval") is True
    assert spy_verify == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_whitespace_only_yaml_still_redirects(spy_verify, spy_run, blank):
    out = dispatch("verify_playbook", {"yaml_text": blank, "playbook": "PB Name"})
    assert out.get("_redirected_from") == "verify_playbook"
    assert spy_run == [{"playbook": "PB Name"}]
    assert spy_verify == []


def test_advisory_fallback_when_no_run_playbook_registered(spy_verify, monkeypatch):
    """Registry without run_playbook → the advisory envelope, naming the tool."""
    monkeypatch.delitem(REGISTRY, "run_playbook", raising=False)
    out = dispatch("verify_playbook", {"yaml_text": "", "playbook": "Get Latest NIST-NVD CVE Details"})
    assert out.get("code") == "run_not_author"
    assert out.get("redirect_tool") == "run_playbook"
    assert out.get("playbook") == "Get Latest NIST-NVD CVE Details"
    assert "run_playbook(playbook='Get Latest NIST-NVD CVE Details')" in out.get("error", "")
    assert spy_verify == []


def test_real_yaml_authoring_is_not_intercepted(spy_verify):
    """A genuine authoring call (real yaml_text) runs verify_playbook normally,
    even if a `playbook` label is also present."""
    out = dispatch("verify_playbook", {
        "yaml_text": "playbooks:\n- name: X\n  steps: []\n",
        "playbook": "X",
    })
    assert out.get("code") != "run_not_author"
    assert len(spy_verify) == 1


def test_verify_without_playbook_name_is_not_intercepted(spy_verify):
    """Blank yaml but NO playbook name is an ordinary authoring error path,
    not a run request -- let the tool report it, don't redirect."""
    out = dispatch("verify_playbook", {"yaml_text": ""})
    assert out.get("code") != "run_not_author"
    assert len(spy_verify) == 1


def test_guard_set_names_the_authoring_tools():
    assert "verify_playbook" in _AUTHORING_YAML_TOOLS
