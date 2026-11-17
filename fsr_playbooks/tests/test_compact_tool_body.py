"""Older oversized tool results are compacted by structure, not cut by position.

Live (box, triage turn): run_op on a VirusTotal IP report returned ~26 KB.
On the next round it was no longer the newest result, so shrink_history
clipped it to its first 5000 and last 1500 chars. last_analysis_stats sat in
the middle, behind the per-engine map and whois/rdap, so the model told the
analyst the vote counts "were cut off in the tool output" while the IOC card,
built from the full result, showed 0/92.
"""
from __future__ import annotations

import json

from fsr_playbooks.llm._loop_helpers import (
    _LATEST_RESULT_CAP_CHARS,
    _RESULT_CAP_CHARS,
    cap_model_content,
    compact_json_body,
    shrink_history,
)
from fsr_playbooks.llm.provider import Message

STATS = {"malicious": 0, "suspicious": 0, "undetected": 22, "harmless": 70, "timeout": 0}


def _vt_report() -> dict:
    """A VirusTotal-shaped IP report: the verdict keys in the MIDDLE."""
    engines = {f"Engine{i:02d}": {"method": "blacklist", "engine_name": f"Engine{i:02d}",
                                  "category": "harmless", "result": "clean"}
               for i in range(92)}
    return {"ok": True, "data": {"id": "198.51.100.7", "type": "ip_address", "attributes": {
        "network": "198.51.100.0/24",
        "whois": "NetRange: 198.51.100.0 - 198.51.100.255\n" * 120,
        "last_analysis_results": engines,
        "rdap": {"entities": [{"handle": f"H{i}", "roles": ["registrant"],
                               "vcard_array": [["fn", {}, "text", "Example Org " * 8]]}
                              for i in range(40)]},
        "last_analysis_stats": STATS,
        "reputation": 115,
        "total_votes": {"harmless": 9, "malicious": 1},
        "tags": ["suspicious-udp"],
        "asn": 64500,
        "as_owner": "Example Networks",
        "crowdsourced_context": [{"title": "note " * 200, "details": "d " * 400}
                                 for _ in range(30)],
        "jarm": "2" * 62,
    }}}


def _call(cid: str) -> Message:
    return Message(role="assistant",
                   content=[{"type": "tool_use", "id": cid, "name": "run_op", "input": {}}])


def _result(cid: str, body: str) -> Message:
    return Message(role="user",
                   content=[{"type": "tool_result", "tool_use_id": cid, "content": body}])


def test_older_vt_report_keeps_its_verdict_after_shrink():
    body = json.dumps(_vt_report())
    assert len(body) > 3 * _RESULT_CAP_CHARS
    history = [_call("c1"), _result("c1", body),
               _call("c2"), _result("c2", json.dumps({"filler": "x" * 9000}))]

    shrink_history(history)

    after = history[1].content[0]["content"]
    assert len(after) < _RESULT_CAP_CHARS
    attrs = json.loads(after)["data"]["attributes"]
    assert attrs["last_analysis_stats"] == STATS
    assert attrs["reputation"] == 115
    assert attrs["total_votes"] == {"harmless": 9, "malicious": 1}
    assert attrs["tags"] == ["suspicious-udp"]
    assert attrs["as_owner"] == "Example Networks"
    # The bulk is marked, not silently gone: the key stays with a size note.
    assert "omitted for size" in str(attrs["last_analysis_results"])


def test_compaction_is_a_fixed_point_under_shrink():
    history = [_call("c1"), _result("c1", json.dumps(_vt_report())),
               _call("c2"), _result("c2", json.dumps({"filler": "x" * 9000}))]
    shrink_history(history)
    snapshot = history[1].content[0]["content"]
    assert shrink_history(history) == 0
    assert history[1].content[0]["content"] == snapshot


def test_latest_result_cap_also_compacts_json():
    report = _vt_report()
    report["data"]["attributes"]["extra"] = ["y" * 500 for _ in range(80)]
    body = json.dumps(report)
    assert len(body) > _LATEST_RESULT_CAP_CHARS
    capped = cap_model_content(body)
    assert len(capped) <= _LATEST_RESULT_CAP_CHARS
    assert json.loads(capped)["data"]["attributes"]["last_analysis_stats"] == STATS


def test_non_json_falls_back_to_head_and_tail():
    assert compact_json_body("not json " * 2000, 6500) is None
    assert compact_json_body(json.dumps("a bare string" * 900), 6500) is None


def test_every_key_survives_compaction():
    report = _vt_report()
    out = json.loads(compact_json_body(json.dumps(report), 6500))
    assert set(report["data"]["attributes"]) <= set(out["data"]["attributes"])


def test_hostile_shapes_fall_back_to_head_and_tail():
    """Tool output is third-party data: deep nesting or a huge body must not
    raise out of the budgeter (it would break the turn) or stall it."""
    from fsr_playbooks.llm._loop_helpers import clip_tool_body

    deep = "[" * 5000 + "]" * 5000 + " " * 30000
    nested = json.dumps(_vt_report())
    for _ in range(80):
        nested = '{"a":' + nested + "}"
    huge = json.dumps({"rows": ["z" * 100] * 20000})
    for body in (deep, nested, huge):
        out = clip_tool_body(body, "<<{n}>>", head=5000, tail=1500)
        assert len(out) < _RESULT_CAP_CHARS
        assert "<<" in out
