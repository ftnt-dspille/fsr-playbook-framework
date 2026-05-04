"""Strict whitelist + canonical-form pass-through for manual_input.

Regression coverage for the silent-drop trap that produced the
screenshot-YAML bug: the resolver used to accept any top-level keys on
manual_input (including `label`, `message`, `type: textarea`) and
silently fill in defaults, leaving the deployed step rendering only a
default Continue button.
"""
from __future__ import annotations

from compiler import compile_yaml
from compiler.errors import ErrorCode


def _wrap(args_block: str, branches_block: str = "") -> str:
    """Wrap a manual_input arguments block in a minimal compilable
    playbook. Indented to match the test fixtures' 8-space step depth."""
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
{args_block}{branches_block}        next: stop
      - id: stop
        type: stop
"""


# ---- friendly form -----------------------------------------------

def test_friendly_form_compiles_clean(db_path):
    text = _wrap(
        "          title: Approve?\n"
        "          description: Click approve\n"
        "          options:\n"
        "            - {option: approve, primary: true}\n"
        "            - {option: reject}\n",
        branches_block=(
            "        branches:\n"
            "          approve: stop\n"
            "          reject: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_friendly_form_options_string_shorthand(db_path):
    """Options list of bare strings should expand."""
    text = _wrap(
        "          title: Pick\n"
        "          options: [approve, reject]\n",
        branches_block=(
            "        branches:\n"
            "          approve: stop\n"
            "          reject: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_friendly_form_default_continue_when_no_options(db_path):
    """No options at all → resolver supplies a primary 'Continue'."""
    text = _wrap("          title: Continue?\n")
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


# ---- canonical wire form -----------------------------------------

def test_canonical_form_passes_through(db_path):
    """An author who hand-writes the full FSR shape should not get
    rejected — every key is on the canonical whitelist."""
    text = _wrap(
        "          type: InputBased\n"
        "          input:\n"
        "            schema:\n"
        "              title: T\n"
        "              description: D\n"
        "              inputVariables: []\n"
        "          response_mapping:\n"
        "            options:\n"
        "              - {option: Continue, primary: true}\n"
        "            duplicateOption: false\n"
        "            customSuccessMessage: ok\n"
        "          record: ''\n"
        "          owner_detail: {isAssigned: false}\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


# ---- the trap: unknown keys ---------------------------------------

def test_unknown_key_label_rejected(db_path):
    """The bug from the screenshot: `label` is not a valid key."""
    text = _wrap("          label: Message\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "label" in e.message


def test_unknown_key_message_rejected(db_path):
    text = _wrap("          message: hello\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "message" in e.message


def test_unknown_key_timeout_rejected(db_path):
    """`timeout` is silently ignored by FSR — must surface to author."""
    text = _wrap("          timeout: 3600\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "timeout" in e.message


# ---- the trap: bad `type` value ----------------------------------

def test_type_textarea_rejected(db_path):
    """`type: textarea` is not a real FSR ManualInput dispatch."""
    text = _wrap("          type: textarea\n          title: hi\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "InputBased" in e.message


def test_type_single_select_rejected(db_path):
    """Old `type: single-select` shape — pre-fix examples used it."""
    text = _wrap("          type: single-select\n          title: hi\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "InputBased" in e.message


# ---- the trap: input must be a dict ------------------------------

def test_input_string_rejected_with_pointer(db_path):
    """An LLM that emits `input: "some string"` would crash FSR with
    `'str' object has no attribute 'get'`. Resolver catches it early
    and points to the right shape."""
    text = _wrap('          input: "some string"\n')
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "must be a mapping" in e.message
