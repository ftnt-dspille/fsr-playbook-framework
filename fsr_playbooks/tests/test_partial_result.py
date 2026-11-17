"""The partial-result shape: delivered / unknowns / next for gap conditions."""
import pytest
from pydantic import ValidationError

from fsr_playbooks.llm.tool_result import partial_problems, partial_result


def test_shape_and_back_compat_keys():
    r = partial_result("c", "m", unknowns=["a"], next=["b"], delivered={"x": 1})
    assert r["ok"] is False and r["partial"] is True and r["code"] == "c"
    assert r["delivered"] == {"x": 1}
    assert r["unknowns"] == ["a"] and r["next"] == ["b"]
    assert r["suggestions"] == ["b"]
    assert partial_problems(r) == []


@pytest.mark.parametrize("kw", [
    {"unknowns": [], "next": ["b"]},
    {"unknowns": ["a"], "next": []},
    {"unknowns": [" "], "next": ["b"]},
])
def test_gap_result_must_name_unknown_and_next(kw):
    with pytest.raises(ValidationError):
        partial_result("c", "m", **kw)


def test_bare_refusal_is_not_partial():
    assert partial_problems({"ok": False, "code": "x", "message": "no"})
    assert partial_problems("nope")


@pytest.fixture
def no_fsr(monkeypatch):
    from fsr_playbooks.mcp_server import _shared
    monkeypatch.setattr(_shared, "_live_client", lambda: None)


def test_read_tools_return_partial_without_fsr(no_fsr):
    from fsr_playbooks.mcp_server import tools_triage
    for out in (tools_triage.search_module_records(module="alerts"),
                tools_triage.get_record(module="alerts", uuid="0" * 8 + "-0000-0000-0000-" + "0" * 12)):
        assert out["code"] == "no_fsr_configured"
        assert partial_problems(out) == [], out


def test_helpers_build_valid_partials():
    from fsr_playbooks.llm.tool_result import (
        carry_partial,
        no_fsr_partial,
        unreachable_partial,
    )
    a = no_fsr_partial("the thing", delivered={"k": []})
    b = unreachable_partial("the data", "GET", "https://x/y", RuntimeError("boom"))
    assert partial_problems(a) == [] and partial_problems(b) == []
    assert b["code"] == "transport_error" and b["url"] == "https://x/y"
    # a wrapper keeps the gap and adds its own context
    c = carry_partial(a, op="siem_search")
    assert c["op"] == "siem_search" and partial_problems(c) == []
    assert carry_partial({"ok": False, "code": "x", "message": "m"}) is None
    assert carry_partial("nope") is None


def test_unreachable_read_is_partial(monkeypatch):
    from fsr_playbooks.mcp_server import _shared, tools_triage

    class _C:
        base_url = "https://soar.example.com"

    def _boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(_shared, "_live_client", lambda: _C())
    monkeypatch.setattr(tools_triage, "_get_with_reauth", _boom)
    out = tools_triage.get_record(module="alerts", uuid="0" * 8 + "-0000-0000-0000-" + "0" * 12)
    assert out["code"] == "transport_error"
    assert partial_problems(out) == [], out


# --- W4 rest: source gaps from run_op, write-side unknown outcomes ----------

_RUN_OP_GAPS = {
    "transport_failed": {"ok": False, "code": "transport_failed", "message": "conn reset", "status": "?"},
    "upstream_error": {"ok": False, "code": "upstream_error", "message": "boom (HTTP 502)", "status": "502"},
    "op_request_rejected": {"ok": False, "code": "op_request_rejected", "message": "bad id", "status": "400"},
    "connector_unhealthy": {"ok": False, "code": "connector_unhealthy", "message": "healthcheck failing",
                            "health_status": "Disconnected", "suggestions": ["check creds"]},
    "connector_not_configured": {"ok": False, "code": "connector_not_configured", "message": "no config"},
}


@pytest.fixture
def run_op_answers(monkeypatch):
    """Make every run_op answer ``box['res']``."""
    from fsr_playbooks import execution_api
    from fsr_playbooks.mcp_server import tools_edr, tools_noc, tools_triage
    box: dict = {}
    monkeypatch.setattr(execution_api, "run_op", lambda *a, **k: box["res"])
    monkeypatch.setattr(tools_triage, "_siem_connector", lambda: "fortinet-fortisiem")
    monkeypatch.setattr(tools_edr, "_edr_connector", lambda: "fortinet-fortiedr")
    monkeypatch.setattr(tools_noc, "_fmg_config", lambda: "")
    return box


def _callers():
    from fsr_playbooks.mcp_server import tools_edr, tools_noc, tools_triage
    return {
        "siem": lambda: tools_triage._siem_run("search", {}, 5, {"q": "x"}),
        "faz": lambda: tools_triage._faz_run("get_alerts", {}, 5, {"q": "x"}, lambda r: r),
        "fmg": lambda: tools_noc._fmg_get("/dvmdb/device", {"q": "x"}, lambda r: r, 5, "devices"),
        "edr": lambda: tools_edr._error("events", _RUN_OP_GAPS["x"], {"q": "x"}),
    }


@pytest.mark.parametrize("code", sorted(_RUN_OP_GAPS))
@pytest.mark.parametrize("who", ["siem", "faz", "fmg"])
def test_source_gap_codes_are_partial(run_op_answers, who, code):
    run_op_answers["res"] = _RUN_OP_GAPS[code]
    out = _callers()[who]()
    assert out["code"] == code
    assert partial_problems(out) == [], out
    assert out["query"] == {"q": "x"}


@pytest.mark.parametrize("code", sorted(_RUN_OP_GAPS))
def test_edr_source_gap_is_partial(code):
    from fsr_playbooks.mcp_server import tools_edr
    out = tools_edr._error("events", _RUN_OP_GAPS[code], {"q": "x"})
    assert out["code"] == code and out["step"] == "events"
    assert partial_problems(out) == [], out


def test_gap_keeps_underlying_context(run_op_answers):
    run_op_answers["res"] = _RUN_OP_GAPS["connector_unhealthy"]
    out = _callers()["siem"]()
    assert out["health_status"] == "Disconnected"
    assert "check creds" in out["next"]


def test_actionable_errors_stay_plain_errors(run_op_answers):
    run_op_answers["res"] = {"ok": False, "code": "bad_params", "message": "x",
                             "suggestions": ["fix it"]}
    out = _callers()["siem"]()
    assert out["code"] == "bad_params" and "partial" not in out


def test_siem_raw_clause_hint_survives_rejection(run_op_answers):
    from fsr_playbooks.mcp_server import tools_triage
    out = tools_triage._siem_error("search", {"where": "a OR b"}, _RUN_OP_GAPS["op_request_rejected"])
    assert partial_problems(out) == []
    assert out["next"][0].startswith("Don't retry this raw clause")


def test_siem_dead_fetch_is_not_zero_events(monkeypatch):
    """A failed progress/results call used to read as an ok query with no events."""
    from fsr_playbooks import execution_api
    from fsr_playbooks.mcp_server import tools_triage
    monkeypatch.setattr(tools_triage, "_siem_connector", lambda: "fortinet-fortisiem")
    monkeypatch.setattr(tools_triage, "_time", type("T", (), {"sleep": staticmethod(lambda s: None)}),
                        raising=False)
    calls = []

    def fake(conn, op, params, **kw):
        calls.append(params.get("endpoint"))
        if params.get("endpoint", "").endswith("/query"):
            return {"ok": True, "data": "qid-1"}
        if "progress" in params.get("endpoint", ""):
            return {"ok": True, "data": {"progress": 100}}
        return _RUN_OP_GAPS["upstream_error"]

    monkeypatch.setattr(execution_api, "run_op", fake)
    out = tools_triage.siem_raw_query("srcIpAddr=\"10.1.1.1\"")
    assert out["ok"] is False and out["code"] == "upstream_error", (out, calls)
    assert partial_problems(out) == []


def test_failed_assertion_lookup_is_partial(monkeypatch):
    from fsr_playbooks.mcp_server import tools_triage
    monkeypatch.setattr(tools_triage, "_query_module",
                        lambda *a, **k: {"_error": "timeout", "_http_status": 504})
    for kind in ("record_exists", "record_count", "field_equals"):
        out = tools_triage._assert_one(None, {"kind": kind, "module": "alerts", "value": 1,
                                              "field": "f"})
        assert out["code"] == "query_failed" and out["kind"] == kind
        assert partial_problems(out) == [], out


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text

    def json(self):
        return {}


@pytest.fixture
def write_env(monkeypatch):
    from fsr_playbooks.mcp_server import _shared, tools_records

    class _C:
        base_url = "https://soar.example.com"

    monkeypatch.setattr(_shared, "_live_client", lambda: _C())
    monkeypatch.setattr(tools_records, "_unknown_fields", lambda *a, **k: None)
    monkeypatch.setattr(tools_records, "_structured_into_text", lambda *a, **k: None)
    monkeypatch.setattr(_shared, "record_write_gate", lambda m: None)
    return tools_records


def _boom(*a, **k):
    raise ConnectionError("reset")


def test_create_transport_error_never_says_retry_blindly(write_env, monkeypatch):
    monkeypatch.setattr(write_env, "_request", _boom)
    out = write_env.create_record(module="alerts", fields={"name": "x"})
    assert out["code"] == "transport_error" and partial_problems(out) == [], out
    text = " ".join(out["next"] + out["unknowns"]).lower()
    assert "whether the record was created" in text
    assert out["next"][0].lower().startswith("look the record up first")
    assert "retry" not in text
    assert out["next"][1].lower().startswith("create it again only if")


def test_update_transport_error_asks_for_a_reread(write_env, monkeypatch):
    monkeypatch.setattr(write_env, "_request", _boom)
    out = write_env.update_record(module="alerts", uuid="0" * 8 + "-0000-0000-0000-" + "0" * 12,
                                  fields={"name": "x"})
    assert out["code"] == "transport_error" and partial_problems(out) == [], out
    assert out["next"][0].lower().startswith("re-read the record")


def test_write_5xx_outcome_unknown_but_4xx_stays_refusal(write_env, monkeypatch):
    monkeypatch.setattr(write_env, "_request", lambda *a, **k: _Resp(502, "bad gateway"))
    out = write_env.create_record(module="alerts", fields={"name": "x"})
    assert out["code"] == "http_502" and partial_problems(out) == [], out
    monkeypatch.setattr(write_env, "_request", lambda *a, **k: _Resp(403, "nope"))
    out = write_env.create_record(module="alerts", fields={"name": "x"})
    assert out["code"] == "http_403" and "partial" not in out
