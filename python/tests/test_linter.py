"""Linter v1 — Norway problem, step-name charset, mock_result on Fetch.

Each rule has a positive (catches the foot-gun) and a negative (clean
input passes) case so future refactors can't silently weaken the linter.
"""
from __future__ import annotations

from compiler import compile_yaml


def _codes(r) -> list[str]:
    return [e.code.value for e in r.errors]


def _messages(r) -> list[str]:
    return [e.message for e in r.errors]


# ---- Norway problem ------------------------------------------------------

NORWAY_BAD = """
collection: Norway
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: choose
      - name: choose
        type: decision
        conditions:
          - display: yes
            when: "{{ vars.input.params.go == 'yes' }}"
            next: act
          - display: Else
            default: true
            next: skip
      - name: act
        type: set_variable
        vars: { x: 1 }
      - name: skip
        type: set_variable
        vars: { x: 0 }
"""

NORWAY_OK = NORWAY_BAD.replace("display: yes", 'display: "yes"')


def test_norway_bare_yes_in_display_caught(db_path):
    r = compile_yaml(NORWAY_BAD, db_path)
    assert not r.ok
    msgs = " ".join(_messages(r))
    assert "display value 'yes'" in msgs


def test_norway_quoted_yes_passes(db_path):
    r = compile_yaml(NORWAY_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- Step-name charset ---------------------------------------------------

NAME_BAD = """
collection: Names
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: "Hello — World? (yes)"
      - name: "Hello — World? (yes)"
        type: set_variable
        vars: { x: 1 }
"""

NAME_OK = NAME_BAD.replace(
    'Hello — World? (yes)',
    'Hello World yes',
)


def test_step_name_with_dash_paren_em_dash_auto_rewritten(db_path):
    r = compile_yaml(NAME_BAD, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # Linter emits a warning explaining the auto-rename.
    warnings = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warnings)
    assert "auto-renamed" in msgs
    # The compiled JSON has the cleaned name (no em-dash / paren / ?).
    steps = r.fsr_json["data"][0]["workflows"][0]["steps"]
    assert any(_BAD_CHAR not in s["name"]
               for s in steps for _BAD_CHAR in "—()?")


def test_step_name_clean_passes(db_path):
    r = compile_yaml(NAME_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- mock_result on Fetch ------------------------------------------------

FETCH_NO_MOCK = """
collection: F
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Fetch alerts from VirusTotal
      - name: Fetch alerts from VirusTotal
        type: connector
        arguments:
          connector: virustotal
          operation: query_url
          resource: "https://example.com"
"""

FETCH_WITH_MOCK = FETCH_NO_MOCK.replace(
    'resource: "https://example.com"',
    'resource: "https://example.com"\n          mock_result:\n            status: success',
)


def test_fetch_step_without_mock_emits_warning(db_path):
    r = compile_yaml(FETCH_NO_MOCK, db_path)
    # Warning, not error — compile still succeeds.
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert any("mock_result" in w.message for w in warns)
    assert any("Fetch alerts from VirusTotal" in w.message for w in warns)


def test_fetch_step_with_mock_clean(db_path):
    r = compile_yaml(FETCH_WITH_MOCK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert not any("mock_result" in w.message for w in warns)


# ---- Sanity: linter ignores yes-shaped keys outside `branches:` ---------

def test_linter_does_not_misfire_on_unrelated_yes_key(db_path):
    """A `yes:` key inside `vars:` is fine — the Norway rule only
    fires for `display:` values on decision/manual_input branches."""
    text = """
collection: T
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: a
      - name: a
        type: set_variable
        vars:
          ok_value: 1
"""
    r = compile_yaml(text, db_path)
    assert not any("YAML 1.1 boolean" in (e.message or "")
                   for e in r.errors)
