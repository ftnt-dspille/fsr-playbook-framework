"""dispatch is a fixed sequence of named stages (llm/tools.py).

It used to be one ~360-line function with a dozen inline special cases; a new
rule meant another branch in the middle of it. Now each rule is a stage with
its own test, and dispatch itself only sequences them.
"""
from __future__ import annotations

import inspect

from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.tool_models import coerce_json_string_args


def _call(name, args, internal=False):
    return T._Call(name=name, spec=T.REGISTRY[name], args=dict(args),
                   internal=internal, session_id=None, approved_by=None,
                   summary=None)


def test_refusals_run_before_any_argument_rewrite():
    names = [s.__name__ for s in T._DISPATCH_STAGES]
    assert names[0] == "_refuse_for_turn"
    assert names.index("_coerce_args") < names.index("_check_args")


def test_dispatch_only_sequences():
    assert len(inspect.getsource(T.dispatch).splitlines()) < 50


def test_wire_approved_is_rejected_and_internal_is_taken_off():
    spec = T.REGISTRY["find_connector"]
    out = T._accept("find_connector", spec, {"_approved": True}, internal=False,
                    session_id=None, approved_by=None)
    assert out["code"] == "reserved_key_rejected"
    c = T._accept("find_connector", spec, {"q": "x", "_approved": True,
                                           "_summary": "s"},
                  internal=True, session_id=None, approved_by="system:autonomy")
    assert c.args == {"q": "x"} and c.approved_by == "system:autonomy" and c.summary == "s"


def test_emit_card_fields_fold_into_payload():
    c = _call("emit_card", {"card_type": "playbook_offer", "id": "p1", "summary": "s"})
    assert T._fold_emit_card_payload(c) is None
    assert c.args == {"card_type": "playbook_offer",
                      "payload": {"id": "p1", "summary": "s"}}


def test_run_op_params_as_json_or_blank_string():
    assert coerce_json_string_args("run_op", {"connector": "c", "op": "o",
                                              "params": '{"ip": "1.2.3.4"}'})["params"] == \
        {"ip": "1.2.3.4"}
    assert "params" not in coerce_json_string_args(
        "run_op", {"connector": "c", "op": "o", "params": "  "})


def test_verify_defaults_to_the_live_probe_unless_told():
    c = _call("verify_playbook", {"yaml_text": "x"})
    T._default_live_probe(c)
    assert c.args["live_probe"] is True
    c = _call("verify_playbook", {"yaml_text": "x", "live_probe": False})
    T._default_live_probe(c)
    assert c.args["live_probe"] is False
