"""I4 -- fault-class retry.

Pins `llm.fault_class` and its wiring in `dispatch`:
  - a failed envelope is classed transient / malformed / unavailable, or None
    (not a fault class, untouched);
  - a transient fault on a read-only call is retried exactly once;
  - a malformed call is NOT retried; its hint names the bad part so the model
    rewords or narrows it;
  - an unavailable connector is NOT retried; its hint says stop and emit a
    capability_gap card.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import fault_class as F
from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.tools import ToolSpec


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(F, "RETRY_BACKOFF_S", 0.0)


def _install_tool(name, fn, tier=1):
    spec = ToolSpec(name=name, description="test", input_schema={"type": "object"},
                    fn=fn, tier=tier)
    T.REGISTRY[name] = spec
    return lambda: T.REGISTRY.pop(name, None)


def _fail_503():
    return {"ok": False, "code": "op_request_rejected",
            "message": "svc.get rejected the request (HTTP 503): upstream down"}


# ----------------------------------------------------------- classification

@pytest.mark.parametrize("env,cls", [
    # transient: the source faulted, the call did not
    ({"ok": False, "code": "upstream_error", "message": "502"}, "transient"),
    ({"ok": False, "code": "transport_failed", "message": "reset"}, "transient"),
    ({"ok": False, "code": "transport_error", "message": "conn"}, "transient"),
    ({"ok": False, "code": "agent_timeout", "message": "timed out"}, "transient"),
    ({"ok": False, "code": "http_503", "message": "maintenance"}, "transient"),
    ({"ok": False, "code": "op_request_rejected",
      "message": "svc.op rejected the request (HTTP 503): x"}, "transient"),
    ({"ok": False, "code": "op_request_rejected", "message": "x",
      "status": "500"}, "transient"),
    # malformed: the call is wrong
    ({"ok": False, "code": "op_request_rejected",
      "message": "svc.op rejected the request (HTTP 400): bad"}, "malformed"),
    ({"ok": False, "code": "http_400", "message": "400 Client Error"}, "malformed"),
    ({"ok": False, "code": "400", "message": "bad"}, "malformed"),
    ({"ok": False, "code": "unknown_filter_field", "field": "iri"}, "malformed"),
    ({"ok": False, "code": "unknown_sort_field", "field": "-x"}, "malformed"),
    ({"ok": False, "code": "unknown_operation", "op": "siem_search"}, "malformed"),
    ({"ok": False, "code": "no_time_window", "message": "needs a window"}, "malformed"),
    # unavailable: retrying cannot help
    ({"ok": False, "code": "connector_not_configured", "connector": "t"}, "unavailable"),
    ({"ok": False, "code": "connector_unhealthy", "message": "401"}, "unavailable"),
    ({"ok": False, "code": "unknown_connector", "message": "not in store"}, "unavailable"),
    ({"ok": False, "code": "connector_not_found", "message": "no ops"}, "unavailable"),
    # a name the store does not know, with the fix in the envelope: reword, not gap
    ({"ok": False, "code": "unknown_connector", "suggestions": ["fortinet-fortisiemv2"]}, "malformed"),
    ({"ok": False, "code": "connector_not_found", "near": ["fortinet-fortisase"]}, "malformed"),
    ({"ok": False, "code": "unknown_config", "message": "Its configurations: ['lab']"}, "malformed"),
    ({"ok": False, "code": "op_request_rejected",
      "message": "svc.op rejected the request (HTTP 401): no"}, "unavailable"),
    # not fault classes: keep their own envelope
    ({"ok": False, "code": "not_found", "message": "no record"}, None),
    ({"ok": False, "code": "op_request_rejected",
      "message": "svc.op rejected the request (HTTP 404): gone"}, None),
    ({"ok": False, "code": "bad_params", "message": "x"}, None),
    ({"ok": False, "code": "tool_error", "error": "internal"}, None),
    ({"ok": True, "code": "upstream_error"}, None),
    ("naked", None),
    (None, None),
])
def test_classify_fault(env, cls):
    assert F.classify_fault(env) == cls


# ------------------------------------------------------------- hint shaping

def test_bad_part_names_the_structured_field():
    assert F.bad_part({"field": "iri"}) == "`iri`"


def test_bad_part_names_the_connector():
    assert F.bad_part({"connector": "fortinet-fortisiem"}) == "`fortinet-fortisiem`"


def test_bad_part_falls_back_to_the_source_message():
    part = F.bad_part({"message": "svc.op rejected the request (HTTP 400): "
                                  "{\"message\":\"Invalid table sn_si_incident\"}"})
    assert "Invalid table sn_si_incident" in part


def test_shape_fault_keeps_envelope_and_adds_hint():
    env = {"ok": False, "code": "unknown_filter_field", "field": "iri",
           "suggestions": ["use uuid"]}
    out = F.shape_fault(env, "malformed")
    assert out["code"] == "unknown_filter_field" and out["ok"] is False
    assert out["fault_class"] == "malformed"
    assert "`iri`" in out["retry_hint"] and "reword" in out["retry_hint"].lower()
    assert out["suggestions"][0] == out["retry_hint"]
    assert out["suggestions"][1] == "use uuid"


def test_unavailable_hint_says_stop_and_gap_card():
    out = F.shape_fault({"ok": False, "code": "connector_unhealthy"}, "unavailable")
    assert "capability_gap" in out["retry_hint"]
    assert "do not" in out["retry_hint"].lower() or "cannot" in out["retry_hint"].lower()


# -------------------------------------------------------------- retry helper

def test_retry_transient_repeats_once_on_read_only():
    calls = []
    out, retried = F.retry_transient(
        _fail_503(), lambda: calls.append(1) or {"ok": True, "record": {}},
        tier=1, sleep=lambda s: None)
    assert retried is True and out == {"ok": True, "record": {}} and calls == [1]


def test_retry_transient_refused_on_gated_call():
    calls = []
    out, retried = F.retry_transient(
        _fail_503(), lambda: calls.append(1) or {"ok": True}, tier=3,
        sleep=lambda s: None)
    assert retried is False and calls == [] and out == _fail_503()


@pytest.mark.parametrize("first", [
    {"ok": False, "code": "unknown_filter_field", "field": "x"},
    {"ok": False, "code": "connector_not_configured"},
    {"ok": True, "record": {}},
])
def test_retry_transient_only_for_transient(first):
    calls = []
    out, retried = F.retry_transient(first, lambda: calls.append(1) or {"ok": True},
                                     tier=1, sleep=lambda s: None)
    assert retried is False and calls == [] and out == first


def test_retry_transient_reports_second_failure():
    out, retried = F.retry_transient(_fail_503(), _fail_503, tier=1,
                                     sleep=lambda s: None)
    assert retried is True and F.classify_fault(out) == "transient"
    shaped = F.shape_fault(out, "transient", retried=retried)
    assert shaped["retried"] is True and "Do not retry" in shaped["retry_hint"]


# ------------------------------------------------------- dispatch integration

def test_dispatch_transient_read_is_retried_once_and_recovers(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    calls = []

    def flaky():
        calls.append(1)
        return _fail_503() if len(calls) == 1 else {"ok": True, "record": {"n": 1}}

    cleanup = _install_tool("_i4_flaky", flaky, tier=1)
    try:
        out = T.dispatch("_i4_flaky", {})
    finally:
        cleanup()
    assert calls == [1, 1]
    assert out == {"ok": True, "record": {"n": 1}}


def test_dispatch_transient_retry_gives_up_after_one(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    calls = []

    def down():
        calls.append(1)
        return _fail_503()

    cleanup = _install_tool("_i4_down", down, tier=1)
    try:
        out = T.dispatch("_i4_down", {})
    finally:
        cleanup()
    assert len(calls) == 2
    assert out["retried"] is True and out["fault_class"] == "transient"


def test_dispatch_transient_on_gated_tool_is_not_retried(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    calls = []

    def gated():
        calls.append(1)
        return _fail_503()

    monkeypatch.setitem(T.TOOL_TIERS, "_i4_gated", 3)  # tier comes from the static table
    cleanup = _install_tool("_i4_gated", gated, tier=3)
    try:  # an approved re-dispatch runs it; the gate was passed, so it runs once
        out = T.dispatch("_i4_gated", {"_approved": True}, _internal=True)
    finally:
        cleanup()
    assert len(calls) == 1 and "retried" not in out


def test_dispatch_planted_first_call_400_is_not_blindly_retried_and_names_the_part(monkeypatch):
    """Known-answer shape: the first call is a bad query. The loop must NOT repeat
    it unchanged; the envelope names the bad field so the model's reworded second
    call can succeed."""
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    calls = []

    def search(field="iri"):
        calls.append(field)
        if field == "iri":
            return {"ok": False, "code": "unknown_filter_field", "field": "iri",
                    "message": "'iri' is not a field on this module"}
        return {"ok": True, "records": [{"uuid": "u1"}]}

    cleanup = _install_tool("_i4_search", search, tier=1)
    try:
        first = T.dispatch("_i4_search", {"field": "iri"})
        assert calls == ["iri"]
        assert first["fault_class"] == "malformed" and "`iri`" in first["retry_hint"]
        second = T.dispatch("_i4_search", {"field": "uuid"})
    finally:
        cleanup()
    assert second == {"ok": True, "records": [{"uuid": "u1"}]}
    assert calls == ["iri", "uuid"]


def test_dispatch_unavailable_is_not_retried_and_says_gap(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    calls = []

    def unhealthy():
        calls.append(1)
        return {"ok": False, "code": "connector_unhealthy", "message": "401"}

    cleanup = _install_tool("_i4_unhealthy", unhealthy, tier=1)
    try:
        out = T.dispatch("_i4_unhealthy", {})
    finally:
        cleanup()
    assert len(calls) == 1
    assert out["fault_class"] == "unavailable" and "capability_gap" in out["retry_hint"]


def test_dispatch_non_fault_result_is_untouched(monkeypatch):
    monkeypatch.delenv("FSRPB_STRICT_TOOL_OUTPUT", raising=False)
    env = {"ok": False, "code": "not_found", "message": "no record"}
    cleanup = _install_tool("_i4_nf", lambda: dict(env), tier=1)
    try:
        assert T.dispatch("_i4_nf", {}) == env
    finally:
        cleanup()
