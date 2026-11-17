"""A rename the analyst ASKED for is not a silent rename.

`step_renamed_silently` fired unconditionally, at error severity, so an
analyst who typed "rename the Enrich IP step to Reputation Lookup" got their
own request back as a blocking regression: `ready_to_push` false, and the
#126 enhancement card reporting the edit as damage. The word *silently* in
the kind name described an exemption the code did not have.

`verify_enhancement` already knew which steps the user named
(`_user_referenced_steps`, feeding `behavior_changed_outside_diff`). The fix
reuses that set, narrowed by an explicit rename verb, and emits
`step_renamed_as_requested` at warning severity instead.

The exemption has to be narrow in BOTH directions, which is what these tests
pin: mentioning a step is not permission to rename it, and a rename verb
aimed at one step is not permission to rename another.
"""
from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.mcp_server.tools_enhancement import _diff_collections

_BEFORE = """
collection: Rename Fixtures
description: before/after fixture for the requested-rename exemption.

playbooks:
  - name: Suspicious IP Response
    description: fixture.
    steps:
      - name: start
        type: start
        next: Enrich IP
      - name: Enrich IP
        type: set_variable
        next: Note It
        vars:
          reputation: unknown
      - name: Note It
        type: set_variable
        vars:
          note: done
"""

_RENAMED = _BEFORE.replace("name: Enrich IP", "name: Reputation Lookup").replace(
    "next: Enrich IP", "next: Reputation Lookup")

# The SAME rename, plus a second one nobody asked for. It renames the START
# step rather than `Note It` on purpose: renaming a step also mutates the
# projection of whatever points AT it, and the rename pairing matches on
# equal projections -- so chaining two adjacent renames defeats the pairing
# for both and the case would stop testing what it claims to. That is a
# pre-existing limit of `_diff_collections`, unrelated to this exemption.
_RENAMED_PLUS = _RENAMED.replace("name: start", "name: Begin")


def _regressions(after: str, user_message):
    before_coll, _ = parse_yaml(_BEFORE)
    after_coll, _ = parse_yaml(after)
    regs, _ = _diff_collections(before_coll, after_coll, user_message)
    return {r["kind"]: r for r in regs}


def test_a_requested_rename_is_a_warning_not_a_blocker():
    regs = _regressions(_RENAMED,
                        "rename the Enrich IP step to Reputation Lookup")
    assert "step_renamed_silently" not in regs
    r = regs["step_renamed_as_requested"]
    assert r["severity"] == "warning"
    assert r["before"] == "Enrich IP" and r["after"] == "Reputation Lookup"


def test_the_consequence_still_reaches_the_analyst():
    # Demoting it must not hide it: the reason a rename matters is that
    # external vars.steps.<slug>.* consumers break, and the analyst has to
    # read that even when they asked for it.
    regs = _regressions(_RENAMED,
                        "rename the Enrich IP step to Reputation Lookup")
    assert "vars.steps" in regs["step_renamed_as_requested"]["message"]


def test_naming_a_step_is_not_permission_to_rename_it():
    # The narrowing that keeps this from being a licence to rewrite. The
    # step is named -- so `referenced` contains it -- but nothing in the ask
    # is a rename, so the old error stands.
    regs = _regressions(
        _RENAMED, "add a step after Enrich IP that creates an incident")
    assert regs["step_renamed_silently"]["severity"] == "error"
    assert "step_renamed_as_requested" not in regs


def test_a_rename_verb_does_not_cover_a_step_the_user_never_named():
    # One requested rename must not launder a second, unrequested one. The
    # assertion is on SEVERITY, not kind: the unrequested rename of `start`
    # comes back as `step_dropped` rather than `step_renamed_silently`,
    # because the rename pairing declines to pair it. Either way it blocks,
    # which is the property that matters here.
    regs = _regressions(_RENAMED_PLUS,
                        "rename the Enrich IP step to Reputation Lookup")
    assert regs["step_renamed_as_requested"]["step"] == "Enrich IP"
    blocking = {k: v for k, v in regs.items() if v["severity"] == "error"}
    assert [v["step"] for v in blocking.values()] == ["start"], blocking


def test_without_chat_context_every_rename_still_blocks():
    # `user_message=None` is the agent calling without chat context and the
    # eval harness's old path. Strict is the safe default: an exemption that
    # applied when we cannot tell what was asked would apply always.
    regs = _regressions(_RENAMED, None)
    assert regs["step_renamed_silently"]["severity"] == "error"


def test_ready_to_push_is_no_longer_blocked_by_the_analysts_own_request():
    # The end-to-end reason this matters -- the card the analyst approves.
    from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement

    out = verify_enhancement(
        _BEFORE, _RENAMED,
        user_message="rename the Enrich IP step to Reputation Lookup")
    blocking = [r for r in out.get("regressions") or []
                if r.get("severity") == "error"]
    assert blocking == [], blocking
    assert out.get("ready_to_push") is True, out.get("regressions")
