"""Every axis of a merged hunt tool must actually dispatch (#69).

`siem_search` / `faz_search` / `fmg_device` replaced fifteen per-axis tools on
the model surface. Each one is a `by=` switch that delegates to the old
function -- and delegation is exactly where a merge like this rots: the callee
may live in a SIBLING module that was never imported, and nothing notices,
because the axis the author tested by hand is the one that happens to be
implemented inline.

That is precisely what shipped. `faz_search` handles `by="ip"` inline but
delegates `device` and `serial` to `tools_noc`, which `tools_triage` does not
import at module scope (it cannot: tools_noc imports _faz_run/_faz_window back
out of it). Both axes raised `NameError`, on a tool advertised as supporting
three -- while the per-axis tools that used to serve them had just been taken
off the surface. A pre-push `ruff` F821 caught it; no test did.

So these tests assert the one property the unit suite could not see: for every
declared axis, the call REACHES its implementation. They stub the transport, so
they say nothing about whether the query is right -- only that the axis is not
a dead name. An unsupported axis must come back as a structured `error`, never
an exception.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import tools_noc, tools_triage


def _unwrap(tool):
    """`@mcp.tool()` may return a wrapper; get at the plain function."""
    return getattr(tool, "fn", tool)


@pytest.fixture
def no_transport(monkeypatch):
    """Stub every appliance call so the axis switch is all that runs."""
    sentinel = {"ok": True, "stubbed": True}
    for mod in (tools_triage, tools_noc):
        # _siem_pubv2_query: siem_search's ip/host/user axes submit a pub/v2
        # query and poll it with real one-second sleeps (3s per axis here).
        for name in ("_faz_run", "_siem_run", "_fmg_run", "_fmg_get", "_siem_pubv2_query"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, lambda *a, **k: dict(sentinel))
    return sentinel


@pytest.mark.parametrize("axis", ["ip", "device", "serial"])
def test_faz_search_every_axis_reaches_an_implementation(axis, no_transport):
    out = _unwrap(tools_triage.faz_search)(by=axis, value="10.0.0.1")
    assert isinstance(out, dict)
    # The bug was a NameError escaping. A structured error is also a failure
    # here: every axis in the docstring is meant to be implemented.
    assert "unsupported by=" not in str(out.get("error", ""))


@pytest.mark.parametrize("axis", ["ip", "host", "user"])
def test_siem_search_every_axis_reaches_an_implementation(axis, no_transport):
    out = _unwrap(tools_triage.siem_search)(by=axis, value="10.0.0.1")
    assert isinstance(out, dict)
    assert "unsupported by=" not in str(out.get("error", ""))


@pytest.mark.parametrize("axis", ["list", "status", "ha", "policy"])
def test_fmg_device_every_axis_reaches_an_implementation(axis, no_transport):
    out = _unwrap(tools_noc.fmg_device)(by=axis, device="fgt-1")
    assert isinstance(out, dict)
    assert "unsupported by=" not in str(out.get("error", ""))


def test_an_unknown_axis_is_a_structured_error_not_an_exception(no_transport):
    """The switch's fall-through is a real branch and must stay one -- a raise
    here would surface to the analyst as a tool crash rather than a usable
    'use ip, device, or serial'."""
    out = _unwrap(tools_triage.faz_search)(by="not_an_axis", value="x")
    assert "unsupported by=" in out["error"]


# --- B3a: the helpers folded in as axes --------------------------------------
# siem_events_for_incident, siem_raw_query, faz_get_alerts, faz_raw_query and
# faz_event_summary left the advertised surface and became axes. "Reaches an
# implementation" is not enough for these: each axis must hand the helper the
# argument it used to take directly, or the model's one-verb call silently
# queries for nothing.

@pytest.fixture
def spy(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def install(mod, name):
        def fake(**kw):
            calls.append((name, kw))
            return {"ok": True, "via": name}
        monkeypatch.setattr(mod, name, fake)

    for name in ("siem_events_for_incident", "siem_raw_query",
                 "faz_get_alerts", "faz_raw_query"):
        install(tools_triage, name)
    install(tools_noc, "faz_event_summary")
    return calls


@pytest.mark.parametrize("call, helper, expect", [
    (("siem", dict(by="incident", value="10868", source_ip="10.0.0.5")),
     "siem_events_for_incident", {"incident_id": "10868", "source_ip": "10.0.0.5"}),
    (("siem", dict(by="raw", value='{"srcIpAddr": "10.0.0.5"}', select=["eventType"])),
     "siem_raw_query", {"where": {"srcIpAddr": "10.0.0.5"}, "select": ["eventType"]}),
    (("siem", dict(by="RAW", value="srcIpAddr = 10.0.0.5")),
     "siem_raw_query", {"where": "srcIpAddr = 10.0.0.5"}),
    (("faz", dict(by="alerts", value="severity=high")),
     "faz_get_alerts", {"alert_filter": "severity=high"}),
    (("faz", dict(by="raw", value='{"method": "get"}')),
     "faz_raw_query", {"data": {"method": "get"}}),
    (("faz", dict(by="summary", value="FGT-BRANCH-04")),
     "faz_event_summary", {"device": "FGT-BRANCH-04", "logtype": "Event", "limit": 200}),
    (("faz", dict(by="Summary", value="FGT-1", logtype="Traffic", limit=500)),
     "faz_event_summary", {"logtype": "Traffic", "limit": 500}),
])
def test_folded_helper_axes_pass_their_argument_through(call, helper, expect, spy):
    which, kw = call
    fn = tools_triage.siem_search if which == "siem" else tools_triage.faz_search
    out = _unwrap(fn)(**kw)
    assert out == {"ok": True, "via": helper}
    [(name, got)] = spy
    assert name == helper
    assert {k: got[k] for k in expect} == expect


@pytest.mark.parametrize("kw", [
    dict(by="raw", value="not json"),
    dict(by="summary", value=""),
])
def test_folded_faz_axes_refuse_bad_input_with_a_structured_error(kw, spy):
    out = _unwrap(tools_triage.faz_search)(**kw)
    assert "error" in out and not spy
