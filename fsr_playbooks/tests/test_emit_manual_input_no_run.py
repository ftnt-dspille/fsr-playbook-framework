"""emit_manual_input called outside a paused playbook run.

A manual_input form only works while a playbook run is paused at a gate --
`workflow_run_iri` ties the analyst's answer back to that run. In a plain
triage/chat turn there is no paused run, yet the tool is advertised, so the
model reaches for it to ask the analyst a question (e.g. for a record key).

The old contract returned ``"workflow_run_iri must be a non-empty string"``.
That (a) dead-ended the model with no path forward and (b) leaked the internal
param name into analyst-facing text -- live, the assistant printed
"The form failed because `workflow_run_iri must be a non-empty string`".

The fix: a self-correcting, analyst-safe redirect -- no internal field name,
and it tells the model to ask directly or use a choice card instead.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_emit import emit_manual_input

FIELDS = [{"name": "key", "label": "Record key"}]


def test_missing_run_iri_does_not_leak_the_internal_field_name():
    for bad in ("", "   ", None):
        out = emit_manual_input("q", bad, "Which record?", FIELDS)
        assert not out.get("ok"), out
        blob = (out.get("message", "") + " " + out.get("code", "")).lower()
        assert "workflow_run_iri" not in blob, (
            "the internal param name leaked into the tool error, which the "
            f"model surfaces verbatim to the analyst: {out!r}"
        )


def test_missing_run_iri_tells_the_model_how_to_recover():
    out = emit_manual_input("q", "", "Which record?", FIELDS)
    assert out.get("code") == "no_paused_playbook", out
    msg = out.get("message", "").lower()
    # Points at the two real recovery paths in a chat turn.
    assert "choice card" in msg
    assert "ask" in msg and "directly" in msg


def test_a_real_paused_run_still_emits_the_card():
    out = emit_manual_input("q", "/wf/api/workflows/abc/", "Which record?", FIELDS)
    assert out.get("ok"), out
    assert out["card"]["type"] == "manual_input"
    assert out["card"]["workflow_run_iri"] == "/wf/api/workflows/abc/"
