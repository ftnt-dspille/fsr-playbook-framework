"""NOC scaffolding: a weak model drives the FortiManager by=diff layer correctly.

Live (fortiai-proxy), the data layer was right and the model was not: it stopped
at by=changes, never named the install task, called a blackhole route that drops
the asked-about traffic "benign", and staged no fix. Each gap is closed by a typed
check; these tests drive each through its real site, on the real tool output of
the NOC sim (a routed blackhole 192.0.2.0/24, sequence 900, newest object).
"""
from __future__ import annotations

import pytest

import fsr_playbooks.execution_api as exec_api
from fsr_playbooks.llm.task_spec import asks_for_fix
from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server import _noc_scaffold as noc
from fsr_playbooks.mcp_server import _sim_fixtures as fx
from fsr_playbooks.mcp_server import tools_noc as tn
from fsr_playbooks.mcp_server.tools_emit import emit_verdict

DEV = "FGT-BRANCH-04"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    tn._FMG_CONFIG_CACHE.clear()
    tn._FMG_MANAGED_CACHE.clear()
    from fsr_playbooks.mcp_server import _shared
    monkeypatch.setattr(_shared, "_live_client", lambda: None)

    def fake_run_op(connector, op, params=None, **kw):
        return {"ok": True, "data": fx._fmg_json_rpc_get(params or {})}

    monkeypatch.setattr(exec_api, "run_op", fake_run_op)
    ev = cv.TurnEvidence()
    cv.set_turn_evidence(ev)
    yield ev
    cv.set_turn_evidence(None)
    tn._FMG_CONFIG_CACHE.clear()
    tn._FMG_MANAGED_CACHE.clear()


def _read(ev, cid, by):
    """Run the real tool and register its real result, as the loop does."""
    args = {"by": by, "device": DEV}
    result = tn.fmg_device(**args)
    cv.register_tool_result(cid, "fmg_device", True, args, result)
    return result


def _verdict(cite, disposition="benign", severity="low", confidence=1.0,
             summary="The route was dropped as intended; no sign of error.",
             claim="the install applied cleanly"):
    return emit_verdict(
        disposition=disposition, severity=severity, confidence=confidence,
        summary=summary, findings=[{"claim": claim, "evidence": [cite]}],
        unknowns=["what the install was meant to do"])


# ── gap 3 (safety): benign over a blackhole ───────────────────────────────────
def test_the_diff_fact_flags_the_newest_blackhole_route(_env):
    _read(_env, "d1", "diff")
    fact = _env.valid_ids()["d1"]["noc"]
    assert fact["task_id"] == 210
    assert [(b["seq"], b["dst"]) for b in fact["bad"]] == [(900, "192.0.2.0/24")]


def test_benign_is_refused_when_the_install_added_a_blackhole(_env):
    _read(_env, "d1", "diff")
    out = _verdict("d1")
    assert out["ok"] is False and out["code"] == "benign_over_blackhole"
    assert "192.0.2.0/24" in out["message"]
    assert "blackhole" in out["message"]


def test_a_repeated_benign_is_held_at_suspicious_never_shipped(_env):
    _env.ask_nets = ["192.0.2.0/24"]
    _read(_env, "d1", "diff")
    assert _verdict("d1")["code"] == "benign_over_blackhole"
    again = _verdict("d1")
    assert again["ok"] is True
    card = again["card"]
    assert card["disposition"] == "suspicious"
    assert card["severity"] == "medium"
    assert any("blackhole" in u for u in card["unknowns"])
    assert "Held from benign" in card["summary"]


def test_false_positive_is_guarded_like_benign(_env):
    _read(_env, "d1", "diff")
    assert _verdict("d1", disposition="false_positive")["code"] == "benign_over_blackhole"


def test_a_cause_named_verdict_is_not_touched(_env):
    _read(_env, "d1", "diff")
    out = _verdict("d1", disposition="true_positive", severity="high", confidence=0.9,
                   summary="Install 210 added a blackhole route to 192.0.2.0/24.",
                   claim="seq 900 blackholes 192.0.2.0/24")
    assert out["ok"] is True and out["card"]["disposition"] == "true_positive"


def test_no_blackhole_no_guard(_env, monkeypatch):
    monkeypatch.setattr(fx, "_fmg_device_db_rows", lambda url: (
        [{"oid": 1, "seq-num": 1, "dst": ["0.0.0.0", "0.0.0.0"], "blackhole": "disable",
          "gateway": "198.51.100.254", "device": ["port1"], "status": "enable"}]
        if url.endswith("/router/static") else None))
    _read(_env, "d1", "diff")
    assert _env.valid_ids()["d1"]["noc"]["bad"] == []
    assert _verdict("d1")["ok"] is True


def test_an_old_blackhole_deep_in_the_list_is_not_the_installs_change(_env, monkeypatch):
    rows = [{"oid": 100 - i, "seq-num": i + 1, "dst": [f"198.51.100.{i}", "255.255.255.255"],
             "blackhole": "disable", "gateway": "198.51.100.254", "device": ["port1"],
             "status": "enable"} for i in range(5)]
    rows.append({"oid": 1, "seq-num": 99, "dst": ["203.0.113.0", "255.255.255.0"],
                 "blackhole": "enable", "status": "enable"})
    monkeypatch.setattr(fx, "_fmg_device_db_rows",
                        lambda url: rows if url.endswith("/router/static") else None)
    _read(_env, "d1", "diff")
    assert _env.valid_ids()["d1"]["noc"]["bad"] == []


def test_an_unrelated_blackhole_costs_one_refusal_then_passes(_env):
    # The analyst asked about another address: the route is flagged once so the
    # model checks it, then the verdict is accepted as written.
    _env.ask_nets = ["203.0.113.9"]
    _read(_env, "d1", "diff")
    assert _verdict("d1")["code"] == "benign_over_blackhole"
    out = _verdict("d1")
    assert out["ok"] is True and out["card"]["disposition"] == "benign"


# ── gap 2: the install task is cited ──────────────────────────────────────────
def test_the_verdict_names_the_install_task_the_diff_attributes_the_change_to(_env):
    _read(_env, "d1", "diff")
    out = _verdict("d1", disposition="true_positive", severity="high", confidence=0.9,
                   summary="A blackhole route was added.", claim="seq 900 drops traffic")
    claims = [f["claim"] for f in out["card"]["findings"]]
    task_claim = [c for c in claims if "210" in c]
    assert task_claim and "blackhole route to 192.0.2.0/24" in task_claim[0]
    assert out["card"]["findings"][-1]["evidence"] == ["d1"]


def test_a_verdict_that_names_the_task_is_left_alone(_env):
    _read(_env, "d1", "diff")
    out = _verdict("d1", disposition="true_positive", severity="high", confidence=0.9,
                   summary="Install task 210 added the blackhole route.",
                   claim="seq 900 drops traffic")
    assert len(out["card"]["findings"]) == 1


def test_task_citation_does_not_match_a_longer_number(_env):
    _read(_env, "d1", "diff")
    out = _verdict("d1", disposition="true_positive", severity="high", confidence=0.9,
                   summary="Route 2100 was added.", claim="seq 900 drops traffic")
    assert len(out["card"]["findings"]) == 2


def test_a_reply_without_a_verdict_must_name_the_task(_env):
    _read(_env, "d1", "diff")
    held = noc.noc_hold(_env, "A blackhole route to 192.0.2.0/24 was added.")
    assert "210" in held
    assert noc.noc_hold(_env, "Install task 210 added a blackhole route.") == ""


# ── gap 1: by=diff is chosen ──────────────────────────────────────────────────
def test_changes_with_an_install_points_at_diff(_env):
    out = _read(_env, "c1", "changes")
    assert "by=diff" in out["next_step"] and DEV in out["next_step"]
    fact = _env.valid_ids()["c1"]["noc"]
    assert fact["kind"] == "changes" and fact["content_unread"] is True


def test_a_turn_that_stopped_at_changes_is_held_open_for_diff(_env):
    _read(_env, "c1", "changes")
    held = noc.noc_hold(_env, "The install ran and finished.")
    assert "by=diff" in held and DEV in held


def test_the_hold_is_bounded(_env):
    _read(_env, "c1", "changes")
    texts = [noc.noc_hold(_env, "done") for _ in range(noc.NOC_NUDGE_CAP + 2)]
    assert all(texts[:noc.NOC_NUDGE_CAP]) and texts[noc.NOC_NUDGE_CAP:] == ["", ""]


def test_reading_the_diff_ends_the_hold(_env):
    _read(_env, "c1", "changes")
    _read(_env, "d1", "diff")
    assert noc.noc_hold(_env, "Install task 210 added a blackhole route.") == ""


def test_a_verdict_over_unread_content_is_refused_until_diff_is_read(_env):
    _read(_env, "c1", "changes")
    out = _verdict("c1", disposition="needs_more_info", severity="low", confidence=0.6,
                   summary="Installed; contents unknown.", claim="an install ran")
    assert out["code"] == "diff_not_read" and "by=diff" in out["message"]
    _read(_env, "d1", "diff")
    ok = _verdict("c1", disposition="true_positive", severity="high", confidence=0.9,
                  summary="Install task 210 added a blackhole route.", claim="seq 900")
    assert ok["ok"] is True


def test_no_install_no_hold(_env, monkeypatch):
    monkeypatch.setattr(fx, "_fmg_tasks", lambda params: [])
    _read(_env, "c1", "changes")
    assert noc.noc_hold(_env, "nothing changed") == ""


def test_status_in_sync_does_not_hold(_env):
    _read(_env, "s1", "status")
    assert noc.noc_hold(_env, "device is down") == ""


def test_state_survives_a_suspended_session(_env):
    _read(_env, "c1", "changes")
    noc.noc_hold(_env, "x")
    _env.ask_nets = ["192.0.2.0/24"]
    again = cv.TurnEvidence.from_dict(_env.to_dict())
    assert again.noc_nudges() == 1 and again.ask_nets == ["192.0.2.0/24"]
    assert noc.unread_devices(again) == [DEV]


# ── gap 4: the fix is staged ──────────────────────────────────────────────────
def test_the_fix_card_removes_exactly_the_offending_route(_env):
    _read(_env, "d1", "diff")
    p = noc.remediation_payload(_env)
    assert p["operation"] == "json_rpc_delete"
    assert p["args"] == {"url": f"/pm/config/device/{DEV}/vdom/root/router/static/900"}
    assert "192.0.2.0/24" in p["summary"] and p["editable_fields"] == []


def test_no_offending_item_no_fix_card(_env):
    assert noc.remediation_payload(_env) is None
    _read(_env, "c1", "changes")
    assert noc.remediation_payload(_env) is None


@pytest.mark.parametrize("text,expected", [
    ("Propose the fix, do not execute.", True),
    ("Stage an approval card to delete the route.", True),
    ("can you revert it?", True),
    ("Do not remove anything, just explain.", False),
    ("How do I fix this in general?", False),
    ("what changed on FGT-BRANCH-04?", False),
    ("it was already fixed yesterday", False),
])
def test_asks_for_fix(text, expected):
    assert asks_for_fix(text) is expected


# ── the loop: the fix card is staged, the reply is held, bounded ───────────────
def _drive(monkeypatch, turns, ask, dispatched):
    import asyncio

    from test_guard_sites_are_recorded import _NOC_SLICE, _Client, _Final  # noqa: F401

    from fsr_playbooks.llm import agent_loop
    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
    from fsr_playbooks.llm.provider import Message

    def dispatch(name, args, **_kw):
        dispatched.append((name, args))
        if name == "fmg_device":
            return tn.fmg_device(**args)
        return {"ok": True, "card": args}

    monkeypatch.setattr(agent_loop, "dispatch", dispatch)
    monkeypatch.setattr(agent_loop, "_tier_for", lambda n, a: 1)
    provider = AnthropicProvider(model="fake", client=_Client(turns))

    async def go():
        return [e async for e in provider.stream(
            system="sys", messages=[Message(role="user", content=ask)],
            tools=_NOC_SLICE)]

    return asyncio.run(go())


def test_an_analyst_fix_request_stages_the_route_removal_card(monkeypatch):
    from test_guard_sites_are_recorded import _Final, _say, _use
    dispatched: list = []
    turns = [_Final([_use("a", "fmg_device", {"by": "diff", "device": DEV})]),
             _Final([_say("Install task 210 added a blackhole route.")]),
             _Final([_use("f", "emit_card", {"card_type": "capability_gap",
                                              "payload": {}})]),
             _Final([_say("Staged for your approval.")])]
    _drive(monkeypatch, turns, "Stage an approval card to delete the route.", dispatched)
    cards = [a for n, a in dispatched if n == "emit_card"
             and a["card_type"] == "action"]
    assert len(cards) == 1
    assert cards[0]["payload"]["operation"] == "json_rpc_delete"
    assert cards[0]["payload"]["args"]["url"].endswith("/router/static/900")


def test_no_fix_request_no_fix_card(monkeypatch):
    from test_guard_sites_are_recorded import _Final, _say, _use
    dispatched: list = []
    turns = [_Final([_use("a", "fmg_device", {"by": "diff", "device": DEV})]),
             _Final([_say("Install task 210 added a blackhole route.")])]
    _drive(monkeypatch, turns, "what changed on the device?", dispatched)
    assert [n for n, _ in dispatched if n == "emit_card"] == []


def test_the_loop_sends_a_changes_only_reply_back_for_diff(monkeypatch):
    from test_guard_sites_are_recorded import _Final, _say, _use
    dispatched: list = []
    turns = [_Final([_use("a", "fmg_device", {"by": "changes", "device": DEV})]),
             _Final([_say("The install finished.")]),
             _Final([_use("b", "fmg_device", {"by": "diff", "device": DEV})]),
             _Final([_say("Install task 210 added a blackhole route.")])]
    _drive(monkeypatch, turns, "what changed on the device?", dispatched)
    assert [a["by"] for n, a in dispatched if n == "fmg_device"] == ["changes", "diff"]
