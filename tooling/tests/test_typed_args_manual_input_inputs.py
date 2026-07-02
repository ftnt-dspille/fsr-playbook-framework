"""Typed-args model for ``manual_input.arguments.inputs[]`` -- the P2 discover win.

The 28-kind input-field contract was previously invisible: `inputs` was `Any`,
so `get_step_arg_schema("manual_input")` emitted `{}` for it. An agent authoring
a manual_input form had no machine-readable answer to "what kinds can I use, and
what does each require?"

`InputVariableArgs` types each entry -- `name` (required), `kind` (the 28-value
Literal derived from the live-grounded `PicklistMixin._INPUT_FIELD_KINDS`, so it
cannot drift), and the per-entry friendly scalars.

DESIGN SPLIT (important):
  * The **schema** (introspection / discover) is the typed model's job -- the
    28-kind enum + required `name`/`kind` surface via `emit_step_arg_schema`.
  * Runtime **per-entry validation stays in the resolver** (`_expand_input_variables`),
    which produces richer, suggestion-bearing messages than pydantic's generic
    "Field required" / "Extra inputs are not permitted" (difflib kind suggestions,
    "unknown key(s) on inputs[] entry: 'bogus'", per-kind co-presence). The typed
    layer strips `inputs` before `validate_args` so it does NOT shadow those.

So these tests assert: (a) the schema emits the 28-kind contract (the win), and
(b) the resolver's runtime per-entry errors are unchanged by the model's presence
(no regression in the agent-facing messages)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    ManualInputArgs,
    STEP_ARG_MODELS,
)
from fsr_playbooks.compiler.resolver.picklists import PicklistMixin


_KNOWN_KINDS = sorted(PicklistMixin._INPUT_FIELD_KINDS)


def _schema_inputs_items():
    """The inputs[] item schema from the emitted manual_input schema."""
    s = emit_step_arg_schema("manual_input")
    assert s is not None
    defs = s.get("$defs", {})
    inputs_prop = s["properties"]["inputs"]
    # inputs is Optional[list[InputVariableArgs]] -> "anyOf" -> array branch.
    item_ref = None
    for branch in inputs_prop.get("anyOf", []):
        if branch.get("type") == "array":
            item_ref = branch["items"].get("$ref")
            break
    assert item_ref, inputs_prop
    name = item_ref.split("/")[-1]
    return defs[name]


def test_inputs_is_list_of_input_variable_args():
    assert "inputs" in ManualInputArgs.model_fields
    assert STEP_ARG_MODELS["manual_input"] is ManualInputArgs


def test_kind_enum_is_the_full_live_grounded_set():
    # The Literal derives from the resolver dict -- must match exactly, no drift.
    kind_prop = _schema_inputs_items()["properties"]["kind"]
    assert "enum" in kind_prop
    assert sorted(kind_prop["enum"]) == _KNOWN_KINDS


def test_kind_enum_count_matches_resolver():
    # 28 kinds (the dict has 28 distinct keys).
    kind_prop = _schema_inputs_items()["properties"]["kind"]
    assert len(kind_prop["enum"]) == len(_KNOWN_KINDS) == 28


def test_name_and_kind_are_required():
    items = _schema_inputs_items()
    required = set(items.get("required", []))
    assert "name" in required
    assert "kind" in required


def test_per_entry_fields_advertised_in_schema():
    # The friendly scalars an agent can set on each inputs[] entry.
    props = set(_schema_inputs_items()["properties"])
    for expected in ("name", "kind", "label", "tooltip", "required",
                     "default", "options", "module", "picklist"):
        assert expected in props, expected


def test_end_to_end_compile_inputs_form(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          title: Approve?
          inputs:
            - {name: comment, kind: textarea, label: Comment, required: true}
            - {name: severity, kind: select, options: [Low, High]}
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_resolver_unknown_kind_still_surfaces_rich_error(db_path):
    # The typed model must NOT shadow the resolver's per-entry kind error.
    # An unknown kind with no near-match should still surface a value error
    # carrying the resolver's message (not pydantic's generic one).
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          title: T
          inputs:
            - {name: c, kind: bogus_kind}
"""
    r = compile_yaml(text, db_path)
    assert any(
        e.code in (ErrorCode.BAD_VALUE, ErrorCode.UNKNOWN_PARAM)
        and "kind" in (e.path or "")
        for e in r.errors
    ), [e.to_dict() for e in r.errors]


def test_resolver_unknown_entry_key_still_surfaces_rich_error(db_path):
    # A typo'd entry key (tooptip) must surface the resolver's
    # "unknown key(s) on inputs[] entry" message, not pydantic's
    # "Extra inputs are not permitted".
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          title: T
          inputs:
            - {name: c, kind: text, tooptip: x}
"""
    r = compile_yaml(text, db_path)
    msgs = [e.message or "" for e in r.errors]
    assert any("unknown key" in m and "inputs[]" in m for m in msgs), msgs
