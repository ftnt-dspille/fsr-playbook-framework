"""The eval must score the playbook a turn DELIVERED, not the bit it pasted.

Scoring read `extract_yaml(final_text)` alone, so an agent that followed our
own instructions -- `emit_playbook_offer` says a turn that "prints YAML at the
analyst has delivered nothing" -- handed the scorer an empty string. `draft`,
`verified` and `adherence` then failed together on EVERY fixture regardless of
content, which is what produced a flat 5/8 across nine unrelated fixtures and
read as a model-quality regression that was never there.

The metric was measuring obedience to an instruction the product reversed.
"""
from __future__ import annotations

import pytest

from evals.scoring import delivered_yaml, score
from evals.tasks import load_tasks


@pytest.fixture(scope="module")
def gold() -> str:
    return load_tasks(["hello_connector"])[0].gold_yaml_text()


def _trace(gold: str, terminal: str = "emit_playbook_offer") -> list[dict]:
    return [
        {"name": "verify_playbook", "args": {"yaml_text": gold},
         "result": {"ready_to_push": True}},
        {"name": terminal, "args": {"id": "pb1", "summary": "s", "yaml": gold}},
    ]


def test_offer_card_yaml_is_found(gold):
    assert delivered_yaml("no yaml here", _trace(gold)) == gold


def test_falls_back_to_the_last_gated_document(gold):
    """No offer card, but the agent did verify something -- score that."""
    tr = [{"name": "verify_playbook", "args": {"yaml_text": gold}}]
    assert delivered_yaml("prose only", tr) == gold


def test_falls_back_to_a_fenced_block_when_there_is_no_trace(gold):
    assert delivered_yaml(f"```yaml\n{gold}\n```", None).strip()


def test_refused_calls_are_not_treated_as_delivery(gold):
    """A guard-refused offer never reached the analyst, so its YAML must not
    be scored as delivered. (`extract_yaml` echoes unfenced text, so the
    assertion is 'not the gold doc', not 'empty'.)"""
    tr = [{"name": "emit_playbook_offer", "args": {"yaml": gold},
           "refused": True}]
    assert delivered_yaml("prose", tr) != gold


def test_delivery_route_does_not_change_the_score(gold):
    """The whole point: card-delivery and chat-paste must grade the same."""
    tr = _trace(gold)
    via_card = score(delivered_yaml("Delivered above.", tr), trace=tr,
                     final_text="Delivered above.")
    pasted = score(delivered_yaml(f"```yaml\n{gold}\n```", tr), trace=tr,
                   final_text=f"```yaml\n{gold}\n```")
    assert via_card["score"] == pasted["score"]
    assert via_card["levels"]["draft"]["passed"]
    assert via_card["levels"]["adherence"]["passed"]


def test_adherence_did_not_become_a_rubber_stamp(gold):
    """A turn that delivers NOTHING must still fail -- otherwise the fix
    just deleted the gate."""
    tr = [{"name": "find_connector", "args": {}}]
    s = score(delivered_yaml("Here's what I'd suggest...", tr), trace=tr,
              final_text="Here's what I'd suggest...")
    assert not s["levels"]["adherence"]["passed"]
    assert not s["levels"]["draft"]["passed"]


def test_enhancement_offer_also_counts_as_delivery(gold):
    tr = [{"name": "verify_enhancement", "args": {"after_yaml": gold}},
          {"name": "emit_enhancement_offer",
           "args": {"id": "e1", "verified_id": "v1"}}]
    s = score(delivered_yaml("Applied.", tr), trace=tr, final_text="Applied.")
    assert s["levels"]["adherence"]["passed"]
    assert s["levels"]["adherence"]["delivered_via"] == "emit_enhancement_offer"


def test_refuse_mode_fails_a_turn_that_delivered_a_card(gold):
    """Refuse-mode inverts adherence. Now that a card counts as delivery, a
    refuse task must fail for emitting one -- not only for pasting YAML."""
    tr = _trace(gold)
    s = score(delivered_yaml("", tr), trace=tr, final_text="", mode="refuse")
    assert not s["levels"]["adherence"]["passed"]


def test_refuse_mode_passes_when_nothing_was_delivered():
    tr = [{"name": "find_connector", "args": {}}]
    s = score("", trace=tr, final_text="I can't build that.", mode="refuse")
    assert s["levels"]["adherence"]["passed"]
