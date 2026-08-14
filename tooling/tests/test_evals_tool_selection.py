"""Tool-selection eval scoring (PLAN.md Phase 1.2).

`mode="tool_selection"` grades ONE thing: did the turn reach the terminal
tool the ask requires. Every other gate is demoted to informational, so a
turn that researches competently and never acts scores zero -- which is the
live failure shape this mode exists to measure.
"""
from __future__ import annotations

import importlib

scoring = importlib.import_module("evals.scoring")
tasks = importlib.import_module("evals.tasks")


def _call(name, **args):
    return {"name": name, "args": args}


DECOYS = [
    {"tool": "find_connector", "label": "researched connectors"},
    {"tool": "list_playbook_runs", "label": "listed past runs"},
]


# --- _score_tool_selection --------------------------------------------------

def test_reached_terminal_tool_passes():
    trace = [_call("find_connector"), _call("run_playbook", playbook="Block IP")]
    r = scoring._score_tool_selection(trace, ["run_playbook"], DECOYS)
    assert r["passed"] is True
    assert r["calls_before"] == 1


def test_research_without_terminal_call_fails():
    """The exact live failure: three competent calls, no action."""
    trace = [_call("find_connector"), _call("list_playbook_runs"),
             _call("find_operation")]
    r = scoring._score_tool_selection(trace, ["run_playbook"], DECOYS)
    assert r["passed"] is False
    assert r["calls_before"] == 3
    assert "never called run_playbook" in r["detail"]


def test_empty_trace_fails_rather_than_skipping():
    r = scoring._score_tool_selection([], ["run_playbook"], DECOYS)
    assert r["passed"] is False
    assert r["skipped"] is False


def test_any_of_several_terminal_tools_counts():
    trace = [_call("emit_enhancement_offer")]
    r = scoring._score_tool_selection(
        trace, ["emit_playbook_offer", "emit_enhancement_offer"], None)
    assert r["passed"] is True


def test_refused_terminal_call_does_not_count():
    """The model picked right but the guard blocked it -- same convention as
    _score_investigation's forbidden-pivot handling."""
    trace = [{"name": "run_playbook", "args": {}, "refused": True}]
    assert scoring._score_tool_selection(trace, ["run_playbook"], None)["passed"] is False


def test_decoys_before_terminal_are_reported_but_do_not_fail():
    trace = [_call("find_connector"), _call("list_playbook_runs"),
             _call("run_playbook")]
    r = scoring._score_tool_selection(trace, ["run_playbook"], DECOYS)
    assert r["passed"] is True
    assert r["decoys_before"] == ["researched connectors", "listed past runs"]


def test_decoys_after_terminal_are_not_counted():
    trace = [_call("run_playbook"), _call("find_connector")]
    r = scoring._score_tool_selection(trace, ["run_playbook"], DECOYS)
    assert r["decoys_before"] == []


def test_missing_terminal_tool_declaration_skips():
    r = scoring._score_tool_selection([_call("run_playbook")], [], DECOYS)
    assert r["skipped"] is True


# --- score() wiring ---------------------------------------------------------

def _score(trace, terminal_tool):
    return scoring.score("", trace=trace, final_text="",
                         mode="tool_selection", terminal_tool=terminal_tool)


def test_research_only_turn_gets_no_credit_for_the_authoring_gates():
    """A research-only turn must lose the terminal gate outright, not earn
    partial credit for the authoring gates it happened to satisfy."""
    out = _score([_call("find_connector")], ["run_playbook"])
    assert out["levels"]["terminal_tool_reached"]["passed"] is False
    assert out["fraction"] < 1.0


def test_the_terminal_gate_is_necessary_but_no_longer_sufficient():
    # #127: this used to be (1, 1) -- one gate, and a baseline of 5/5 that
    # could only stay flat or drop. The composite adds the gates that were
    # already failing in the informational block, so a run has somewhere to
    # climb from.
    out = _score([_call("run_playbook")], ["run_playbook"])
    assert out["levels"]["terminal_tool_reached"]["passed"] is True
    assert out["max"] > 1


def test_only_the_composite_gates_are_counted():
    out = _score([_call("run_playbook")], ["run_playbook"])
    counted = {k for k, v in out["levels"].items()
               if not v.get("skipped") and not v.get("informational")}
    # `appropriate_approval_requests` needs an audit log this helper does not
    # pass, so it skips -- a missing instrument must not count as a failure.
    assert counted == {"terminal_tool_reached", "offer_timing", "no_spiral"}
    assert counted <= {"terminal_tool_reached", *scoring._SELECTION_COUNTED_GATES}


def test_build_fidelity_skipped_in_selection_mode():
    out = _score([_call("run_playbook")], ["run_playbook"])
    assert out["levels"]["build_fidelity"]["skipped"] is True


def test_no_trace_skips_the_gate():
    out = scoring.score("", trace=None, mode="tool_selection",
                        terminal_tool=["run_playbook"])
    assert out["levels"]["terminal_tool_reached"]["skipped"] is True


# --- fixture loading --------------------------------------------------------

def test_selection_fixtures_declare_a_terminal_tool():
    sel = [t for t in tasks.load_tasks() if t.mode == "tool_selection"]
    assert sel, "no tool_selection fixtures found"
    for t in sel:
        assert t.terminal_tool, f"{t.name} declares no terminal_tool"


def test_run_pair_differs_only_by_prompt_variant():
    """The Phase 1.4 experiment is only valid if the two arms are otherwise
    identical -- same ask, same tool surface."""
    by_name = {t.name: t for t in tasks.load_tasks()}
    build = by_name["select_run_playbook"]
    neutral = by_name["select_run_playbook_neutral"]
    assert build.prompt == neutral.prompt
    assert build.tool_slice == neutral.tool_slice
    assert build.terminal_tool == neutral.terminal_tool
    assert (build.prompt_variant, neutral.prompt_variant) == ("build", "neutral")


def test_terminal_tool_accepts_string_or_list():
    assert tasks._as_list("run_playbook") == ["run_playbook"]
    assert tasks._as_list(["a", "b"]) == ["a", "b"]
    assert tasks._as_list(None) == []


def test_selection_terminal_tools_are_registered():
    """A terminal tool that isn't in SAFE_TOOLS is never advertised and never
    dispatchable, so the fixture would measure nothing (the B4 lesson)."""
    from fsr_playbooks.llm.tools import SAFE_TOOLS
    for t in tasks.load_tasks():
        if t.mode != "tool_selection":
            continue
        for name in t.terminal_tool:
            assert name in SAFE_TOOLS, f"{t.name}: {name} not in SAFE_TOOLS"


# --- model screening --------------------------------------------------------

def _matrix(model_to_scores):
    """Build a fake matrix: {model: {task: (score, max)}}."""
    rows = []
    for m, tasks_ in model_to_scores.items():
        for t, (s, mx) in tasks_.items():
            rows.append({"model": m, "task": t, "score": s, "max": mx})
    return {"tasks": sorted({r["task"] for r in rows}),
            "models": list(model_to_scores), "rows": rows, "summary": {}}


def _stub_runs(monkeypatch, sequence):
    harness = importlib.import_module("evals.harness")
    calls = {"n": 0}

    def fake(**_kw):
        m = sequence[calls["n"] % len(sequence)]
        calls["n"] += 1
        return _matrix(m)

    monkeypatch.setattr(harness, "run_matrix", fake)
    return harness


def test_screen_consistent_when_every_repeat_passes(monkeypatch):
    h = _stub_runs(monkeypatch, [{"m1": {"t": (1, 1)}}])
    out = h.screen_models(model_names=["m1"], repeats=3)
    assert out["verdicts"]["m1"] == "consistent"
    assert out["cells"]["m1"]["t"]["passes"] == 3


def test_screen_flaky_when_a_fixture_passes_sometimes(monkeypatch):
    """The dangerous case -- demos fine, fails in front of a customer."""
    h = _stub_runs(monkeypatch, [{"m1": {"t": (1, 1)}}, {"m1": {"t": (0, 1)}}])
    out = h.screen_models(model_names=["m1"], repeats=2)
    assert out["verdicts"]["m1"] == "flaky"


def test_screen_failing_when_a_fixture_never_passes(monkeypatch):
    h = _stub_runs(monkeypatch, [{"m1": {"t1": (1, 1), "t2": (0, 1)}}])
    out = h.screen_models(model_names=["m1"], repeats=3)
    assert out["verdicts"]["m1"] == "failing"


def test_screen_counts_provider_errors_as_non_passes(monkeypatch):
    harness = importlib.import_module("evals.harness")
    monkeypatch.setattr(harness, "run_matrix", lambda **_kw: {
        "tasks": ["t"], "models": ["m1"], "summary": {},
        "rows": [{"model": "m1", "task": "t", "error": "boom",
                  "score": 0, "max": 0}]})
    out = harness.screen_models(model_names=["m1"], repeats=2)
    assert out["cells"]["m1"]["t"]["errors"] == 2
    assert out["verdicts"]["m1"] == "failing"


def test_render_screen_names_every_model_and_verdict(monkeypatch):
    h = _stub_runs(monkeypatch, [{"m1": {"t": (1, 1)}, "m2": {"t": (0, 1)}}])
    txt = h.render_screen(h.screen_models(model_names=["m1", "m2"], repeats=2))
    assert "m1" in txt and "m2" in txt
    assert "consistent" in txt and "failing" in txt


# --- no_spiral: repetition WITHOUT progress, not repetition ----------------

def test_five_lookups_of_five_DIFFERENT_step_types_is_not_a_spiral():
    """The turn this gate used to fail.

    `select_build_offer`, run 20260814T115131Z: the agent looked up start,
    set_variable, decision, end and connector back to back -- which is how you
    build a five-step playbook -- then compiled, verified and delivered it.
    Every other gate passed and this one called the correct method a spiral.
    Rule 1: a grader that punishes a right answer is worse than no grader.
    """
    trace = [{"name": "get_step_type", "args": {"name": n}, "ok": True}
             for n in ("start", "set_variable", "decision", "end", "connector")]
    run, tool, kind = scoring._longest_spiral(trace)
    assert run == 1, f"{run} x {tool} ({kind})"


def test_the_same_lookup_repeated_verbatim_IS_a_spiral():
    """A deterministic lookup repeated with identical args cannot return
    anything new -- the waste #128 went looking for."""
    trace = [{"name": "find_operation",
              "args": {"connector": "fortigate-firewall", "q": "block"},
              "ok": True}] * 5
    run, tool, kind = scoring._longest_spiral(trace)
    assert (run, tool, kind) == (5, "find_operation", "identical")


def test_retrying_a_DEAD_tool_with_fresh_guesses_IS_a_spiral():
    """The classic flail, and the one the args-only rule would miss: every
    call different, every call failed. This is the shape the SIEM pivot had
    before its sim fixture existed."""
    trace = [{"name": "siem_search", "args": {"try": i}, "ok": False}
             for i in range(5)]
    run, tool, kind = scoring._longest_spiral(trace)
    assert (run, kind) == (5, "failing")


def test_a_succeeding_run_of_distinct_args_is_left_to_the_flail_gate():
    """Rule 3: this gate must disagree with its neighbour somewhere.
    `investigation_no_param_flail` owns arg-cycling on one op; no_spiral owns
    repetition that cannot make progress. A run that is distinct AND working
    belongs to neither."""
    trace = [{"name": "run_op", "args": {"ip": f"10.0.0.{i}"}, "ok": True}
             for i in range(6)]
    run, _, _ = scoring._longest_spiral(trace)
    assert run == 1
