"""A turn ends when it stops learning, not at a fixed count.

The 16-round cap fired 5 times over 362 sweep turns and every one was
productive (28-33 calls, all distinct) -- it cut builds off mid-authoring while
never meeting an actual runaway. ProgressMeter replaces it as the runaway
guard; MAX_TOOL_TURNS stays only as a cost ceiling.
"""
from __future__ import annotations

import json

from test_openai_build_progress_forced import (
    _delta_chunk,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm._loop_helpers import (
    MAX_TOOL_TURNS,
    STALL_ERROR_ROUNDS,
    ProgressMeter,
)

OK, ERR = {"ok": True}, {"ok": False, "code": "not_found"}


def _round(m, calls):
    for name, args, res in calls:
        m.note_result(name, args, res)
    return m.end_round()


def test_distinct_calls_never_stall_however_many():
    m = ProgressMeter()
    for i in range(MAX_TOOL_TURNS):
        assert _round(m, [("find", {"q": i}, OK)]) is None


def test_an_error_then_a_corrected_call_is_progress():
    # A refused card re-sent with the fix: exactly how the model corrects.
    m = ProgressMeter()
    for i in range(STALL_ERROR_ROUNDS * 2):
        res = ERR if i % 2 == 0 else OK
        assert _round(m, [("emit_card", {"try": i}, res)]) is None


def test_sustained_failure_stalls():
    # Live: seven module names guessed in a row, each a 404.
    m = ProgressMeter()
    got = [_round(m, [("search_module_records", {"module": f"m{i}"}, ERR)])
           for i in range(STALL_ERROR_ROUNDS)]
    assert got[-1] == "flail" and all(g is None for g in got[:-1])


def test_guard_steering_is_not_failure():
    m = ProgressMeter()
    steer = {"ok": False, "kind": "guard_redirect"}
    for i in range(STALL_ERROR_ROUNDS + 1):
        assert _round(m, [("x", {"i": i}, steer)]) is None


def test_the_ceiling_is_a_cost_net_not_the_runaway_guard():
    assert MAX_TOOL_TURNS >= 32


# --- through the real loops -------------------------------------------------
_NAMES = ("get_record",)


def _dispatch(name, args):
    return {"ok": True, "record": {"name": "t"}}


def _call(cid):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=cid, name="get_record",
                                         args=json.dumps({"uuid": "u"}))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


async def _drain(gen):
    return [ev async for ev in gen]
