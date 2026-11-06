"""find_connector surfaces whether a connector needs a configuration (S3 residual).

The S3 build-persona eval's one remaining failure: the model called
`list_configured_connectors`, didn't see cyops_utilities (a config-LESS utility,
config_count=0), concluded "connector not available", and bailed to a skeleton
with an undefined input. cyops_utilities needs no config -- its ops run with
`config: ''`. `find_connector` now returns a `config_required` bool per match and
a note that absence from the configured list is not unavailability.
"""
from fsr_playbooks.mcp_server.tools_discovery import (
    _connector_config_required as needs_config,
)
from fsr_playbooks.mcp_server.tools_discovery import (
    find_connector,
)


def test_config_required_helper():
    # config-LESS → False
    for empty in (None, "", "{}", '{"fields": []}', "[]"):
        assert needs_config(empty) is False, f"{empty!r} should be config-less"
    # config-REQUIRING → True
    assert needs_config('{"fields": [{"name": "server_url"}]}') is True
    assert needs_config('[{"name": "host"}]') is True
    # malformed blob → treated as config-less (fail open, never crash)
    assert needs_config("not json{{") is False


def test_find_connector_marks_config_required_per_match():
    r = find_connector("utilities")
    matches = r.get("matches") or []
    assert matches, "expected at least one utilities-category match in the catalog"
    for m in matches:
        assert isinstance(m.get("config_required"), bool), \
            "every match must carry a config_required bool"
    # If any match is config-less, the note must steer away from the
    # 'absent-from-configured-list == unavailable' misread.
    if any(not m["config_required"] for m in matches):
        assert "config: ''" in (r.get("note") or ""), \
            "config-less matches must include the `config: ''` guidance note"


def _warmed_catalog(tmp_path, schema_json: str):
    """A copy of the shipped catalog whose FortiAIGate row is shaped like a box
    warm left it: no schema in the column (empty, or the saved configurations)."""
    import shutil
    import sqlite3
    from pathlib import Path

    import fsr_playbooks
    db = tmp_path / "warmed.db"
    shutil.copy(Path(fsr_playbooks.__file__).parent / "_data" / "fsr_reference.db", db)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM connectors WHERE name='fortinet-fortiaigate'")
        cols = [c[1] for c in con.execute("PRAGMA table_info(connectors)")]
        row = {c: None for c in cols}
        row.update(name="fortinet-fortiaigate", label="Fortinet FortiAIGate",
                   category="analytics", config_schema_json=schema_json,
                   version="1.7.1", source="fortisoar_api")
        con.execute(f"INSERT INTO connectors ({','.join(cols)}) VALUES "
                    f"({','.join('?' * len(cols))})", [row[c] for c in cols])
    return db


def test_find_connector_asks_the_box_when_the_row_holds_no_schema(monkeypatch, tmp_path):
    # Seen live: after a box warm, find(kind=connector) said FortiAIGate (12
    # saved configs, a schema with fields) "needs NO configuration" and told
    # the model to author `config: ''`.
    from fsr_playbooks.mcp_server import tools_emit
    monkeypatch.setattr(tools_emit, "_LIVE_SCHEMA_CACHE", {})
    asked = []

    def fake(connector, version):
        asked.append((connector, version))
        return {"fields": [{"name": "server_url", "required": True}]}
    monkeypatch.setattr(tools_emit, "_box_config_schema", fake)
    for blob in ("", '[{"config_id": "c1", "name": "Prod"}]'):
        asked.clear()
        r = find_connector("fortiaigate", db_path=_warmed_catalog(tmp_path, blob))
        [m] = r["matches"]
        assert m["name"] == "fortinet-fortiaigate"
        assert m["config_required"] is True, (blob, r)
        assert asked == [("fortinet-fortiaigate", "1.7.1")], blob
        assert "fortinet-fortiaigate" not in (r.get("note") or ""), r
        (tmp_path / "warmed.db").unlink()


def test_find_connector_keeps_a_real_schema_without_asking(monkeypatch, tmp_path):
    from fsr_playbooks.mcp_server import tools_emit
    monkeypatch.setattr(tools_emit, "_box_config_schema",
                        lambda c, v: (_ for _ in ()).throw(AssertionError("asked")))
    r = find_connector("fortiaigate", db_path=_warmed_catalog(tmp_path, '{"fields": []}'))
    assert r["matches"][0]["config_required"] is False
