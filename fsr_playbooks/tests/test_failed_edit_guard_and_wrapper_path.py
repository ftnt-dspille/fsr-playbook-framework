"""A turn must not end on an edit that still has required fixes, and the
commonest such fix (an extra `.vars.` hop) names the exact path."""
from fsr_playbooks.llm._loop_helpers import FAILED_EDIT_DIRECTIVE, EnhanceDeliveryGuard

ALLOWED = {"emit_card", "edit_playbook", "verify_enhancement"}
FAIL = {"ok": False, "ready_to_push": False,
        "required_fixes": [{"code": "missing_field_on_step_output"}] * 4}
PASS = {"ok": True, "ready_to_push": True, "verified_id": "v1"}


def test_ending_on_a_failed_edit_is_nudged_once():
    g = EnhanceDeliveryGuard()
    g.note_result("edit_playbook", {}, FAIL)
    assert g.failed_edit(ALLOWED) == 4
    g.mark_fix_forced()
    assert g.failed_edit(ALLOWED) == 0
    assert "{n}" in FAILED_EDIT_DIRECTIVE


def test_a_later_pass_or_a_gap_card_clears_it():
    g = EnhanceDeliveryGuard()
    g.note_result("edit_playbook", {}, FAIL)
    g.note_result("edit_playbook", {}, PASS)
    assert g.failed_edit(ALLOWED) == 0
    g2 = EnhanceDeliveryGuard()
    g2.note_result("edit_playbook", {}, FAIL)
    g2.note_result("emit_card", {"card_type": "capability_gap"}, {"ok": True})
    assert g2.failed_edit(ALLOWED) == 0


def test_inert_without_an_offer_tool():
    g = EnhanceDeliveryGuard()
    g.note_result("edit_playbook", {}, FAIL)
    assert g.failed_edit({"edit_playbook"}) == 0


def test_a_hung_healthcheck_holds_only_the_first_probe(monkeypatch):
    # Live (.159): one healthcheck never answered and, uncached, held every
    # list_configured_connectors(probe=True) to the full deadline.
    import threading
    import time

    from fsr_playbooks.mcp_server import tools_connector_discovery as d
    from fsr_playbooks.mcp_server import tools_execution as te
    release = threading.Event()

    def live(client, name, version, agent_id=""):
        if name == "hangs":
            release.wait(5)
        return {"status": "Available"}
    monkeypatch.setattr(te, "_live_healthcheck", live)
    monkeypatch.setattr(te, "_cached_health", lambda *a, **k: None)
    monkeypatch.setattr(te, "_store_health", lambda *a, **k: None)
    monkeypatch.setattr(d, "_PROBE_STRAGGLERS", {})
    targets = [("hangs", "1"), ("fine", "1")]
    t = time.perf_counter()
    first = d._healthcheck_many(None, targets, deadline_s=0.5)
    assert time.perf_counter() - t >= 0.5 and first == {"fine": "Available"}
    t = time.perf_counter()
    second = d._healthcheck_many(None, targets, deadline_s=0.5)
    release.set()
    assert time.perf_counter() - t < 0.4 and second == {"fine": "Available"}
