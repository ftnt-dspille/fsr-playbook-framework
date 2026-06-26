"""Phase 4 (STATIC_TYPE_FLOW_PLAN) — source→target type check.

The walker now compares a connector param's *target* type (supplied by a
`param_type_fn`) against the inferred *source* type of a pure reference
(`{{ vars.steps.X.y }}` or `{{ vars.name }}`). Two evidence-sound rules:
shape-into-scalar (list/object → scalar param) is an unambiguous error, and
numeric/bool category crossings error; string/any/null sources stay
permissive (FSR runtime coercion). Filtered/interpolated values are deferred
to the resolver's Tier 3.

Tests build IR by hand and pass a stub `param_type_fn`, so they're decoupled
from store contents.
"""
from fsr_playbooks.compiler.ir import Collection, Playbook, Step
from fsr_playbooks.compiler.typed_walker import (
    _pure_single_ref, _shape_to_src_tag, _source_target_compatible,
    _shape_scalar, _shape_list, _shape_object, walk_playbook,
)


# ---- unit: pure-ref detection ---------------------------------------------

def test_pure_single_ref_classifies():
    assert _pure_single_ref("{{ vars.steps.fetch.count }}") == (
        "step", "fetch", ".count")
    assert _pure_single_ref("{{ vars.steps.fetch['hydra:member'] }}") == (
        "step", "fetch", "['hydra:member']")
    assert _pure_single_ref("{{ vars.my_ip }}") == ("var", "my_ip", "")
    # filtered → skip (resolver Tier 3 owns it)
    assert _pure_single_ref("{{ vars.steps.fetch.count | int }}") is None
    # interpolation → skip (coerces to str)
    assert _pure_single_ref("ip is {{ vars.my_ip }}") is None
    # function call → skip
    assert _pure_single_ref("{{ foo() }}") is None
    # non-jinja literal → skip
    assert _pure_single_ref("10.0.0.1") is None
    assert _pure_single_ref(42) is None


# ---- unit: shape → tag + compatibility ------------------------------------

def test_shape_to_src_tag():
    assert _shape_to_src_tag(_shape_scalar("integer")) == "int"
    assert _shape_to_src_tag(_shape_scalar("boolean")) == "bool"
    assert _shape_to_src_tag(_shape_scalar("string")) == "str"
    assert _shape_to_src_tag(_shape_scalar("any")) is None  # too vague
    assert _shape_to_src_tag(_shape_list(_shape_scalar("any"))) == "list"
    assert _shape_to_src_tag(_shape_object({})) == "dict"


def test_source_target_compatible():
    # untyped/vague → always tolerated
    assert _source_target_compatible("list", None)
    assert _source_target_compatible(None, "int")
    assert _source_target_compatible("str", "int")    # str coerces broadly
    assert _source_target_compatible("null", "int")
    # shape into scalar → incompatible
    assert not _source_target_compatible("list", "ipv4")
    assert not _source_target_compatible("list", "int")
    assert not _source_target_compatible("dict", "int")
    # shape into matching container → ok
    assert _source_target_compatible("list", "json_array")
    assert _source_target_compatible("dict", "json_object")
    assert not _source_target_compatible("list", "json_object")
    # scalar category crossings
    assert not _source_target_compatible("bool", "int")
    assert not _source_target_compatible("int", "bool")
    assert not _source_target_compatible("int", "ipv4")
    assert _source_target_compatible("int", "float")  # numeric promotion
    assert _source_target_compatible("int", "int")
    assert _source_target_compatible("bool", "bool")


# ---- integration: walk a hand-built playbook ------------------------------

def _coll(param_value: str, list_source: bool = False):
    """start → set_variable → connector(query_ip, ip=<param_value>)."""
    set_args = {"arg_list": [
        {"name": "the_count", "value": "123"},      # → integer
        {"name": "the_name", "value": "hello"},     # → string
    ]}
    steps = [
        Step(id="start", type="start", name="start", next="setv"),
        Step(id="setv", type="set_variable", name="Setv",
             arguments=set_args, next="call"),
        Step(id="call", type="connector", name="Call",
             arguments={"connector": "acme", "operation": "query_ip",
                        "params": {"ip": param_value}}),
    ]
    pb = Playbook(name="P", trigger_step_id="start", steps=steps)
    return Collection(name="C", playbooks=[pb])


def _ptf(target):
    return lambda c, o, p: target if p == "ip" else None


def _codes(coll, target):
    res = walk_playbook(coll, param_type_fn=_ptf(target))
    return [d.code for d in res.diagnostics]


def test_integer_var_into_ipv4_param_flags():
    coll = _coll("{{ vars.the_count }}")
    assert "type_mismatch" in _codes(coll, "ipv4")


def test_string_var_into_ipv4_param_clean():
    # string source is tolerated (could hold a valid ipv4 at runtime)
    coll = _coll("{{ vars.the_name }}")
    assert "type_mismatch" not in _codes(coll, "ipv4")


def test_correct_type_clean():
    # integer var into an integer param — fine
    coll = _coll("{{ vars.the_count }}")
    assert "type_mismatch" not in _codes(coll, "int")


def test_no_param_type_fn_skips_phase4():
    coll = _coll("{{ vars.the_count }}")
    res = walk_playbook(coll)  # no param_type_fn
    assert "type_mismatch" not in [d.code for d in res.diagnostics]


def test_filtered_ref_not_flagged_by_phase4():
    # `| int` is the resolver's Tier 3 job; the walker stays out of it
    coll = _coll("{{ vars.the_count | string }}")
    assert "type_mismatch" not in _codes(coll, "ipv4")


def test_list_step_output_into_scalar_param_flags():
    """A find_record output (list) referenced directly into an ipv4 param."""
    steps = [
        Step(id="start", type="start", name="start", next="find"),
        Step(id="find", type="find_record", name="Find",
             arguments={"module": "alerts"}, next="call"),
        Step(id="call", type="connector", name="Call",
             arguments={"connector": "acme", "operation": "query_ip",
                        "params": {"ip": "{{ vars.steps.Find }}"}}),
    ]
    pb = Playbook(name="P", trigger_step_id="start", steps=steps)
    coll = Collection(name="C", playbooks=[pb])
    res = walk_playbook(coll, param_type_fn=_ptf("ipv4"))
    assert "type_mismatch" in [d.code for d in res.diagnostics]


# ---- Phase 5: trace decisions records passes AND failures ------------------

def test_type_decisions_record_pass_and_fail():
    # mismatch case → one decision with verdict type_mismatch
    coll = _coll("{{ vars.the_count }}")
    res = walk_playbook(coll, param_type_fn=_ptf("ipv4"))
    decs = [d for b in res.branches for d in b.type_decisions]
    assert len(decs) == 1
    d = decs[0]
    assert d["param"] == "ip" and d["source_type"] == "int"
    assert d["target_type"] == "ipv4" and d["verdict"] == "type_mismatch"
    # ok case → decision recorded as ok
    res2 = walk_playbook(coll, param_type_fn=_ptf("int"))
    decs2 = [d for b in res2.branches for d in b.type_decisions]
    assert decs2 and decs2[0]["verdict"] == "ok"


def test_to_dict_carries_type_decisions():
    coll = _coll("{{ vars.the_count }}")
    res = walk_playbook(coll, param_type_fn=_ptf("ipv4"))
    d = res.to_dict()
    assert "type_decisions" in d["branches"][0]


# ---- #3: LITERAL param values are owned by the RESOLVER, not the walker ----
# The resolver's Tier-1/2.3 passes (connector_args.py) validate literal param
# values against the widget type at *compile* time — more precisely than the
# walker could (it models the real int()/float() coercion: `[1,2,3]`/`{a:1}`/
# `"abc"`/`true`/`5.5` into an integer param all error as `bad_value`, while
# `"007"`/`"123"` pass). These tests pin that the resolver owns literal #3 so a
# future walker refactor doesn't wrongly try to re-add it.

import pytest


def _lit_compile_codes(value):
    from fsr_playbooks.compiler import compile_yaml
    from fsr_playbooks._db import default_db_path
    yaml_text = f"""
collection: P
playbooks:
  - name: P1
    steps:
      - name: start
        type: start
        next: S
      - name: S
        type: connector
        arguments:
          connector: nist-nvd
          operation: cve_search
          config: ""
          params:
            resultsPerPage: {value}
"""
    res = compile_yaml(yaml_text, str(default_db_path()))
    codes = [e.code.value for e in (res.errors or [])]
    # The slim CI DB lacks nist-nvd; the widget-type pass can't run, so these
    # literal checks are only meaningful against the warmed reference DB.
    if "unknown_connector" in codes or "unknown_operation" in codes:
        pytest.skip("nist-nvd cve_search not in this DB (slim/offline)")
    return codes


def test_resolver_flags_literal_list_into_int():
    assert "bad_value" in _lit_compile_codes("[1, 2, 3]")


def test_resolver_flags_literal_dict_into_int():
    assert "bad_value" in _lit_compile_codes("{a: 1}")


def test_resolver_flags_noncoercible_string_into_int():
    assert "bad_value" in _lit_compile_codes('"abc"')


def test_resolver_allows_coercible_string_into_int():
    assert "bad_value" not in _lit_compile_codes('"123"')
