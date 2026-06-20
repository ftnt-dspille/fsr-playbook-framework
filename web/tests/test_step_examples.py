"""Tests for the corpus-mined step-examples summariser + clusterer."""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.step_examples import (
    cluster_examples,
    summarise_decision,
    summarise_delay,
    summarise_find_record,
    summarise_manual_input,
    summarise_record_write,
    summarise_set_variable,
    summarise_trigger,
    summarise_workflow_ref,
)


# ---------------------------------------------------------------------------
# Pure-summariser tests (no DB)
# ---------------------------------------------------------------------------

def test_summarise_decision_renders_each_branch():
    out = summarise_decision({
        "conditions": [
            {"option": "Yes",  "condition": "{{ vars.score > 50 }}"},
            {"option": "No",   "default": True},
        ]
    })
    assert "if vars.score > 50 → Yes" in out
    assert "else → No" in out


def test_summarise_decision_handles_empty():
    assert summarise_decision({"conditions": []}) == "Branches with no conditions configured."
    assert summarise_decision({}) == "Branches with no conditions configured."


def test_summarise_trigger_with_filter_tree():
    args = {
        "resource": "alerts",
        "fieldbasedtrigger": {
            "logic": "AND",
            "filters": [
                {"field": "severity", "operator": "eq", "value": "/api/3/picklists/abc",
                 "_value": {"display": "High", "itemValue": "High"}},
                {"field": "escalated", "operator": "neq", "value": "Yes"},
            ],
        },
    }
    out = summarise_trigger(args, "cybersponse.post_create")
    assert out == "On create of alerts where severity is High and escalated is not Yes."


def test_summarise_trigger_empty_filters_says_all():
    out = summarise_trigger({"resource": "incidents"}, "cybersponse.post_update")
    assert out == "On update of all incidents."


def test_summarise_trigger_nested_or_group():
    args = {
        "resource": "indicators",
        "fieldbasedtrigger": {
            "logic": "AND",
            "filters": [
                {"logic": "OR", "filters": [
                    {"field": "typeofindicator", "operator": "eq", "value": "Domain"},
                    {"field": "typeofindicator", "operator": "eq", "value": "URL"},
                ]},
                {"field": "indicatorStatus", "operator": "neq", "value": "Excluded"},
            ],
        },
    }
    out = summarise_trigger(args, "cybersponse.post_create")
    assert "(typeofindicator is Domain or typeofindicator is URL)" in out
    assert "indicator status is not Excluded" in out


def test_summarise_manual_input_lists_fields_and_buttons():
    args = {
        "input": {"schema": {
            "title": "Approve PR",
            "inputVariables": [
                {"name": "orgName"}, {"name": "branchName"},
            ],
        }},
        "response_mapping": {"options": [
            {"option": "Approve", "primary": True},
            {"option": "Reject"},
        ]},
    }
    out = summarise_manual_input(args)
    assert "Approve PR" in out
    assert "orgName, branchName" in out
    assert "Approve / Reject" in out


def test_summarise_find_record_reports_module_filter_and_sort():
    args = {
        "module": "tasks?$limit=30",
        "query": {
            "logic": "AND",
            "filters": [{"field": "name", "operator": "eq", "value": "{{ vars.id }}"}],
            "sort": [{"field": "createDate", "direction": "DESC"}],
        },
    }
    out = summarise_find_record(args)
    assert out.startswith("Find tasks where name is vars.id")
    assert "sorted by create date desc" in out


def test_summarise_record_write_lists_field_names():
    args = {
        "collection": "/api/3/comments",
        "operation": "Overwrite",
        "resource": {"content": "<p>hi</p>", "tasks": "<iri>", "isImportant": False},
    }
    out = summarise_record_write(args, "UpdateRecord")
    assert "Overwrite a comments record" in out
    assert "content, tasks, isImportant" in out


def test_summarise_workflow_ref_with_inputs():
    args = {
        "workflowReference": "/api/3/workflows/abc-uuid",
        "arguments": {"orgName": "x", "repo": "y"},
    }
    out = summarise_workflow_ref(args)
    assert "Calls playbook abc-uuid with orgName, repo" in out


def test_summarise_delay_canonical_and_friendly_shapes():
    assert summarise_delay({"delay": {"seconds": 5, "minutes": 0}}) == "Wait 5 seconds."
    assert summarise_delay({"minutes": 2, "seconds": 30}) == "Wait 2 minutes 30 seconds."
    assert summarise_delay({}) == "Delay (duration not set)."


def test_summarise_set_variable_handles_both_shapes():
    # Friendly form (post-parse).
    assert summarise_set_variable({"arg_list": [
        {"name": "a", "value": 1}, {"name": "b", "value": 2},
    ]}) == "Sets a, b."
    # Canonical FSR form — every top-level non-system key is a var.
    assert summarise_set_variable({
        "base_branch": "{{ vars.x }}",
        "repo_name": "{{ vars.y }}",
        "step_variables": [],  # system key — excluded
    }) == "Sets base_branch, repo_name."


# ---------------------------------------------------------------------------
# Clusterer tests (in-memory DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_corpus(tmp_path):
    """Build a tiny playbook_steps DB so clustering is deterministic."""
    db = tmp_path / "ref.db"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE playbook_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, source_path TEXT, collection TEXT,
            playbook_name TEXT, playbook_uuid TEXT,
            step_uuid TEXT, step_name TEXT,
            step_type_uuid TEXT, step_type_name TEXT,
            arguments_json TEXT, ingested_at TEXT
        )
    """)
    rows = [
        # Three near-identical Decision steps that vary only in the
        # condition expression — should cluster together because the
        # canonicaliser strips Jinja templates.
        ("Decision", "pb-A", json.dumps({"conditions": [
            {"option": "Yes", "condition": "{{ vars.x > 5 }}"},
            {"option": "No", "default": True},
        ]})),
        ("Decision", "pb-B", json.dumps({"conditions": [
            {"option": "Yes", "condition": "{{ vars.y == 'foo' }}"},
            {"option": "No", "default": True},
        ]})),
        ("Decision", "pb-A", json.dumps({"conditions": [
            {"option": "Yes", "condition": "{{ vars.z != null }}"},
            {"option": "No", "default": True},
        ]})),
        # Distinct shape — three branches instead of two.
        ("Decision", "pb-C", json.dumps({"conditions": [
            {"option": "Hi", "condition": "x"},
            {"option": "Med", "condition": "y"},
            {"option": "Lo", "default": True},
        ]})),
        # A SetVariable row to confirm the friendly mapping picks the
        # right corpus type.
        ("SetVariable", "pb-D", json.dumps({"output": "{{ vars.r }}"})),
    ]
    for st, pb, args in rows:
        conn.execute(
            "INSERT INTO playbook_steps (source, source_path, step_type_name, "
            "playbook_name, arguments_json, ingested_at) VALUES "
            "('test', '/x', ?, ?, ?, '2026-05-08')",
            (st, pb, args),
        )
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_cluster_examples_groups_jinja_variants(fake_corpus):
    clusters = cluster_examples(fake_corpus, "decision", limit=10)
    # Two distinct Decision shapes: 2-branch (×3) and 3-branch (×1).
    assert len(clusters) == 2
    assert clusters[0]["frequency"] == 3
    assert clusters[0]["playbook_count"] == 2  # pb-A, pb-B
    assert clusters[1]["frequency"] == 1
    # Summaries are populated.
    assert clusters[0]["summary"].startswith("if ")
    assert "Yes" in clusters[0]["summary"]


def test_cluster_examples_returns_empty_for_unknown_type(fake_corpus):
    assert cluster_examples(fake_corpus, "not_a_real_step_type") == []


def test_cluster_examples_respects_limit(fake_corpus):
    out = cluster_examples(fake_corpus, "decision", limit=1)
    assert len(out) == 1
    assert out[0]["frequency"] == 3  # highest-frequency cluster wins


def test_cluster_examples_friendly_to_corpus_mapping(fake_corpus):
    out = cluster_examples(fake_corpus, "set_variable", limit=5)
    assert len(out) == 1
    assert out[0]["corpus_type"] == "SetVariable"
    assert out[0]["summary"] == "Sets output."
