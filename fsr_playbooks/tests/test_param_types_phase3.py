"""Phase 3 (STATIC_TYPE_FLOW_PLAN) — playbook parameter declared types.

`parameters:` now accepts a mapping {name: type} alongside the back-compatible
bare list. The parser populates `Playbook.parameter_types`; the walker seeds
`vars.input.params.<name>` shapes from it so a typed param flowing into a
connector op is caught by the Phase 4 source→target check.
"""
from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.compiler.ir import Collection, Playbook, Step
from fsr_playbooks.compiler.typed_walker import (
    _param_type_to_shape, _pure_single_ref, walk_playbook,
)


# ---- parser: mapping vs list ----------------------------------------------

_MAPPING = """
collection: t
playbooks:
  - name: P
    parameters:
      ip: string
      count: integer
      raw: any
    steps:
      - name: start
        type: start
"""

_LIST = """
collection: t
playbooks:
  - name: P
    parameters: [ip, count]
    steps:
      - name: start
        type: start
"""

_BAD_TYPE = """
collection: t
playbooks:
  - name: P
    parameters:
      ip: bogustype
    steps:
      - name: start
        type: start
"""


def test_parser_mapping_populates_parameter_types():
    coll, errs = parse_yaml(_MAPPING)
    assert coll is not None
    pb = coll.playbooks[0]
    assert set(pb.parameters) == {"ip", "count", "raw"}
    # `any` is stored as untyped (omitted)
    assert pb.parameter_types == {"ip": "string", "count": "integer"}


def test_parser_bare_list_leaves_types_empty():
    coll, errs = parse_yaml(_LIST)
    assert coll is not None
    pb = coll.playbooks[0]
    assert pb.parameters == ["ip", "count"]
    assert pb.parameter_types == {}


def test_parser_unknown_type_warns_not_blocks():
    coll, errs = parse_yaml(_BAD_TYPE)
    assert coll is not None  # warning, not a hard error
    assert any("unknown type" in e.message for e in errs)
    assert coll.playbooks[0].parameter_types == {}


# ---- bad-shape error carries an example + recovery hint (§F) ---------------

_LIST_OF_DICTS = """
collection: t
playbooks:
  - name: P
    parameters:
      - name: ip
        type: string
        description: address to block
      - name: reason
    steps:
      - name: start
        type: start
"""

_UNRECOVERABLE = """
collection: t
playbooks:
  - name: P
    parameters: 42
    steps:
      - name: start
        type: start
"""


def test_parser_list_of_dicts_error_suggests_mapping():
    _, errs = parse_yaml(_LIST_OF_DICTS)
    err = next(e for e in errs if "parameters must be" in e.message)
    # rule + concrete example of both shapes
    assert "parameters: [ip, reason]" in err.message
    assert "{ip: string, reason: string}" in err.message
    # the exact mapping equivalent of what the author wrote
    assert "parameters: {ip: string, reason: any}" in err.message


def test_parser_bad_scalar_error_still_carries_example():
    _, errs = parse_yaml(_UNRECOVERABLE)
    err = next(e for e in errs if "parameters must be" in e.message)
    assert "parameters: [ip, reason]" in err.message
    assert "list-of-dicts" not in err.message


# ---- type → shape mapping --------------------------------------------------

def test_param_type_to_shape():
    assert _param_type_to_shape("integer")["type"] == "integer"
    assert _param_type_to_shape("string")["type"] == "string"
    assert _param_type_to_shape("ipv4")["type"] == "string"  # scalar str tag
    assert _param_type_to_shape("list")["kind"] == "list"
    assert _param_type_to_shape("object")["kind"] == "object"
    assert _param_type_to_shape("any") is None


# ---- pure-ref recognises vars.input.params --------------------------------

def test_pure_ref_input_param():
    assert _pure_single_ref("{{ vars.input.params.ip }}") == ("param", "ip", "")


# ---- walker integration ----------------------------------------------------

def _coll(param_types, ref):
    steps = [
        Step(id="start", type="start", name="start", next="call"),
        Step(id="call", type="connector", name="Call",
             arguments={"connector": "acme", "operation": "query_ip",
                        "params": {"ip": ref}}),
    ]
    pb = Playbook(name="P", trigger_step_id="start", steps=steps,
                  parameters=list(param_types), parameter_types=param_types)
    return Collection(name="C", playbooks=[pb])


def _ptf(target):
    return lambda c, o, p: target if p == "ip" else None


def _codes(coll, target):
    return [d.code for d in
            walk_playbook(coll, param_type_fn=_ptf(target)).diagnostics]


def test_typed_param_into_mismatched_op_flags():
    # count declared integer → flows into an ipv4 param → mismatch
    coll = _coll({"count": "integer"}, "{{ vars.input.params.count }}")
    assert "type_mismatch" in _codes(coll, "ipv4")


def test_typed_param_correct_clean():
    coll = _coll({"count": "integer"}, "{{ vars.input.params.count }}")
    assert "type_mismatch" not in _codes(coll, "int")


def test_untyped_param_stays_any():
    # no declared type → no shape → nothing to check (no regression)
    coll = _coll({}, "{{ vars.input.params.count }}")
    assert "type_mismatch" not in _codes(coll, "ipv4")
