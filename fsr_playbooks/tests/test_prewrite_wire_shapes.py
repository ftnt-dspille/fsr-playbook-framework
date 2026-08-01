"""The pre-write loss gate must survive the shapes a LIVE crudhub GET returns.

The gate fails CLOSED: anything it cannot compare becomes "refusing the save".
That is the right posture and it also means any crash inside normalization
presents as a blanket refusal to edit, not as a readable error. Both defects
below were exactly that -- a correct-looking refusal hiding a bug.
"""
from __future__ import annotations

from fsr_playbooks.compiler.prewrite import check_prewrite


def _env(wf: dict, *, name: str = "_prewrite_wf") -> dict:
    w = dict(wf)
    w["name"] = name
    return {"data": [{"name": "_prewrite", "description": "",
                      "workflows": [w]}]}


def test_dict_keyed_steps_do_not_crash_the_gate():
    """A live GET can return `steps` keyed by id instead of as a list.
    Iterating that yields string KEYS, so `s["uuid"]` raised TypeError --
    which the gate turned into "refusing the save" on every edit of such a
    playbook."""
    live = {"uuid": "w", "name": "n",
            "steps": {"s1": {"uuid": "u1", "name": "one"}}}
    outgoing = {"name": "n", "steps": [{"uuid": "u1", "name": "one"}]}
    v = check_prewrite(_env(live), _env(outgoing))
    assert v.ok, v.message
    assert "could not run" not in v.message


def test_dict_keyed_routes_do_not_crash_the_gate():
    live = {"uuid": "w", "name": "n",
            "steps": {"s1": {"uuid": "u1", "name": "one"},
                      "s2": {"uuid": "u2", "name": "two"}},
            "routes": {"r1": {"sourceStep": "u1", "targetStep": "u2"}}}
    outgoing = {"name": "n",
                "steps": [{"uuid": "u1", "name": "one"},
                          {"uuid": "u2", "name": "two"}],
                "routes": [{"sourceStep": "u1", "targetStep": "u2"}]}
    v = check_prewrite(_env(live), _env(outgoing))
    assert v.ok, v.message


def test_a_real_drop_in_dict_keyed_form_is_still_refused():
    """Tolerating the shape must not blunt the gate."""
    live = {"uuid": "w", "name": "n",
            "steps": {"s1": {"uuid": "u1", "name": "one"},
                      "s2": {"uuid": "u2", "name": "two"}}}
    outgoing = {"name": "n", "steps": [{"uuid": "u1", "name": "one"}]}
    v = check_prewrite(_env(live), _env(outgoing))
    assert not v.ok
    assert any("two" in p for p in v.dropped), v.dropped


def test_a_dropped_argument_is_still_caught_through_a_dict_shape():
    """The `for_each` / declared-parameters defect class, via the wire shape
    that used to crash before it could be checked."""
    live = {"uuid": "w", "name": "n",
            "steps": {"s1": {"uuid": "u1", "name": "one",
                             "arguments": {"keep": 1, "lose": 2}}}}
    outgoing = {"name": "n",
                "steps": [{"uuid": "u1", "name": "one",
                           "arguments": {"keep": 1}}]}
    v = check_prewrite(_env(live), _env(outgoing))
    assert not v.ok
    assert any("lose" in p for p in v.dropped), v.dropped


def test_renaming_a_workflow_is_not_a_deletion():
    """The gate joins workflows by NAME. update_playbook targets ONE workflow
    by IRI, so the two sides are the same workflow by construction -- but with
    the name left free, renaming a playbook (an ordinary edit) reported the
    whole workflow as dropped and refused the save.

    The connector pins a synthetic name on both sides; this asserts the
    semantics that fix depends on.
    """
    body = {"uuid": "w", "steps": [{"uuid": "u1", "name": "one"}]}
    same = check_prewrite(_env(body, name="pinned"), _env(body, name="pinned"))
    assert same.ok, same.message

    # Left un-pinned, a pure rename reads as total loss -- the bug's mechanism.
    renamed = check_prewrite(_env(body, name="old title"),
                             _env(body, name="new title"))
    assert not renamed.ok
    assert any("old title" in p for p in renamed.dropped)
