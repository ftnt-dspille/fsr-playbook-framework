"""#127 -- re-score an archived run without calling a model.

Grading and generation are separate problems and only one of them needs a
model. A saved row already carries the `yaml` the turn delivered and the
`trace` it produced -- every input `score()` takes -- so iterating on a gate or
a fixture's `ir_assertions` does not need another agentic run. The slow loop is
why grader bugs sat unread in the detail column: nobody re-runs ten minutes of
model calls to check a one-line assertion.

The danger is a replay that scores DIFFERENTLY from the run it replays, which
would be a lying instrument of exactly the kind this card exists to remove.
These tests pin fidelity and force the known gap to be declared.
"""
from __future__ import annotations

import importlib
import json

harness = importlib.import_module("evals.harness")
scoring = importlib.import_module("evals.scoring")

GOOD_YAML = (
    "collection: Replay\n"
    "playbooks:\n"
    "  - name: P\n"
    "    steps:\n"
    "      - name: start\n"
    "        type: start\n"
)


def _run(rows, tasks_present=("hello_connector",)):
    return {"models": ["m"], "tasks": list(tasks_present), "rows": rows}


def _row(task="hello_connector", **kw):
    row = {"model": "m", "task": task, "yaml": GOOD_YAML, "trace": [],
           "score": 1, "max": 1, "fraction": 1.0, "levels": {}}
    row.update(kw)
    return row


def test_replay_regrades_with_todays_graders(monkeypatch):
    seen = {}

    def fake_score(yaml_text, **kw):
        seen.update(kw)
        seen["yaml"] = yaml_text
        return {"levels": {"x": {"passed": True}}, "score": 7, "max": 7,
                "fraction": 1.0}

    monkeypatch.setattr(harness, "score", fake_score)
    monkeypatch.setattr(harness, "load_run", lambda rid: _run([_row(audit=[])]))
    m = harness.replay_run("whatever")
    assert m["rows"][0]["score"] == 7
    # The archived candidate is what gets re-graded -- not a fresh generation.
    assert seen["yaml"] == GOOD_YAML
    # …and the fixture's assertions come from the CORPUS as it is now, which is
    # the whole point of a replay.
    assert "ir_assertions" in seen


def test_an_error_row_is_carried_through_not_dropped(monkeypatch):
    monkeypatch.setattr(harness, "load_run",
                        lambda rid: _run([_row(error="provider call: boom")]))
    m = harness.replay_run("whatever")
    # A replay that quietly shrinks the corpus reads as an improvement.
    assert len(m["rows"]) == 1
    assert "error" in m["rows"][0]


def test_a_task_deleted_from_the_corpus_errors_rather_than_vanishing(monkeypatch):
    monkeypatch.setattr(harness, "load_run",
                        lambda rid: _run([_row(task="task_that_is_gone")]))
    m = harness.replay_run("whatever")
    assert "no longer exists" in m["rows"][0]["error"]


def test_a_run_without_an_audit_log_declares_the_gap(monkeypatch):
    # Runs captured before rows carried `audit` cannot re-grade the approval
    # gate. It skips, so `max` drops by one -- and a smaller denominator must
    # not be allowed to read as a cleaner result.
    monkeypatch.setattr(harness, "load_run",
                        lambda rid: _run([_row(trace=[{"name": "run_op"}])]))
    m = harness.replay_run("whatever")
    assert m["replay_gaps"]
    assert "appropriate_approval_requests" in m["replay_gaps"][0]


def test_a_run_with_an_audit_log_declares_no_gap(monkeypatch):
    monkeypatch.setattr(harness, "load_run",
                        lambda rid: _run([_row(trace=[{"name": "run_op"}],
                                               audit=[])]))
    m = harness.replay_run("whatever")
    assert "replay_gaps" not in m


def test_replay_matches_a_real_row_when_every_input_was_captured(monkeypatch):
    # Fidelity, end to end: a row carrying yaml+trace+audit re-scores to the
    # same counted gates it scored the first time.
    trace = [{"name": "emit_playbook_offer", "args": {"yaml": GOOD_YAML}}]
    # Same inputs the replay will use, INCLUDING the fixture's assertions --
    # replay grades against the corpus as it is now, so a comparison that
    # omits them is comparing two different scoreboards.
    tasks = importlib.import_module("evals.tasks")
    fixture = next(x for x in tasks.load_tasks() if x.name == "hello_connector")
    live = scoring.score(GOOD_YAML, trace=trace, audit=[], final_text="",
                         ir_assertions=fixture.ir_assertions)
    row = _row(yaml=GOOD_YAML, trace=trace, audit=[], final_text="",
               levels=live["levels"], score=live["score"], max=live["max"])
    monkeypatch.setattr(harness, "load_run", lambda rid: _run([row]))
    m = harness.replay_run("whatever")
    assert (m["rows"][0]["score"], m["rows"][0]["max"]) == (live["score"],
                                                            live["max"])
    assert "replay_gaps" not in m


def test_a_repair_row_replays_to_the_same_score(tmp_path, monkeypatch):
    """Replay must be able to re-derive the `before` playbook.

    A repair/enhance row is graded against the document the turn started from,
    which lives in the fixture rather than in the saved row. `replay_run` has
    to ask the fixture for it; when it did not, `no_collateral_damage` silently
    skipped and the replayed row scored 2/2 where the run scored 3/3. A replay
    that disagrees with the run it replays is worse than no replay.
    """
    import pathlib as _p

    from evals import harness
    from evals.scoring import score
    from evals.tasks import load_tasks

    t = {x.name: x for x in load_tasks()}["repair_bad_step_ref"]
    fixed = _p.Path("tooling/evals/golds/manual_input_block_ip.yaml").read_text()

    live = score(fixed, mode=t.mode, ir_assertions=t.ir_assertions,
                 before_yaml=t.broken_yaml_text(),
                 user_message=harness._user_message_for(t))

    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    run_dir = tmp_path / "R"
    run_dir.mkdir()
    (run_dir / "matrix.json").write_text(json.dumps({
        "run_id": "R", "live": False, "tasks": [t.name], "models": ["m"],
        "rows": [{"model": "m", "task": t.name, "yaml": fixed,
                  "score": live["score"], "max": live["max"],
                  "fraction": live["fraction"], "levels": live["levels"],
                  "elapsed_ms": 1}],
        "summary": {}}))

    replayed = harness.replay_run("R")["rows"][0]
    assert (replayed["score"], replayed["max"]) == (live["score"], live["max"])
    assert replayed["levels"]["no_collateral_damage"]["skipped"] is False
