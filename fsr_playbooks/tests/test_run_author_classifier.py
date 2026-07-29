"""Lever 2: run/author LLM classifier + deterministic run-mode slice.

The classifier is language-agnostic (it judges MEANING via an injected LLM and
we parse only our own one-word control output). The run-mode slice removes the
authoring surface so a classified "run" turn has run_playbook as its only
terminal action -- closing the gap Lever 1 (dispatch forcing-redirect) can't:
the model fabricating full YAML with no playbook-name arg to key on.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm.intents import (
    RUN, AUTHOR, OTHER, RUN_MODE_KEEP_TOOLS,
    classify_run_or_author, tools_for_run_mode, tools_for_intent,
)


def _fake(reply):
    """An injected complete(system, user) that always returns `reply`."""
    return lambda system, user: reply


@pytest.mark.parametrize("reply,expected", [
    ("run", RUN),
    ("author", AUTHOR),
    ("other", OTHER),
    ("RUN", RUN),                      # case-insensitive
    ("  run\n", RUN),                  # whitespace
    ("intent: run", RUN),              # padded output
    ("I think this is author.", AUTHOR),
    ("run the playbook", RUN),         # leading token wins
    ("banana", OTHER),                 # unknown → other
    ("", OTHER),                       # empty model reply → other
])
def test_classifier_parses_control_token(reply, expected):
    assert classify_run_or_author("do the thing", _fake(reply)) == expected


def test_empty_message_is_other_without_calling_llm():
    called = []
    def _complete(s, u):
        called.append(1); return "run"
    assert classify_run_or_author("   ", _complete) == OTHER
    assert called == [], "must not spend an LLM call on empty input"


def test_provider_error_fails_open_to_other():
    def _boom(s, u):
        raise RuntimeError("provider down")
    assert classify_run_or_author("run playbook X", _boom) == OTHER


def test_language_agnostic_by_construction():
    """No keyword list is consulted -- a non-English 'run' request classifies as
    run purely from the (fake) model's judgment, proving no regex lock-in."""
    # Spanish: "ejecuta el playbook 'Extract Indicators'"
    assert classify_run_or_author("ejecuta el playbook 'Extract Indicators'", _fake("run")) == RUN


def test_run_mode_slice_is_only_the_allowlist():
    names = {t["name"] for t in tools_for_run_mode("build")}
    # run_playbook survives (it is in the base build slice)
    assert "run_playbook" in names
    # nothing outside the allowlist is advertised -- no authoring, no discovery
    assert names <= RUN_MODE_KEEP_TOOLS
    # the tools the model kept mis-using / wandering into are all gone
    for gone in ("verify_playbook", "search_playbooks", "find_connector",
                 "list_playbook_runs", "why_did_playbook_fail"):
        assert gone not in names


def test_run_mode_slice_is_a_strict_subset_of_build():
    base = {t["name"] for t in tools_for_intent("build")}
    run = {t["name"] for t in tools_for_run_mode("build")}
    assert run <= base
    assert run != base  # it actually removed something
