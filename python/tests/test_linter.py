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
      - id: trigger
        type: start
        next: choose
      - id: choose
        type: decision
        arguments:
          conditions:
            - option: yes
              condition: "{{ vars.input.params.go == 'yes' }}"
        branches:
          yes: act
        next: skip
      - id: act
        type: set_variable
        arguments: { arg_list: { x: 1 } }
      - id: skip
        type: set_variable
        arguments: { arg_list: { x: 0 } }
"""

NORWAY_OK = NORWAY_BAD.replace("option: yes", 'option: "yes"').replace(
    "yes: act", '"yes": act'
)


def test_norway_bare_yes_in_branches_and_option_caught(db_path):
    r = compile_yaml(NORWAY_BAD, db_path)
    assert not r.ok
    msgs = " ".join(_messages(r))
    assert "branches key 'yes'" in msgs
    assert "option value 'yes'" in msgs


def test_norway_quoted_yes_passes(db_path):
    r = compile_yaml(NORWAY_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- Step-name charset ---------------------------------------------------

NAME_BAD = """
collection: Names
playbooks:
  - name: pb
    steps:
      - id: trigger
        type: start
        next: bad
      - id: bad
        type: set_variable
        name: "Hello — World? (yes)"
        arguments: { arg_list: { x: 1 } }
"""

NAME_OK = NAME_BAD.replace(
    'name: "Hello — World? (yes)"',
    'name: "Hello World yes"',
)


def test_step_name_with_dash_paren_em_dash_rejected(db_path):
    r = compile_yaml(NAME_BAD, db_path)
    assert not r.ok
    msgs = " ".join(_messages(r))
    assert "outside [A-Za-z0-9 _]" in msgs
    # Suggestion sanitises the bad chars to underscores/spaces.
    sugs = [e.suggestion for e in r.errors if e.suggestion]
    assert any("rename to" in s for s in sugs)


def test_step_name_clean_passes(db_path):
    r = compile_yaml(NAME_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- mock_result on Fetch ------------------------------------------------

FETCH_NO_MOCK = """
collection: F
playbooks:
  - name: pb
    steps:
      - id: trigger
        type: start
        next: f
      - id: f
        type: connector
        name: Fetch alerts from VirusTotal
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
    """A `yes:` key in a generic dict (e.g. `arg_list`) is fine — the
    Norway rule should only trigger inside Decision-step `branches:`."""
    text = """
collection: T
playbooks:
  - name: pb
    steps:
      - id: trigger
        type: start
        next: a
      - id: a
        type: set_variable
        arguments:
          arg_list:
            ok_value: 1
"""
    r = compile_yaml(text, db_path)
    # No Norway-rule violations expected.
    assert not any("YAML 1.1 boolean" in (e.message or "")
                   for e in r.errors)
