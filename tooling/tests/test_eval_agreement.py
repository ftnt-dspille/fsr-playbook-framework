"""The agreement report REFUSES more often than it reports.

Row 11's number ("does the free lane predict the paid one?") is only worth
publishing if it cannot be produced accidentally. Every test below is a way of
getting a flattering number that must come back as a refusal instead: the same
lane on both sides, an unlabeled run, a changed scorer, or a task set that only
overlaps.
"""
from __future__ import annotations

import pytest
from evals.agreement import (
    AgreementError,
    agree,
    render_agreement,
    task_verdict,
)


def _screen(run_id: str, lane: str, model: str, cells: dict,
            scorer: str = "v1", repeats: int = 3) -> dict:
    return {
        "run_id": run_id, "lane": lane, "repeats": repeats,
        "scorer_version": scorer, "models": [model],
        "tasks": sorted(cells), "cells": {model: cells},
    }


def _cell(passes: int, of: int = 3, errors: int = 0) -> dict:
    return {"passes": passes, "of": of, "errors": errors}


def test_verdict_is_a_majority_not_a_unanimity() -> None:
    assert task_verdict(_cell(3)) == "pass"
    assert task_verdict(_cell(2)) == "pass"
    assert task_verdict(_cell(1)) == "fail"
    assert task_verdict(_cell(0)) == "fail"


def test_all_errors_is_unscoreable_not_a_failure() -> None:
    """A dead gateway agreeing with a dead box is not agreement."""
    assert task_verdict(_cell(0, of=3, errors=3)) == "error"
    assert task_verdict({"passes": 0, "of": 0}) == "error"


def test_agreement_counts_only_scoreable_tasks() -> None:
    a = _screen("A", "screen", "frank",
                {"t1": _cell(3), "t2": _cell(0), "t3": _cell(0, errors=3)})
    b = _screen("B", "confirm", "gpt",
                {"t1": _cell(3), "t2": _cell(3), "t3": _cell(3)})
    rep = agree(a, b)
    assert rep["scored"] == 2
    assert rep["unscoreable"] == 1
    assert rep["agreement"] == 0.5
    assert rep["disagreements"] == ["t2"]


def test_no_scoreable_tasks_yields_no_number_rather_than_zero() -> None:
    a = _screen("A", "screen", "frank", {"t1": _cell(0, errors=3)})
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)})
    rep = agree(a, b)
    assert rep["agreement"] is None
    assert "NO AGREEMENT NUMBER" in render_agreement(rep)


def test_a_flaky_task_is_flagged_even_when_the_verdicts_agree() -> None:
    a = _screen("A", "screen", "frank", {"t1": _cell(2)})
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)})
    rep = agree(a, b)
    assert rep["agreement"] == 1.0
    assert rep["tasks"][0]["flaky"] is True
    assert "~flaky" in render_agreement(rep)


def test_same_lane_on_both_sides_is_refused() -> None:
    a = _screen("A", "screen", "frank", {"t1": _cell(3)})
    b = _screen("B", "screen", "frank", {"t1": _cell(3)})
    with pytest.raises(AgreementError, match="repeatability"):
        agree(a, b)


def test_an_unlabeled_run_is_refused() -> None:
    a = _screen("A", "adhoc", "frank", {"t1": _cell(3)})
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)})
    with pytest.raises(AgreementError, match="unlabeled"):
        agree(a, b)


def test_a_changed_scorer_is_refused() -> None:
    a = _screen("A", "screen", "frank", {"t1": _cell(3)}, scorer="v1")
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)}, scorer="v2")
    with pytest.raises(AgreementError, match="RULER"):
        agree(a, b)


def test_a_partial_task_overlap_is_refused_not_intersected() -> None:
    """Agreeing over the intersection is a different -- and flattering --
    number, so it is refused rather than silently computed."""
    a = _screen("A", "screen", "frank", {"t1": _cell(3), "t2": _cell(0)})
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)})
    with pytest.raises(AgreementError, match="same tasks"):
        agree(a, b)


def test_a_multi_model_screen_is_refused() -> None:
    a = {"run_id": "A", "lane": "screen", "repeats": 3, "scorer_version": "v1",
         "models": ["frank", "gold"], "tasks": ["t1"],
         "cells": {"frank": {"t1": _cell(3)}, "gold": {"t1": _cell(3)}}}
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3)})
    with pytest.raises(AgreementError, match="exactly one model"):
        agree(a, b)


def test_the_report_names_the_tasks_a_paid_run_is_still_needed_for() -> None:
    a = _screen("A", "screen", "frank", {"t1": _cell(3), "t2": _cell(0)})
    b = _screen("B", "confirm", "gpt", {"t1": _cell(3), "t2": _cell(3)})
    out = render_agreement(agree(a, b))
    assert "Agreement: 1/2 (50%)" in out
    assert "only tasks that ever need a paid run again" in out
    assert "t2" in out


def test_a_repeat_run_archives_a_screen(tmp_path, monkeypatch) -> None:
    """`--save` used to be silently ignored on the --repeat path, so the one
    run trustworthy enough to publish was the one that could not be read back."""
    import evals.agreement as agmod

    monkeypatch.setattr(agmod, "RUNS_DIR", tmp_path)
    screen = {
        "repeats": 3, "tasks": ["t1"], "models": ["frank"],
        "cells": {"frank": {"t1": _cell(3)}}, "verdicts": {"frank": "consistent"},
        "runs": [{"lane": "screen", "offline": True, "scorer_version": "v1",
                  "tool_substrate": "framework", "record_substrate": "bundle"}],
    }
    run_dir = agmod.save_screen(screen, run_id="RID")
    loaded = agmod.load_screen("RID")
    assert run_dir.name == "RID"
    assert loaded["lane"] == "screen"
    assert loaded["scorer_version"] == "v1"
    assert agmod.list_screens() == ["RID"]


def test_the_report_names_what_actually_varies() -> None:
    """A number that mixes two variables must SAY so.

    The first agreement number this repo produced compared screen against
    confirm, which moves the model and the substrate at once. Two of its five
    cells disagreed; one was substrate, one was behaviour, and nothing in the
    output said which -- so the report is now explicit that neither is
    attributable, and points at the lane that splits them.
    """
    cells = {"select_build_offer": _cell(3)}
    rep = agree(_screen("A", "screen", "agentic_frank", cells),
                _screen("B", "confirm", "agentic_openai_api", cells))
    assert rep["differs_in"] == ["model", "substrate"]
    assert rep["attributable_to"] is None
    assert "attribute" in render_agreement(rep)


def test_a_single_factor_pair_is_attributed() -> None:
    cells = {"select_build_offer": _cell(3)}
    model_only = agree(_screen("A", "screen", "agentic_frank", cells),
                       _screen("B", "attribute", "agentic_openai_api", cells))
    assert model_only["attributable_to"] == "model"
    assert "MODEL" in render_agreement(model_only)

    substrate_only = agree(
        _screen("A", "attribute", "agentic_openai_api", cells),
        _screen("B", "confirm", "agentic_openai_api", cells))
    assert substrate_only["attributable_to"] == "substrate"
    assert "SUBSTRATE" in render_agreement(substrate_only)


def test_an_archived_run_naming_an_unknown_lane_is_not_guessed_at() -> None:
    """Archives outlive the lane map; an unknown lane attributes to nothing."""
    cells = {"select_build_offer": _cell(3)}
    rep = agree(_screen("A", "screen", "agentic_frank", cells),
                _screen("B", "lane_that_was_deleted", "some_model", cells))
    assert rep["differs_in"] == []
    assert rep["attributable_to"] is None
