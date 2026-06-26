"""Approval previews must stay human-readable, never the whole payload.

Regression for the "bizarre playbook approval popup": push_playbook is tier-3,
so its approval preview embedded the FULL `yaml_text`. The widget renders the
preview as JSON.stringify(preview.args), so an unbounded value produced a
multi-KB wall of text that made the popup unusable (and bogged the digest).
`_build_preview` now caps strings and list lengths.
"""
from __future__ import annotations

from fsr_playbooks.llm.tools import (
    _PREVIEW_MAX_LIST,
    _PREVIEW_MAX_STR,
    _build_preview,
)


def test_long_string_is_truncated_with_marker():
    huge = "a" * 5000
    preview = _build_preview("push_playbook", {"yaml_text": huge})
    shown = preview["args"]["yaml_text"]
    assert len(shown) < len(huge)
    assert shown.startswith("a" * _PREVIEW_MAX_STR)
    assert "chars truncated" in shown
    # The whole payload must never survive into the preview.
    assert huge not in shown


def test_short_values_pass_through_unchanged():
    preview = _build_preview("run_op", {"connector": "fortigate", "ip": "1.2.3.4"})
    assert preview["args"] == {"connector": "fortigate", "ip": "1.2.3.4"}
    assert preview["tool"] == "run_op"


def test_long_list_is_capped():
    iocs = [f"10.0.0.{i}" for i in range(200)]
    preview = _build_preview("block_ips", {"indicators": iocs})
    shown = preview["args"]["indicators"]
    assert len(shown) == _PREVIEW_MAX_LIST + 1  # capped items + truncation marker
    assert "more items truncated" in shown[-1]


def test_sensitive_keys_still_masked_after_truncation():
    preview = _build_preview("auth", {"api_key": "x" * 5000, "user": "admin"})
    assert preview["args"]["api_key"] == "***"
    assert preview["args"]["user"] == "admin"


def test_nested_dict_and_list_truncation():
    preview = _build_preview(
        "x", {"outer": {"yaml": "y" * 5000, "items": list(range(100))}}
    )
    inner = preview["args"]["outer"]
    assert "chars truncated" in inner["yaml"]
    assert len(inner["items"]) == _PREVIEW_MAX_LIST + 1
