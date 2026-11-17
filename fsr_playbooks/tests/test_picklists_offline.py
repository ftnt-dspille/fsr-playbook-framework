"""The picklist tools answer from the SHIPPED catalog, with no appliance.

All five used to require a live instance AND this repo's `tooling/` on
sys.path (`from picklists import ...`, `from recipes.prechecks import ...`).
Neither holds on an appliance, so on-box they were dead: every call returned
"FSR instance not configured" or raised ImportError, and the agent spent ~5
calls per turn rediscovering that. The tools now read
`fsr_playbooks.picklists`, which is store-first.

These tests pin the offline path specifically -- they force `DB_PATH` to the
packaged slim DB and blank the live client, which is exactly the on-box
no-warmup state. Running them against the repo's full `data/` DB would pass
for the wrong reason (that DB has real IRIs).
"""
import sqlite3

import pytest

from fsr_playbooks import picklists as pl
from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_picklists as t

SLIM_DB = _shared.REPO_ROOT / "fsr_playbooks" / "_data" / "fsr_reference.db"


def _call(tool, *a, **kw):
    """FastMCP wraps tools; call the underlying function."""
    return (tool.fn if hasattr(tool, "fn") else tool)(*a, **kw)


@pytest.fixture
def offline(monkeypatch):
    """Packaged catalog, no live instance -- the on-box cold-start state."""
    monkeypatch.setattr(_shared, "DB_PATH", str(SLIM_DB))
    monkeypatch.setitem(_shared._LIVE_CLIENT_CACHE, "client", None)
    return SLIM_DB


def test_slim_catalog_ships_values_but_never_iris(offline):
    """The whole carve-out: values are globally stable, IRIs are per-install.

    A shipped IRI would resolve to the WRONG item on every other appliance,
    silently -- worse than not resolving at all.
    """
    conn = sqlite3.connect(f"file:{offline}?mode=ro", uri=True)
    try:
        total, with_iri = conn.execute(
            "SELECT COUNT(*), SUM(COALESCE(item_iri,'') <> '') FROM picklists"
        ).fetchone()
    finally:
        conn.close()
    assert total > 0, "slim catalog ships no picklist values"
    assert not with_iri, "per-install picklist IRIs must never ship"


def test_list_picklists_answers_offline(offline):
    out = _call(t.list_picklists)
    assert out.get("count"), out
    assert "AlertStatus" in out["names"]
    assert out["source"] == "reference_db"


def test_invalid_value_is_caught_without_an_appliance(offline):
    """The bug this tool exists for: 'In Progress' is not an AlertStatus."""
    out = _call(t.resolve_picklist_value, "In Progress",
                picklist_name="AlertStatus")
    assert out["ok"] is False
    assert out["code"] == "invalid_value"
    assert "Investigating" in out["valid_values"]


def test_valid_value_reports_a_missing_iri_as_missing_not_invalid(offline):
    """`iri_unavailable` != `invalid_value`.

    Conflating them would tell the agent a correct value is wrong, and it
    would rewrite a correct playbook to satisfy the error.
    """
    out = _call(t.resolve_picklist_value, "Open", picklist_name="AlertStatus")
    assert out["code"] == "iri_unavailable"
    assert out["value_is_valid"] is True
    assert any("warmup" in s for s in out["suggestions"])


def test_precheck_passes_a_valid_value_with_no_iri(offline):
    """A precheck asks "would this value be rejected?" -- a per-install IRI
    it cannot see yet is not a rejection."""
    out = _call(t.precheck_picklist_value, "AlertStatus", "Open")
    assert out["ok"] is True
    out = _call(t.precheck_picklist_value, "AlertStatus", "In Progress")
    assert out["ok"] is False


def test_unknown_picklist_gets_near_matches_not_an_empty_list(offline):
    out = _call(t.get_picklist, "AlertStatuss")
    assert out["unknown_picklist"] is True
    assert "AlertStatus" in out["near"]


def test_field_to_picklist_mapping_says_it_needs_a_warmed_catalog(offline):
    """`module_fields` deliberately ships empty -- it is the switch on the
    compiler's picklist validation, and validating against an unwarmed
    catalog rejects values that are valid on a stock appliance. So this tool
    cannot answer offline; the requirement is that it SAYS so instead of
    returning a bare null the model reads as "no picklist"."""
    out = _call(t.picklist_for_field, "alerts", "severity")
    assert out["picklist_name"] is None
    assert "warmup" in out["note"]


def test_field_to_picklist_mapping_works_once_warmed(monkeypatch):
    """The same call against a warmed catalog (the repo's full store stands
    in for one) resolves, so the offline miss above is environmental."""
    full = _shared.REPO_ROOT / "data" / "fsr_reference.db"
    if not full.exists():
        pytest.skip("full reference store absent")
    try:
        conn = sqlite3.connect(f"file:{full}?mode=ro", uri=True)
        try:
            warmed = conn.execute(
                "SELECT 1 FROM picklists LIMIT 1").fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        warmed = False
    if not warmed:
        pytest.skip("reference DB has no picklist rows (slim CI DB)")
    monkeypatch.setattr(_shared, "DB_PATH", str(full))
    monkeypatch.setitem(_shared._LIVE_CLIENT_CACHE, "client", None)
    out = _call(t.picklist_for_field, "alerts", "severity")
    assert out["picklist_name"] == "Severity"
    assert "Critical" in out["valid_values_local"]


def test_no_source_at_all_names_the_fix(tmp_path):
    """Empty store + no instance is the one case with no answer -- it must
    say what to run, not return an empty list (AGENT_HARDENING_PLAN §H)."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE picklists (list_name TEXT, item_value TEXT, "
                 "item_iri TEXT)")
    conn.commit()
    with pytest.raises(pl.NoPicklistData) as exc:
        pl.picklist_names(conn, client=None)
    payload = exc.value.to_dict()
    assert payload["code"] == "no_picklist_data"
    assert any("warmup" in s for s in payload["suggestions"])
    conn.close()


def test_a_real_iri_passes_through(offline):
    iri = "/api/3/picklists/7de816ff-7140-4ee5-bd05-93ce22002146"
    out = _call(t.resolve_picklist_value, iri, picklist_name="AlertStatus")
    assert out["ok"] is True and out["iri"] == iri
