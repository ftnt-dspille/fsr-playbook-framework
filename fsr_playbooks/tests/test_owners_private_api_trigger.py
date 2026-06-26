"""owners / is_private / api_endpoint trigger ��� compiler support.

Live-grounded on an exported private playbook owned by a single team, with an
API-Endpoint trigger step (step type `cybersponse.api_call`, uuid
df26c7a2-…). The three trigger auth modes map to:

    No Authentication -> authentication_methods: ["anonymous"], route deferred/<name>
    Basic            -> authentication_methods: ["Basic"],     route deferred/<name>
    Token Based      -> authentication_methods: [""],          route <name>

Token-based is the mode that exposes the playbook at
`POST /api/triggers/1/<name>` (no `deferred/` prefix).

Owner teams are authored as friendly NAMES (``owners: ["TeamA"]``); the
compiler resolves them to ``/api/3/teams/<uuid>`` IRIs via the warmed
``teams`` table (populated by the modules probe). IRIs pass through directly.
"""
from __future__ import annotations

import shutil
import sqlite3

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml

_TEAM_A_UUID = "d34aff9d-3b61-413e-8ced-854743e8ddcc"
_TEAM_A_IRI = f"/api/3/teams/{_TEAM_A_UUID}"
_API_ENDPOINT_STEPTYPE = "/api/3/workflow_step_types/df26c7a2-4166-4ca5-91e5-548e24c01b5f"


def _trigger_step(wf: dict) -> dict:
    ts_iri = wf["triggerStep"]
    return next(s for s in wf["steps"]
                if f"/api/3/workflow_steps/{s['uuid']}" == ts_iri)


def _warmed_db(tmp_path, teams: dict[str, str]):
    """A copy of the slim catalog plus a populated `teams` table."""
    db = tmp_path / "warmed.db"
    shutil.copy(PACKAGED_SLIM_DB, db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY, iri TEXT NOT NULL)")
    conn.executemany("INSERT OR REPLACE INTO teams (name, iri) VALUES (?, ?)",
                     list(teams.items()))
    conn.commit()
    conn.close()
    return db


_TOKEN_TRIGGER = """\
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
          authentication_methods: [""]
          __triggerLimit: true
          triggerOnSource: true
          triggerOnReplicate: false
          step_variables:
            input:
              params:
                api_body: "{{vars.request.data}}"
                api_params: "{{vars.request.params}}"
"""


def test_owner_team_name_resolves_to_iri(tmp_path):
    db = _warmed_db(tmp_path, {"TeamA": _TEAM_A_IRI})
    yaml = f"""
collection: 00-test
playbooks:
  - name: Lookup IP
    owners: ["TeamA"]
    steps:
{_TOKEN_TRIGGER}
"""
    res = compile_yaml(yaml, db)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]

    # Name resolved to the team IRI; private derived from owners (present => private).
    assert wf["owners"] == [_TEAM_A_IRI]
    assert wf["isPrivate"] is True
    assert _trigger_step(wf)["stepType"] == _API_ENDPOINT_STEPTYPE


def test_owner_iri_passes_through_offline():
    # IRIs need no `teams` table — works against the unsynced slim catalog.
    yaml = f"""
collection: 00-test
playbooks:
  - name: Lookup IP
    owners: ["{_TEAM_A_IRI}"]
    steps:
{_TOKEN_TRIGGER}
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    assert wf["owners"] == [_TEAM_A_IRI]
    assert wf["isPrivate"] is True


def test_unknown_owner_team_errors_with_suggestion(tmp_path):
    db = _warmed_db(tmp_path, {"TeamA": _TEAM_A_IRI, "TeamB": "/api/3/teams/b-uuid"})
    yaml = """
collection: 00-test
playbooks:
  - name: Lookup IP
    owners: ["TeemA"]
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
          authentication_methods: [""]
"""
    res = compile_yaml(yaml, db)
    err = next(e for e in res.errors if "owners" in (e.path or ""))
    assert "BAD_VALUE" in str(err.code)
    assert "TeemA" in err.message
    # did-you-mean against the synced team names.
    assert err.suggestion and "TeamA" in err.suggestion
    assert not res.ok


def test_unsynced_teams_table_errors_on_name():
    # A team NAME against the unsynced slim catalog (no `teams` table) is a
    # clear error — the compiler never silently emits a bare name on the wire.
    yaml = """
collection: 00-test
playbooks:
  - name: Lookup IP
    owners: ["TeamA"]
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
          authentication_methods: [""]
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    err = next(e for e in res.errors if "owners" in (e.path or ""))
    assert "unsynced" in err.message or "warmup" in err.message.lower()
    assert not res.ok


def test_no_owners_is_public():
    # SOAR default: no owners => not private, any team can run it.
    yaml = """
collection: 00-test
playbooks:
  - name: Public
    steps:
      - name: Start
        type: start
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    assert wf["isPrivate"] is False
    assert wf["owners"] == []


def test_explicit_private_with_no_owners_warns_and_is_public():
    yaml = """
collection: 00-test
playbooks:
  - name: Orphan
    is_private: true
    steps:
      - name: Start
        type: start
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    # Warned (SOAR invariant: private requires owners) and emitted public.
    assert any(
        "is_private" in (e.path or "") and e.severity == "warning"
        for e in res.errors
    )
    wf = res.fsr_json["data"][0]["workflows"][0]
    assert wf["isPrivate"] is False
    assert wf["owners"] == []


def test_owners_must_be_a_list():
    yaml = """
collection: 00-test
playbooks:
  - name: Bad
    owners: TeamA
    steps:
      - name: Start
        type: start
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert any(
        "BAD_VALUE" in str(e.code) and "owners" in (e.path or "")
        for e in res.errors
    )


# --- is_active default --------------------------------------------------------
#
# Authors almost never want to deploy an inactive playbook, so omitting
# `is_active:` defaults to active (matches FSR's UI). Set false explicitly for
# a disabled draft.

def test_is_active_defaults_to_true_when_omitted():
    yaml = """
collection: 00-test
playbooks:
  - name: Active
    steps:
      - name: Start
        type: start
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    assert wf["isActive"] is True


def test_is_active_false_is_honored():
    yaml = """
collection: 00-test
playbooks:
  - name: Draft
    is_active: false
    steps:
      - name: Start
        type: start
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    assert wf["isActive"] is False


# --- api_endpoint auth default ------------------------------------------------
#
# Token-based is the useful mode (exposes `POST /api/triggers/1/<route>`), but
# its wire value is the awkward empty-string `[""]`. The compiler defaults to
# it when `authentication_methods` is omitted, so authors write the minimal
# clean form and never spell `[""]`.

def test_api_endpoint_defaults_to_token_based_when_auth_omitted():
    # Minimal clean form — `route` only. The compiler fills token-based
    # auth (`[""]`) + the trigger-infra fields, so this compiles to the same
    # wire shape as the fully-specified `_TOKEN_TRIGGER` fixture below.
    yaml = """
collection: 00-test
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    trig = _trigger_step(res.fsr_json["data"][0]["workflows"][0])
    assert trig["stepType"] == _API_ENDPOINT_STEPTYPE
    args = trig["arguments"]
    assert args["authentication_methods"] == [""]      # token-based default
    assert args["route"] == "lookup_ip"
    # Trigger-infra defaults auto-filled to the canonical designer shape.
    assert args["__triggerLimit"] is True
    assert args["triggerOnSource"] is True
    assert args["triggerOnReplicate"] is False
    assert args["step_variables"] == {
        "input": {"params": {
            "api_body": "{{vars.request.data}}",
            "api_params": "{{vars.request.params}}",
        }},
    }


def test_api_endpoint_minimal_form_matches_explicit_token_fixture():
    # The minimal clean form must produce the SAME trigger arguments as the
    # fully-specified token-based fixture — i.e. the defaults are exactly
    # what an author would have written by hand.
    minimal = """
collection: 00-test
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
"""
    explicit = f"""
collection: 00-test
playbooks:
  - name: Lookup IP
    steps:
{_TOKEN_TRIGGER}
"""
    a = _trigger_step(compile_yaml(minimal, PACKAGED_SLIM_DB)
                      .fsr_json["data"][0]["workflows"][0])["arguments"]
    b = _trigger_step(compile_yaml(explicit, PACKAGED_SLIM_DB)
                      .fsr_json["data"][0]["workflows"][0])["arguments"]
    assert a == b


def test_api_endpoint_explicit_anonymous_is_preserved():
    # Explicit ["anonymous"] (No-Auth) is NOT overwritten by the token-based
    # default — only the *omission* of authentication_methods defaults to [""].
    yaml = """
collection: 00-test
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
          authentication_methods: ["anonymous"]
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    trig = _trigger_step(res.fsr_json["data"][0]["workflows"][0])
    assert trig["arguments"]["authentication_methods"] == ["anonymous"]


def test_api_endpoint_explicit_basic_is_preserved():
    yaml = """
collection: 00-test
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
          authentication_methods: ["Basic"]
"""
    res = compile_yaml(yaml, PACKAGED_SLIM_DB)
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    trig = _trigger_step(res.fsr_json["data"][0]["workflows"][0])
    assert trig["arguments"]["authentication_methods"] == ["Basic"]
