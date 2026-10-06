"""get_step_type describes every step type the compiler accepts.

Discovery kept its own copy of the compiler's short-type map, and the copy
lagged by nine types: asked for `api_endpoint`, `send_email`, `delete_record`
or `start_on_delete`, get_step_type answered "not found" while the compiler
compiled them. A model told a type does not exist builds around it -- a sweep
run built a manual button for "when an alert is created" after only ever
looking up `start`.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.compiler.resolver._constants import SHORT_TYPE_TO_FSR
from fsr_playbooks.mcp_server.tools_discovery import (
    _FRIENDLY_FORMS,
    get_step_type,
)


@pytest.mark.parametrize("short", sorted(SHORT_TYPE_TO_FSR))
def test_every_compiler_type_resolves(short):
    res = get_step_type(short)
    assert res.get("code") != "not_found", res


@pytest.mark.parametrize("short", sorted(
    s for s, c in SHORT_TYPE_TO_FSR.items()
    if c == "Connectors" and s not in {"connector", "stop", "end"}))
def test_connector_family_aliases_get_their_own_page(short):
    # Without its own form an alias renders the generic connector page,
    # which teaches connector:/operation: the alias exists to hide.
    assert short in _FRIENDLY_FORMS
    assert get_step_type(short)["markdown"].startswith(
        f"# step type: {short} ")


def test_connector_spelling_still_means_connector():
    assert get_step_type("Connectors")["markdown"].startswith(
        "# step type: connector ")


def test_the_manual_trigger_points_at_the_automatic_ones():
    md = get_step_type("start")["markdown"]
    for auto in ("start_on_create", "start_on_update", "start_on_delete"):
        assert auto in md
    for auto in ("start_on_create", "start_on_update", "start_on_delete",
                 "api_endpoint"):
        assert auto in _FRIENDLY_FORMS


@pytest.mark.parametrize("trigger", ["start_on_create", "start_on_update",
                                     "start_on_delete", "api_endpoint"])
def test_trigger_examples_compile_as_the_trigger(trigger):
    # The friendly-form compile test scaffolds each example as a MIDDLE step,
    # so it skips triggers; compile these where a trigger goes.
    import yaml

    from fsr_playbooks.mcp_server.tools_verify import verify_playbook
    first = dict(_FRIENDLY_FORMS[trigger]["example"])
    first["name"] = "Start"
    first["next"] = "Note"
    doc = {"playbooks": [{"name": "P", "parameters": [], "steps": [
        first,
        {"name": "Note", "type": "set_variable", "vars": {"seen": "1"}},
    ]}]}
    v = verify_playbook(yaml.safe_dump(doc, sort_keys=False))
    assert v["ready_to_push"], v["required_fixes"]


def test_no_note_is_cut_on_the_slim_page():
    from fsr_playbooks.mcp_server.tools_discovery import _NOTE_CAP
    long = {k: len(" ".join((v.get("note") or v.get("shape") or "").split()))
            for k, v in _FRIENDLY_FORMS.items()}
    assert {k: n for k, n in long.items() if n > _NOTE_CAP} == {}
