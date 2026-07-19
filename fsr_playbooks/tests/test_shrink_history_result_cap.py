"""§2.3 output budgeting — oversized tool_result bodies are capped by
``shrink_history`` while the freshest result stays full.

Covers the gap the idempotent-dedup and yaml-arg passes miss: a single large
tool *result* (verify_playbook ~47KB, duplicate-enrichment ~40KB) that is
neither a duplicate read-only call nor a yaml arg body.
"""

from __future__ import annotations

from fsr_playbooks.llm._loop_helpers import (
    _RESULT_CAP_CHARS,
    _RESULT_HEAD_CHARS,
    _RESULT_KEEP_LATEST,
    _RESULT_TAIL_CHARS,
    shrink_history,
)
from fsr_playbooks.llm.provider import Message


def _assistant_call(cid: str, name: str) -> Message:
    return Message(
        role="assistant",
        content=[{"type": "tool_use", "id": cid, "name": name, "input": {}}],
    )


def _tool_result(cid: str, body: str) -> Message:
    return Message(
        role="user",
        content=[{"type": "tool_result", "tool_use_id": cid, "content": body}],
    )


def _big(marker: str) -> str:
    # Unique, deterministic, well over the cap.
    return (marker + "X") * (_RESULT_CAP_CHARS)


def test_older_oversized_result_capped_latest_kept_full():
    old_body = _big("OLD")
    new_body = _big("NEW")
    history = [
        _assistant_call("c1", "verify_playbook"),
        _tool_result("c1", old_body),
        _assistant_call("c2", "verify_playbook"),
        _tool_result("c2", new_body),
    ]

    saved = shrink_history(history)

    old_after = history[1].content[0]["content"]
    new_after = history[3].content[0]["content"]

    # Freshest result is untouched; the model reasons from latest full data.
    assert new_after == new_body
    # Older result is clipped to head + tail + marker, and is now small.
    assert len(old_after) < _RESULT_CAP_CHARS
    assert old_after.startswith(old_body[:_RESULT_HEAD_CHARS])
    assert old_after.endswith(old_body[-_RESULT_TAIL_CHARS:])
    assert "capped by the output budgeter" in old_after
    assert saved == len(old_body) - len(old_after)
    assert saved > 0


def test_single_oversized_result_not_capped():
    # With only one oversized result and KEEP_LATEST=1, nothing is clipped.
    assert _RESULT_KEEP_LATEST == 1
    body = _big("SOLO")
    history = [
        _assistant_call("c1", "verify_playbook"),
        _tool_result("c1", body),
    ]
    saved = shrink_history(history)
    assert history[1].content[0]["content"] == body
    assert saved == 0


def test_small_results_untouched():
    small = "ok"
    history = [
        _assistant_call("c1", "verify_playbook"),
        _tool_result("c1", small),
        _assistant_call("c2", "verify_playbook"),
        _tool_result("c2", small),
    ]
    assert shrink_history(history) == 0
    assert history[1].content[0]["content"] == small


def test_clip_is_a_fixed_point():
    # Re-running shrink on an already-clipped history is a no-op (byte-stable
    # across turns → prompt-prefix consistency).
    history = [
        _assistant_call("c1", "verify_playbook"),
        _tool_result("c1", _big("OLD")),
        _assistant_call("c2", "verify_playbook"),
        _tool_result("c2", _big("NEW")),
    ]
    shrink_history(history)
    snapshot = history[1].content[0]["content"]
    saved2 = shrink_history(history)
    assert history[1].content[0]["content"] == snapshot
    assert saved2 == 0
