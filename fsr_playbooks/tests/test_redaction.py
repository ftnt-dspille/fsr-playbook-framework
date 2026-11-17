"""Model-provider redaction (llm.redaction): what the provider is sent, what
the analyst and the tools get back.

The model is a scripted fake at the SDK boundary (`client.chat.completions.
create`), so every request the provider would put on the wire is captured and
inspected. All hosts and addresses are documentation values (RFC 5737, RFC
3849, example.com).
"""
from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm import redaction as R
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import (
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
)

PH = re.compile(r"<[A-Z]{2,8}_\d+>")

IP4 = "203.0.113.7"
IP4_B = "198.51.100.4"
IP6 = "2001:db8::1"
MAC = "aa:bb:cc:dd:ee:ff"
MAIL = "alice@example.com"
KEY = "sk-abcdefghijklmnop1234"
HOST = "web-1.example.com"
HOST2 = "srv-9.example.com"
USER = "carol"
NOTE = "Customer escalation: ceo laptop at the Zurich branch"


def _red(mode=R.MODE_STANDARD, **kw):
    return R.Redactor(mode, **kw)


def _red_in_record(mode=R.MODE_STANDARD, **kw):
    """A redactor that has been shown the mounted record: its typed fields are
    what teach it the hostname (prose is never guessed)."""
    r = R.Redactor(mode, **kw)
    r.learn_record({"hostname": HOST})
    return r


async def _drain(gen):
    return [ev async for ev in gen]


# ------------------------------------------------------------- unit: the map


def test_every_value_type_round_trips():
    r = _red()
    text = (f"ip {IP4}, v6 {IP6}, mac {MAC}, mail {MAIL}, key {KEY}, "
            f"net {IP4}/24")
    masked = r.mask_text(text)
    for raw in (IP4, IP6, MAC, MAIL, KEY):
        assert raw not in masked
    assert masked.count("<IP_1>") == 2          # one value, one placeholder
    assert "<IP_2>" in masked and "<MAC_1>" in masked
    assert "<EMAIL_1>" in masked and "<SECRET_1>" in masked
    assert "/24" in masked
    assert r.unmask_text(masked) == text


def test_typed_fields_are_masked_by_what_they_are_not_by_how_they_look():
    r = _red()
    rec = {"hostname": HOST, "createUser": "/api/3/people/u1",
           "src_ip": IP4, "userName": USER, "emailFrom": MAIL,
           "api_key": "plainsecretvalue", "description": NOTE, "count": 3}
    out = r.mask_result(rec)
    assert out["hostname"] == "<HOST_1>" and out["src_ip"] == "<IP_1>"
    assert out["userName"] == "<USER_1>" and out["emailFrom"] == "<EMAIL_1>"
    assert out["api_key"] == "<SECRET_1>"
    assert out["createUser"] == "/api/3/people/u1"     # an IRI is structure
    assert out["description"] == NOTE and out["count"] == 3  # standard: free text stays
    # The learned host is then masked inside prose too, in any language.
    assert HOST not in r.mask_text(f"le serveur {HOST} a redemarre")


def test_registered_form_types_drive_masking():
    r = _red()
    r.register_field_types({"contactAddr": "email", "box": "hostname"})
    out = r.mask_result({"contactAddr": "bob@example.com", "box": "edge-1.example.com"})
    assert out == {"contactAddr": "<EMAIL_1>", "box": "<HOST_1>"}


def test_strict_masks_opted_in_free_text_standard_does_not():
    rec = {"description": NOTE, "title": "short"}
    std = _red(R.MODE_STANDARD, free_text_fields={"description"}).mask_result(rec)
    assert std["description"] == NOTE
    strict = _red(R.MODE_STRICT, free_text_fields={"description"})
    out = strict.mask_result(rec)
    assert out["description"] == "<TEXT_1>" and out["title"] == "short"
    assert strict.unmask_text(out["description"]) == NOTE
    # Strict without a named list masks the registered free-text form types.
    s2 = _red(R.MODE_STRICT)
    s2.register_field_types({"notes": "textarea"})
    assert s2.mask_result({"notes": NOTE})["notes"] == "<TEXT_1>"


def test_the_map_survives_a_round_trip_through_storage():
    r = _red()
    masked = r.mask_text(f"{IP4} {MAIL}")
    r2 = _red(state=json.loads(json.dumps(r.to_dict())))
    assert r2.mask_text(f"{MAIL} {IP4}") == " ".join(reversed(masked.split()))
    assert r2.mask_text(IP4_B) == "<IP_2>"     # counters continue, never reused


def test_masking_is_idempotent_and_prose_is_left_alone():
    r = _red()
    once = r.mask_text(f"from {IP4} at 12:30:45 on version 1.2.3")
    assert r.mask_text(once) == once
    assert "12:30:45" in once and "1.2.3" in once
    assert r.mask_text("nothing sensitive here") == "nothing sensitive here"


def test_unknown_placeholders_never_survive_unmasking():
    r = _red()
    assert r.unmask_text("see <IP_99> now") == f"see {R.UNRESOLVED} now"
    assert not PH.search(r.unmask_obj({"a": ["<HOST_4>"]})["a"][0])


def test_stream_unmasker_holds_a_split_placeholder():
    r = _red()
    r.mask_text(IP4)
    un = R.StreamUnmasker(r)
    out = [un.feed(d) for d in ("go to <I", "P_", "1> now ", "and <")]
    out.append(un.flush())
    assert "".join(out) == f"go to {IP4} now and <"
    assert not any("<IP" in piece for piece in out)


# ----------------------------------------------------------- loop: OpenAI wire


class _Wire:
    """A scripted OpenAI endpoint. `script[i](wire_text)` returns the chunks of
    round i; every request body is kept for inspection."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[str] = []
        self.client = MagicMock()
        self.client.chat = MagicMock()
        self.client.chat.completions = MagicMock(create=AsyncMock(side_effect=self._create))

    async def _create(self, **kw):
        body = json.dumps(kw["messages"], default=str)
        self.requests.append(body)
        return _FakeStream(self.script.pop(0)(body))

    def provider(self):
        return OpenAIProvider(model="gpt-4o", base_url="http://x/v1", api_key="x",
                              client=self.client)


def _ph(body: str, kind: str) -> list[str]:
    return sorted(set(re.findall(rf"<{kind}_\d+>", body)), key=lambda s: int(s[:-1].split("_")[1]))


_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n, "parameters": {"type": "object", "properties": {}}}}
    for n in ("lookup", "emit_card")]

SYSTEM = f"You help triage {HOST}. Escalation contact {MAIL}."
USERMSG = f"check {IP4} and {IP6} seen with {MAC}; the key is {KEY}"


def _run(wire, *, redactor, tags=None, tool_result=None, system=SYSTEM, user=USERMSG):
    p = wire.provider()
    tool_result = tool_result if tool_result is not None else {
        "hostname": HOST2, "user": USER, "seen_from": IP4_B, "description": NOTE}
    calls = []

    def fake_dispatch(name, args, **_kw):
        calls.append((name, json.loads(json.dumps(args))))
        return tool_result if name == "lookup" else {"ok": True, "card": {"id": "k1"}}

    token = R.bind(redactor)
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch", side_effect=fake_dispatch), \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            events = asyncio.run(_drain(p.stream(
                system=system, messages=[Message(role="user", content=user)],
                tools=_TOOLS, tags=dict(tags or {}))))
    finally:
        R.reset(token)
    return events, calls


def _round1(body):
    ips, hosts = _ph(body, "IP"), _ph(body, "HOST")
    args = json.dumps({"ip": ips[0], "ip6": ips[1], "host": hosts[0]})
    # The placeholder in the prose is split across two deltas on purpose.
    head, tail = ips[0][:3], ips[0][3:]
    return [_delta_chunk(content=f"Checking {head}"),
            _delta_chunk(content=f"{tail} first. "),
            _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="lookup",
                                         args=args[:15])]),
            _delta_chunk(tool_calls=[_tc(index=0, args=args[15:])]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _round2(body):
    # The tool result named a new host and a new address: they arrive masked,
    # and the earlier ones keep their placeholders.
    hosts, ips, users = _ph(body, "HOST"), _ph(body, "IP"), _ph(body, "USER")
    card = json.dumps({"card_type": "verdict", "payload": {
        "summary": f"{hosts[1]} talks to {ips[-1]} as {users[0]}",
        "findings": [{"claim": f"same host as {hosts[0]}", "evidence": ["c1"]}]}})
    return [_delta_chunk(tool_calls=[_tc(index=0, id="c2", name="emit_card", args=card)]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _round3(body):
    hosts = _ph(body, "HOST")
    return [_delta_chunk(content=f"Done: {hosts[0]} and {hosts[1]} reviewed."),
            _delta_chunk(finish="stop"), _usage_chunk()]


def _ran(events):
    return ([e for e in events if isinstance(e, TextEvent)],
            [e for e in events if isinstance(e, ToolUseEvent)],
            [e for e in events if isinstance(e, ToolResultEvent)])


def test_chat_tool_call_and_card_round_trip_through_the_provider():
    wire = _Wire(_round1, _round2, _round3)
    events, calls = _run(wire, redactor=_red_in_record())

    # 1. The provider never sees a real value, in any round.
    for body in wire.requests:
        for raw in (IP4, IP4_B, IP6, MAC, MAIL, KEY, HOST, HOST2, USER):
            assert raw not in body, f"{raw} reached the provider"
    assert len(wire.requests) == 3

    # 2. Tool calls are dispatched with the real values.
    name, args = calls[0]
    assert name == "lookup"
    assert args == {"ip": IP4, "ip6": IP6, "host": HOST}

    # 3. The card carries real text; its citation (a tool-call id) is untouched.
    card = next(a for n, a in calls if n == "emit_card")
    assert card["payload"]["summary"] == f"{HOST2} talks to {IP4_B} as {USER}"
    assert card["payload"]["findings"][0]["claim"] == f"same host as {HOST}"
    assert card["payload"]["findings"][0]["evidence"] == ["c1"]

    # 4. The analyst's stream is real text, the placeholder split across deltas
    #    included; nothing placeholder-shaped is on any event.
    texts, uses, results = _ran(events)
    shown = "".join(t.text for t in texts)
    assert shown.startswith(f"Checking {IP4} first.")
    assert f"Done: {HOST} and {HOST2} reviewed." in shown
    assert not PH.search(shown)
    assert not PH.search(json.dumps([u.arguments for u in uses], default=str))
    assert not PH.search(json.dumps([r.result for r in results], default=str))


def test_placeholders_are_stable_across_rounds():
    wire = _Wire(_round1, _round2, _round3)
    _run(wire, redactor=_red_in_record())
    first_host = _ph(wire.requests[0], "HOST")[0]
    assert first_host in wire.requests[1] and first_host in wire.requests[2]
    assert _ph(wire.requests[0], "IP")[0] in wire.requests[2]


def test_tool_results_are_masked_on_the_way_back_in():
    wire = _Wire(_round1, _round2, _round3)
    _run(wire, redactor=_red_in_record())
    second = wire.requests[1]
    assert HOST2 not in second and USER not in second and IP4_B not in second
    assert len(_ph(second, "HOST")) == 2 and _ph(second, "USER")


def test_strict_masks_the_opted_in_free_text_standard_sends_it():
    def wire_for(redactor):
        w = _Wire(_round1, _round2, _round3)
        _run(w, redactor=redactor)
        return w.requests[1]

    assert NOTE in wire_for(_red_in_record(R.MODE_STANDARD, free_text_fields={"description"}))
    strict = wire_for(_red_in_record(R.MODE_STRICT, free_text_fields={"description"}))
    assert NOTE not in strict and _ph(strict, "TEXT")


def test_a_model_invented_placeholder_never_reaches_analyst_or_tool():
    def bad_round1(body):
        return [_delta_chunk(content="Maybe <IP_77> is it."),
                _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="lookup",
                                             args='{"ip": "<IP_77>"}')]),
                _delta_chunk(finish="tool_calls"), _usage_chunk()]

    def done(_body):
        return [_delta_chunk(content="ok <HOST_55>"), _delta_chunk(finish="stop"),
                _usage_chunk()]

    events, calls = _run(_Wire(bad_round1, done), redactor=_red_in_record())
    texts, _, _ = _ran(events)
    assert not PH.search("".join(t.text for t in texts))
    assert calls[0][1] == {"ip": R.UNRESOLVED}


def test_off_is_byte_identical_and_untagged():
    def echo(body):
        return [_delta_chunk(content="fine"), _delta_chunk(finish="stop"), _usage_chunk()]

    plain = _Wire(echo)
    events, _ = _run(plain, redactor=None, tags={"intent": "triage"})
    body = plain.requests[0]
    assert IP4 in body and HOST in body and MAIL in body and KEY in body
    assert not PH.search(body)
    from fsr_playbooks.llm.provider import UsageEvent
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert "redaction" not in usage.tags


def test_the_redaction_mode_is_recorded_in_the_turn_tags():
    from fsr_playbooks.llm.provider import UsageEvent

    def echo(_body):
        return [_delta_chunk(content="fine"), _delta_chunk(finish="stop"), _usage_chunk()]

    events, _ = _run(_Wire(echo), redactor=_red_in_record(R.MODE_STRICT))
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.tags["redaction"] == "strict"


def test_a_stored_map_gives_a_resumed_turn_the_same_placeholders():
    first = _red_in_record()
    w1 = _Wire(_round1, _round2, _round3)
    _run(w1, redactor=first)
    again = _red(state=json.loads(json.dumps(first.to_dict())))
    w2 = _Wire(_round1, _round2, _round3)
    _run(w2, redactor=again)
    assert _ph(w1.requests[0], "IP") == _ph(w2.requests[0], "IP")
    assert _ph(w1.requests[0], "HOST") == _ph(w2.requests[0], "HOST")


# ------------------------------------------------------------- loop: Anthropic


def test_anthropic_wire_is_masked_and_tool_input_restored():
    from test_anthropic_enhance_delivery_forced import (
        _FakeStream as AStream,
    )
    from test_anthropic_enhance_delivery_forced import (
        _text_block,
        _tool_use_block,
        _usage,
    )

    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider

    sent: list[str] = []
    rounds = []

    def stream(**kw):
        sent.append(json.dumps({"s": kw.get("system"), "m": kw.get("messages")},
                               default=str))
        return rounds.pop(0)(sent[-1])

    def r1(body):
        ip = _ph(body, "IP")[0]
        return AStream([f"Looking at {ip[:2]}", f"{ip[2:]}."], MagicMock(
            content=[_text_block(f"Looking at {ip}."),
                     _tool_use_block("c1", "lookup", {"ip": ip})],
            stop_reason="tool_use", usage=_usage()))

    def r2(body):
        return AStream(["fine"], MagicMock(content=[_text_block("fine")],
                                           stop_reason="end_turn", usage=_usage()))

    rounds[:] = [r1, r2]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=stream)
    p = AnthropicProvider(model="claude-sonnet-5", base_url="http://x", api_key="x",
                          client=client)
    calls = []

    def fake_dispatch(name, args, **_kw):
        calls.append((name, args))
        return {"hostname": HOST2}

    tools = [{"name": "lookup", "description": "d",
              "input_schema": {"type": "object", "properties": {}}}]
    token = R.bind(_red_in_record())
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch", side_effect=fake_dispatch), \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            events = asyncio.run(_drain(p.stream(
                system=SYSTEM, messages=[Message(role="user", content=USERMSG)],
                tools=tools, tags={})))
    finally:
        R.reset(token)
    for body in sent:
        for raw in (IP4, IP6, MAC, MAIL, KEY, HOST):
            assert raw not in body
    assert calls == [("lookup", {"ip": IP4})]
    shown = "".join(e.text for e in events if isinstance(e, TextEvent))
    assert IP4 in shown and not PH.search(shown)


# ------------------------------------------- a real card validates after unmasking


def test_a_verdict_card_citing_a_masked_run_validates_with_real_values():
    """The citation validator sees the real card: evidence ids are call ids
    (never masked) and the claim text is restored before dispatch."""
    from fsr_playbooks.llm import tools as T

    real_dispatch = T.dispatch
    seen = []

    def routed(name, args, **kw):
        if name == "lookup":
            return {"ok": True, "hostname": HOST2, "seen_from": IP4_B}
        out = real_dispatch(name, args, **kw)
        seen.append((args, out))
        return out

    def r1(body):
        return [_delta_chunk(tool_calls=[_tc(index=0, id="c1", name="lookup", args="{}")]),
                _delta_chunk(finish="tool_calls"), _usage_chunk()]

    def r2(body):
        h, ip = _ph(body, "HOST")[-1], _ph(body, "IP")[-1]
        card = json.dumps({"card_type": "verdict", "payload": {
            "disposition": "true_positive", "severity": "high", "confidence": 0.8,
            "summary": f"{h} is beaconing",
            "findings": [{"claim": f"{h} beacons to {ip}", "evidence": ["c1"]}],
            "unknowns": []}})
        return [_delta_chunk(tool_calls=[_tc(index=0, id="c2", name="emit_card", args=card)]),
                _delta_chunk(finish="tool_calls"), _usage_chunk()]

    def r3(_body):
        return [_delta_chunk(content="done"), _delta_chunk(finish="stop"), _usage_chunk()]

    wire = _Wire(r1, r2, r3)
    p = wire.provider()
    token = R.bind(_red_in_record())
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch", side_effect=routed), \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            events = asyncio.run(_drain(p.stream(
                system=SYSTEM, messages=[Message(role="user", content="triage it")],
                tools=_TOOLS, tags={})))
    finally:
        R.reset(token)
    assert seen, "emit_card never reached dispatch"
    args, out = seen[0]
    assert f"{HOST2} beacons to {IP4_B}" == args["payload"]["findings"][0]["claim"]
    assert isinstance(out, dict) and out.get("ok") is not False, out
    assert not PH.search(json.dumps([getattr(e, "result", None) for e in events
                                     if isinstance(e, ToolResultEvent)], default=str))


# ------------------------------------- known values inside longer strings

_ALERT_NAME = "Agent Lab - C2 callback from dev-laptop-13"


def _alert_json():
    return json.dumps({"name": _ALERT_NAME, "sourceHost": "dev-laptop-13",
                       "tags": ["web-server-01 beacon"], "hostname": "web-server-01"})


def test_a_known_host_inside_a_record_name_is_masked_whatever_the_key_order():
    for mode in (R.MODE_STANDARD, R.MODE_STRICT):
        r = _red(mode)
        # `name` precedes the typed field that teaches the host.
        out = r.mask_result(json.loads(_alert_json()))
        assert "dev-laptop-13" not in json.dumps(out), mode
        assert "web-server-01" not in json.dumps(out), mode
        assert out["name"].startswith("Agent Lab - C2 callback from <HOST_")
        assert r.unmask_obj(out)["name"] == _ALERT_NAME


def test_a_tool_result_json_text_teaches_its_typed_fields_before_masking():
    for mode in (R.MODE_STANDARD, R.MODE_STRICT):
        r = _red(mode)
        masked = r.mask_text(_alert_json())
        assert "dev-laptop-13" not in masked and "web-server-01" not in masked, mode
        assert json.loads(masked)["name"].startswith("Agent Lab - C2 callback from <HOST_")
        assert r.unmask_text(masked) == _alert_json()


def test_a_value_learned_later_is_masked_in_the_whole_batch_of_rows():
    r = _red(R.MODE_STRICT)
    rows = [{"result": _ALERT_NAME}, {"params": {"hostname": "dev-laptop-13"}}]
    out = r.mask_result(rows)
    assert "dev-laptop-13" not in json.dumps(out)


def test_model_bound_tool_result_masks_a_host_embedded_in_a_name():
    sent = []
    inner = MagicMock()
    inner.append_tool_results = lambda outcomes, note=None: sent.extend(
        o.content for o in outcomes)
    r = _red(R.MODE_STRICT)
    turn = R.RedactingTurn(inner, r)
    import dataclasses as _dc
    outcome = _dc.make_dataclass("O", [("content", str)])(_alert_json())
    turn.append_tool_results([outcome])
    assert "dev-laptop-13" not in sent[0] and "web-server-01" not in sent[0]


def test_a_truncated_json_result_still_teaches_its_complete_typed_pairs():
    r = _red(R.MODE_STRICT)
    cut = _alert_json()[:-30]          # cut inside the last pair
    r.mask_text(cut)
    assert "dev-laptop-13" not in r.mask_text("callback from dev-laptop-13 seen")


def test_known_hosts_and_users_can_be_shared_between_two_maps():
    a, b = _red(R.MODE_STRICT), _red(R.MODE_STRICT)
    a.mask_result({"sourceHost": "dev-laptop-13", "userName": "jdoe123", "ip": IP4})
    pairs = a.shareable()
    assert ("HOST", "dev-laptop-13") in pairs and ("USER", "jdoe123") in pairs
    assert all(t in ("HOST", "USER", "EMAIL") for t, _v in pairs)
    b.adopt(pairs)
    out = b.mask_text("callback from dev-laptop-13 by jdoe123")
    assert "dev-laptop-13" not in out and "jdoe123" not in out
    assert b.unmask_text(out) == "callback from dev-laptop-13 by jdoe123"


def test_a_long_known_host_is_masked_even_glued_into_a_query_but_short_values_need_a_token():
    r = _red(R.MODE_STRICT)
    r.mask_result({"hostname": "web-server-01", "userName": "adm"})
    out = r.mask_text("q=descriptionLIKEweb-server-01^ORadministrator adm")
    assert "web-server-01" not in out and "administrator" in out
    assert r.unmask_text(out) == "q=descriptionLIKEweb-server-01^ORadministrator adm"
