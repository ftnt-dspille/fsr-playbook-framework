"""Regression: SIEM search wrappers must tolerate a string `limit` (the shape
the MCP layer hands a model). Before the fix, `siem_search_ip(..., limit="25")`
crashed at `min(limit, 1000)` with
`'<' not supported between instances of 'int' and 'str'`, so the agent's SIEM
pivot dead-ended and it fell back to alert-module evidence only (observed live
on a telnet brute-force triage).
"""
import contextlib

from fsr_playbooks.mcp_server import tools_triage as T


def test_as_int_tolerates_mcp_string_and_junk():
    assert T._as_int("25", 9) == 25
    assert T._as_int(25, 9) == 25
    assert T._as_int("  7 ", 9) == 7
    for junk in ("", None, "abc", True, False):
        assert T._as_int(junk, 9) == 9


def _drive_pubv2_with_string_limit(monkeypatch):
    """Run _siem_pubv2_query through the results/min(limit,1000) path with a
    stubbed connector, passing limit as a string."""
    from fsr_playbooks import execution_api as EA

    calls = {"n": 0}

    def fake_run_op(connector, op, args, confirm=False):
        ep = args.get("endpoint", "")
        if ep.endswith("/eventQuery"):
            return {"ok": True, "data": {"queryId": "q-123"}}
        if ep.endswith("/progress"):
            return {"ok": True, "data": {"progress": 100}}
        if ep.endswith("/results"):
            # This branch runs `min(limit, 1000)` -- the crash site.
            calls["n"] += 1
            return {"ok": True, "data": {"events": []}}
        return {"ok": True, "data": {}}

    monkeypatch.setattr(EA, "run_op", fake_run_op, raising=False)
    monkeypatch.setattr(EA, "mute_recording",
                        lambda *a, **k: contextlib.nullcontext(), raising=False)
    return calls


def test_siem_search_ip_accepts_string_limit(monkeypatch):
    calls = _drive_pubv2_with_string_limit(monkeypatch)
    out = T.siem_search_ip("198.51.100.43", direction="src",
                           window="24h", limit="25")  # string, as MCP delivers
    assert isinstance(out, dict) and out.get("ok") is True
    assert calls["n"] == 1  # reached the results fetch without raising


def test_siem_raw_query_accepts_string_poll_and_limit(monkeypatch):
    _drive_pubv2_with_string_limit(monkeypatch)
    out = T.siem_raw_query({"sourceIPv4": "1.2.3.4"},
                           window="1d", limit="10", poll_max="8")
    assert isinstance(out, dict) and out.get("ok") is True
