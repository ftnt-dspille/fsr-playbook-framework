"""why_did_playbook_fail diagnoses by NAME on an installed wheel.

The no-YAML fallback imported the repo's tooling/cli.py for the fetch +
decompile. tooling/ does not exist in an installed wheel, so on a box every
name-only diagnose died with decompile_import_failed ("No module named
'cli'") -- the one call the model makes first for "why did my playbook
fail". The pull now lives in the package (_workflow_pull) over the same
live client every MCP tool uses; the repo-tooling path survives only for a
bare library with no live client registered.
"""
from __future__ import annotations

import sys
from typing import Any

from fsr_playbooks.mcp_server import tools_recipe
from fsr_playbooks.mcp_server._workflow_pull import (
    pull_collection_with_refs,
    resolve_workflow_uuid,
)

_tool = tools_recipe.why_did_playbook_fail
_pull_tool_fn = _tool.fn if hasattr(_tool, "fn") else _tool

ROOT_UUID = "u" * 8 + "-4" + "u" * 3 + "-4" + "u" * 3 + "-4" + "u" * 3 + "-" + "u" * 12
DEP_UUID = "d" * 8 + "-4" + "d" * 3 + "-4" + "d" * 3 + "-4" + "d" * 3 + "-" + "d" * 12
COLL_UUID = "c" * 8 + "-4" + "c" * 3 + "-4" + "c" * 3 + "-4" + "c" * 3 + "-" + "c" * 12

ROOT = {
    "uuid": ROOT_UUID, "name": "Agent Lab Diagnose Practice",
    "modified": "2026-01-02T00:00:00Z",
    "collection": f"/api/3/workflow_collections/{COLL_UUID}",
    "steps": [{"name": "Tag Alert",
               "arguments": {"workflowReference": f"/api/3/workflows/{DEP_UUID}"}}],
}
DEP = {
    "uuid": DEP_UUID, "name": "Dep", "modified": "2026-01-01T00:00:00Z",
    "collection": f"/api/3/workflow_collections/{COLL_UUID}", "steps": [],
}
COLLS = {COLL_UUID: {"name": "Agent Lab", "description": "", "uuid": COLL_UUID}}


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._p = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._p


class _FakeClient:
    """Just enough client surface for the pull: `.get(path, params)` serving
    listings, exports and collection reads. Mirrors both shapes the pull must
    support -- pyfsr (Response objects) and the connector's crudhub bridge
    (parsed bodies) -- by honoring whatever `.get` returns."""

    def __init__(self, listing: list[dict], exports: dict[str, dict],
                 colls: dict[str, dict] | None = None) -> None:
        self._listing = listing
        self._exports = exports
        self._colls = colls or {}
        self.get_calls: list[tuple[str, dict | None]] = []
        # Response-shaped (pyfsr-like): the pull must raise_for_status + .json().
        self.response_shaped = True

    def _resp(self, payload: dict) -> Any:
        return _Resp(payload) if self.response_shaped else payload

    def get(self, path: str, params: dict | None = None) -> Any:
        self.get_calls.append((path, params))
        if path == "/api/3/workflows":
            uuids = []
            if params and "$export" in params:
                uuids = [u for u in (params.get("uuid$in") or "").split(",") if u]
                return self._resp({"hydra:member": [self._exports[u] for u in uuids
                                                    if u in self._exports]})
            return self._resp({"hydra:member": self._listing})
        if path.startswith("/api/3/workflow_collections/"):
            return self._resp(self._colls.get(path.rsplit("/", 1)[-1], {}))
        raise AssertionError(f"unexpected GET {path!r}")


def test_pull_bundles_root_and_transitive_refs():
    client = _FakeClient(listing=[ROOT], exports={ROOT_UUID: ROOT, DEP_UUID: DEP},
                         colls=COLLS)
    coll = pull_collection_with_refs(client, "Agent Lab Diagnose Practice")
    assert coll is not None
    wf_uuids = [w["uuid"] for w in coll["data"][0]["workflows"]]
    assert wf_uuids == [ROOT_UUID, DEP_UUID], "the referenced sub-playbook rides along"
    assert coll["data"][0]["name"] == "Agent Lab"
    exports = [p for p, q in client.get_calls if q and "$export" in q]
    assert len(exports) == 2, "one export for the root, one for the ref"


def test_pull_works_on_a_parsed_body_client_too():
    """The crudhub bridge client returns dicts, not Response objects."""
    client = _FakeClient(listing=[ROOT], exports={ROOT_UUID: ROOT, DEP_UUID: DEP},
                         colls=COLLS)
    client.response_shaped = False
    coll = pull_collection_with_refs(client, "Agent Lab Diagnose Practice")
    assert coll is not None
    assert [w["uuid"] for w in coll["data"][0]["workflows"]] == [ROOT_UUID, DEP_UUID]


def test_pull_resolves_a_shared_name_to_the_most_recent():
    older = dict(ROOT, modified="2025-01-02T00:00:00Z", steps=[])
    newer = dict(ROOT, uuid=ROOT_UUID, modified="2026-01-02T00:00:00Z", steps=[])
    client = _FakeClient(listing=[older, newer], exports={ROOT_UUID: newer})
    assert resolve_workflow_uuid(client, "Agent Lab Diagnose Practice") == ROOT_UUID


def test_pull_returns_none_for_an_unknown_name():
    client = _FakeClient(listing=[], exports={})
    assert pull_collection_with_refs(client, "No Such Playbook") is None


def test_recipe_diagnoses_by_run_id_through_the_package_pull(monkeypatch):
    """Run-id + no YAML must reach the package pull (never the repo's cli)."""
    client = _FakeClient(listing=[ROOT], exports={ROOT_UUID: ROOT, DEP_UUID: DEP},
                         colls=COLLS)
    monkeypatch.setattr("fsr_playbooks.mcp_server._shared._live_client",
                        lambda: client)
    monkeypatch.setattr("fsr_playbooks.mcp_server.tools_connector_discovery.get_run_env",
                        lambda pb: {"name": "Agent Lab Diagnose Practice"})
    seen: list[dict] = []

    def _spy_decompile(coll, db_path):
        seen.append(coll)
        return "# decompiled yaml"

    monkeypatch.setattr("fsr_playbooks.compiler.decompiler.decompile_to_yaml",
                        _spy_decompile)
    sentinel = {"ok": True, "summary": {}}
    monkeypatch.setattr(
        "fsr_playbooks.mcp_server.tools_recipe.diagnose_yaml_against_pb_execution",
        lambda yaml_text, pb_execution: sentinel)

    result = _pull_tool_fn("7797")

    assert result is sentinel, "the diagnosis ran on the pulled YAML"
    assert seen and [w["uuid"] for w in seen[0]["data"][0]["workflows"]] == \
        [ROOT_UUID, DEP_UUID], "the pull fed the decompile"
    assert any(q and "$export" in q for _, q in client.get_calls), \
        "the package pull fetched the live workflow"


def test_recipe_accepts_a_numeric_run_id_from_fsr_param_coercion(monkeypatch):
    """FSR deep-coerces op params: a direct caller's "7797" arrives as int.

    echo_param_types proved it live (args {'playbook_or_id': 7797}). The tool
    must normalize the int itself -- _looks_like_run_id's .isdigit() would
    otherwise AttributeError before any diagnosis could start.
    """
    client = _FakeClient(listing=[ROOT], exports={ROOT_UUID: ROOT, DEP_UUID: DEP},
                         colls=COLLS)
    monkeypatch.setattr("fsr_playbooks.mcp_server._shared._live_client",
                        lambda: client)
    monkeypatch.setattr("fsr_playbooks.mcp_server.tools_connector_discovery.get_run_env",
                        lambda pb: {"name": "Agent Lab Diagnose Practice"})
    monkeypatch.setattr("fsr_playbooks.compiler.decompiler.decompile_to_yaml",
                        lambda coll, db_path: "# decompiled yaml")
    seen_calls: list[dict] = []
    monkeypatch.setattr(
        "fsr_playbooks.mcp_server.tools_recipe.diagnose_yaml_against_pb_execution",
        lambda yaml_text, pb_execution: seen_calls.append(
            {"yaml": yaml_text, "pb": pb_execution}) or {"ok": True})

    result = _pull_tool_fn(7797)  # int, exactly as FSR delivers it

    assert result.get("ok") is True
    assert seen_calls and seen_calls[0]["pb"] == "7797", "run id normalized to str"


def test_fallback_without_a_live_client_still_reports_the_repo_import(monkeypatch,
                                                                      tmp_path):
    """No live client + no repo tooling -> the honest decompile_import_failed."""
    monkeypatch.setattr("fsr_playbooks.mcp_server._shared._live_client",
                        lambda: None)
    monkeypatch.setattr("fsr_playbooks.mcp_server.tools_connector_discovery.get_run_env",
                        lambda pb: {"name": "Agent Lab Diagnose Practice"})
    monkeypatch.setattr("fsr_playbooks.mcp_server.tools_recipe.REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    # The rest of the suite may legitimately have imported the repo's cli (its
    # own tests do). Hide both repo-only modules so this test pins the
    # installed-wheel reality whatever ran before it.
    monkeypatch.setitem(sys.modules, "cli", None)
    monkeypatch.setitem(sys.modules, "probes", None)

    result = _pull_tool_fn("7797")

    assert result.get("ok") is False
    assert result.get("code") == "decompile_import_failed"
