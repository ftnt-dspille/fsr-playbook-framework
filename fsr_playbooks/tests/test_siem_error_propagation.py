"""SIEM first-class tools must PROPAGATE the underlying run_op failure detail,
not collapse it to a bare code. Export sess-vtd15c5v: siem_search_ip returned
only `code:"bad_params"` with no `issues`/`message`, so the agent couldn't
self-correct and fell back to raw run_op guessing."""
from fsr_playbooks.mcp_server.tools_triage import _siem_error


def test_propagates_issues_and_suggestions():
    underlying = {
        "ok": False, "code": "bad_params",
        "message": "operation 'execute_api_request' called with 1 invalid arg",
        "issues": [{"param": "payload_format", "problem": "bad_select_value",
                    "options": ["json", "xml"]}],
        "suggestions": ["Re-issue with corrected args"],
        "valid_params": [{"name": "endpoint", "required": True}],
    }
    out = _siem_error("siem_search_ip", {"ip": "1.2.3.4"}, underlying)
    assert out["ok"] is False
    assert out["code"] == "bad_params"
    assert out["message"].startswith("operation 'execute_api_request'")
    assert out["issues"] == underlying["issues"]
    assert out["suggestions"] == underlying["suggestions"]
    assert out["valid_params"] == underlying["valid_params"]
    assert out["query"] == {"ip": "1.2.3.4"}


def test_handles_non_dict_underlying():
    out = _siem_error("siem_raw_query", {"where": "x"}, None)
    assert out["ok"] is False
    assert out["code"] == "siem_op_failed"
    assert "issues" not in out  # nothing to propagate, no empty keys
