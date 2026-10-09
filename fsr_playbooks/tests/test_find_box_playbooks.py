"""find(kind='playbook') searches the analyst's own playbooks first.

Analyst sim: "call our existing 'Block IP - Shared' playbook" -- the only
playbook search covered the reference library, so the model could not see the
playbook, guessed `target: <name>` (which resolves only within the YAML) and
then a raw step type that compiled and called nothing.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import _shared, tools_find
from fsr_playbooks.mcp_server._fixture_box import _PlaybooksAPI

_ROWS = [
    {"name": "Block IP - Shared", "uuid": "11111111-1111-4111-8111-111111111111",
     "parameters": ["ip"], "isActive": True},
    {"name": "Enrich Host", "uuid": "22222222-2222-4222-8222-222222222222",
     "parameters": [], "isActive": True},
]


class _Box:
    playbooks = _PlaybooksAPI(_ROWS)


def test_box_playbooks_come_first_with_what_a_reference_needs(monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Box())
    out = tools_find.find("playbook", query="block ip")
    first = out["results"][0]
    assert first["on_this_box"] is True and first["name"] == "Block IP - Shared"
    assert first["workflowReference"] == "/api/3/workflows/11111111-1111-4111-8111-111111111111"
    assert first["parameters"] == ["ip"]
    assert out["on_this_box"] == 1 and "how_to_call" in out
    assert all(r.get("name") != "Enrich Host" for r in out["results"])


def test_without_a_box_it_says_the_box_was_not_searched(monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: None)
    out = tools_find.find("playbook", query="block ip")
    assert out["on_this_box"] == 0
    assert "not searched" in out["note"]


def test_the_compile_error_for_an_unknown_target_points_here():
    from fsr_playbooks._db import default_db_path
    from fsr_playbooks.compiler import compile_yaml
    res = compile_yaml("""
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Call}
      - {name: Call, type: workflow_reference, target: Block IP - Shared}
""", default_db_path())
    err = next(e for e in res.errors if e.code.value == "workflow_reference_unresolvable")
    assert "find(kind='playbook'" in err.message and "workflowReference" in err.message
