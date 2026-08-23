"""Two named lanes over ONE corpus and ONE scorer.

Before this module there were two testing stories that could not be compared.
`make tool-gate` ran five routing fixtures on free/offline Frank;
`chat-calibrate` and `enhance-live` each drove their own script against a live
appliance with their own provider default. Nothing ran the same corpus both
ways, so "does the free lane still predict the paid one?" was an assumption
rather than a number -- and a degrading box read as agent regression five
separate times (auto-memory: `substrate_failure_scored_as_behavior`).

A lane is the whole measurement environment named once: provider, model,
whether an appliance is behind the tools, and which records it can read. A
mode is a slice of the corpus, taken from each fixture's own `mode` field
rather than a hand-kept list of names -- so a new fixture joins its slice by
declaring what it is.

`screen` is the default for everything and is free. `confirm` costs money and
touches a box, so it exists to answer exactly one question at milestones --
*does the free lane still predict the paid one?* -- and never runs in an
iteration loop (auto-memory: `feedback_no_long_eval_loops`).

The lane name is recorded into the matrix and joins the comparability key, so
the differ refuses to diff a screen run against a confirm run rather than
printing a table of cells that moved because the world did.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lane:
    """One named measurement environment."""

    name: str
    models: str
    offline: bool
    bundle: str | None
    live: bool
    #: True when a run spends money and/or reaches an appliance. Those runs
    #: must be asked for deliberately -- see `resolve`.
    costs: bool
    why: str


#: GLM-5.2 on the Fortilab gateway: free, reasoning-capable, and a real tool
#: loop, so it is the only free provider that can score tool_selection at all.
#: `soc_invest_surface` gives the investigation fixtures a real record table;
#: without it they measure an agent triaging an empty box.
SCREEN = Lane(
    name="screen",
    models="agentic_frank",
    offline=True,
    bundle="soc_invest_surface",
    live=False,
    costs=False,
    why="free, box-free, every change",
)

#: The paid lane. `agentic_openai_api` is the provider the product actually
#: runs in FortiSOAR, against a real appliance -- which is the only reason to
#: pay for it, and also why its numbers are only meaningful when the box is
#: known healthy.
CONFIRM = Lane(
    name="confirm",
    models="agentic_openai_api",
    offline=False,
    bundle=None,
    live=True,
    costs=True,
    why="paid + live box, milestones only",
)

LANES: dict[str, Lane] = {lane.name: lane for lane in (SCREEN, CONFIRM)}


#: Corpus slices, keyed on each fixture's own `mode`. `None` is the authoring
#: corpus -- fixtures that predate the field and score YAML alone.
#:
#: `all` is deliberately absent from this map and handled as "no filter": it
#: must not drift from the corpus as fixtures are added.
MODES: dict[str, tuple[str | None, ...]] = {
    "routing": ("tool_selection",),
    "invest": ("investigation",),
    "enhance": ("enhance",),
    "repair": ("repair",),
    "refuse": ("refuse",),
    "authoring": (None,),
}


#: The five appliance-light routing fixtures `make tool-gate` pins. They are a
#: strict subset of `routing`: the other four (`select_explain_playbook` and
#: the three `versatility_*`) were added after the gate's baseline was pinned,
#: and folding them in silently would have moved every diff.
#:
#: Kept here rather than only in the Makefile so the two cannot drift --
#: `tooling/tests/test_eval_lanes.py` asserts they still match.
GATE_TASKS: tuple[str, ...] = (
    "select_run_playbook",
    "select_build_offer",
    "select_enhance_offer",
    "select_diagnose_failure",
    "select_run_playbook_neutral",
)


class LaneError(ValueError):
    """A lane/mode request that cannot be honored, with the reason."""


@dataclass(frozen=True)
class Plan:
    """What a `matrix` invocation resolved to, before anything runs."""

    lane: Lane
    mode: str
    tasks: list[str]

    def describe(self) -> str:
        sub = ("offline" if self.lane.offline else "LIVE BOX") + (
            f" + {self.lane.bundle}" if self.lane.bundle else "")
        return (f"lane={self.lane.name} ({self.lane.why})  "
                f"model={self.lane.models}  substrate={sub}  "
                f"mode={self.mode}  tasks={len(self.tasks)}")


def select_tasks(mode: str, all_tasks) -> list[str]:
    """Task names for `mode`, taken from the fixtures' own `mode` field.

    `all_tasks` is the loaded corpus (anything with `.name` and `.mode`), so
    this stays testable without a provider or a box.
    """
    if mode == "all":
        return [t.name for t in all_tasks]
    if mode == "gate":
        # Name-keyed, not mode-keyed, on purpose: this slice is pinned to a
        # baseline, so a newly-added tool_selection fixture must not join it
        # by declaring a mode.
        known = {t.name for t in all_tasks}
        missing = [n for n in GATE_TASKS if n not in known]
        if missing:
            raise LaneError(
                f"the pinned tool-gate slice names fixtures that no longer "
                f"exist: {', '.join(missing)}")
        return list(GATE_TASKS)
    if mode not in MODES:
        raise LaneError(
            f"unknown mode {mode!r}; expected one of: "
            f"all, gate, {', '.join(sorted(MODES))}")
    wanted = MODES[mode]
    names = [t.name for t in all_tasks if getattr(t, "mode", None) in wanted]
    if not names:
        raise LaneError(
            f"mode {mode!r} matched no fixtures. A slice that selects nothing "
            f"looks exactly like a slice that passed, so this is a refusal "
            f"rather than an empty run.")
    return names


def resolve(*, lane: str, mode: str = "all",
            tasks: str | None = None,
            all_tasks=None,
            allow_live: bool = False) -> Plan:
    """Turn a lane/mode request into the exact task list to run.

    `allow_live` is the deliberate opt-in a costing lane requires. Without it
    `confirm` refuses: a paid live run started by habit is how an iteration
    loop turns into a bill, and the free lane is supposed to be the default
    for everything.
    """
    if lane not in LANES:
        raise LaneError(
            f"unknown lane {lane!r}; expected one of: "
            f"{', '.join(sorted(LANES))}")
    ln = LANES[lane]
    if ln.costs and not allow_live:
        raise LaneError(
            f"lane {lane!r} spends money and reaches a live appliance "
            f"({ln.why}). Pass LIVE_OK=1 to say you meant it. The screen lane "
            f"is free and is the default for everything.")
    if tasks:
        names = [t.strip() for t in tasks.split(",") if t.strip()]
        mode = "explicit"
    else:
        if all_tasks is None:
            from evals.tasks import load_tasks
            all_tasks = load_tasks(None)
        names = select_tasks(mode, all_tasks)
    return Plan(lane=ln, mode=mode, tasks=names)
