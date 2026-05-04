"""Friendly `inputs:` expansion in manual_input.

Each `kind:` should expand to FSR's canonical inputVariable shape with
the right (formType, dataType, type, templateUrl) tuple. Verified
against live exports under fortisoar/SPs/playbooks/.
"""
from __future__ import annotations

from compiler import compile_yaml
from compiler.errors import ErrorCode


def _compile_and_get_inputs(db_path, inputs_yaml: str):
    """Compile a manual_input step with the given `inputs:` block and
    return its expanded `inputVariables` list."""
    text = f"""
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - id: start
        type: start
        next: ask
      - id: ask
        type: manual_input
        name: Ask
        arguments:
          title: Form
          inputs:
{inputs_yaml}
        next: stop
      - id: stop
        type: stop
"""
    res = compile_yaml(text, db_path)
    assert res.ok, [str(e) for e in res.errors]
    for step in res.fsr_json["data"][0]["workflows"][0]["steps"]:
        if step.get("name") == "Ask":
            return step["arguments"]["input"]["schema"]["inputVariables"]
    raise AssertionError("no Ask step in compiled output")


def test_kind_text_expands(db_path):
    fields = _compile_and_get_inputs(
        db_path, "            - {name: ticket, kind: text, label: 'Ticket'}\n",
    )
    assert len(fields) == 1
    f = fields[0]
    assert f["name"] == "ticket"
    assert f["label"] == "Ticket"
    assert f["formType"] == "text"
    assert f["dataType"] == "text"
    assert f["type"] == "string"
    assert f["templateUrl"].endswith("/input.html")


def test_kind_textarea_expands(db_path):
    fields = _compile_and_get_inputs(
        db_path, "            - {name: notes, kind: textarea}\n",
    )
    assert fields[0]["formType"] == "textarea"
    assert fields[0]["dataType"] == "text"
    assert fields[0]["type"] == "string"


def test_kind_select_expands_with_options(db_path):
    fields = _compile_and_get_inputs(
        db_path,
        "            - {name: sev, kind: select, options: [Low, Med, High]}\n",
    )
    f = fields[0]
    assert f["formType"] == "dynamicList"
    assert f["dataType"] == "dynamicList"
    assert f["type"] == "array"
    assert f["templateUrl"].endswith("/dynamicList.html")
    assert f["options"] == ["Low", "Med", "High"]


def test_kind_checkbox_expands(db_path):
    fields = _compile_and_get_inputs(
        db_path,
        "            - {name: notify, kind: checkbox, default: false}\n",
    )
    f = fields[0]
    assert f["formType"] == "checkbox"
    assert f["dataType"] == "checkbox"
    assert f["type"] == "boolean"
    assert f["defaultValue"] is False


def test_kind_richtext_expands_to_html_editor(db_path):
    fields = _compile_and_get_inputs(
        db_path, "            - {name: body, kind: richtext}\n",
    )
    assert fields[0]["formType"] == "html"
    assert fields[0]["templateUrl"].endswith("/htmlEditor.html")


def test_kind_integer_expands(db_path):
    fields = _compile_and_get_inputs(
        db_path, "            - {name: count, kind: integer}\n",
    )
    assert fields[0]["formType"] == "integer"
    assert fields[0]["type"] == "integer"


def test_label_defaults_to_name(db_path):
    fields = _compile_and_get_inputs(
        db_path, "            - {name: foo, kind: text}\n",
    )
    assert fields[0]["label"] == "foo"


def test_required_flag_flows_through(db_path):
    fields = _compile_and_get_inputs(
        db_path,
        "            - {name: x, kind: text, required: true}\n",
    )
    assert fields[0]["required"] is True


def test_pre_expanded_field_passes_through(db_path):
    """If the author hand-rolls a full FSR field dict, the resolver
    must not second-guess it."""
    fields = _compile_and_get_inputs(
        db_path,
        '            - name: bespoke\n'
        '              type: array\n'
        '              formType: dynamicList\n'
        '              dataType: dynamicList\n'
        '              templateUrl: app/components/form/fields/dynamicList.html\n'
        '              options: ["a", "b"]\n',
    )
    assert fields[0]["name"] == "bespoke"
    assert fields[0]["formType"] == "dynamicList"


# ---- error paths -------------------------------------------------

def _err(text, db_path):
    return compile_yaml(text, db_path).errors


def _yaml_with_inputs(inputs_yaml: str) -> str:
    return f"""
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - id: start
        type: start
        next: ask
      - id: ask
        type: manual_input
        name: Ask
        arguments:
          title: Form
          inputs:
{inputs_yaml}
        next: stop
      - id: stop
        type: stop
"""


def test_missing_name_is_error(db_path):
    errs = _err(_yaml_with_inputs(
        "            - {kind: text, label: Foo}\n"
    ), db_path)
    e = next(e for e in errs if e.code is ErrorCode.MISSING_FIELD)
    assert "name" in e.message


def test_missing_kind_is_error(db_path):
    errs = _err(_yaml_with_inputs(
        "            - {name: foo, label: Foo}\n"
    ), db_path)
    e = next(e for e in errs if e.code is ErrorCode.BAD_VALUE)
    assert "kind" in e.message


def test_unknown_kind_is_error(db_path):
    errs = _err(_yaml_with_inputs(
        "            - {name: foo, kind: bogus}\n"
    ), db_path)
    e = next(e for e in errs if e.code is ErrorCode.BAD_VALUE)
    assert "bogus" in e.message
    # Suggestion should list the legal kinds.
    assert "text" in e.message and "select" in e.message


def test_select_without_options_is_error(db_path):
    errs = _err(_yaml_with_inputs(
        "            - {name: foo, kind: select}\n"
    ), db_path)
    e = next(e for e in errs if e.code is ErrorCode.MISSING_FIELD)
    assert "options" in e.message


def test_unknown_per_field_key_is_error(db_path):
    """Catches typos like `message:` on an inputs entry."""
    errs = _err(_yaml_with_inputs(
        "            - {name: foo, kind: text, message: oops}\n"
    ), db_path)
    e = next(e for e in errs if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "message" in e.message
