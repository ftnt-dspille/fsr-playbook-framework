"""`owner_detail.assignedToTeam` must be the list-of-OBJECTS the UI writes.

The compiler used to wrap whatever the author put in `assign_to: {team: ...}`
in a bare list and emit it unresolved. That single line caused both known
symptoms of a broken approval gate:

  * a team NAME produced `["SOC Team"]`, which FSR cannot resolve -- the gate
    was created UNOWNED and invisible to the people meant to answer it;
  * a team IRI produced `["/api/3/teams/<uuid>"]`, which routes, but the
    editor's Team picker has nothing to bind to and renders blank. Open that
    step in the UI and save it and the empty dropdown can be written back as
    unassigned, silently breaking routing on a playbook that worked.

The wire shape, confirmed against every UI-authored assignment on a live box:

    [{"iri": "/api/3/teams/<uuid>", "teamname": "SOC Team"}]

Live-verified on 8.0.0: a gate compiled from a team NAME comes back from
`list_wfinput` with `assignment_type: "team"` and the owning team resolved.
"""
import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

# Present in the reference DB's `teams` table (warmed from a live box).
_TEAM_NAME = "SOC Team"
_TEAM_IRI = "/api/3/teams/6e569c09-3bd4-40f1-98b0-cc994464c3c5"


def _compile(assign_block: str):
    src = f"""
collection: t
playbooks:
  - name: T
    trigger: start
    steps:
      - {{type: start, name: Start, next: Gate}}
      - type: manual_input
        name: Gate
        title: Approve?
        description: body
{assign_block}
        options:
          - {{option: Continue, primary: true}}
"""
    return compile_yaml(src, default_db_path())


def _owner_detail(assign_block: str) -> dict:
    r = _compile(assign_block)
    assert r.ok, r.errors
    steps = r.fsr_json["data"][0]["workflows"][0]["steps"]
    return next(s for s in steps if s["name"] == "Gate")["arguments"]["owner_detail"]


@pytest.mark.parametrize("team", [_TEAM_NAME, _TEAM_IRI])
def test_a_name_or_an_iri_both_reach_the_wire_fully_shaped(team):
    od = _owner_detail(f"        assign_to:\n          team: {team!r}")
    assert od["isAssigned"] is True
    assert od["assignedToTeam"] == [{"iri": _TEAM_IRI, "teamname": _TEAM_NAME}]


def test_a_hand_written_owner_detail_is_shaped_too():
    """Raw wire form (or a decompiled step) gets the same treatment."""
    od = _owner_detail(
        "        owner_detail:\n"
        "          isAssigned: true\n"
        f"          assignedToTeam: [{_TEAM_IRI!r}]"
    )
    assert od["assignedToTeam"] == [{"iri": _TEAM_IRI, "teamname": _TEAM_NAME}]


def test_an_unknown_team_name_is_a_compile_error_not_an_unowned_gate():
    """The old behaviour pushed clean and produced a gate nobody could see."""
    r = _compile("        assign_to:\n          team: 'No Such Team'")
    assert not r.ok
    assert any("unknown assigned team" in e.message for e in r.errors), r.errors
