"""Walk a draft offline and see which reads come out empty.

With no box, step_through_playbook used to hand back raw templates and report
a clean walk, so "does this playbook run" had no offline answer. The analyst
sim then counted playbooks as good that could never work: a VirusTotal gate
reading `... | default(0) | int >= 1` off a path the op does not return is
always 0, so the block never fires. These pin the offline walk that finds it.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from fsr_playbooks.compiler import local_render  # noqa: E402
from fsr_playbooks.mcp_server import _shared  # noqa: E402
from fsr_playbooks.mcp_server.tools_analysis import walk_paths  # noqa: E402
from fsr_playbooks.mcp_server.tools_verify import verify_playbook  # noqa: E402


@pytest.fixture(autouse=True)
def offline_alerts(tmp_path, monkeypatch):
    db = tmp_path / "ref.db"
    shutil.copy(_shared.DB_PATH, db)
    with sqlite3.connect(db) as c:
        c.executemany(
            "INSERT OR REPLACE INTO module_fields (module_name, field_name, type) "
            "VALUES ('alerts', ?, 'text')",
            [("destinationIp",), ("sourceIp",), ("name",)])
    monkeypatch.setattr(_shared, "DB_PATH", str(db))
    monkeypatch.setattr(_shared, "_live_client", lambda: None)


_GATE = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Stash}
      - name: Stash
        type: set_variable
        vars: {ip: "{{ vars.input.records[0].__FIELD__ }}"}
        next: VT
      - name: VT
        type: connector
        connector: virustotal
        operation: query_ip
        params: {ip: "{{ vars.ip }}"}
        next: Gate
      - name: Gate
        type: decision
        conditions:
          - display: Bad
            when: "{{ (vars.steps.VT.__PATH__ | default(0)) | int >= 1 }}"
            next: Note
          - {display: Else, default: true, next: Done}
      - name: Note
        type: set_variable
        vars: {who: "{{ vars.steps.VT.__OTHER__ }}"}
        next: Done
      - {name: Done, type: end}
"""

_GOOD = {"__FIELD__": "destinationIp",
         "__PATH__": "data.attributes.last_analysis_stats.malicious",
         "__OTHER__": "data.attributes.as_owner"}


def _yaml(**over: str) -> str:
    y = _GATE
    for k, v in {**_GOOD, **over}.items():
        y = y.replace(k, v)
    return y


def _empties(r) -> dict[str, list[str]]:
    return {e["step"]: e["empty"] + e["defaulted"] for e in r["renders_empty"]}


def test_a_correct_playbook_walks_clean_down_every_branch():
    r = walk_paths(_yaml())
    assert r["ok"] and r["renders_empty"] == []
    assert r["steps_reached"] == r["steps_total"] == 6


def test_an_invented_record_field_comes_out_empty():
    assert _empties(walk_paths(_yaml(__FIELD__="destIp")))["Stash"] == ["destIp"]


def test_a_gate_that_is_always_zero_is_reported():
    r = walk_paths(_yaml(__PATH__="data.data.attributes.last_analysis_stats.malicious"))
    assert _empties(r)["Gate"] == ["data | default"]
    gate = next(e for e in r["renders_empty"] if e["step"] == "Gate")
    assert gate["certain"] is False  # a recorded run is one run


def test_a_broken_read_on_the_other_branch_is_found():
    # On sample data the gate takes `Bad` here; `Note` only renders when
    # pinned -- one walk per option is what finds it.
    r = walk_paths(_yaml(__OTHER__="data.verdict"))
    assert _empties(r)["Note"] == ["verdict"]


def test_slug_routes_are_followed():
    y = _yaml().replace("next: Stash", "next: stash").replace("next: VT", "next: vt")
    assert walk_paths(y)["steps_reached"] == 6


def test_verify_reports_the_walk_as_warnings():
    r = verify_playbook(_yaml(__OTHER__="data.verdict"))
    codes = [w["code"] for w in r.get("warnings") or []]
    assert "renders_empty" in codes
    assert r["evidence"]["offline_walk"]["steps_reached"] == 6


def test_unknown_data_is_unverified_not_empty():
    ctx = {"vars": {"steps": {"X": local_render.Opaque("no run")},
                    "input": {"params": {}}}}
    r = local_render.render("{{ vars.steps.X.a.b | default(0) }} {{ vars.input.params.p }}", ctx)
    assert r["empty"] == r["defaulted"] == [] and r["opaque"]


def test_a_filter_the_sandbox_lacks_is_unrendered_not_failed():
    r = local_render.render("{{ '1.2.3.4' | ipaddr }}", {"vars": {}})
    assert r["unrendered"] and r["empty"] == []


_NESTED = """
collection: C
playbooks:
  - name: Router
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Route}
      - name: Route
        type: decision
        conditions:
          - {display: Critical, when: "{{ vars.input.records[0].name == 'never on sample data' }}", next: Make}
          - {display: Else, default: true, next: Done}
      - {name: Make, type: set_variable, vars: {made: true}, next: Check}
      - name: Check
        type: decision
        conditions:
          - {display: Success, when: "{{ vars.made }}", next: Done}
          - {display: Failed, default: true, next: Tell}
        next: Done
      - {name: Tell, type: set_variable, vars: {told: true}, next: Done}
      - {name: Done, type: end}
"""


def test_a_branch_behind_another_branch_is_walked():
    # Analyst sim: "Email Incident Failure" sat behind the Critical arm AND its
    # decision carried a stray step-level `next`. Pinning "Failed" alone never
    # reached the decision, and the stepper then followed the stray `next`.
    from fsr_playbooks.mcp_server.tools_analysis import walk_paths
    w = walk_paths(_NESTED)
    assert w["never_reached"] == [], w["never_reached"]
