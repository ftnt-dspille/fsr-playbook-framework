"""Phase 0 (STATIC_TYPE_FLOW_PLAN) — branch enumeration on the resolved IR.

The typed walker is branch-aware (each trigger→leaf path gets its own
`typed_env`; a `vars.steps.X` ref resolves only against producers on its
branch), but it only forks at `decision`/`manual_input` steps whose
`branches` dict is populated. `branches` is filled by the *resolver*, not
the parser — so walking a fresh `parse_yaml` IR (branches={}) stops at the
first decision. `verify_playbook` must walk `cres.ir` (the resolved IR)
instead. These tests pin that.
"""
from pathlib import Path

from fsr_playbooks.compiler import compile_yaml, parse_yaml
from fsr_playbooks.compiler.typed_walker import walk_playbook

DB = Path("data/fsr_reference.db")

_DECISION = Path("examples/decision_branch.yaml").read_text()


def _walk_resolved(text: str):
    cres = compile_yaml(text, DB)
    assert cres.ir is not None, "compile produced no IR"
    return walk_playbook(cres.ir)


# ---- the dormant-fork defect, pinned both ways -----------------------------

def test_reparse_collapses_to_single_branch():
    """Regression-anchor: the *old* behavior (walk a fresh parse) sees only
    one branch because decision routing is unresolved."""
    coll, _ = parse_yaml(_DECISION)
    w = walk_playbook(coll)
    assert len(w.branches) == 1


def test_resolved_ir_enumerates_both_arms():
    w = _walk_resolved(_DECISION)
    assert len(w.branches) == 2
    # The two arms diverge at the decision step's targets.
    leaves = {b.step_ids[-1] for b in w.branches}
    assert leaves == {"escalate_to_tier_2", "log_low_severity"}


def test_branch_typed_envs_differ():
    # typed_env is keyed by jinja-key (display name, spaces→underscores,
    # case preserved) — not the lowercased step id.
    w = _walk_resolved(_DECISION)
    env_keysets = [frozenset(b.typed_env.keys()) for b in w.branches]
    assert env_keysets[0] != env_keysets[1]
    all_keys = set().union(*env_keysets)
    assert "Escalate_to_Tier_2" in all_keys
    assert "Log_low_severity" in all_keys
    # No single branch sees both terminal arms.
    for ks in env_keysets:
        assert not ({"Escalate_to_Tier_2", "Log_low_severity"} <= ks)


# ---- cross-branch references are now caught --------------------------------

# set_variable outputs are rewritten by the resolver to `vars.<name>`
# (not `vars.steps.<step>`), so a cross-branch *step-output* reference must
# use a step type whose output survives as `vars.steps.<step>` — e.g.
# find_record. The Log-low arm references Find_Alerts, which only runs on
# the high arm.
_CROSS_BRANCH = """
collection: t
playbooks:
  - name: Cross Branch
    steps:
      - name: start
        type: start
        next: Branch
      - name: Branch
        type: decision
        conditions:
          - display: high
            when: "{{ vars.input.records[0].severity == 'high' }}"
            next: Find Alerts
          - display: Else
            default: true
            next: Log low
      - name: Find Alerts
        type: find_record
        module: alerts
        query: []
      - name: Log low
        type: set_variable
        vars:
          note: "{{ vars.steps.Find_Alerts[0].name }}"
"""


def test_cross_branch_reference_flagged():
    w = _walk_resolved(_CROSS_BRANCH)
    bad = [d for d in w.diagnostics if d.code == "unreachable_step_reference"]
    assert bad, "cross-branch vars.steps ref should be unreachable"
    # It is attributed to the Log low branch only.
    assert any(d.step == "log_low" for d in bad)
    assert all(b.name != "branch:high" or
               not any(d.code == "unreachable_step_reference"
                       for d in b.diagnostics)
               for b in w.branches)


# Find Alerts runs above Announce on the SAME branch — the ref is clean.
_SAME_BRANCH = """
collection: t
playbooks:
  - name: Same Branch
    steps:
      - name: start
        type: start
        next: Branch
      - name: Branch
        type: decision
        conditions:
          - display: high
            when: "{{ vars.input.records[0].severity == 'high' }}"
            next: Find Alerts
          - display: Else
            default: true
            next: Log low
      - name: Find Alerts
        type: find_record
        module: alerts
        query: []
        next: Announce
      - name: Announce
        type: set_variable
        vars:
          note: "{{ vars.steps.Find_Alerts[0].name }}"
      - name: Log low
        type: set_variable
        vars:
          tier: "tier1"
"""


def test_same_branch_reference_clean():
    w = _walk_resolved(_SAME_BRANCH)
    codes = {d.code for d in w.diagnostics if d.severity == "error"}
    assert "unreachable_step_reference" not in codes
    assert "unknown_step_reference" not in codes
