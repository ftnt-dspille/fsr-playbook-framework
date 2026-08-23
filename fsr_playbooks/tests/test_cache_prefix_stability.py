"""The prompt cache keys on a prefix -- so measure whether ours holds still.

Anthropic renders `tools` -> `system` -> `messages`, and `anthropic_provider`
marks the last tool with `cache_control`, making the cached prefix exactly
*(tools, system)*. Any byte change there discards the whole prefix, system
prompt included.

The token counters for this were always plumbed (`UsageEvent.cache_read`,
populated from `cache_read_input_tokens`), but nothing ever ASSERTED on them
and nothing said *why* a cache went cold. That is the gap these tests close:
a fingerprint over the cacheable prefix, and the invariant that a turn which
changed nothing must not move it.

Box-free and deterministic: this is a property of how we build the request,
not of what a model answers.
"""
from __future__ import annotations

from fsr_playbooks.llm.cache_prefix import (
    explain_change,
    prefix_fingerprint,
    tool_names,
)

_SYS = "You are a FortiSOAR analyst."
_TOOLS = [
    {"name": "run_op", "description": "run an op",
     "input_schema": {"type": "object", "properties": {"op": {"type": "string"}}}},
    {"name": "get_record", "description": "read a record",
     "input_schema": {"type": "object", "properties": {}}},
]


def test_identical_inputs_give_an_identical_fingerprint() -> None:
    assert prefix_fingerprint(_SYS, _TOOLS) == prefix_fingerprint(
        _SYS, [dict(t) for t in _TOOLS])


def test_cache_control_marker_does_not_move_the_fingerprint() -> None:
    """We stamp `cache_control` on the LAST tool ourselves.

    If that marker counted, the fingerprint would change every time the
    slice's length changed for an unrelated reason -- double-counting the very
    thing we are trying to measure."""
    marked = [dict(_TOOLS[0]),
              {**_TOOLS[1], "cache_control": {"type": "ephemeral"}}]
    assert prefix_fingerprint(_SYS, marked) == prefix_fingerprint(_SYS, _TOOLS)


def test_key_order_within_a_tool_does_not_matter() -> None:
    """JSON key order is an artifact of dict construction, not a wire fact."""
    flipped = [{k: t[k] for k in reversed(list(t))} for t in _TOOLS]
    assert prefix_fingerprint(_SYS, flipped) == prefix_fingerprint(_SYS, _TOOLS)


def test_tool_ORDER_does_move_the_fingerprint() -> None:
    """A reorder really does invalidate the cache, so it must not be hidden."""
    assert prefix_fingerprint(_SYS, list(reversed(_TOOLS))) != prefix_fingerprint(
        _SYS, _TOOLS)


def test_dropping_a_tool_moves_the_fingerprint() -> None:
    assert prefix_fingerprint(_SYS, _TOOLS[:1]) != prefix_fingerprint(_SYS, _TOOLS)


def test_system_prompt_change_moves_the_fingerprint() -> None:
    assert prefix_fingerprint(_SYS + " Be terse.", _TOOLS) != prefix_fingerprint(
        _SYS, _TOOLS)


def test_explain_change_names_the_cause() -> None:
    """A bare mismatch is not actionable; the diff has to say what moved."""
    assert explain_change(_SYS, _TOOLS, _SYS, _TOOLS) == ""
    assert "ORDER" in explain_change(_SYS, _TOOLS, _SYS, list(reversed(_TOOLS)))
    assert "-1 tools" in explain_change(_SYS, _TOOLS, _SYS, _TOOLS[:1])
    assert "get_record" in explain_change(_SYS, _TOOLS, _SYS, _TOOLS[:1])
    assert "system prompt changed" in explain_change(
        _SYS, _TOOLS, _SYS + "!", _TOOLS)
    schema_moved = [_TOOLS[0],
                    {**_TOOLS[1], "input_schema": {"type": "object",
                                                   "properties": {"n": {}}}}]
    assert "SCHEMA" in explain_change(_SYS, _TOOLS, _SYS, schema_moved)


def test_tool_names_reads_both_advertised_shapes() -> None:
    """Anthropic-shaped and OpenAI-wrapped tools both have to be legible."""
    assert tool_names(_TOOLS) == ["run_op", "get_record"]
    assert tool_names([{"type": "function",
                        "function": {"name": "wrapped"}}]) == ["wrapped"]
    assert tool_names(None) == []


def test_usage_event_carries_the_fingerprint() -> None:
    """The field has to exist and default empty, so a provider that does not
    report one (the FortiAI proxy) is distinguishable from one that reports
    a stable prefix."""
    from fsr_playbooks.llm.provider import UsageEvent
    ev = UsageEvent(session_id="s", turn=1, model="m", input_tokens=1,
                    output_tokens=1, cache_read=0, cache_write=0,
                    history_chars=0, stop_reason="end_turn")
    assert ev.prefix_fingerprint == ""
    ev2 = UsageEvent(session_id="s", turn=2, model="m", input_tokens=1,
                     output_tokens=1, cache_read=0, cache_write=0,
                     history_chars=0, stop_reason="end_turn",
                     prefix_fingerprint="abc123")
    assert ev2.prefix_fingerprint == "abc123"
