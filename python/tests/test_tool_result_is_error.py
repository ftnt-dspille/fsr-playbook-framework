"""Tool-result `is_error` flagging (Phase 1.2).

Without `is_error`, the model's self-repair loop has to guess whether a
tool failed from prose. We set it from the result envelope so a transient
connector failure escalates/alternates instead of being blindly retried.
"""
from __future__ import annotations

from fsr_core.llm.anthropic_provider import _is_error_result


def test_ok_false_envelope_is_error():
    assert _is_error_result({"ok": False, "code": "bad_params"}) is True


def test_bare_error_dict_is_error():
    assert _is_error_result({"error": "connector 500"}) is True


def test_ok_true_is_not_error():
    assert _is_error_result({"ok": True, "data": {"x": 1}}) is False


def test_plain_success_dict_is_not_error():
    assert _is_error_result({"data": [1, 2, 3]}) is False


def test_non_dict_is_not_error():
    assert _is_error_result("some string result") is False
    assert _is_error_result(None) is False
    assert _is_error_result([{"ok": False}]) is False
