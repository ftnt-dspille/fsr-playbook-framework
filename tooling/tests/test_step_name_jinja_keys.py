"""Step names become `vars.steps.<name>` attribute reads -- not statements.

The validator used to reject step names matching a list of "reserved keywords"
(`Return`, `If`, `none`, and Python-only strays like `class`/`def`/`import`),
claiming `vars.steps.<name>` "won't parse". Jinja2 reserves keywords in
STATEMENT position only; after a `.` the lexer emits a plain NAME. The rule had
no true positive available to it and blocked a playbook Fortinet ships.

These tests assert against Jinja2 itself rather than against our own opinion of
it -- that opinion is exactly what was wrong.
"""
import pytest
from jinja2 import Environment

from fsr_playbooks.compiler import compile_yaml

FORMERLY_REJECTED = [
    "Return", "If", "For", "Class", "Import",
    "none", "true", "false", "null", "and", "or", "not", "is", "in",
    "class", "def", "return", "import", "from", "as", "with",
]


@pytest.mark.parametrize("tok", FORMERLY_REJECTED)
def test_jinja_accepts_the_token_as_an_attribute(tok):
    """Ground truth: Jinja2 parses it, so we must not reject it."""
    Environment().parse("{{ vars.steps.%s.data }}" % tok)


def test_jinja_rejects_only_assignment_to_a_constant():
    """The one real restriction -- and a step name is never an assign target."""
    env = Environment()
    with pytest.raises(Exception):
        env.parse("{% set none = 5 %}")
    env.parse("{% set Return = 5 %}")      # not a constant, fine


def test_step_named_return_compiles(db_path):
    """The corpus case: `> convert json dictionary to Yaml.json`."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Return
      - name: Return
        type: set_variable
        vars:
          out: 'x'
"""
    r = compile_yaml(text, db_path)
    blocking = [e for e in r.errors if e.severity != "warning"]
    assert not blocking, [e.to_dict() for e in blocking]


def test_step_name_starting_with_a_digit_is_still_rejected(db_path):
    """The adjacent check is real: `vars.steps.2foo` genuinely won't parse."""
    with pytest.raises(Exception):
        Environment().parse("{{ vars.steps.2foo }}")

    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: 2 Bad Name
      - name: 2 Bad Name
        type: set_variable
        vars:
          out: 'x'
"""
    r = compile_yaml(text, db_path)
    assert any(e.severity != "warning" and "identifier-style" in e.message
               for e in r.errors), [e.to_dict() for e in r.errors]
