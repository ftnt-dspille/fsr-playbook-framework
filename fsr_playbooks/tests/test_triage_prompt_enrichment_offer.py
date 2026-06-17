"""Triage intent must let the analyst build a playbook from a read-only
investigation, not only after a containment action.

The tool side (`emit_playbook_offer` accepting an enrichment-only trace) is
covered by test_playbook_offer.py. This guards the PROMPT contract that drives
the agent to actually offer it: regression-proofs against reverting to the old
"only after a containment action" gate, which dead-ended the analyst at "use
the Designer" when they asked to save a pure-enrichment investigation.
"""
from __future__ import annotations

from fsr_playbooks.llm.intents import load_intent_prompt, tools_for_intent


def test_emit_playbook_offer_is_in_triage_slice():
    # The offer is a triage card emitter — it must survive the build-only drop.
    names = {t["name"] for t in tools_for_intent("triage")}
    assert "emit_playbook_offer" in names


def test_triage_prompt_grants_offer_from_enrichment_when_asked():
    prompt = load_intent_prompt("triage").lower()
    # It still names the tool as the only authoring path.
    assert "emit_playbook_offer" in prompt
    # It no longer gates the offer SOLELY on a containment action: the analyst
    # asking to save/build from the investigation/enrichment is in scope.
    assert "enrichment" in prompt
    # An explicit "ask → offer, even without containment" affordance exists.
    assert "even if no containment" in prompt or "no containment step" in prompt


def test_triage_prompt_does_not_send_analyst_to_designer_for_authoring():
    prompt = load_intent_prompt("triage").lower()
    # The old behavior redirected enrichment-playbook requests to the Designer /
    # called authoring out of scope. The prompt must explicitly forbid that.
    assert "out of scope" in prompt or "designer" in prompt
    # ...specifically in the don't-do-this framing.
    assert "never tell them it's out of scope" in prompt \
        or "do not say authoring is" in prompt
