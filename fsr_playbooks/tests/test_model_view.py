"""What the model re-reads from a tool result: everything it needs to act on,
not echoes of what it just sent. The host still gets the full result."""
from fsr_playbooks.llm._loop_helpers import model_view


def test_a_delivered_card_is_not_echoed_back():
    res = {"ok": True, "card_type": "enhancement_offer",
           "card": {"id": "e1", "final_yaml": "x" * 9000}}
    assert model_view("emit_card", res) == {
        "ok": True, "card_type": "enhancement_offer", "card_id": "e1", "delivered": True}
    refused = {"ok": False, "code": "not_afforded", "error": "why"}
    assert model_view("emit_card", refused) == refused


def test_a_passing_edit_keeps_the_handle_and_drops_echoes():
    res = {"ok": True, "ready_to_push": True, "verified_id": "v1",
           "how_to_apply": "emit_card(...)", "after_yaml": "y" * 3000,
           "applied": ["added X"], "checks_run": [{}],
           "evidence": {"type_trace_path": "/tmp/t.json", "typed_walk": {"b": 1}},
           "diff_summary": {"steps_added": ["X"], "changes": [
               {"playbook": "P", "step": "X", "kind": "added", "type": "set_variable",
                "before": None, "after": {"vars": {"a": 1}}, "changed_fields": []},
               {"playbook": "P", "step": "New", "kind": "renamed", "type": "decision",
                "before": {"name": "Old"}, "after": {"name": "New"},
                "changed_fields": ["name"]}]}}
    v = model_view("edit_playbook", res)
    assert v["verified_id"] == "v1" and v["how_to_apply"]
    for gone in ("after_yaml", "applied", "checks_run"):
        assert gone not in v
    assert v["evidence"] == {}
    assert v["diff_summary"]["changes"] == [
        {"playbook": "P", "step": "X", "kind": "added", "type": "set_variable"},
        {"playbook": "P", "step": "New", "kind": "renamed", "type": "decision",
         "changed_fields": ["name"], "before": "Old", "after": "New"}]
    assert "after" in res["diff_summary"]["changes"][0]  # host copy untouched


def test_a_failing_edit_keeps_its_fixes_and_yaml():
    res = {"ok": False, "ready_to_push": False, "after_yaml": "y",
           "required_fixes": [{"code": "bad_value", "message": "m"}],
           "how_to_apply": "NOT ready", "applied": ["a"]}
    v = model_view("edit_playbook", res)
    assert v["required_fixes"] and v["after_yaml"] == "y"
    assert "how_to_apply" not in v and "applied" not in v


def test_find_operation_carries_connector_status(monkeypatch):
    from fsr_playbooks.mcp_server import tools_find
    monkeypatch.setattr(tools_find, "_connector_status",
                        lambda n: {"configured": True, "health": "Disconnected"})
    out = tools_find.find("operation", "create incident", connector="servicenow")
    assert out["connector_status"] == {"configured": True, "health": "Disconnected"}
