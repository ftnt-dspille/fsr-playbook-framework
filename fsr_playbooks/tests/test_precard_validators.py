"""Pre-card validators: a doomed tier-3 call must bounce, not reach a human.

A tier-3+ call is suspended into an approval card WITHOUT running the tool body,
so an argument that cannot possibly work (a connector that exists nowhere, a
playbook name the model invented) used to reach the analyst as a card that looks
legitimate and can only fail *after* approval. Live: a ztpf session carded
`run_playbook("Create Next SingleLo Interface")` -- a step label, not a playbook.

A pre-card validator runs just before the envelope is built and may short-circuit
with an actionable error. It must be fail-open: a validator that raises, or that
returns a non-dict, falls through to normal carding rather than blocking a
legitimate action.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import tools as tools_mod
from fsr_playbooks.llm.tools import REGISTRY, ToolSpec, dispatch


@pytest.fixture
def probe(monkeypatch):
    """A throwaway tier-3 tool + a clean validator registry."""
    calls: list[dict] = []

    spec = ToolSpec(
        name="_precard_probe",
        description="test-only tier-3 tool",
        input_schema={"type": "object", "properties": {}},
        fn=lambda **kw: calls.append(kw) or {"ok": True, "did_run": True},
        tier=3,
    )
    monkeypatch.setitem(REGISTRY, "_precard_probe", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "_precard_probe", 3)
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)
    # Isolate the registry so a test's validator can't leak into the next.
    monkeypatch.setattr(tools_mod, "_PRECARD_VALIDATORS",
                        dict(tools_mod._PRECARD_VALIDATORS))
    return calls


def test_no_validator_still_cards(probe):
    out = dispatch("_precard_probe", {"x": 1})
    assert out.get("pending_approval") is True
    assert probe == [], "the body must not run before approval"


def test_validator_error_short_circuits_the_card(probe):
    tools_mod.set_precard_validator(
        "_precard_probe",
        lambda args: {"ok": False, "code": "unknown_playbook",
                      "candidates": ["Create Run Group and Queue Steps"]},
    )
    out = dispatch("_precard_probe", {"playbook": "Create Next SingleLo Interface"})
    assert out.get("pending_approval") is None, "a doomed call must NOT be carded"
    assert out["code"] == "unknown_playbook"
    assert out["candidates"] == ["Create Run Group and Queue Steps"]
    assert probe == [], "the body must not run either"


def test_validator_returning_none_falls_through_to_the_card(probe):
    tools_mod.set_precard_validator("_precard_probe", lambda args: None)
    out = dispatch("_precard_probe", {"playbook": "Create Run Group and Queue Steps"})
    assert out.get("pending_approval") is True


def test_validator_that_raises_is_fail_open(probe):
    def _boom(args):
        raise RuntimeError("box unreachable")

    tools_mod.set_precard_validator("_precard_probe", _boom)
    out = dispatch("_precard_probe", {"playbook": "Something Real"})
    assert out.get("pending_approval") is True, (
        "a transport blip in a validator must never block a legitimate action")


def test_validator_returning_non_dict_is_ignored(probe):
    tools_mod.set_precard_validator("_precard_probe", lambda args: "nope")
    out = dispatch("_precard_probe", {"playbook": "Something Real"})
    assert out.get("pending_approval") is True


def test_tier1_call_skips_validators_entirely(probe, monkeypatch):
    """Validators guard the CARD, not execution. A tier-1 tool never cards, so
    it must run untouched -- otherwise a validator becomes a second, silent
    authorization layer on read-only calls."""
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "_precard_probe", 1)
    monkeypatch.setitem(
        REGISTRY, "_precard_probe",
        ToolSpec(name="_precard_probe", description="t", tier=1,
                 input_schema={"type": "object", "properties": {}},
                 fn=REGISTRY["_precard_probe"].fn))
    tools_mod.set_precard_validator(
        "_precard_probe", lambda args: {"ok": False, "code": "should_not_fire"})
    out = dispatch("_precard_probe", {})
    assert out.get("did_run") is True


def test_run_op_validator_is_registered_by_default():
    """The original of this class stays wired -- run_op on a connector that
    exists nowhere must keep bouncing `unknown_connector`."""
    assert "run_op" in tools_mod._PRECARD_VALIDATORS
