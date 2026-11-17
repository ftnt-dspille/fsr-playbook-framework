"""find(containment) matches the target on words, not substrings.

Live: "block ip ..." with FortiGate down offered NinjaOne Run Script as the IP
block -- `"ip" in "run_script"` -- and the agent staged it with placeholder
args. The target keyword has to name a word of the op, not hide inside one.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_connector_discovery as tcd

IP = tcd._TARGET_KEYWORDS["ip"]


@pytest.mark.parametrize("op,title", [
    ("block_ip_new", "Block IP Address"),
    ("blockIPAddress", ""),
    ("quarantine_ipv4", ""),
    ("add_to_blacklist", "Add To Blacklist"),
])
def test_ops_that_name_an_ip_match(op, title):
    assert tcd._names_target(op, title, IP)


@pytest.mark.parametrize("op,title", [
    ("run_script", "Run Script"),
    ("update_device_description", "Update Device Description"),
])
def test_an_ip_hidden_inside_a_word_does_not_match(op, title):
    assert not tcd._names_target(op, title, IP)


def test_file_does_not_match_profile():
    assert not tcd._names_target("disable_profile", "Disable Profile",
                                 tcd._TARGET_KEYWORDS["file"])
    assert tcd._names_target("quarantine_files", "", tcd._TARGET_KEYWORDS["file"])


def test_run_script_is_not_ip_containment(monkeypatch, tmp_path):
    # Its own store: the packaged slim DB carries no NinjaOne ops, and a test
    # that leans on a dev DB goes green in CI for the wrong reason.
    db = tmp_path / "ops.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE operations (connector_name, op_name, title, "
                  "category, enabled)")
        c.executemany("INSERT INTO operations VALUES (?,?,?,?,1)", [
            ("ninjaone", "run_script", "Run Script", "remediation"),
            ("fortigate-firewall", "block_ip_new", "Block IP Address", "containment"),
        ])
    monkeypatch.setattr(tcd, "DB_PATH", str(db))
    monkeypatch.setattr(tcd, "_required_params", lambda *a, **k: [])
    monkeypatch.setattr(tcd, "_param_sig", lambda *a, **k: [])
    monkeypatch.setattr(tcd, "list_configured_connectors", lambda **_: {
        "configured": [{"name": n, "status": "Completed", "version": "1.0.0"}
                       for n in ("ninjaone", "fortigate-firewall")]})
    monkeypatch.setattr(_shared, "_live_client", lambda: object())
    monkeypatch.setattr(tcd, "_healthcheck_many",
                        lambda client, targets, **_: {t[0]: "Available" for t in targets})
    out = tcd.find_containment_actions(target_type="ip", probe=True)
    assert {(a["connector"], a["op"]) for a in out["actions"]} == {
        ("fortigate-firewall", "block_ip_new")}
