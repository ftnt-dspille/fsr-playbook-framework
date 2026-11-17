"""Derived step/route uuids are seeded by the playbook's real uuid when it has
one (tracker #153).

Live: applying an enhancement 409'd on (uuid) because a step it added had the
same uuid5 as an orphaned step left by a deleted collection whose playbook and
step names matched. Names are not unique on the box; a playbook's uuid is.
A fresh build has no uuid and must keep its name-seeded output.
"""
from __future__ import annotations

from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.compiler.emitter import emit


def _doc(pb_uuid: str | None) -> str:
    uuid_line = f"    uuid: {pb_uuid}\n" if pb_uuid else ""
    return ("collection: C\n"
            "playbooks:\n"
            "  - name: P\n"
            + uuid_line +
            "    steps:\n"
            "      - name: Start\n"
            "        type: start\n"
            "        next: Reviewer Decision\n"
            "      - name: Reviewer Decision\n"
            "        type: set_variable\n"
            "        vars: {d: \"1\"}\n")


def _wf(yaml_text: str) -> dict:
    coll, errs = parse_yaml(yaml_text)
    assert coll is not None, errs
    return emit(coll)["data"][0]["workflows"][0]


def _uuids(wf: dict) -> set[str]:
    return ({s["uuid"] for s in wf["steps"]}
            | {r["uuid"] for r in wf["routes"]})


def test_same_names_different_playbooks_get_different_step_uuids():
    a = _wf(_doc("11111111-1111-4111-8111-111111111111"))
    b = _wf(_doc("22222222-2222-4222-8222-222222222222"))
    assert _uuids(a).isdisjoint(_uuids(b))


def test_box_playbook_does_not_reuse_the_name_seeded_uuids():
    fresh = _wf(_doc(None))
    boxed = _wf(_doc("11111111-1111-4111-8111-111111111111"))
    assert _uuids(fresh).isdisjoint(_uuids(boxed))


def test_fresh_build_is_deterministic():
    assert _uuids(_wf(_doc(None))) == _uuids(_wf(_doc(None)))
