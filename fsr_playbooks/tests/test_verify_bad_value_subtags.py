"""Fine-grained `bad_value` check sub-tags.

`bad_value` is emitted from ~60 sites, so historically it could only be
toggled coarsely via the `value` group. These tests cover the sub-tag split:
a `CompileError.check` tag lets `disable_checks=["picklist"|"param_type"|
"snippet"]` silence just one class of `bad_value` without touching the rest,
and without renaming the coarse `code` (which every consumer relies on).
"""
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.mcp_server.tools_verify import (
    verify_playbook, _resolve_disabled_codes, _finalize, CHECK_GROUPS,
)


# ---- unit: CompileError carries the sub-tag --------------------------------

def test_compile_error_check_defaults_none_and_serializes():
    e = CompileError(code=ErrorCode.BAD_VALUE, message="x")
    assert e.check is None
    assert e.to_dict()["check"] is None


def test_compile_error_check_roundtrips():
    e = CompileError(code=ErrorCode.BAD_VALUE, message="x", check="picklist_drift")
    assert e.to_dict()["check"] == "picklist_drift"


# ---- unit: the three new groups map to sub-tags ----------------------------

def test_subtag_groups_registered():
    assert CHECK_GROUPS["picklist"] == frozenset({"picklist_drift"})
    assert CHECK_GROUPS["param_type"] == frozenset({"param_type"})
    assert CHECK_GROUPS["snippet"] == frozenset({"snippet_sandbox"})
    # The coarse catch-all is untouched — nothing downstream breaks.
    assert CHECK_GROUPS["value"] == frozenset({"bad_value"})


def test_resolve_subtag_group_expands_to_check():
    for group, tag in (("picklist", "picklist_drift"),
                       ("param_type", "param_type"),
                       ("snippet", "snippet_sandbox")):
        codes, unknown = _resolve_disabled_codes([group])
        assert codes == frozenset({tag})
        assert unknown == []


# ---- unit: _finalize suppresses on the `check` sub-tag ----------------------

def _fix(code="bad_value", check=None):
    return {"code": code, "message": "m", "path": "p", "check": check}


def test_finalize_suppresses_by_check_subtag():
    r = _finalize([], [_fix(check="picklist_drift")], [], {},
                  disabled_codes=frozenset({"picklist_drift"}))
    assert r["ready_to_push"] is True
    assert r["suppressed_count"] == 1


def test_finalize_subtag_does_not_suppress_other_subtag():
    # Disabling `snippet` must NOT silence a picklist-drift bad_value.
    r = _finalize([], [_fix(check="picklist_drift")], [], {},
                  disabled_codes=frozenset({"snippet_sandbox"}))
    assert r["ready_to_push"] is False
    assert r["suppressed_count"] == 0


def test_finalize_coarse_value_still_suppresses_tagged_bad_value():
    # The coarse `value` group (matches on `code`) keeps working even for a
    # diagnostic that also carries a `check` sub-tag — backward-compatible.
    r = _finalize([], [_fix(check="param_type")], [], {},
                  disabled_codes=CHECK_GROUPS["value"])
    assert r["ready_to_push"] is True
    assert r["suppressed_count"] == 1


# ---- integration: snippet-sandbox path (no warmed catalog needed) ----------

# A code_snippet that calls a sandbox-banned builtin (`open`). This fires from
# the linter without a warmed catalog, so it exercises the whole compile →
# verify → suppress path offline.
_BANNED_SNIPPET = """
collection: C
playbooks:
  - name: P
    is_active: true
    steps:
      - name: trigger
        type: start
        next: Run snippet
      - name: Run snippet
        type: code_snippet
        code: |
          f = open("/etc/passwd")
          data = f.read()
"""


def test_snippet_sandbox_blocks_by_default_and_is_tagged():
    r = verify_playbook(_BANNED_SNIPPET)
    assert r["ready_to_push"] is False
    tagged = [f for f in r["required_fixes"]
              if f.get("code") == "bad_value" and f.get("check") == "snippet_sandbox"]
    assert tagged, r["required_fixes"]


def test_snippet_group_suppresses_and_unblocks():
    r = verify_playbook(_BANNED_SNIPPET, disable_checks=["snippet"])
    assert r["ready_to_push"] is True
    assert r["suppressed_count"] >= 1
    assert all(f.get("check") != "snippet_sandbox" for f in r["required_fixes"])


def test_unrelated_subtag_leaves_snippet_ban_blocking():
    # Disabling `param_type` must NOT suppress a snippet-sandbox ban.
    r = verify_playbook(_BANNED_SNIPPET, disable_checks=["param_type"])
    assert r["ready_to_push"] is False
    assert r["suppressed_count"] == 0
