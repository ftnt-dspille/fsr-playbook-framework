"""Three defects found by running playbooks on a live 8.0 box, each of which
compiled green and then silently did nothing:

1. `vars.steps['Analyst IP Action']` -- the display name in subscript form.
   Step keys replace spaces with underscores (the run env keys are
   `Fetch_Alert`, `Read_Full_Alert`, ...). A repair turn "fixed" a broken
   reference this way; the subscript spelling was never checked.
2. A find_record's output is a plain LIST of records (with or without
   `partial:`). `.records` and `['hydra:member']` -- both of which our own
   docs taught -- render empty.
3. `op:` on a find_record filter (the trigger `when:` spelling) was not read:
   it rode to the wire beside a defaulted `operator: eq`, so `op: contains`
   searched for an exact match and found nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks.compiler.pipeline import compile_yaml
from fsr_playbooks.mcp_server._shared import DB_PATH
from fsr_playbooks.mcp_server.tools_verify import verify_playbook

GATE = """\
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Analyst IP Action
      - name: Analyst IP Action
        type: manual_input
        title: Which IP?
        inputs:
          - name: target_ip
            label: IP address
            kind: ipv4
        options:
          - display: go
            primary: true
            next: Use It
      - name: Use It
        type: set_variable
        vars:
          ip: "{{ REF.input.target_ip }}"
"""


def _fixes(yaml_text):
    return verify_playbook(yaml_text)["required_fixes"]


@pytest.mark.parametrize("ref", ["vars.steps.Analyst_IP_Action",
                                 "vars.steps['Analyst_IP_Action']"])
def test_the_underscore_key_resolves(ref):
    assert _fixes(GATE.replace("REF", ref)) == []


def test_the_display_name_in_a_subscript_is_an_error_naming_the_key():
    (fix,) = _fixes(GATE.replace("REF", "vars.steps['Analyst IP Action']"))
    assert "replace spaces with underscores" in fix["message"]
    assert fix["suggestion"] == "use vars.steps.Analyst_IP_Action"


def test_an_unknown_subscript_key_is_an_error():
    (fix,) = _fixes(GATE.replace("REF", "vars.steps['Nope']"))
    assert "no step with jinja-key 'Nope'" in fix["message"]


FIND = """\
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Fetch Alert
      - name: Fetch Alert
        type: find_record
        module: alerts
        limit: 2
        filters:
          - field: name
            FILTER_OP: contains
            value: "a"
        next: Look
      - name: Look
        type: set_variable
        vars:
          x: "{{ EXPR }}"
"""


def _find(expr, op_key="operator"):
    return FIND.replace("EXPR", expr).replace("FILTER_OP", op_key)


@pytest.mark.parametrize("expr", [
    "vars.steps.Fetch_Alert[0]['@id']",
    "vars.steps.Fetch_Alert | length",
])
def test_find_record_output_indexed_as_a_list_is_clean(expr):
    assert _fixes(_find(expr)) == []


@pytest.mark.parametrize("expr", [
    "vars.steps.Fetch_Alert.records[0]['@id']",
    "vars.steps.Fetch_Alert['hydra:member'][0]['@id']",
])
def test_find_record_output_read_as_a_mapping_is_an_error(expr):
    (fix,) = _fixes(_find(expr))
    assert "LIST of records" in fix["message"]
    assert "vars.steps.Fetch_Alert[0]" in fix["suggestion"]


def _wire_filters(yaml_text):
    r = compile_yaml(yaml_text, Path(DB_PATH))
    assert not [e for e in r.errors if e.severity == "error"], r.errors
    step = next(s for s in r.fsr_json["data"][0]["workflows"][0]["steps"]
                if s["name"] == "Fetch Alert")
    return step["arguments"]["query"]["filters"]


def test_op_on_a_find_filter_is_the_operator():
    expr = "vars.steps.Fetch_Alert | length"
    assert _wire_filters(_find(expr, "op")) == _wire_filters(_find(expr))
    (f,) = _wire_filters(_find(expr, "op"))
    assert f["operator"] == f["_operator"] == "like" and "op" not in f


def test_op_and_operator_disagreeing_is_an_error():
    y = _find("vars.steps.Fetch_Alert | length").replace(
        "            operator: contains\n",
        "            operator: eq\n            op: contains\n")
    r = compile_yaml(y, Path(DB_PATH))
    assert any("sets both operator" in e.message for e in r.errors)


def test_get_step_type_teaches_the_list_shape():
    from fsr_playbooks.mcp_server.tools_discovery import get_step_type
    md = get_step_type("find_record")["markdown"]
    assert "LIST of records" in md and "[0]['@id']" in md
    assert "records are at `vars.steps.<name>['hydra:member']`" not in md
