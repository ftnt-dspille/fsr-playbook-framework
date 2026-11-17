"""Typed-args layer: foundation bridge + live-grounded trigger `when:` models.

The trigger wire shapes asserted here are pinned to real output pulled from
box 198.51.100.205 (`tooling/probes/fixtures/live_trigger_filter_shapes.json`):
the five filter `type`s (primitive / object / array / datetime / changed) and
nested AND/OR groups. The flat imperative `_expand_when` could only author the
primitive + changed shapes; these tests cover the shapes the typed models add.
"""
from __future__ import annotations

import json
from pathlib import Path

from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args import (
    StrictArgs,
    expand_when,
    validate_args,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "probes" / "fixtures" / "live_trigger_filter_shapes.json"
)


def _live():
    return json.loads(FIXTURE.read_text())


def _when(filters, logic="AND"):
    return {"logic": logic, "filters": filters}


# ── foundation: the pydantic ↔ CompileError bridge ────────────────────────
class _Demo(StrictArgs):
    name: str
    count: int = 0


def test_bridge_maps_validation_error_loc_to_path():
    errs: list[CompileError] = []
    out = validate_args(_Demo, {"count": "not-an-int"}, "step.args", errs)
    assert out is None
    codes = {(e.code, e.path) for e in errs}
    # missing required `name` → MISSING_FIELD at the field path
    assert (ErrorCode.MISSING_FIELD, "step.args.name") in codes
    # bad type for `count` → BAD_VALUE at the field path
    assert any(e.code == ErrorCode.BAD_VALUE and e.path == "step.args.count"
               for e in errs)


def test_bridge_unknown_key_is_unknown_param():
    errs: list[CompileError] = []
    assert validate_args(_Demo, {"name": "x", "bogus": 1}, "s", errs) is None
    assert any(e.code == ErrorCode.UNKNOWN_PARAM for e in errs)


def test_bridge_success_returns_model_no_errors():
    errs: list[CompileError] = []
    out = validate_args(_Demo, {"name": "x", "count": 3}, "s", errs)
    assert isinstance(out, _Demo) and out.count == 3 and errs == []


# ── trigger: parity with the imperative expander (primitive + changed) ────
def test_primitive_flat_shape_is_unchanged():
    errs: list[CompileError] = []
    fbt = expand_when(
        _when([{"field": "source", "op": "eq", "value": "X"}]),
        "start_on_create", "p", errs)
    assert errs == []
    assert fbt == {
        "sort": [], "limit": 30, "logic": "AND",
        "filters": [{"type": "primitive", "field": "source",
                     "value": "X", "operator": "eq", "_operator": "eq"}],
    }


def test_changed_shape_is_object_typed_update_only():
    errs: list[CompileError] = []
    fbt = expand_when(
        _when([{"field": "state", "op": "changed"}]),
        "start_on_update", "p", errs)
    leaf = fbt["filters"][0]
    assert leaf["type"] == "object" and leaf["operator"] == "changed"
    assert leaf["value"] is None and leaf["_value"] == {"display": "", "itemValue": ""}
    # changed on create is blocked
    errs2: list[CompileError] = []
    expand_when(_when([{"field": "state", "op": "changed"}]),
                "start_on_create", "p", errs2)
    assert any("changed" in e.message and e.severity == "error" for e in errs2)


def test_contains_rewrites_to_like_with_wildcards_and_warns():
    errs: list[CompileError] = []
    fbt = expand_when(
        _when([{"field": "name", "op": "contains", "value": "mal"}]),
        "start_on_create", "p", errs)
    leaf = fbt["filters"][0]
    assert leaf["operator"] == "like" and leaf["value"] == "%mal%"
    assert any(e.severity == "warning" and "contains" in e.message.lower()
               for e in errs)


# ── trigger: live-grounded shapes the flat expander could not author ──────
def test_nested_and_or_group_authoring():
    errs: list[CompileError] = []
    fbt = expand_when(_when([
        {"field": "escalated", "op": "eq", "value": "No"},
        _when([{"field": "severity", "op": "eq", "value": "High"},
               {"field": "severity", "op": "eq", "value": "Critical"}], logic="OR"),
    ]), "start_on_create", "p", errs)
    assert errs == []
    inner = fbt["filters"][1]
    # nested group carries only logic/filters (matches live wire output)
    assert set(inner.keys()) == {"logic", "filters"}
    assert inner["logic"] == "OR" and len(inner["filters"]) == 2


def test_object_picklist_shape_matches_live():
    live = _live()["leaf_samples"]["object"]
    errs: list[CompileError] = []
    fbt = expand_when(_when([{
        "field": live["field"], "op": live["operator"], "type": "object",
        "value": live["value"], "_value": live["_value"],
    }]), "start_on_create", "p", errs)
    assert errs == []
    assert fbt["filters"][0] == live  # byte-for-byte against the live sample


def test_array_tags_shape_matches_live():
    live = _live()["leaf_samples"]["array"]
    errs: list[CompileError] = []
    fbt = expand_when(_when([{
        "field": live["field"], "op": live["operator"], "type": "array",
        "value": live["value"], "module": live["module"],
        "template": live["template"], "OPERATOR_KEY": live["OPERATOR_KEY"],
        "previousOperator": live["previousOperator"],
        "previousTemplate": live["previousTemplate"],
    }]), "start_on_create", "p", errs)
    assert errs == []
    assert fbt["filters"][0] == live


def test_datetime_shape_matches_live():
    live = _live()["leaf_samples"]["datetime"]
    errs: list[CompileError] = []
    fbt = expand_when(_when([{
        "field": live["field"], "op": live["operator"],
        "type": "datetime", "value": live["value"],
    }]), "start_on_create", "p", errs)
    assert errs == []
    assert fbt["filters"][0] == live


# ── trigger: structural typing catches authoring typos ────────────────────
def test_typo_key_is_caught_structurally():
    errs: list[CompileError] = []
    out = expand_when(
        _when([{"feild": "severity", "op": "eq", "value": "High"}]),
        "start_on_create", "p", errs)
    assert out is None
    assert any(e.code == ErrorCode.UNKNOWN_PARAM and "feild" in e.path
               for e in errs)


def test_when_must_be_mapping_message_preserved():
    errs: list[CompileError] = []
    assert expand_when(["not", "a", "dict"], "start_on_create", "p", errs) is None
    assert any("must be a mapping" in e.message for e in errs)
