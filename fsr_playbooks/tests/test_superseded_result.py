"""A call dropped because an earlier one in its batch needed approval must be
reported as NOT RUN, in words, by every path that synthesizes it.

The bare `{"ok": false, "code": "superseded_by_approval"}` read to a model as
"queued for approval": offline, a profile build batched seven step creates,
one carded, and after the approval the model told the analyst the other six
"were routed through the approval flow" and showed all seven as built.
"""
from pathlib import Path

from fsr_playbooks.llm import approvals

LLM = Path(approvals.__file__).parent


def test_the_result_says_it_did_not_run_and_how_to_proceed():
    r = approvals.SUPERSEDED_RESULT
    assert r["ok"] is False and r["executed"] is False
    assert r["code"] == "superseded_by_approval"
    msg = r["message"].lower()
    assert "not run" in msg and "call it again" in msg and "not queued" not in msg
    assert "nothing is queued" in msg


def test_every_synthesis_site_uses_the_one_definition():
    """Parallel literals drift: a provider still sending the bare code would
    bring the misreading back for that provider only."""
    for f in sorted(LLM.glob("*.py")):
        if f.name == "approvals.py":
            continue
        text = f.read_text()
        assert '\\"superseded_by_approval\\"' not in text, f.name
        assert '"code": "superseded_by_approval"' not in text, f.name
    for name in ("run_turn.py", "agent_loop.py"):
        assert "SUPERSEDED_RESULT" in (LLM / name).read_text() \
            or "superseded_result_json" in (LLM / name).read_text(), name
