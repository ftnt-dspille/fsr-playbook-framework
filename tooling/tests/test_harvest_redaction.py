"""Harvest-time redaction: the probes must not store credentials they read.

A live appliance's playbooks carry real secrets (an API key pair in a
`SetAPIKeys` step, bearer tokens, service-account passwords in code
snippets). Every probe that INSERTs step arguments or snippets runs them
through `redact_obj` first; these tests drive the real probe functions with
fake appliance data and assert nothing secret reaches the DB.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from probes import probe_playbook_steps as pps
from probes import probe_playbooks as pp
from probes.common import REPO_ROOT

PEM = ("-----BEGIN RSA PRIVATE KEY-----\n"
       "MIIFAKEFAKEFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfake1234\n"
       "fakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfake5678\n"
       "-----END RSA PRIVATE KEY-----")
ARGS = {
    "private_key": PEM,
    "headers": "{\n  \"Authorization\": \"Bearer fakeTokenfakeTokenfakeToken00\"\n}",
    "python_function": "payload = {'password': 'Sup3rSecret!'}",
    "keep": {"password": "changeme"},
}
SECRETS = ("MIIFAKEFAKEF", "fakeTokenfakeTokenfakeToken00", "Sup3rSecret")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript((REPO_ROOT / "data" / "schema.sql").read_text())
    conn.execute("INSERT INTO step_types (name, uuid) VALUES ('SetAPIKeys', 't1')")
    return conn


def _assert_clean(text: str):
    for s in SECRETS:
        assert s not in text, s
    assert "changeme" in text            # vendor default untouched


class _Client:
    def get(self, url, params=None):
        return {"hydra:totalItems": 1, "hydra:member": [
            {"uuid": "u1", "name": "set keys", "stepType": {"name": "SetAPIKeys"},
             "arguments": ARGS}]}


def test_probe_playbooks_step_examples_are_redacted():
    conn = _db()
    pp._mine_steps(conn, _Client())
    rows = conn.execute("SELECT snippet_json FROM step_examples").fetchall()
    assert rows
    _assert_clean(rows[0][0])


def test_probe_playbook_steps_ingest_is_redacted(tmp_path: Path):
    conn = _db()
    wf = {"@type": "Workflow", "name": "pb", "uuid": "w1", "steps": [
        {"@type": "WorkflowStep", "uuid": "s1", "name": "set keys",
         "stepType": "/api/3/workflow_step_types/t1", "arguments": ARGS},
        {"@type": "WorkflowStep", "uuid": "s2", "name": "x",
         "stepType": "/api/3/workflow_step_types/t1", "arguments": {}}]}
    f = tmp_path / "pb.json"
    f.write_text(json.dumps(wf))
    pps._ingest_file(conn, "incoming", f, {"t1": "SetAPIKeys"}, "now", include_samples=True)
    rows = conn.execute("SELECT arguments_json FROM playbook_steps").fetchall()
    assert rows
    _assert_clean(" ".join(r[0] for r in rows))
