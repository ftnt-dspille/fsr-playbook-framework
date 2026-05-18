from backend.llm.tools import (
    AUDIT_LOG,
    REGISTRY,
    _resolve_tier,
    anthropic_tools,
    dispatch,
)


def test_registry_nonempty():
    assert len(REGISTRY) >= 10
    assert "find_connector" in REGISTRY
    assert "verify_playbook" in REGISTRY


def test_anthropic_schema_shape():
    schemas = anthropic_tools()
    for s in schemas:
        assert set(s) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
        assert isinstance(s["input_schema"]["properties"], dict)
        assert isinstance(s["input_schema"]["required"], list)


def test_dispatch_find_connector():
    out = dispatch("find_connector", {"q": "jira", "limit": 3})
    assert isinstance(out, dict)
    assert isinstance(out["matches"], list)
    assert len(out["matches"]) <= 3


def test_dispatch_unknown_tool_returns_error():
    out = dispatch("does_not_exist", {})
    assert isinstance(out, dict) and "error" in out


def test_dispatch_bad_args_returns_error():
    out = dispatch("find_connector", {"unexpected_kw": 1})
    assert isinstance(out, dict) and "error" in out


def test_tier_resolution_static():
    assert _resolve_tier("find_connector", {}) == 0
    assert _resolve_tier("verify_playbook", {}) == 1


def test_tier_resolution_run_op_unknown_escalates():
    # No DB row for this fake op → must escalate, not auto-allow.
    tier = _resolve_tier("run_op", {"connector": "__nope__", "op": "__nope__"})
    assert tier >= 3


def test_tier_resolution_simulator_unsafe_flag_escalates():
    assert _resolve_tier("step_through_playbook", {}) == 1
    assert _resolve_tier("step_through_playbook", {"execute_unsafe_ops": True}) == 3


def test_dispatch_gates_tier3_calls():
    # Unknown connector/op → resolver returns tier 3, dispatch returns pending_approval
    # without invoking the underlying function.
    out = dispatch("run_op", {"connector": "__nope__", "op": "__nope__"})
    assert isinstance(out, dict)
    assert out.get("pending_approval") is True
    assert "approval_id" in out
    assert out["tier"] >= 3
    assert out["tool"] == "run_op"
    assert "preview" in out and out["preview"]["tool"] == "run_op"


def test_dispatch_preview_masks_sensitive_keys():
    out = dispatch(
        "run_op",
        {"connector": "__nope__", "op": "__nope__", "params": {"api_key": "shh", "host": "h"}},
    )
    assert out["pending_approval"] is True
    preview_args = out["preview"]["args"]
    assert preview_args["params"]["api_key"] == "***"
    assert preview_args["params"]["host"] == "h"


def test_dispatch_auto_allow_tier0_records_audit():
    before = len(AUDIT_LOG)
    dispatch("find_connector", {"q": "jira", "limit": 1})
    assert len(AUDIT_LOG) > before
    row = AUDIT_LOG[-1]
    assert row["tool"] == "find_connector"
    assert row["tier"] == 0
    assert row["decision"] == "auto_allow"
