"""SIEM first-class tools must PROPAGATE the underlying run_op failure detail,
not collapse it to a bare code. Export a live session: siem_search_ip returned
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


_FSM_400 = ('fortinet-fortisiemv2.execute_api_request rejected the request '
            '(HTTP 400): {"message":"Internal Server Error  Connector :: '
            'fortinet-fortisiemv2V6.1.1","stack_trace":"Traceback (most recent '
            'call last):\\n  File \\"connections.py\\", line 430"}')


def test_a_connector_stack_trace_is_dropped_but_its_message_kept():
    out = _siem_error("siem_raw_query", {"ip": "1.2.3.4"},
                      {"ok": False, "status": "400", "message": _FSM_400})
    assert "Traceback" not in out["message"]
    assert out["message"].endswith("Internal Server Error  Connector :: "
                                   "fortinet-fortisiemv2V6.1.1")


def test_a_failed_raw_clause_points_at_the_structured_searches():
    """Live: three multi-field OR raw clauses drew FortiSIEM 400s and the turns
    stalled -- nothing in the error said what to try instead."""
    out = _siem_error("siem_raw_query",
                      {"where": 'srcIpAddr="10.0.0.1" OR userName="w"', "window": "24h"},
                      {"ok": False, "status": "400", "message": _FSM_400,
                       "suggestions": ["from the connector"]})
    assert 'siem_search(by="ip"' in out["suggestions"][0]
    assert out["suggestions"][1:] == ["from the connector"]


def test_a_structured_search_error_gets_no_raw_clause_advice():
    out = _siem_error("siem_search_ip", {"ip": "1.2.3.4"},
                      {"ok": False, "code": "bad_params", "message": "x"})
    assert "suggestions" not in out
