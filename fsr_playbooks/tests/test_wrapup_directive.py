"""The forced wrap-up round must not tell an empty turn to stay empty.

When a turn exhausts MAX_TOOL_TURNS both providers force one no-tools round so
the chat never goes silent. That round had exactly one directive, and it ended
"Do not re-emit the YAML" -- correct when a playbook exists and a guarantee of
nothing when none does.

The live shape (sweep row `build_plain_request_no_record`, 2/2 under Frank): a
build request with NO record mounted fans out across connector, step-type and
Jinja lookups -- 31 and 37 tool calls against a 16-round budget -- exhausts the
budget before authoring a line, and is then explicitly instructed not to
deliver. The analyst asked for a playbook and got a paragraph about the
research. Record-mounted build rows are unaffected: grounding cuts the research
to ~11 calls and they close on `awaiting_playbook_offer`.

`BuildProgressGuard` is the right guard for the sibling shape and cannot help
here: it is consulted only where the model VOLUNTARILY stops calling tools
(`if not tool_calls_for_msg`). A turn that researches until the budget dies
never reaches that branch -- which is why its own docstring notes its live case
"did not run out of turns".
"""
from fsr_playbooks.llm._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS, MAX_TOOL_TURNS, analyst_has_the_yaml,
    wrapup_directive,
)


PLAYBOOK = """```yaml
name: fixture
workflows:
  - name: wf
    steps:
      - name: Start
        type: start
```"""

BODY = "name: fixture\nworkflows:\n  - name: wf\n    steps:\n      - name: Start\n"


# --- analyst_has_the_yaml ----------------------------------------------------

def test_no_yaml_when_the_turn_only_researched():
    history = [
        {"role": "user", "content": "Write me a playbook that emails an SLA report."},
        {"role": "assistant", "content": "Let me look up the email connector."},
    ]
    assert analyst_has_the_yaml(history) is False


def test_yaml_found_in_an_assistant_fence():
    assert analyst_has_the_yaml(
        [{"role": "assistant", "content": PLAYBOOK}]) is True


def test_a_delivery_carrier_counts_as_delivered():
    """Build turns are fenceless in practice -- the playbook rides as an arg.

    Reading only assistant text would call a turn that got all the way to an
    offer card "empty" and hand it the write-it-now directive, which is the
    opposite of what it needs.
    """
    history = [{
        "role": "assistant",
        "tool_calls": [{
            "type": "function",
            "function": {"name": "push_playbook",
                         "arguments": '{"yaml_text": %s}' % repr(BODY).replace("'", '"')},
        }],
    }]
    assert analyst_has_the_yaml(history) is True


def test_yaml_found_in_an_anthropic_tool_use_block():
    history = [{
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Verifying."},
            {"type": "tool_use", "name": "emit_playbook_offer",
             "input": {"yaml": BODY}},
        ],
    }]
    assert analyst_has_the_yaml(history) is True


def test_validate_yaml_is_the_scratchpad_not_a_deliverable():
    """The second bug, found by driving the first fix.

    This run authored a real playbook, pushed it through `validate_yaml`, and
    was then told "do not re-emit the YAML" -- so the playbook died inside the
    tool call it was validated in and the analyst got a status paragraph. A
    full, valid body must still read as NOT delivered here: `validate_yaml` is
    where you check your work, not where the user receives it.
    """
    history = [{
        "role": "assistant",
        "content": [{"type": "tool_use", "name": "validate_yaml",
                     "input": {"yaml_text": BODY * 3}}],
    }]
    assert analyst_has_the_yaml(history) is False, (
        "a validated-but-undelivered playbook counted as delivered")


def test_an_empty_carrier_argument_is_not_a_deliverable():
    """A probing call with a stub body must not count as having authored."""
    history = [{
        "role": "assistant",
        "content": [{"type": "tool_use", "name": "push_playbook",
                     "input": {"yaml_text": "   "}}],
    }]
    assert analyst_has_the_yaml(history) is False


def test_a_malformed_openai_argument_blob_carries_nothing():
    history = [{
        "role": "assistant",
        "tool_calls": [{"type": "function",
                        "function": {"name": "push_playbook",
                                     "arguments": "{not json"}}],
    }]
    assert analyst_has_the_yaml(history) is False


# --- wrapup_directive ------------------------------------------------------

def test_research_only_turn_is_told_to_deliver():
    """The regression itself. This turn's last chance is the wrap-up round."""
    directive, max_tokens = wrapup_directive(
        [{"role": "assistant", "content": "Let me check the connectors."}])
    assert "```yaml" in directive
    assert "Do not re-emit the YAML" not in directive
    assert str(MAX_TOOL_TURNS) in directive
    assert max_tokens == DEFAULT_MAX_OUTPUT_TOKENS, (
        f"the delivery round got {max_tokens} tokens, not the full output "
        f"ceiling. Driven at 4096 this emitted an unterminated ```yaml fence "
        f"cut off mid-step -- worse than silence, because it looks like a "
        f"deliverable and the fence extractor finds nothing")


def test_a_turn_that_built_something_still_gets_the_status_directive():
    """The other half. Re-emitting a playbook the user already has wastes the
    last round, and the status summary is what they actually need."""
    directive, max_tokens = wrapup_directive(
        [{"role": "assistant", "content": PLAYBOOK}])
    assert "Do not re-emit the YAML" in directive
    assert max_tokens == 512


def test_the_two_branches_are_actually_different():
    """Guards against a future edit collapsing them back into one string."""
    empty, _ = wrapup_directive([{"role": "assistant", "content": "researching"}])
    built, _ = wrapup_directive([{"role": "assistant", "content": PLAYBOOK}])
    assert empty != built


def test_a_playbook_the_model_only_READ_is_not_a_deliverable():
    """`search_playbooks` returns the corpus, fenced, in a tool result.

    Scanning every message role made "the model read a playbook" score the same
    as "the model wrote one". Live: a 39-call research turn that authored
    nothing at all was judged to have delivered, so it took the
    do-not-re-emit branch and the analyst got a status paragraph. The false
    positive is silent and it defeats the whole fix, so it is pinned here.
    """
    history = [
        {"role": "user", "content": "Write me an SLA playbook."},
        {"role": "assistant",
         "tool_calls": [{"type": "function",
                         "function": {"name": "search_playbooks",
                                      "arguments": '{"q": "sla"}'}}]},
        {"role": "tool", "content": PLAYBOOK},
    ]
    assert analyst_has_the_yaml(history) is False


def test_yaml_the_analyst_pasted_in_is_input_not_output():
    history = [{"role": "user", "content": PLAYBOOK}]
    assert analyst_has_the_yaml(history) is False


def test_a_verified_but_unoffered_playbook_is_not_delivered():
    """Verification is a gate, not delivery -- the second half of the same bug.

    Live: the turn drafted a playbook, cleared `verify_playbook`, ran out of
    tool budget before `emit_playbook_offer`, and was told "do not re-emit the
    YAML". The playbook was correct, verified, and invisible. Passing a gate
    means the bytes are good, not that anybody received them.
    """
    history = [{
        "role": "assistant",
        "content": [{"type": "tool_use", "name": "verify_playbook",
                     "input": {"yaml_text": BODY * 3}}],
    }]
    assert analyst_has_the_yaml(history) is False
    directive, _ = wrapup_directive(history)
    assert "Do not re-emit the YAML" not in directive
