"""CLI smoke tests — invoke each subcommand as a subprocess.

We use subprocess (not import) because that's how users actually run
fsrpb. Catches PYTHONPATH / module-resolution regressions the unit
tests would miss.
"""
from __future__ import annotations

import json
import subprocess

import pytest

CLI = ["python3", "cli.py"]  # cwd will be python/


def _run(repo_root, *args, **kw):
    return subprocess.run(
        CLI + list(args),
        cwd=repo_root / "tooling",
        capture_output=True, text=True, **kw,
    )


def test_compile(repo_root, db_path, tmp_path):
    out = tmp_path / "out.json"
    r = _run(repo_root, "compile", str(repo_root / "examples" / "hello_connector.yaml"),
             "-o", str(out))
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    assert data["data"][0]["workflows"][0]["name"] == "Hello Connector"


def test_validate_ok(repo_root, db_path):
    r = _run(repo_root, "validate", str(repo_root / "examples" / "hello_connector.yaml"))
    assert r.returncode == 0, r.stderr


def test_validate_errors_json(repo_root, db_path, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "collection: T\nplaybooks:\n  - name: P\n    steps:\n"
        "      - name: s\n        type: connetor\n"
    )
    r = _run(repo_root, "validate", str(bad), "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert any(e["code"] == "unknown_step_type" for e in payload)


def test_explain_handler(repo_root, db_path):
    r = _run(repo_root, "explain", "handler", "cond")
    assert r.returncode == 0
    assert "cond(step, conditions" in r.stdout


def test_explain_step(repo_root, db_path):
    r = _run(repo_root, "explain", "step", "Decision")
    assert r.returncode == 0
    assert "handler: cond" in r.stdout


def test_roundtrip_subcommand(repo_root, db_path, corpus_path, tmp_path):
    src = json.loads(corpus_path.read_text())
    target = None
    for col in src["data"]:
        for wf in col.get("workflows", []):
            if wf.get("uuid") == "688c7f82-d148-40d7-a308-392412170b7a":
                target = (col, wf)
                break
        if target: break
    if not target:
        pytest.skip("known target playbook missing from corpus")
    col, wf = target
    extract = {
        "type": "workflow_collections", "macros": [], "exported_tags": [],
        "data": [{
            "@type": "WorkflowCollection", "name": col["name"],
            "description": col.get("description", ""),
            "visible": col.get("visible", True), "uuid": col["uuid"],
            "workflows": [wf],
        }],
    }
    p = tmp_path / "single.json"
    p.write_text(json.dumps(extract))
    r = _run(repo_root, "roundtrip", str(p))
    assert r.returncode == 0, r.stderr


def test_push_subcommand_registered(repo_root):
    """We don't hit the live FSR in tests — just confirm the subcommand
    is wired and shows up in --help."""
    r = _run(repo_root, "--help")
    assert r.returncode == 0
    assert " push " in r.stdout


def test_decompile(repo_root, db_path, corpus_path, tmp_path):
    src = json.loads(corpus_path.read_text())
    extract = {
        "type": "workflow_collections", "macros": [], "exported_tags": [],
        "data": [src["data"][0]],
    }
    p = tmp_path / "in.json"
    p.write_text(json.dumps(extract))
    r = _run(repo_root, "decompile", str(p))
    assert r.returncode == 0, r.stderr
    assert "collection:" in r.stdout
    assert "playbooks:" in r.stdout
