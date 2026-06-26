"""verify_playbook `disable_checks` — let a caller (pyfsr) skip groups or
individual checks. Disabled diagnostics move to evidence.suppressed (never
silent) and stop blocking ready_to_push.
"""
from fsr_playbooks.mcp_server.tools_verify import (
    verify_playbook, _resolve_disabled_codes, CHECK_GROUPS,
)

# A playbook with a hard Jinja syntax error (missing endif).
_BAD_JINJA = """
collection: C
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: S
      - name: S
        type: set_variable
        vars:
          x: "{% if vars.a %}hi"
"""


# ---- unit: resolver ------------------------------------------------------

def test_resolve_group_expands_to_codes():
    codes, unknown = _resolve_disabled_codes(["jinja"])
    assert codes == CHECK_GROUPS["jinja"]
    assert unknown == []


def test_resolve_individual_code():
    codes, unknown = _resolve_disabled_codes(["jinja_syntax_error"])
    assert codes == frozenset({"jinja_syntax_error"})
    assert unknown == []


def test_resolve_mixed_and_case_insensitive():
    codes, _ = _resolve_disabled_codes(["JINJA", "type_mismatch"])
    assert "jinja_syntax_error" in codes and "type_mismatch" in codes


def test_resolve_unknown_token_reported_but_applied():
    codes, unknown = _resolve_disabled_codes(["totally_made_up"])
    assert "totally_made_up" in codes
    assert unknown == ["totally_made_up"]


def test_resolve_empty():
    assert _resolve_disabled_codes(None) == (frozenset(), [])
    assert _resolve_disabled_codes([]) == (frozenset(), [])


# ---- integration: end-to-end through verify_playbook ---------------------

def test_jinja_error_blocks_by_default():
    r = verify_playbook(_BAD_JINJA)
    assert r["ready_to_push"] is False
    assert "jinja_syntax_error" in [f["code"] for f in r["required_fixes"]]
    assert r["suppressed_count"] == 0


def test_disable_group_suppresses_and_unblocks():
    r = verify_playbook(_BAD_JINJA, disable_checks=["jinja"])
    assert r["ready_to_push"] is True
    assert r["suppressed_count"] == 1
    assert [s["code"] for s in r["evidence"]["suppressed"]] == ["jinja_syntax_error"]
    # The suppressed diagnostic is gone from the blocking list.
    assert "jinja_syntax_error" not in [f["code"] for f in r["required_fixes"]]


def test_disable_by_exact_code():
    r = verify_playbook(_BAD_JINJA, disable_checks=["jinja_syntax_error"])
    assert r["ready_to_push"] is True
    assert r["suppressed_count"] == 1


def test_disable_unrelated_group_leaves_error_blocking():
    # Disabling `type` must NOT suppress a jinja error.
    r = verify_playbook(_BAD_JINJA, disable_checks=["type"])
    assert r["ready_to_push"] is False
    assert r["suppressed_count"] == 0


def test_unknown_token_surfaced_in_evidence():
    r = verify_playbook(_BAD_JINJA, disable_checks=["nope"])
    assert r["evidence"]["disabled_checks"]["unknown_tokens"] == ["nope"]
