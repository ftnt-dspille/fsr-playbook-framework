"""A manual_input's `message` must never reach FSR as a bare string.

`message` reads like prose, and the friendly form encourages writing it that
way. On a real appliance it is not prose: it is the comment/notification object
`{content, records, tags, tenant, type}` -- 11 of the 12 manual_inputs captured
from live playbooks carry a dict there. Handing FSR a string makes its workflow
engine call `.get()` on it, and the RUN DIES with

    'str' object has no attribute 'get'

Nothing catches that earlier: the YAML validates, the collection compiles, the
playbook pushes clean, and the failure only appears when someone executes it.
Live on 8.0.0 it took out `offer_playbook_runs` -- the last check in the P4 arc
-- while every offline gate stayed green.

The prompt already has a home (`input.schema.description`), so a string is
folded in there and the scalar dropped. A dict is a genuine FSR notification
and rides through untouched.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml


def _gate_args(step_yaml: str) -> dict:
    src = f"""
collection: t
playbooks:
  - name: T
    trigger: start
    steps:
      - {{type: start, name: Start, next: Gate}}
{step_yaml}
      - {{type: set_variable, name: B, vars: {{x: 1}}}}
      - {{type: set_variable, name: S, vars: {{y: 2}}}}
"""
    r = compile_yaml(src, default_db_path())
    assert r.ok, r.errors
    steps = r.fsr_json["data"][0]["workflows"][0]["steps"]
    return next(s for s in steps if s["name"] == "Gate")["arguments"]


def test_a_string_message_never_reaches_the_wire():
    """The regression: a scalar `message` is what killed the live run."""
    a = _gate_args(
        '      - {type: manual_input, name: Gate, message: "Proceed?",'
        ' options: [{display: Confirm, next: B}, {display: Stop, next: S}]}'
    )
    assert not isinstance(a.get("message"), str), (
        "a bare string `message` reached FSR; the engine will call .get() on it "
        "and the run will die with \"'str' object has no attribute 'get'\""
    )


def test_the_string_message_becomes_the_prompt_body():
    """Dropping it must not lose the text the author wrote."""
    a = _gate_args(
        '      - {type: manual_input, name: Gate, message: "Proceed?",'
        ' options: [{display: Confirm, next: B}, {display: Stop, next: S}]}'
    )
    assert a["input"]["schema"]["description"] == "Proceed?"


def test_an_explicit_description_wins_over_message():
    a = _gate_args(
        '      - {type: manual_input, name: Gate, message: "ignored",'
        ' description: "the real prompt",'
        ' options: [{display: Confirm, next: B}, {display: Stop, next: S}]}'
    )
    assert a["input"]["schema"]["description"] == "the real prompt"


def test_a_dict_message_is_a_real_notification_and_survives():
    """Only the string form is wrong -- don't break the genuine feature."""
    a = _gate_args(
        '      - type: manual_input\n'
        '        name: Gate\n'
        '        message: {content: "<p>hi</p>", records: "", tags: []}\n'
        '        options: [{display: Confirm, next: B}, {display: Stop, next: S}]'
    )
    assert isinstance(a.get("message"), dict)
    assert a["message"]["content"] == "<p>hi</p>"
