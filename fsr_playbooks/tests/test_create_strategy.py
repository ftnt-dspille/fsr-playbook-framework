"""Create-strategy resolution + slice narrowing (Guided / Freeform / Auto).

The widget's create-method toggle maps to a `create_strategy`. Guided removes
the free-text YAML authoring surface so `compose_playbook` (plan->compiler) is
the only path to a deliverable; Freeform keeps today's full authoring slice;
Auto picks by the resolved model's capability. These are the pure primitives the
connector calls when it assembles the per-turn tool slice.
"""
from __future__ import annotations

from fsr_playbooks.llm import intents


def test_auto_gives_weak_or_unknown_model_the_guided_path():
    # Frank proxies, mini/haiku, and an unknown/empty model are NOT create-
    # capable -- valid-by-construction is the floor.
    assert intents.resolve_create_strategy("auto", "coding-b200/qwen3.8-27b") == "guided"
    assert intents.resolve_create_strategy("auto", "gpt-4.1-mini") == "guided"
    assert intents.resolve_create_strategy("auto", "claude-haiku-5-5") == "guided"
    assert intents.resolve_create_strategy("auto", "") == "guided"
    assert intents.resolve_create_strategy("auto", None) == "guided"


def test_auto_gives_a_strong_authoring_model_the_freeform_path():
    assert intents.resolve_create_strategy("auto", "claude-opus-4-8") == "freeform"
    assert intents.resolve_create_strategy("auto", "gpt-4.1") == "freeform"


def test_incapable_substring_beats_capable_substring():
    # gpt-4.1-mini matches BOTH "gpt-4.1" (capable) and "mini" (incapable);
    # incapable must win so the weaker variant does not get free text.
    assert intents.is_create_capable_model("gpt-4.1-mini") is False
    assert intents.is_create_capable_model("gpt-4.1") is True


def test_explicit_toggle_overrides_auto_regardless_of_model():
    # The analyst's manual choice wins over the capability heuristic both ways.
    assert intents.resolve_create_strategy("guided", "claude-opus-4-8") == "guided"
    assert intents.resolve_create_strategy("freeform", "coding-b200/qwen3.8-27b") == "freeform"


def test_unknown_strategy_value_falls_back_to_auto():
    # Legacy/garbage value is treated as auto, then resolved by model.
    assert intents.resolve_create_strategy("bogus", "claude-opus-4-8") == "freeform"
    assert intents.resolve_create_strategy("bogus", "gpt-4.1-mini") == "guided"


def _names(tools):
    return {t["name"] for t in tools}


def test_guided_drops_free_text_authoring_but_keeps_compose_and_discovery():
    build = intents.tools_for_intent("build")
    advertised = _names(build)
    # Precondition: the free-text authoring tools and compose are all present in
    # the full build slice (else this test proves nothing).
    assert "compose_playbook" in advertised
    assert intents.FREEFORM_AUTHORING_TOOLS & advertised

    guided = intents.apply_create_strategy(build, "guided")
    gnames = _names(guided)
    # The free-text authoring surface is gone...
    assert not (intents.FREEFORM_AUTHORING_TOOLS & gnames)
    # ...but compose_playbook (the only authoring path left) survives, as does
    # discovery and delivery.
    assert "compose_playbook" in gnames
    for keep in ("find_connector", "find_operation", "get_op_schema"):
        if keep in advertised:
            assert keep in gnames


def test_freeform_and_auto_are_noops_on_the_slice():
    build = intents.tools_for_intent("build")
    assert _names(intents.apply_create_strategy(build, "freeform")) == _names(build)
    # apply_create_strategy does NOT silently resolve a raw "auto" to guided --
    # the caller resolves first; an unresolved auto leaves the slice whole.
    assert _names(intents.apply_create_strategy(build, "auto")) == _names(build)
