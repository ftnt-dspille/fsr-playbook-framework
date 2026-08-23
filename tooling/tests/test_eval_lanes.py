"""One entry point, two named lanes -- and the guards that keep them honest.

Before `evals/lanes.py` there were three eval entry points (`tool-gate`,
`chat-calibrate`, `enhance-live`), each with its own provider default and its
own substrate, so no two of their numbers were comparable. These tests pin the
four properties that make the unified entry point worth having:

  1. a slice that selects NOTHING is a refusal, not an empty pass (a gate
     selecting zero files looks exactly like a passing one -- auto-memory:
     `gates_can_be_silently_dead`);
  2. the paid/live lane cannot start by habit;
  3. the pinned tool-gate task list has not drifted from the Makefile;
  4. the lane name reaches the comparability key, so screen-vs-confirm is
     refused BY NAME rather than inferred from `offline: True -> False`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.harness import _substrate_delta  # noqa: E402
from evals.lanes import (  # noqa: E402
    ATTRIBUTE,
    CONFIRM,
    GATE_TASKS,
    LANES,
    SCREEN,
    LaneError,
    attributable_to,
    differs_in,
    resolve,
    select_tasks,
)
from evals.scoring import SCORER_VERSION  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


class _T:
    def __init__(self, name, mode=None):
        self.name = name
        self.mode = mode


CORPUS = [
    _T("hello_connector"),
    _T("select_run_playbook", "tool_selection"),
    _T("select_build_offer", "tool_selection"),
    _T("select_enhance_offer", "tool_selection"),
    _T("select_diagnose_failure", "tool_selection"),
    _T("select_run_playbook_neutral", "tool_selection"),
    _T("invest_intrusion_incident", "investigation"),
    _T("enhance_rename_step", "enhance"),
]


def test_screen_is_free_and_box_free() -> None:
    """The default lane must never reach an appliance or a bill."""
    assert SCREEN.offline is True
    assert SCREEN.live is False
    assert SCREEN.costs is False
    assert SCREEN.bundle == "soc_invest_surface"


def test_confirm_refuses_without_the_explicit_opt_in() -> None:
    with pytest.raises(LaneError) as e:
        resolve(lane="confirm", mode="gate", all_tasks=CORPUS)
    assert "LIVE_OK" in str(e.value)
    plan = resolve(lane="confirm", mode="gate", all_tasks=CORPUS,
                   allow_live=True)
    assert plan.lane is CONFIRM
    assert plan.lane.live is True


def test_an_empty_slice_is_a_refusal_not_an_empty_run() -> None:
    """A gate that selects zero fixtures looks exactly like a passing one."""
    with pytest.raises(LaneError) as e:
        select_tasks("repair", CORPUS)
    assert "looks exactly like" in str(e.value)


def test_unknown_lane_and_mode_name_what_was_expected() -> None:
    with pytest.raises(LaneError) as e:
        resolve(lane="nope", all_tasks=CORPUS)
    assert "screen" in str(e.value) and "confirm" in str(e.value)
    with pytest.raises(LaneError) as e:
        select_tasks("nope", CORPUS)
    assert "gate" in str(e.value)


def test_explicit_tasks_override_the_mode() -> None:
    plan = resolve(lane="screen", mode="all", tasks="a, b",
                   all_tasks=CORPUS)
    assert plan.tasks == ["a", "b"]
    assert plan.mode == "explicit"


def test_gate_slice_is_name_pinned_not_mode_pinned() -> None:
    """A newly-added tool_selection fixture must not join the pinned slice.

    `routing` takes everything declaring `mode: tool_selection`; `gate` takes
    the five names the baseline was captured on. If the two were the same
    thing, adding a fixture would move every tool-gate diff.
    """
    corpus = CORPUS + [_T("select_brand_new", "tool_selection")]
    assert select_tasks("gate", corpus) == list(GATE_TASKS)
    assert "select_brand_new" in select_tasks("routing", corpus)


def test_gate_slice_has_not_drifted_from_the_makefile() -> None:
    """Two copies of one list is a drift bug waiting; assert they agree."""
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^TOOL_GATE_TASKS\s*:=\s*(.+)$", mk, re.M)
    assert m, "TOOL_GATE_TASKS vanished from the Makefile"
    from_makefile = tuple(t.strip() for t in m.group(1).split(",") if t.strip())
    assert from_makefile == GATE_TASKS


def test_gate_slice_refuses_when_a_pinned_fixture_disappears() -> None:
    with pytest.raises(LaneError) as e:
        select_tasks("gate", [_T("hello_connector")])
    assert "no longer exist" in str(e.value)


def test_every_mode_selects_something_in_the_real_corpus() -> None:
    """The slices are only useful if the shipped fixtures actually fill them."""
    from evals.lanes import MODES
    from evals.tasks import load_tasks
    corpus = load_tasks(None)
    for mode in list(MODES) + ["gate", "all"]:
        assert select_tasks(mode, corpus), mode


def _run(**over):
    base = {
        "run_id": "20260101T000000Z",
        "offline": True,
        "tool_substrate": "framework+connector",
        "record_substrate": "soc_invest_surface",
        "scorer_version": SCORER_VERSION,
        "lane": "screen",
    }
    base.update(over)
    return base


def test_lane_joins_the_comparability_key() -> None:
    """Screen vs confirm is refused BY NAME, not inferred from `offline`."""
    d = _substrate_delta(_run(), _run())
    assert d["comparable"] is True
    d = _substrate_delta(_run(), _run(lane="confirm"))
    assert d["comparable"] is False
    assert "lane" in [f["field"] for f in d["fields"] if not f["match"]]


def test_an_unlabelled_run_is_not_comparable_to_a_lane_run() -> None:
    """A run predating the lane field carries none, and `unknown` is a miss."""
    prior = _run()
    prior.pop("lane")
    d = _substrate_delta(prior, _run())
    assert d["comparable"] is False


def test_lanes_registry_is_keyed_by_name() -> None:
    assert {"screen", "confirm", "attribute"} == set(LANES)
    assert all(name == lane.name for name, lane in LANES.items())


def test_the_attribute_lane_varies_exactly_one_factor_against_each_side() -> None:
    """The whole point of a third lane.

    screen vs confirm moves the model AND the substrate at once, so a
    disagreement between them is attributable to neither. The first agreement
    number this repo produced (3/5) was hand-read as "one substrate, one
    behavioural"; measuring it showed both were the model. Each pair below
    moves exactly one thing.
    """
    assert differs_in(SCREEN, CONFIRM) == ("model", "substrate")
    assert attributable_to(SCREEN, CONFIRM) is None

    assert attributable_to(SCREEN, ATTRIBUTE) == "model"
    assert attributable_to(ATTRIBUTE, CONFIRM) == "substrate"


def test_the_attribute_lane_is_paid_but_box_free() -> None:
    """It costs money, so it is gated like `confirm`; it never reaches an
    appliance, so it can run while a box is down -- and a box being down is
    the most common reason a paid number is worthless."""
    assert ATTRIBUTE.costs is True
    assert ATTRIBUTE.live is False
    assert ATTRIBUTE.offline is True
    assert ATTRIBUTE.bundle == SCREEN.bundle
    assert ATTRIBUTE.models == CONFIRM.models

    with pytest.raises(LaneError) as e:
        resolve(lane="attribute", mode="gate", all_tasks=CORPUS)
    assert "LIVE_OK" in str(e.value)
    # ...but it must not claim to reach an appliance, because it does not.
    assert "appliance" not in str(e.value)
    plan = resolve(lane="attribute", mode="gate", all_tasks=CORPUS,
                   allow_live=True)
    assert plan.lane is ATTRIBUTE
