"""Tests for the NOC / FortiManager + FortiAnalyzer device-diagnostic tools.

Like the FAZ/SIEM tests, run_op is monkeypatched so these are offline + fast,
asserting each wrapper's contract: right connector/op/params, the compact
digest shape, tier=1, and the device-down sim fixtures' round-trip.
"""
from __future__ import annotations

import pytest

# tools_noc resolves run_op through the execution_api facade (the triage seam),
# so the offline fixtures patch run_op there -- not on tools_execution directly.
import fsr_playbooks.execution_api as exec_api
from fsr_playbooks.llm.tools import SAFE_TOOLS, TOOL_TIERS
from fsr_playbooks.mcp_server import _sim_fixtures as fx
from fsr_playbooks.mcp_server.tools_noc import (
    faz_event_summary,
    faz_search_by_serial,
    faz_search_device_events,
    fmg_get_device_list,
    fmg_get_device_status,
    fmg_get_ha_status,
    fmg_get_policy_package_status,
)

_NOC_TOOLS = [
    "fmg_get_device_list", "fmg_get_device_status", "fmg_get_ha_status",
    "fmg_get_policy_package_status", "faz_search_device_events",
    "faz_search_by_serial", "faz_event_summary",
]


@pytest.fixture(autouse=True)
def _reset_fmg_caches(monkeypatch):
    """The FMG config + managed-device caches are per-process module state; clear
    them between tests so the managed-device gate (which pre-lists devices) is
    deterministic regardless of order. Also keep config resolution hermetic --
    no live box read -- by forcing live_client to None (offline)."""
    from fsr_playbooks.mcp_server import tools_noc as tn
    tn._FMG_CONFIG_CACHE.clear()
    tn._FMG_MANAGED_CACHE.clear()
    from fsr_playbooks.mcp_server import _shared
    monkeypatch.setattr(_shared, "_live_client", lambda: None)
    yield
    tn._FMG_CONFIG_CACHE.clear()
    tn._FMG_MANAGED_CACHE.clear()


def _call_to(calls, pred):
    """First captured run_op whose url matches pred -- the device-scoped FMG tools
    now pre-list managed devices (the gate), so the op call is no longer calls[0]."""
    return next(c for c in calls if pred(c["params"].get("url", "")))


# --- FMG: json_rpc_get is the single transport; the fixture branches on url ---
@pytest.fixture
def fmg(monkeypatch):
    """Route json_rpc_get through the NOC sim fixture; capture the calls."""
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {},
                      "confirm": kw.get("confirm"),
                      "summarize": kw.get("summarize")})
        data = fx._fmg_json_rpc_get(params or {})
        return {"ok": True, "data": data}

    monkeypatch.setattr(exec_api, "run_op", fake_run_op)
    return calls


def test_device_list_targets_dvmdb_and_digests(fmg):
    out = fmg_get_device_list(adom="root")
    assert out["ok"] and out["count"] == 2
    call = fmg[0]
    assert call["connector"] == "fortinet-fortimanager-json-rpc"
    assert call["op"] == "json_rpc_get"
    assert call["params"]["url"] == "/dvmdb/adom/root/device"
    assert call["confirm"] is True
    # Must bypass run_op's generic summarization: it caps dicts to the first 40
    # keys, which silently strips late-ordered FMG fields (name/sn/ip). The
    # wrapper digests + bounds the rows itself, so it asks for raw output.
    assert call["summarize"] is False
    # And it projects the query to just the digest fields (small payload that
    # also keeps name/sn/ip inside any downstream key cap).
    fields = call["params"]["data"]["fields"]
    assert {"name", "sn", "ip", "conn_status"} <= set(fields)
    down = next(d for d in out["devices"] if d["name"] == "FGT-BRANCH-04")
    assert down["conn_status"] == "down"  # int 0 normalized
    assert down["serial"] == "FGT60F0000000404"
    up = next(d for d in out["devices"] if d["name"] == "FGT-HQ-01")
    assert up["conn_status"] == "up"


def test_device_status_single_device_url(fmg):
    out = fmg_get_device_status("FGT-BRANCH-04")
    assert out["ok"] and out["count"] == 1
    call = _call_to(fmg, lambda u: u == "/dvmdb/adom/root/device/FGT-BRANCH-04")
    assert call["params"]["url"] == "/dvmdb/adom/root/device/FGT-BRANCH-04"
    assert out["devices"][0]["conn_status"] == "down"


def test_ha_status_peer_is_up(fmg):
    out = fmg_get_ha_status("FGT-BRANCH-04")
    assert out["ok"]
    assert _call_to(fmg, lambda u: u.endswith("/ha_slave"))
    roles = {m["name"]: m["conn_status"] for m in out["members"]}
    assert roles["FGT-BRANCH-04"] == "down"
    assert roles["FGT-BRANCH-04-B"] == "up"  # failover survived


def test_policy_package_status_clean_and_device_filter(fmg):
    out = fmg_get_policy_package_status("FGT-BRANCH-04")
    assert out["ok"]
    assert _call_to(fmg, lambda u: "/_package/status" in u)
    assert out["count"] == 1
    assert out["packages"][0]["status"] == "installed"  # rules out bad push
    assert out["packages"][0]["device"] == "FGT-BRANCH-04"


def test_non_managed_device_is_skipped_not_called(fmg):
    """An endpoint host FMG doesn't manage (e.g. an EDR collector) must NOT reach
    a live FMG device-posture op -- it's a clean skip, not a 400 that burns the
    agent's error budget. Regression for GA C1: the agent ran
    fmg_get_device_status(device='ubuntu') against an EDR host."""
    out = fmg_get_device_status("ubuntu")
    assert out["ok"] is True               # a skip is not an error
    assert out.get("skipped") == "not_fmg_managed"
    assert out["devices"] == []
    assert "not a FortiManager-managed device" in out["note"]
    # Only the inventory listing ran; NO device-scoped op was dispatched.
    assert all(not c["params"].get("url", "").endswith("/device/ubuntu")
               for c in fmg)


def test_managed_gate_fails_open_when_inventory_unreadable(monkeypatch):
    """If the FMG inventory can't be read (FMG down/unconfigured), don't hide a
    real device -- proceed so the op's own result/error speaks."""
    seq = {"n": 0}

    def run_op(connector, op, params=None, **kw):
        seq["n"] += 1
        url = (params or {}).get("url", "")
        if url.rstrip("/").endswith("/device"):        # the gate's inventory read
            return {"ok": False, "status": "connector_unhealthy",
                    "message": "FortiManager unreachable"}
        return {"ok": True, "data": fx._fmg_json_rpc_get(params or {})}

    monkeypatch.setattr(exec_api, "run_op", run_op)
    out = fmg_get_device_status("FGT-BRANCH-04")
    assert out["ok"] is True and out["count"] == 1      # proceeded past the gate
    assert seq["n"] == 2                                 # inventory read + op


def test_conn_state_keeps_unknown_distinct_from_down():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_conn_state
    assert _fmg_conn_state(1) == "up"
    assert _fmg_conn_state(0) == "down"
    assert _fmg_conn_state("down") == "down"
    # never-connected / model device must NOT be reported as an outage
    assert _fmg_conn_state("UNKNOWN") == "unknown"
    assert _fmg_conn_state("") == "unknown"


def test_digest_tags_model_device():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_digest_device
    model = _fmg_digest_device({
        "name": "Branch1", "conn_status": "UNKNOWN",
        "flags": ["is_model", "linked_to_model"], "platform_str": "FortiGate-30G",
    })
    assert model["conn_status"] == "unknown"
    assert model["is_model"] is True
    real = _fmg_digest_device({
        "name": "Branch2", "sn": "FGVM...", "ip": "192.0.2.17",
        "conn_status": 0, "flags": None,
    })
    assert real["conn_status"] == "down"
    assert "is_model" not in real  # omitted unless a model device


def test_fmg_error_passthrough(monkeypatch):
    def failing(connector, op, params=None, **kw):
        return {"ok": False, "status": "connector_unhealthy",
                "message": "FortiManager unreachable"}
    monkeypatch.setattr(exec_api, "run_op", failing)
    out = fmg_get_device_status("FGT-BRANCH-04")
    assert out["ok"] is False
    assert out["code"] == "connector_unhealthy"
    assert "unreachable" in out["message"]


# --- FAZ device-hunt: reuse the FAZ plumbing, scoped to a devid/serial --------
@pytest.fixture
def faz(monkeypatch):
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {}})
        return {"ok": True, "data": fx._faz_device_logs(params or {})}

    monkeypatch.setattr(exec_api, "run_op", fake_run_op)
    return calls


# --- FAZ wrappers: the params sent must match the OP'S schema ---------------
#
# These tests used to assert `params["devid"] == "FGT-BRANCH-04"` -- i.e. they
# pinned the wrapper's own assumption rather than the operation's contract, and
# stayed green while the tool failed 100% of the time on a live appliance.
# `devid` is a select over device-TYPE buckets; a hostname is not a member, and
# neither is a lowercase logtype. Both were rejected with an opaque "called with
# 2 invalid argument(s)".
#
# So these now pin the WIRE SHAPE against the schema:
#   devid    ∈ All_FortiGate | All_FortiMail | …   (a bucket, never a host)
#   logtype  ∈ Traffic | Event | Attack | …        (capitalised)
#   filter   carries the per-device scope as devname=/devid=

def test_device_events_sends_a_schema_legal_param_set(faz):
    out = faz_search_device_events("FGT-BRANCH-04", window="6h")
    assert out["ok"] and out["count"] == 3
    call = faz[0]
    assert call["connector"] == "fortinet-fortianalyzer"
    assert call["op"] == "start_and_fetch_bulk_device_logs"
    p = call["params"]
    assert p["devid"] == "All_FortiGate", "devid is a type bucket, not a host"
    assert p["logtype"] == "Event", "logtype is capitalised in the op's enum"
    assert p["filter"] == "devname=FGT-BRANCH-04", "host scope goes in filter"
    assert "device" not in p, "the op has no `device` parameter"
    assert p["start"].endswith("Z")
    assert p["wait_for_search_process_to_complete"] is True
    msgs = " ".join(e.get("msg", "") for e in out["events"])
    assert "WAN1" in msgs  # the smoking gun


def test_device_events_folds_logtype_case(faz):
    """'event' was the shipped default and it is not in the enum."""
    faz_search_device_events("FGT-BRANCH-04", logtype="event")
    assert faz[0]["params"]["logtype"] == "Event"


def test_device_events_ands_the_caller_filter_with_the_device_scope(faz):
    faz_search_device_events("FGT-BRANCH-04", event_filter="level=critical")
    assert faz[0]["params"]["filter"] == \
        "devname=FGT-BRANCH-04 and level=critical"


def test_device_events_rejects_a_bad_select_by_name_before_dispatch(faz):
    """The platform says only HOW MANY args were invalid, which the agent
    cannot act on -- it retried the identical call or gave up. Fail early and
    name the param + its legal values."""
    out = faz_search_device_events("FGT-BRANCH-04", logtype="nonsense")
    assert out["ok"] is False
    assert out["code"] == "bad_select_value"
    assert "logtype" in out["message"] and "nonsense" in out["message"]
    assert "Event" in out["message"], "the legal values must be listed"
    assert not faz, "must not dispatch a call the schema rejects"


def test_device_events_hostname_as_devid_is_told_what_to_do(faz):
    """The exact confusion the old wrapper institutionalised."""
    out = faz_search_device_events("FGT-BRANCH-04", devid="FGT-BRANCH-04")
    assert out["ok"] is False and out["code"] == "bad_select_value"
    assert any("devname=" in s for s in out["suggestions"])
    assert not faz


def test_search_by_serial_filters_on_serial_not_devid(faz):
    faz_search_by_serial("FGT60F0000000404")
    p = faz[0]["params"]
    assert p["devid"] == "All_FortiGate"
    assert p["filter"] == "devid=FGT60F0000000404"
    assert p["logtype"] == "Event"


def test_event_summary_rolls_up_by_type_and_action(faz):
    out = faz_event_summary("FGT-BRANCH-04")
    assert out["ok"] and out["scanned"] == 3
    assert out["by_event_type"]["event"] == 3
    assert "link-monitor" in out["by_action"]
    assert out["first_ts"] and out["last_ts"]


# --- registration -------------------------------------------------------------
def test_all_noc_tools_registered_tier_1():
    for name in _NOC_TOOLS:
        assert name in SAFE_TOOLS, f"{name} missing from SAFE_TOOLS"
        assert TOOL_TIERS.get(name) == 1, f"{name} not tier 1"


def test_fmg_config_resolves_through_the_live_client(monkeypatch):
    """`_fmg_config` imported `fsr_playbooks.execution_api.live_client`, which
    does not exist; the ImportError was swallowed and every call fell back to ""
    (the default-config path) even on a box with a named FMG config."""
    from fsr_playbooks.mcp_server import _shared
    from fsr_playbooks.mcp_server import tools_execution as te
    from fsr_playbooks.mcp_server import tools_noc as tn
    monkeypatch.setattr(_shared, "_live_client", lambda: object())
    monkeypatch.setattr(te, "_configured_rows", lambda client: [
        {"name": tn._FMG_CONNECTOR, "configuration": [{"config_id": "cfg-1"}]}])
    monkeypatch.setattr(te, "_resolve_config_id", lambda rows, c, n: "cfg-1")
    assert tn._fmg_config() == "cfg-1"
