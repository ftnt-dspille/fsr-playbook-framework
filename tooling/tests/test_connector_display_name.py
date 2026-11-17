"""`display_name:` is the friendly spelling of wire `arguments.name`.

The decompiler renames wire `arguments.name` (the connector's display label) to
`display_name:` because it collides with the IR step field `name` (the canvas
node name). The compiler had no inverse. Two consequences, both found by the
live round-trip test once it could actually run:

  * a custom connector label survived export and was silently DROPPED on
    re-import -- `display_name` rode through to the wire as a key FSR does not
    read, while `name` was re-stamped from the catalog;
  * `send_email`, a connector-family alias, rejected the key outright, so a
    pulled send_email step could not recompile at all.

`display_name` is our spelling, not FSR's: of 2,185 Connectors steps in the
shipped-pack corpus 2,183 carry `name`, and none carry a meaningful
`display_name`. So it must never reach the wire.
"""
import pytest

from fsr_playbooks.compiler import compile_yaml

CONNECTOR_STEP = """
      - name: s
        type: connector
        connector: cyops_utilities
        operation: no_op
"""
SEND_EMAIL_STEP = """
      - name: s
        type: send_email
        to: ['someone@example.com']
        subject: hi
        body: x
"""


def _emit(db_path, step_body: str) -> tuple[list, dict | None]:
    text = f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: s
{step_body}
"""
    r = compile_yaml(text, db_path)
    blocking = [e for e in r.errors if e.severity != "warning"]
    if not r.fsr_json:
        return blocking, None
    for wf in r.fsr_json["data"][0]["workflows"]:
        for st in wf["steps"]:
            if st.get("name") == "s":
                return blocking, st["arguments"]
    return blocking, None


def test_display_name_becomes_the_wire_label(db_path):
    blocking, args = _emit(db_path, CONNECTOR_STEP + "        display_name: 'My Custom Label'\n")
    assert not blocking, [e.to_dict() for e in blocking]
    assert args["name"] == "My Custom Label"


def test_display_name_never_reaches_the_wire(db_path):
    """FSR does not read this key -- shipping it is noise at best."""
    _, args = _emit(db_path, CONNECTOR_STEP + "        display_name: 'My Custom Label'\n")
    assert "display_name" not in args


def test_catalog_label_still_applies_without_display_name(db_path):
    """The pre-existing default must be untouched -- no regression."""
    _, args = _emit(db_path, CONNECTOR_STEP)
    assert args["name"] == "Utilities"


def test_send_email_accepts_display_name(db_path):
    """A connector-family alias; a pulled send_email step carries it."""
    blocking, args = _emit(db_path, SEND_EMAIL_STEP + "        display_name: 'Mailer'\n")
    assert not blocking, [e.to_dict() for e in blocking]
    assert args["name"] == "Mailer"
    assert "display_name" not in args


def test_send_email_without_display_name_unchanged(db_path):
    blocking, args = _emit(db_path, SEND_EMAIL_STEP)
    assert not blocking, [e.to_dict() for e in blocking]
    assert "display_name" not in args


@pytest.mark.parametrize("step_body", [CONNECTOR_STEP, SEND_EMAIL_STEP])
def test_round_trip_preserves_a_custom_label(db_path, step_body):
    """decompile(compile(x)) must give back the label it was handed."""
    from fsr_playbooks.compiler.decompiler import decompile_to_yaml

    _, args = _emit(db_path, step_body + "        display_name: 'Round Trip Label'\n")
    assert args["name"] == "Round Trip Label"

    text = f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: s
{step_body}        display_name: 'Round Trip Label'
"""
    r = compile_yaml(text, db_path)
    pulled = decompile_to_yaml(r.fsr_json, db_path)
    assert "Round Trip Label" in pulled, pulled
