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


# --- FMG: what changed (install / firmware tasks) and the case-4 device fields ---
def _changes(**kw):
    from fsr_playbooks.mcp_server import tools_noc
    return tools_noc.fmg_device.fn(by="changes", **kw) if hasattr(
        tools_noc.fmg_device, "fn") else tools_noc.fmg_device(by="changes", **kw)


def test_changes_finds_the_install_task_that_named_the_device(fmg):
    out = _changes(device="FGT-BRANCH-04")
    assert out["ok"] is True
    ids = [c["task_id"] for c in out["changes"]]
    assert ids == [210]                      # not the HQ install, not the 40d-old upgrade
    task = out["changes"][0]
    assert task["title"] == "Install Device" and task["kind"] == "install"
    assert task["user"] == "ops-apikey" and task["state"] == "done"
    assert task["started"].endswith("Z") and task["finished"].endswith("Z")
    assert "Installation to real device done" in task["result"]
    assert out["window"] == "7d"


def test_changes_says_package_installs_without_a_device_are_not_proof(fmg):
    out = _changes(device="FGT-BRANCH-04")
    # task 212 installs a package and names no device: counted, not attributed
    assert out["install_tasks_without_device"] == 1


def test_changes_reads_ids_first_then_only_the_lines_in_the_window(fmg):
    _changes(device="FGT-BRANCH-04")
    task_calls = [c for c in fmg if c["params"].get("url") == "/task/task"]
    assert len(task_calls) == 2
    assert task_calls[0]["params"]["data"] == {"option": ["no loadsub"]}
    # the second call reads from the oldest in-window task (210), not the 40d one
    assert task_calls[1]["params"]["data"] == {"filter": [["id", ">=", 210]]}
    assert all(c["summarize"] is False for c in task_calls)


def test_changes_widens_to_firmware_upgrades_named_by_serial(fmg):
    out = _changes(device="FGT-BRANCH-04", window="60d")
    by_id = {c["task_id"]: c for c in out["changes"]}
    assert set(by_id) == {210, 201}
    assert by_id[201]["kind"] == "firmware"
    assert [c["task_id"] for c in out["changes"]] == [210, 201]   # newest first


def test_changes_is_bounded_by_limit_and_says_so(fmg):
    out = _changes(device="FGT-BRANCH-04", window="60d", limit=1)
    assert out["count"] == 1 and out["truncated"] is True and out["total_found"] == 2


def test_changes_flags_a_scan_cut_short(fmg, monkeypatch):
    from fsr_playbooks.mcp_server import tools_noc
    monkeypatch.setattr(tools_noc, "_FMG_TASK_SCAN", 1)
    out = _changes(device="FGT-BRANCH-04")
    assert out["scan_truncated"] is True and "newest 1" in out["note"]


def test_changes_empty_window_is_typed_not_clean(fmg):
    out = _changes(device="FGT-HQ-01", window="30m")
    assert out["ok"] is True and out["changes"] == [] and out["code"] == "no_events"


def test_changes_needs_a_device_and_skips_an_unmanaged_one(fmg):
    from fsr_playbooks.mcp_server import tools_noc
    fn = getattr(tools_noc.fmg_device, "fn", tools_noc.fmg_device)
    assert "requires a device" in fn(by="changes")["error"]
    out = _changes(device="some-laptop")
    assert out["skipped"] == "not_fmg_managed" and out["changes"] == []
    assert not [c for c in fmg if c["params"].get("url") == "/task/task"]


def _diff(**kw):
    from fsr_playbooks.mcp_server import tools_noc
    fn = getattr(tools_noc.fmg_device, "fn", tools_noc.fmg_device)
    return fn(by="diff", **kw)


def _section(out, kind, vdom="root"):
    return next(s for s in out["sections"]
                if s["kind"] == kind and s["vdom"] == vdom)


def test_diff_shows_the_content_newest_object_first(fmg):
    out = _diff(device="FGT-BRANCH-04")
    assert out["ok"] is True
    routes = _section(out, "static_routes")
    assert routes["total"] == 3 and routes["truncated"] is False
    newest = routes["items"][0]
    # the blackhole route an install added is first, with its content typed
    assert newest["seq"] == 900 and newest["dst"] == "192.0.2.0/24"
    assert newest["blackhole"] == "enable" and newest["comment"] == "change-ticket"
    assert [r["oid"] for r in routes["items"]] == [3637, 3629, 3628]
    assert routes["items"][-1]["dst"] == "0.0.0.0/0"
    ifaces = _section(out, "interfaces")
    assert {i["name"]: i["status"] for i in ifaces["items"]} == {
        "port1": "up", "port2": "down"}
    assert "allowaccess" not in ifaces["items"][0]       # bounded digest


def test_diff_ties_the_content_to_the_last_install_and_says_it_is_not_a_diff(fmg):
    out = _diff(device="FGT-BRANCH-04")
    assert out["last_install"]["task_id"] == 210
    assert out["last_install"]["state"] == "done"
    assert out["config_state"]["db_status"] == "mod"
    assert "NOT been installed" in out["config_state"]["db_meaning"]
    assert "no revision history" in out["reading"].lower()
    assert "before/after" in out["reading"]


def test_diff_names_a_missing_install_instead_of_implying_one(fmg):
    out = _diff(device="FGT-BRANCH-04", window="30m")
    assert out["last_install"] is None and "no install task" in out["last_install_note"]


def test_diff_reads_the_device_db_per_vdom_with_projection(fmg):
    _diff(device="FGT-BRANCH-04")
    urls = [c["params"]["url"] for c in fmg]
    assert "/pm/config/device/FGT-BRANCH-04/vdom/root/router/static" in urls
    assert "/pm/config/device/FGT-BRANCH-04/vdom/root/system/interface" in urls
    route_call = next(c for c in fmg if c["params"]["url"].endswith("/router/static"))
    assert "blackhole" in route_call["params"]["data"]["fields"]
    assert all(c["summarize"] is False for c in fmg)


def test_diff_is_bounded_by_limit_and_says_so(fmg):
    out = _diff(device="FGT-BRANCH-04", limit=1)
    routes = _section(out, "static_routes")
    assert routes["truncated"] is True and routes["total"] == 3
    assert [r["seq"] for r in routes["items"]] == [900]


def test_diff_needs_a_device_and_skips_an_unmanaged_one(fmg):
    from fsr_playbooks.mcp_server import tools_noc
    fn = getattr(tools_noc.fmg_device, "fn", tools_noc.fmg_device)
    assert "requires a device" in fn(by="diff")["error"]
    out = _diff(device="some-laptop")
    assert out["skipped"] == "not_fmg_managed" and out["sections"] == []


def test_diff_marks_a_section_it_could_not_read_as_incomplete(monkeypatch, fmg):
    real = exec_api.run_op

    def flaky(connector, op, params=None, **kw):
        if str((params or {}).get("url", "")).endswith("/system/interface"):
            return {"ok": False, "status": "fmg_op_failed", "message": "boom"}
        return real(connector, op, params, **kw)

    monkeypatch.setattr(exec_api, "run_op", flaky)
    out = _diff(device="FGT-BRANCH-04")
    assert out["ok"] is True and out["incomplete"] is True
    assert out["unread"] == [{"vdom": "root", "kind": "interfaces"}]
    assert [s["kind"] for s in out["sections"]] == ["static_routes"]


def test_diff_error_passthrough_when_nothing_could_be_read(monkeypatch, fmg):
    real = exec_api.run_op

    def broken(connector, op, params=None, **kw):
        if "/pm/config/device/" in str((params or {}).get("url", "")):
            return {"ok": False, "status": "fmg_op_failed", "message": "boom"}
        return real(connector, op, params, **kw)

    monkeypatch.setattr(exec_api, "run_op", broken)
    out = _diff(device="FGT-BRANCH-04")
    assert not out.get("ok") and "sections" not in out


def test_changes_states_that_a_done_install_means_applied_not_harmless(fmg):
    out = _changes(device="FGT-BRANCH-04")
    task = out["changes"][0]
    assert task["state"] == "done"
    assert task["outcome"] == "applied to the device (impact not judged)"
    assert "WAS APPLIED" in out["reading"] and "by=diff" in out["reading"]


def test_changes_outcome_is_only_for_installs_and_flags_a_failed_one(fmg):
    out = _changes(device="FGT-BRANCH-04", window="60d")
    fw = next(c for c in out["changes"] if c["kind"] == "firmware")
    assert "outcome" not in fw
    assert tools_noc_outcome("install", {"state": "error", "num_err": 1}) \
        == "failed or partly failed"


def tools_noc_outcome(kind, task):
    from fsr_playbooks.mcp_server.tools_noc import _fmg_task_outcome
    return _fmg_task_outcome(kind, task)


def test_unknown_by_names_changes_among_the_choices(fmg):
    from fsr_playbooks.mcp_server import tools_noc
    fn = getattr(tools_noc.fmg_device, "fn", tools_noc.fmg_device)
    assert "'changes'" in fn(by="nope")["error"]
    assert "'diff'" in fn(by="nope")["error"]


def test_changes_error_passthrough(monkeypatch):
    def failing(connector, op, params=None, **kw):
        if (params or {}).get("url") == "/task/task":
            return {"ok": False, "status": "connector_unhealthy",
                    "message": "FortiManager unreachable"}
        return {"ok": True, "data": fx._fmg_json_rpc_get(params or {})}
    monkeypatch.setattr(exec_api, "run_op", failing)
    out = _changes(device="FGT-BRANCH-04")
    assert out["ok"] is False and out["code"] == "connector_unhealthy"


def test_device_digest_carries_case_four_fields_with_epochs_as_iso():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_digest_device
    row = _fmg_digest_device({
        "name": "fgt-a", "sn": "FGT60F0000000001", "conn_status": "down",
        "conf_status": "outofsync", "db_status": "nomod",
        "last_checked": 1790176096, "last_resync": 1790108311,
        "mgmt_mode": "fmgfaz", "conn_mode": "active", "dev_status": "retrieved",
        "flags": ["is_model", "reload_failed"], "first_tunnel_up": 1787857926})
    assert row["last_checked"] == "2026-09-23T15:08:16Z"
    assert row["last_resync"] == "2026-09-22T20:18:31Z"
    assert row["mgmt_mode"] == "fmgfaz" and row["dev_status"] == "retrieved"
    assert row["conn_mode"] == "active"
    assert row["flags"] == ["reload_failed"] and row["is_model"] is True
    assert row["first_tunnel_up"].endswith("Z")


def test_device_digest_never_reports_a_resync_as_the_last_contact():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_digest_device
    row = _fmg_digest_device({"name": "fgt-a", "last_checked": 1790176096,
                              "last_resync": 0, "flags": None})
    assert "last_resync" not in row and "flags" not in row
    assert row["last_checked"].endswith("Z")


def test_status_asks_fmg_for_the_new_device_fields(fmg):
    fmg_get_device_status("FGT-BRANCH-04")
    call = _call_to(fmg, lambda u: u.endswith("/device/FGT-BRANCH-04"))
    fields = call["params"]["data"]["fields"]
    assert {"last_resync", "mgmt_mode", "dev_status", "flags"} <= set(fields)


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
