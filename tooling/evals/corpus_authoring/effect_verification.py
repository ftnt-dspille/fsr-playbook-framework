"""Goal-effect verification: after a write, did the agent read the effect back?

The original question behind the toolkit: how does an agent know its playbook
actually WORKED, not just that a call returned 200 or a card rendered? The
toolkit's answer is verify_effect -- read the record back and compare the fields
the write should have set. We proved that chain COMPOSES on a live box; we never
measured whether the agent chooses to CLOSE it.

This grader scores one drive's tool sequence (in call order) for that discipline:

  * did it perform a write (create/update/upsert/delete_record, run_playbook,
    publish)?
  * if so, did a readback (verify_effect -- the intended tool -- or a plain
    get/query/search) follow the LAST write? A readback BEFORE the write does
    not count: it must observe the effect, so order matters.

A drive that writes and never reads back declared success on the request alone.
Pure bookkeeping over an ordered tool list -- no box, no model -- so the test
pins it with known sequences. Live population is deferred to a build-run drive;
this is the measurement primitive and its mechanics."""
from __future__ import annotations

from collections import Counter
from typing import Any

# tools that change box state (the act whose effect must be verified).
_WRITE_TOOLS = frozenset({
    "create_record", "update_record", "upsert_record", "delete_record",
    "get_or_create_record", "run_playbook", "publish_playbook", "publish",
})
# readbacks that observe the effect. verify_effect is the intended one (it reads
# the record and compares the fields); the plain reads also count as observing.
_INTENDED = "verify_effect"
_READBACK_TOOLS = frozenset({
    _INTENDED, "get_record", "query_records", "search_records",
    "record_lifecycle",
})


def _base(name: str) -> str:
    """Strip an MCP prefix (mcp__<server>__verify_effect -> verify_effect)."""
    return name.rsplit("__", 1)[-1] if name else name


def grade_effect_verification(tools: list[str] | None) -> dict[str, Any]:
    """Score whether a readback followed the last write in this tool sequence."""
    called = [_base(t) for t in (tools or [])]
    write_idxs = [i for i, t in enumerate(called) if t in _WRITE_TOOLS]
    wrote = bool(write_idxs)
    if not wrote:
        # no write -> the dimension does not apply to this drive.
        return {"wrote": False, "verified": None, "verified_right": None,
                "used_intended": None, "called": called}
    last_write = write_idxs[-1]
    after = called[last_write + 1:]
    verified = any(t in _READBACK_TOOLS for t in after)
    used_intended = _INTENDED in after
    return {
        "wrote": True,
        "verified": verified,
        "verified_right": verified,          # wrote AND read the effect back
        "used_intended": used_intended,      # used verify_effect specifically
        "called": called,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-drive grades into verification rates over the drives that wrote."""
    wrote = [r for r in rows if r.get("wrote")]
    hist: Counter = Counter()
    for r in rows:
        hist.update(r.get("called") or [])

    def rate(pred) -> str:
        return (f"{sum(1 for r in wrote if pred(r))}/{len(wrote)}"
                if wrote else "0/0")

    return {
        "drives_that_wrote": len(wrote),
        "verified_effect": rate(lambda r: r["verified"]),
        "used_verify_effect": rate(lambda r: r["used_intended"]),
        "tool_histogram": dict(hist.most_common()),
    }
