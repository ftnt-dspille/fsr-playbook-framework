"""P4 — the tool-output envelope contract.

Pins the contract from `llm.tool_result`:
  - a valid tool output is a dict OR a list whose members are all dicts;
  - a bare/untyped return (scalar, None, list-of-non-dict) is a violation;
  - `dispatch` routes tool-fn results through it — fail-open by default
    (violation logged, result passed through), strict under
    ``FSRPB_STRICT_TOOL_OUTPUT`` (violation replaced with an error envelope);
  - every registered tool declares a return type that satisfies the contract
    (the static half of "every registered tool's output validates").
"""
from __future__ import annotations

import inspect
import typing

import pytest

from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.tool_result import (
    is_valid_tool_output,
    validate_tool_output,
)


# --------------------------------------------------------------- unit contract

@pytest.mark.parametrize("good", [
    {},
    {"ok": True, "code": "done", "message": "hi"},
    {"record": {"id": 1}},
    [],
    [{"hit": 1}, {"hit": 2}],
])
def test_valid_shapes(good):
    assert is_valid_tool_output(good) is True


@pytest.mark.parametrize("bad", [
    "a bare string",
    42,
    True,
    None,
    ["not", "dicts"],
    [{"ok": True}, "mixed"],
    ("a", "tuple"),
])
def test_invalid_shapes(bad):
    assert is_valid_tool_output(bad) is False


def test_failopen_passes_result_through(monkeypatch, caplog):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    with caplog.at_level("WARNING"):
        out = validate_tool_output("some_tool", "bare string")
    assert out == "bare string"  # unchanged — fail-open
    assert any("contract" in r.message for r in caplog.records)


def test_strict_wraps_violation_in_error_envelope(monkeypatch):
    monkeypatch.setenv("FSRPB_STRICT_TOOL_OUTPUT", "1")
    out = validate_tool_output("some_tool", "bare string")
    assert isinstance(out, dict)
    assert out["ok"] is False
    assert out["code"] == "tool_output_contract"
    assert "some_tool" in out["error"]


def test_valid_output_untouched_in_strict(monkeypatch):
    monkeypatch.setenv("FSRPB_STRICT_TOOL_OUTPUT", "1")
    payload = {"ok": True, "record": {"id": 7}}
    assert validate_tool_output("t", payload) is payload
    hits = [{"a": 1}]
    assert validate_tool_output("t", hits) is hits


# ----------------------------------------------------------- static tool audit

def _return_satisfies_contract(ann: object) -> bool:
    """True when a return annotation is `dict[...]` or `list[dict[...]]` (the
    two contract-conforming shapes). Handles both live typing objects and, if a
    module stringizes annotations, their string form."""
    if isinstance(ann, str):
        s = ann.replace(" ", "")
        return s.startswith("dict[") or s.startswith("list[dict[") \
            or s in ("dict", "list[dict]")
    origin = typing.get_origin(ann)
    if origin in (dict,):
        return True
    if origin in (list,):
        args = typing.get_args(ann)
        return bool(args) and typing.get_origin(args[0]) in (dict,)
    return False


def test_every_registered_tool_declares_conforming_return():
    """A tool added with a bare/untyped return type (e.g. `-> str`) fails here —
    the static guard behind the envelope contract."""
    offenders = []
    for name, spec in T.REGISTRY.items():
        ann = inspect.signature(spec.fn).return_annotation
        if ann is inspect.Signature.empty or not _return_satisfies_contract(ann):
            offenders.append((name, ann))
    assert not offenders, f"tools with non-envelope return types: {offenders}"


# ------------------------------------------------------- dispatch integration

def _install_tool(name, fn, tier=0):
    """Register a throwaway tool into REGISTRY for one test; returns a cleanup."""
    from fsr_playbooks.llm.tools import ToolSpec
    spec = ToolSpec(name=name, description="test", input_schema={"type": "object"},
                    fn=fn, tier=tier)
    T.REGISTRY[name] = spec
    return lambda: T.REGISTRY.pop(name, None)


def test_dispatch_failopen_returns_bare_output(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    cleanup = _install_tool("_p4_bare", lambda: "naked")
    try:
        assert T.dispatch("_p4_bare", {}) == "naked"
    finally:
        cleanup()


def test_dispatch_strict_wraps_bare_output(monkeypatch):
    monkeypatch.setenv("FSRPB_STRICT_TOOL_OUTPUT", "1")
    cleanup = _install_tool("_p4_bare", lambda: "naked")
    try:
        out = T.dispatch("_p4_bare", {})
        assert isinstance(out, dict) and out["code"] == "tool_output_contract"
    finally:
        cleanup()


def test_dispatch_passes_valid_dict_unchanged(monkeypatch):
    monkeypatch.setenv("FSRPB_STRICT_TOOL_OUTPUT", "1")
    payload = {"ok": True, "record": {"id": 1}}
    cleanup = _install_tool("_p4_ok", lambda: payload)
    try:
        assert T.dispatch("_p4_ok", {}) == payload
    finally:
        cleanup()
