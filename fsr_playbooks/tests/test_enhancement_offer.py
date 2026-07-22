"""The enhance-mode write path: verified bytes are the delivered bytes.

Enhance mode had no write path at all. `verify_enhancement` returned
`ready_to_push: True` and then nothing happened — the only way an edit could
reach the analyst's playbook was a regex in the widget scraping the LAST
```yaml fence out of the model's prose. Live, that lost the edit outright: the
model verified one document and then re-typed three subtly different ones into
chat (a step name gained a space, `ip_type` vanished, quoting style changed),
the widget applied the last of them, and the transcript recorded a green
verdict for a document nobody applied. The analyst asked three times and the
step never landed.

`emit_enhancement_offer` closes it structurally rather than by asking the model
nicely: it takes a `verified_id`, not YAML, so there is no parameter through
which a re-typed document could arrive.

These tests are about that binding. The suite that grades whether the *model*
reaches for the tool lives in the enhance eval bucket.
"""
from __future__ import annotations

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed; tool bodies are exercised elsewhere",
)

from fsr_playbooks.mcp_server import (  # noqa: E402
    _verified_yaml,
    emit_enhancement_offer,
    verify_enhancement,
)

BEFORE = """collection: C
playbooks:
- name: PB
  trigger_step_id: start
  steps:
  - type: start
    name: Start
    module: alerts
    next: Block IP
  - type: connector
    name: Block IP
    arguments: {connector: cyops_utilities, operation: no_op, params: {}}
"""

# The edit the live session was trying to make: a manual_input approval gate
# in front of the containment step.
AFTER = BEFORE.rstrip("\n") + """
  - type: manual_input
    name: Prompt Block IP
    arguments:
      title: Confirm the block
      description: Approve blocking this address.
      inputs:
      - {name: ip_to_block, kind: ipv4, label: IP to block, required: true}
    options:
    - {display: Confirm, primary: true, next: Block IP}
"""


@pytest.fixture(autouse=True)
def _clean_registry():
    _verified_yaml.clear()
    yield
    _verified_yaml.clear()


def _verified() -> str:
    r = verify_enhancement(BEFORE, AFTER, "add a manual input step")
    assert r["ready_to_push"], r.get("required_fixes")
    assert r["verified_id"], "a passing verify must hand back a handle"
    return r["verified_id"]


def test_offer_carries_the_exact_verified_bytes():
    """The whole point: delivered YAML is byte-identical to verified YAML."""
    card = emit_enhancement_offer(id="e1", summary="Adds an approval gate",
                                  verified_id=_verified())["card"]
    assert card["type"] == "enhancement_offer"
    assert card["final_yaml"] == AFTER


def test_offer_takes_no_yaml_parameter():
    """Structural guard — the failure mode returns the moment a `yaml`-ish
    parameter exists to pass a re-typed document through."""
    import inspect
    params = set(inspect.signature(emit_enhancement_offer).parameters)
    assert params == {"id", "summary", "verified_id"}, (
        f"emit_enhancement_offer must not accept YAML; got params {sorted(params)}"
    )


def test_a_failed_verify_issues_no_handle():
    """No handle for a red verdict, or the offer would apply rejected YAML."""
    broken = AFTER.replace("kind: ipv4", "kind: ip_address")
    r = verify_enhancement(BEFORE, broken, "add a manual input step")
    assert not r["ready_to_push"]
    assert r["verified_id"] is None
    assert "verify_enhancement again" in r["how_to_apply"]


def test_unknown_handle_is_a_typed_refusal_not_a_fallback():
    """A miss must never degrade into 'apply whatever the model has'.

    Cold worker, evicted entry, or a hallucinated id all land here. The only
    correct answer is 'go re-verify' — the moment this returns a card built
    from anything else, the binding is decorative.
    """
    out = emit_enhancement_offer(id="e1", summary="s", verified_id="0" * 16)
    assert out["ok"] is False
    assert out["code"] == "unknown_verified_id"
    assert "card" not in out
    assert any("verify_enhancement" in s for s in out.get("suggestions") or [])


def test_a_retyped_document_cannot_be_delivered():
    """The live regression, expressed as a test.

    The model verifies AFTER, then "cleanly re-renders" it. The fingerprint of
    that text is not a registered handle, so there is no way to ship it — which
    is the difference between this design and one that merely asks the model
    not to re-type.
    """
    vid = _verified()
    # The exact class of drift seen live: a "clean re-render" that changes only
    # quoting. Semantically identical, textually different, never verified.
    retyped = AFTER.replace("{display: Confirm,", '{display: "Confirm",')
    assert retyped != AFTER
    assert _verified_yaml.fingerprint(retyped) != vid
    assert _verified_yaml.lookup(_verified_yaml.fingerprint(retyped)) is None
    # The registered handle still yields the ORIGINAL verified bytes.
    card = emit_enhancement_offer(id="e1", summary="s", verified_id=vid)["card"]
    assert card["final_yaml"] == AFTER


def test_card_reports_the_diff_and_carries_warnings_to_the_human():
    """`ready_to_push` tolerates warnings, so the card is the last place a
    human can see them before the edit becomes their saved playbook."""
    card = emit_enhancement_offer(id="e1", summary="s",
                                  verified_id=_verified())["card"]
    assert card["steps_added"] == ["Prompt Block IP"]
    assert card["steps_removed"] == []
    # Display summary is built from the verified YAML, not hand-written.
    assert {"label": "Prompt Block IP", "step_type": "manual_input"} in \
        card["ops_summary"]


def test_verifying_the_same_text_twice_yields_the_same_handle():
    """Content-addressed, so a re-verify after a no-op edit doesn't strand an
    offer against a dead handle."""
    assert _verified() == _verified()


def test_registry_is_bounded():
    """A long-lived worker must not accumulate playbook bodies forever."""
    for i in range(_verified_yaml._MAX_ENTRIES + 8):
        _verified_yaml.remember(f"playbooks: [{i}]")
    assert len(_verified_yaml._REGISTRY) <= _verified_yaml._MAX_ENTRIES


def test_tool_is_registered_and_build_only():
    """Unregistered = never advertised = the model cannot call it, which is
    indistinguishable from the bug this fixes."""
    from fsr_playbooks.llm import intents, tools
    assert "emit_enhancement_offer" in tools.SAFE_TOOLS
    assert tools.TOOL_TIERS["emit_enhancement_offer"] == 0
    assert "emit_enhancement_offer" in intents.BUILD_ONLY_TOOLS
    build = {t["name"] for t in intents.tools_for_intent("build")}
    triage = {t["name"] for t in intents.tools_for_intent("triage")}
    assert "emit_enhancement_offer" in build, "build mode cannot deliver edits"
    assert "emit_enhancement_offer" not in triage, "triage has no open playbook"
