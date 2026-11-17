"""Tests for the wizard-page-gate rules in the data-ingestion rulesets.

Covers the two rules that encode the Data Ingestion Wizard's hard gates:
  - shared.wizard_create_step_name     (showMappingStep gate)
  - shared.wizard_create_step_collection (_getModuleName gate)

Both are FAIL-level because the wizard silently skips the Data Mapping page
when they're violated -- there is no partial success.
"""
from __future__ import annotations

from fsr_playbooks.compiler import rulesets

CREATE_UUID = "2597053c-e718-44b4-8394-4d40fe26d357"
IBF_UUID = "7b221880-716b-4726-a2ca-5e568d330b3e"


def _doc(step_name: str, collection: str | None, step_uuid: str = CREATE_UUID) -> dict:
    args: dict = {"operation": "Overwrite", "resource": {}}
    if collection is not None:
        args["collection"] = collection
    return {
        "type": "workflow_collections",
        "data": [
            {
                "name": "Conn",
                "recordTags": ["conn", "dataingestion"],
                "workflows": [
                    {
                        "name": "Ingest",
                        "recordTags": [
                            "conn",
                            "dataingestion",
                            "create",
                            "ingest",
                        ],
                        "steps": [
                            {
                                "name": step_name,
                                "stepType": f"/api/3/workflow_step_types/{step_uuid}",
                                "arguments": args,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _wizard_issues(doc: dict, ruleset: str = "data-ingest") -> list[rulesets.Issue]:
    return [
        i
        for i in rulesets.validate(doc, [ruleset])
        if i.rule_id.startswith("shared.wizard")
    ]


# --- name gate ---------------------------------------------------------------


def test_name_gate_fails_when_step_named_create_alerts():
    issues = _wizard_issues(_doc("Create Alerts", "/api/3/upsert/alerts"))
    assert any(
        i.rule_id == "shared.wizard_create_step_name" and i.severity == "fail"
        for i in issues
    )


def test_name_gate_passes_when_step_named_create_record():
    issues = _wizard_issues(_doc("Create Record", "/api/3/upsert/alerts"))
    assert not issues


def test_name_gate_is_case_insensitive():
    issues = _wizard_issues(_doc("create record", "/api/3/upsert/alerts"))
    assert not issues


def test_name_gate_skips_non_create_workflow():
    """A fetch-only workflow (no 'create' tag) should not trigger the gate."""
    doc = _doc("Fetch Data", "/api/3/alerts")
    doc["data"][0]["workflows"][0]["recordTags"] = ["conn", "dataingestion", "fetch"]
    assert not _wizard_issues(doc)


# --- collection gate ---------------------------------------------------------


def test_collection_gate_fails_when_collection_missing():
    issues = _wizard_issues(_doc("Create Record", collection=None))
    assert any(
        i.rule_id == "shared.wizard_create_step_collection" and i.severity == "fail"
        for i in issues
    )


def test_collection_gate_passes_with_api3_collection():
    issues = _wizard_issues(_doc("Create Record", "/api/3/upsert/alerts"))
    assert not issues


def test_collection_gate_passes_with_ingest_feeds_collection():
    """Feed-ingest connectors use /api/ingest-feeds/... -- still valid."""
    issues = _wizard_issues(
        _doc("Create Record", "/api/ingest-feeds/threat_intel_feeds", step_uuid=IBF_UUID),
        ruleset="feed-ingest",
    )
    assert not issues


# --- both rules registered in both rulesets -----------------------------------


def test_rules_registered_in_data_ingest():
    rules = rulesets._REGISTRY.get("data-ingest", [])
    ids = {r.__name__ for r in rules}
    assert "rule_wizard_create_step_name" in ids
    assert "rule_wizard_create_step_collection" in ids


def test_rules_registered_in_feed_ingest():
    rules = rulesets._REGISTRY.get("feed-ingest", [])
    ids = {r.__name__ for r in rules}
    assert "rule_wizard_create_step_name" in ids
    assert "rule_wizard_create_step_collection" in ids
