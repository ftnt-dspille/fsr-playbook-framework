"""Golden turn frames: the readers, graded against frames captured from a live
chat turn (scrubbed), not against a remembered shape.

Each file under `fsr_playbooks/harness/golden/frames/` is one real envelope and
an `expect` block computed WITHOUT the framework (raw json), so a reader that
drifts from the wire fails here. The JS side replays the same files.

Shapes the wire actually sends, and the fixtures encode:
  * text arrives as deltas, one frame per token run;
  * a tool_result carries only `tool_use_id` -- no `name`, no `tool`;
  * a dead gateway arrives as a pre-wrapped error with ok:false.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsr_playbooks.harness.classify import classify_turn
from fsr_playbooks.harness.frames import (
    assistant_text,
    delivered_yaml,
    frames,
    halts,
    pending_halt,
    tool_calls,
)

GOLDEN = Path(__file__).resolve().parent.parent / "harness" / "golden" / "frames"
FILES = sorted(GOLDEN.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(params=FILES, ids=lambda p: p.stem)
def golden(request):
    doc = _load(request.param)
    return doc["name"], doc["envelope"], doc["expect"]


def test_the_corpus_is_present_and_covers_every_shape():
    names = {_load(p)["name"] for p in FILES}
    assert names == {
        "text_deltas_tool_roundtrip", "offer_card_final_yaml", "pending_approval_halt",
        "fence_only_reply", "enhance_after_yaml_no_fence", "refused_offer",
        "transport_error_envelope",
    }


def test_every_golden_file_is_its_own_name(golden):
    name, env, _ = golden
    assert env["transcript"], f"{name}: empty transcript"
    assert all(isinstance(f, dict) and "type" in f for f in frames(env))


def test_assistant_text_matches_the_coalesced_deltas(golden):
    _, env, expect = golden
    assert assistant_text(env) == expect["assistant_text"]


def test_tool_calls_take_their_name_from_the_tool_use(golden):
    """The tool_result carries no name; a reader that looks there gets ''."""
    _, env, expect = golden
    got = [{"id": c.id, "name": c.name, "args": c.args, "has_result": c.has_result,
            "ok": c.ok} for c in tool_calls(env)]
    want = [{"id": t["id"], "name": t["name"], "args": t["args"],
             "has_result": t["has_result"], "ok": t["ok"]} for t in expect["tool_calls"]]
    assert got == want


def test_delivered_yaml_matches_the_offer_fence_carrier_order(golden):
    _, env, expect = golden
    assert delivered_yaml(env) == expect["delivered_yaml"]


def test_halts_are_the_frames_that_wait_for_an_answer(golden):
    _, env, expect = golden
    got = [{"type": f["type"], "id": f.get("id"), "approval_id": f.get("approval_id")}
           for f in halts(env)]
    assert got == expect["halts"]


def test_errors_are_read_from_the_error_frames(golden):
    _, env, expect = golden
    got = [f["message"] for f in frames(env) if f.get("type") == "error"]
    assert got == expect["error_messages"]


def test_classify_turn_outcome(golden):
    _, env, expect = golden
    assert classify_turn(env).kind == expect["outcome"]


def test_pending_halt_resume_key(golden):
    _, env, expect = golden
    assert pending_halt(env) == expect["pending_halt"]


def test_a_refused_offer_is_never_the_delivered_playbook():
    """refused_offer: the offer's tool came back ok:false, and no fence exists,
    so nothing was delivered. A reader that counted the refused argument would
    grade a draft nobody could save."""
    doc = _load(GOLDEN / "refused_offer.json")
    assert doc["expect"]["delivered_yaml"] == ""
    assert any(t["name"] == "emit_playbook_offer" and t["ok"] is False
               for t in doc["expect"]["tool_calls"])
