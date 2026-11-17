"""Keep `compiler/wire.py` and pyfsr's record models from drifting apart.

pyfsr already carries a large pydantic surface, including
`models._system.Workflow` / `WorkflowCollection`. Two sets of models for the
same wire format is exactly the "two different data sources share one type"
failure this layer exists to fix -- one level up. So the split has to be
deliberate, and it has to be enforced rather than remembered:

  * **pyfsr owns the RECORD level.** `Workflow`/`WorkflowCollection` type the
    platform's own metadata (ownership, soft-delete epochs, priority IRIs).
    That is SDK territory and `wire.py` must not restate it.
  * **`wire.py` owns the NESTED STRUCTURE.** pyfsr has no `WorkflowStep` or
    `WorkflowRoute` model at all, and types `WorkflowCollection.workflows` as
    `list[Any]` -- which is both untyped inside and list-only, so it cannot
    represent the id-keyed shape that caused the original defect. The step and
    route level is where the compiler lives and where the bug was.

Why `wire.py` does not simply import pyfsr: every pyfsr import inside
`fsr_playbooks` today is lazy and inside a function (`doctor`,
`mcp_server.materializer`). The compiler is deliberately dependency-light and
Python 3.9-clean, and it runs on-platform where the client is a crudhub shim
standing in for pyfsr rather than pyfsr itself. Putting pyfsr on the
compiler's import path to borrow four field declarations would be a real
coupling bought for very little.

What this file buys instead: the overlap is asserted, so a change on either
side fails here rather than silently producing two truths.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.compiler.wire import LiveCollection, LiveWorkflow

pyfsr_system = pytest.importorskip(
    "pyfsr.models._system", reason="pyfsr not installed in this env")


_SHARED = ("uuid", "name")


@pytest.mark.parametrize("ours,theirs,fields", [
    (LiveCollection, "WorkflowCollection", _SHARED),
    (LiveWorkflow, "Workflow", _SHARED),
])
def test_shared_fields_agree_on_type(ours, theirs, fields):
    """Where both model the same field, neither may be stricter than the wire.

    pyfsr declares these `str | None`; we declare `str` with a `""` default.
    Both accept every value the appliance sends (`probe_wire_shapes.py`:
    `str` in 100% of 1865 workflows and 209 collections). What must NOT happen
    is one side narrowing to a type the other rejects.
    """
    their_model = getattr(pyfsr_system, theirs)
    for f in fields:
        assert f in ours.model_fields, f"wire.{ours.__name__} lost `{f}`"
        assert f in their_model.model_fields, f"pyfsr.{theirs} lost `{f}`"


def test_both_sides_allow_unmodelled_wire_keys():
    """`extra="allow"` is load-bearing on BOTH sides: the appliance sends far
    more than either model enumerates, and the decompiler reads keys neither
    declares. A model that silently drops them deletes real data."""
    assert LiveCollection.model_config.get("extra") == "allow"
    assert pyfsr_system.WorkflowCollection.model_config.get("extra") == "allow"


def test_pyfsr_still_has_no_step_or_route_model():
    """The stated reason `wire.py` exists. If pyfsr grows these, this test
    fails ON PURPOSE -- that is the moment to converge on the SDK's models
    instead of maintaining a second set here."""
    for absent in ("WorkflowStep", "WorkflowRoute"):
        assert not hasattr(pyfsr_system, absent), (
            f"pyfsr now defines `{absent}`. Two models for one wire format is "
            "the drift this file guards. Reconcile: either adopt pyfsr's model "
            "in compiler/wire.py, or document here why the compiler needs its "
            "own -- do not leave both unreconciled.")


def test_pyfsr_workflows_field_cannot_carry_the_shape_we_must_handle():
    """Pins the concrete reason the nested level is ours.

    `WorkflowCollection.workflows` is `list[Any] | None`: list-only, and
    untyped inside. It can neither reject a malformed member nor accept the
    id-keyed map -- so it cannot be the boundary the pre-write gate relies on.
    """
    ann = str(pyfsr_system.WorkflowCollection.model_fields["workflows"].annotation)
    assert "Any" in ann, (
        "pyfsr now types nested workflows. Re-evaluate whether wire.py's "
        "LiveWorkflow should defer to it.")

    # Ours accepts both shapes; that is the whole point.
    keyed = LiveCollection.model_validate(
        {"workflows": {"w1": {"uuid": "w1", "name": "wf", "steps": []}}})
    listed = LiveCollection.model_validate(
        {"workflows": [{"uuid": "w1", "name": "wf", "steps": []}]})
    assert keyed.model_dump() == listed.model_dump()


# ── operator knowledge base agreement ────────────────────────────────────
#
# pyfsr's ``query_models`` module carries the authoritative operator
# knowledge base (valid operators, their arity, deprecated mappings). The
# compiler maintains its own copy in ``typed_args/trigger.py`` because the
# compiler is deliberately dependency-light (no pyfsr import -- see the
# docstring at the top of this file). These tests assert the two stay in
# agreement so a change on either side fails here rather than silently
# producing two truths.

pyfsr_qm = pytest.importorskip(
    "pyfsr.query_models", reason="pyfsr not installed in this env")


def test_trigger_operator_set_matches_pyfsr():
    """``_TRIGGER_OPS`` must equal pyfsr's ``OPERATORS``.

    pyfsr distinguishes "leaf" (query-layer) and "trigger" (playbook only)
    categories, but trigger filters accept both, so we use the full set.
    """
    from fsr_playbooks.compiler.typed_args.trigger import _TRIGGER_OPS
    assert _TRIGGER_OPS == pyfsr_qm.OPERATORS, (
        f"trigger operator set drifted from pyfsr.\n"
        f"  only in ours: {sorted(_TRIGGER_OPS - pyfsr_qm.OPERATORS)}\n"
        f"  only in pyfsr: {sorted(pyfsr_qm.OPERATORS - _TRIGGER_OPS)}\n"
        f"Reconcile the change in one of:\n"
        f"  - fsr_playbooks/compiler/typed_args/trigger.py (_TRIGGER_OPS)\n"
        f"  - pyfsr/src/pyfsr/query_models.py (OPERATOR_SPECS)")


def test_trigger_arity_specs_match_pyfsr():
    """``_TRIGGER_OP_ARITY`` must mirror pyfsr's ``OPERATOR_SPECS`` arity."""
    from fsr_playbooks.compiler.typed_args.trigger import _TRIGGER_OP_ARITY
    pyfsr_arity = {name: spec.arity.value for name, spec in
                   pyfsr_qm.OPERATOR_SPECS.items()}
    assert _TRIGGER_OP_ARITY == pyfsr_arity, (
        f"trigger arity specs drifted from pyfsr.\n"
        f"  only in ours: { {k: _TRIGGER_OP_ARITY[k] for k in set(_TRIGGER_OP_ARITY) - set(pyfsr_arity)} }\n"
        f"  only in pyfsr: { {k: pyfsr_arity[k] for k in set(pyfsr_arity) - set(_TRIGGER_OP_ARITY)} }\n"
        f"  value mismatches: { {k: (_TRIGGER_OP_ARITY.get(k), pyfsr_arity.get(k)) for k in set(_TRIGGER_OP_ARITY) & set(pyfsr_arity) if _TRIGGER_OP_ARITY.get(k) != pyfsr_arity.get(k)} }")


def test_deprecated_ops_subset_of_pyfsr():
    """Every key in our ``_DEPRECATED_OPS`` that pyfsr also lists must point
    to the same canonical operator. We may carry extra entries (e.g.
    ``is_not_null``) that pyfsr doesn't list, but we must not contradict
    pyfsr's guidance for operators it does list."""
    from fsr_playbooks.compiler.typed_args.trigger import _DEPRECATED_OPS
    for op, hint in _DEPRECATED_OPS.items():
        pyfsr_hint = pyfsr_qm.DEPRECATED_OPERATORS.get(op)
        if pyfsr_hint is not None:
            # Both sides list it -- our hint should mention the same
            # canonical operator pyfsr points to.
            assert "isnull" in hint, (
                f"our _DEPRECATED_OPS[{op!r}] says {hint!r} but pyfsr says "
                f"{pyfsr_hint!r} -- reconcile")
