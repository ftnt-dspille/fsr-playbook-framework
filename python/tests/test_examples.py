"""Every YAML in examples/ must compile clean — they're documentation
fixtures and the easiest way to catch a compiler regression that breaks
real-looking authoring."""
from __future__ import annotations

import pytest

from compiler import compile_yaml


def _examples(repo_root):
    return sorted((repo_root / "examples").glob("*.yaml"))


@pytest.mark.parametrize("name", [
    "hello_connector.yaml",
    "decision_branch.yaml",
    "find_and_update.yaml",
    "manual_input_then_act.yaml",
    "parent_calls_child.yaml",
    "demo_for_each.yaml",
    "recipe_threat_feed.yaml",
    "recipe_data_ingestion.yaml",
])
def test_example_compiles(repo_root, db_path, name):
    text = (repo_root / "examples" / name).read_text()
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # Every example produces a non-empty workflow with at least one step.
    wf = r.fsr_json["data"][0]["workflows"][0]
    assert wf["steps"], f"{name} produced an empty workflow"
    assert wf["triggerStep"], f"{name} has no triggerStep"


def test_examples_dir_not_empty(repo_root):
    assert _examples(repo_root), "examples/ went empty — that's a regression"
