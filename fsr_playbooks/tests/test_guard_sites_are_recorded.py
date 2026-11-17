"""Closure: every guard, redirect, refusal, forced wrap-up and cap records a firing.

Why. A guard that forces a correct-looking turn HIDES the prompt or tool bug
that made it necessary, and the only way to find out is to count its firings
(`harness.frames.guards_fired`). Eleven mechanisms were counted; about thirty
steer a turn. A guard added later, or one that was never counted, is invisible
to every eval and every stored transcript. `guard_fires.MECHANISMS` is the one
list; this file closes three ways, none of them a grep count:

1. SITES. Every `record_guard_fire(...)` / `refusal(...)` call in the loop
   modules names a registered mechanism (an f-string or a variable is refused,
   so a name cannot drift from the registry), and every registered mechanism
   has a site (a stale entry fails).
2. SHAPES. The functions that build refusals and redirects may not `return`
   a dict literal: they go through `refusal(...)`. A new refusal written the
   old way fails here. Where a site records elsewhere than where it builds
   (turn refusals, recorded at the dispatch stage), the codes it can return
   must equal the map's keys. Guard classes with a `mark_*` method must record
   in it. New dispatch stages and new loop markers must be classified.
3. BEHAVIOUR. `DRIVERS` fires each mechanism through its real site and asserts
   it lands in `snapshot_guard_fires()`, and that every registered mechanism
   has a driver, so a registered-but-never-recorded entry cannot hide.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from fsr_playbooks.llm import _loop_helpers as lh
from fsr_playbooks.llm import agent_loop, guard_fires, tools, turn_plan
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.guard_fires import MECHANISMS, snapshot_guard_fires
from fsr_playbooks.llm.provider import Message

LLM = Path(guard_fires.__file__).parent
RECORDERS = {"record_guard_fire", "refusal"}


@pytest.fixture(autouse=True)
def _clean():
    guard_fires.clear_guard_fires()
    yield
    guard_fires.clear_guard_fires()


# ───────────────────────────── 1. sites ─────────────────────────────


def _tree(name: str) -> ast.Module:
    return ast.parse((LLM / name).read_text())


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


def _enclosing_function(node: ast.AST, up: dict) -> str:
    while node in up:
        node = up[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return ""


def _recorded_names() -> dict[str, list[str]]:
    """mechanism name -> where it is recorded, over every module in llm/.
    Fails on a recording whose name is not a registered string literal (or
    the one sanctioned form, `type(self).__name__` inside a registered class)."""
    sites: dict[str, list[str]] = {}
    problems: list[str] = []
    for path in sorted(LLM.glob("*.py")):
        if path.name == "guard_fires.py":
            continue
        tree = ast.parse(path.read_text())
        up = _parents(tree)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in RECORDERS and n.args):
                continue
            arg = n.args[0]
            where = f"{path.name}:{n.lineno}"
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                sites.setdefault(arg.value, []).append(where)
            elif (isinstance(arg, ast.Attribute) and arg.attr == "__name__"
                  and isinstance(arg.value, ast.Call)
                  and getattr(arg.value.func, "id", "") == "type"):
                cls = n
                while cls in up and not isinstance(cls, ast.ClassDef):
                    cls = up[cls]
                if isinstance(cls, ast.ClassDef):
                    sites.setdefault(cls.name, []).append(where)
                else:
                    problems.append(f"{where}: type(self).__name__ outside a class")
            elif (isinstance(arg, ast.Name) and path.name == "tools.py"
                  and _enclosing_function(n, up) == "_refuse_for_turn"):
                # The one sanctioned computed name: looked up in
                # TURN_REFUSAL_MECHANISM, whose codes and values
                # `test_every_turn_refusal_code_has_a_mechanism` closes.
                for mech in tools.TURN_REFUSAL_MECHANISM.values():
                    sites.setdefault(mech, []).append(where)
            else:
                problems.append(f"{where}: name is not a string literal")
    assert not problems, "guard sites with a computed mechanism name:\n" + "\n".join(problems)
    return sites


def test_every_site_names_a_registered_mechanism():
    sites = _recorded_names()
    unknown = {n: w for n, w in sites.items() if n not in MECHANISMS}
    assert not unknown, (
        f"recorded but not in guard_fires.MECHANISMS: {unknown}. Register the "
        f"mechanism (name, kind, where) so readers and this closure know it.")


def test_every_registered_mechanism_has_a_site():
    sites = _recorded_names()
    stale = sorted(set(MECHANISMS) - set(sites))
    assert not stale, f"registered but recorded nowhere (stale or lost): {stale}"


# ───────────────────────────── 2. shapes ─────────────────────────────


def _function(tree: ast.Module, qualname: str) -> ast.FunctionDef:
    parts = qualname.split(".")
    scope: ast.AST = tree
    for part in parts:
        scope = next(n for n in ast.walk(scope)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == part)
    return scope  # type: ignore[return-value]


def _dict_returns(fn: ast.AST) -> list[int]:
    """Lines of `return {...}` in `fn`, not descending into nested defs."""
    hits: list[int] = []

    def walk(node: ast.AST) -> None:
        for c in ast.iter_child_nodes(node):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(c, ast.Return) and isinstance(c.value, ast.Dict):
                hits.append(c.lineno)
            walk(c)

    walk(fn)
    return hits


#: Functions that build a guard envelope the model sees. They return it through
#: `refusal(...)`, never as a bare dict, so the record cannot be forgotten.
REFUSAL_BUILDERS = [
    ("agent_loop.py", "run_loop.guarded_dispatch"),
    ("_loop_helpers.py", "TriageDiscipline._check_locked"),
    ("tools.py", "_accept"),
]


@pytest.mark.parametrize("module,qualname", REFUSAL_BUILDERS)
def test_refusal_builders_do_not_return_bare_envelopes(module, qualname):
    bare = _dict_returns(_function(_tree(module), qualname))
    assert not bare, (
        f"{module}:{qualname} returns a dict literal at line(s) {bare}: a refusal "
        f"must go through guard_fires.refusal(<mechanism>, {{...}}) so it records.")


def _codes(fn: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if (isinstance(k, ast.Constant) and k.value == "code"
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    out.add(v.value)
    return out


def test_every_turn_refusal_code_has_a_mechanism():
    """`turn_refusal` is also called to FILTER the advertised tools, so it must
    not record; the dispatch stage records by code. Every code the refusers can
    return must be in the stage's map, or that refusal fires unrecorded."""
    codes = (_codes(_function(_tree("tools.py"), "turn_refusal"))
             | _codes(_function(_tree("turn_plan.py"), "TurnPlan.gate_refusal"))
             | _codes(_function(_tree("turn_plan.py"), "_playbook_side_refusal"))
             | _codes(_function(_tree("ask_scope.py"), "answer_refusal")))
    assert codes == set(tools.TURN_REFUSAL_MECHANISM), (
        f"refusal codes {sorted(codes)} vs recorded {sorted(tools.TURN_REFUSAL_MECHANISM)}")
    assert set(tools.TURN_REFUSAL_MECHANISM.values()) <= set(MECHANISMS)


#: Every dispatch stage and how it is covered. A new stage must be added here
#: with its mechanism (or the reason it refuses nothing), which is the moment
#: to decide whether it needs a firing.
STAGES = {
    "_refuse_for_turn": "tools.* by code (TURN_REFUSAL_MECHANISM)",
    "_fold_emit_card_payload": None,       # fixes arguments in place, never refuses
    "_coerce_args": None,                  # lossless shape fix
    "_check_args": "tools.invalid_tool_args",
    "_default_live_probe": None,           # fills a default
}


def test_every_dispatch_stage_is_classified():
    assert {s.__name__ for s in tools._DISPATCH_STAGES} == set(STAGES)


def test_every_guard_class_records_in_its_mark_methods():
    tree = _tree("_loop_helpers.py")
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for fn in (m for m in cls.body if isinstance(m, ast.FunctionDef)
                   and m.name.startswith("mark_")):
            calls = {n.func.id for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            assert calls & RECORDERS, (
                f"{cls.name}.{fn.name} marks a guard as fired without recording it")


#: Every loop marker (`usage_event(<marker>)`, a nudge tuple's first item, a
#: wrap-up label) and the mechanism that records it, or why it is not a guard.
#: A new marker has to be classified here: the moment to ask "does this need a
#: firing?". None-valued entries are rounds, not interventions.
LOOP_MARKERS = {
    "unverified_draft_verified": "BuildProgressGuard.unverified_draft",
    "unverified_draft_failed": None,       # outcome of the entry above
    "promised_action_forced": "PromisedActionGuard",
    "build_progress_forced": "BuildProgressGuard",
    "unverified_draft_forced": "BuildProgressGuard.unverified_draft",
    "failed_edit_forced": "EnhanceDeliveryGuard.failed_edit",
    "terminal_fence_verified": "turn.terminal_fence_verified",
    "enhance_delivery_forced": "EnhanceDeliveryGuard",
    "create_delivery_forced": "CreateDeliveryGuard",
    "verdict_guard_forced": "VerdictDeliveryGuard",
    "build_incomplete_shown": "BuildProgressGuard.incomplete",
    "pending_approval": None,              # the approval gate, not a guard
    "max_tool_turns": "turn.max_tool_turns",           # wrap-up label
    "answer_scope_wrapup": "turn.answer_scope_wrapup",
}


def _loop_markers() -> set[str]:
    """String literals the loop uses as a round marker."""
    src = _tree("agent_loop.py")
    out: set[str] = set()
    for n in ast.walk(src):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "usage_event" and n.args
                and isinstance(n.args[0], ast.Constant)):
            out.add(n.args[0].value)
        # nudge = ("marker", directive)
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple)
                and len(n.value.elts) == 2
                and isinstance(n.value.elts[0], ast.Constant)
                and isinstance(n.value.elts[0].value, str)
                and any(getattr(t, "id", "") == "nudge" for t in n.targets)):
            out.add(n.value.elts[0].value)
        # wrapup(directive, "label")
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "wrapup" and len(n.args) > 1
                and isinstance(n.args[1], ast.Constant)):
            out.add(n.args[1].value)
    return out


def test_every_loop_marker_is_classified():
    seen = _loop_markers()
    unclassified = sorted(seen - set(LOOP_MARKERS))
    assert not unclassified, (
        f"agent_loop uses round markers {unclassified} that LOOP_MARKERS does not "
        f"classify. A marker that is an intervention needs a registered mechanism "
        f"and a record at its site; one that is only a round maps to None.")
    stale = sorted(set(LOOP_MARKERS) - seen)
    assert not stale, f"LOOP_MARKERS entries the loop no longer uses: {stale}"
    for marker, mech in LOOP_MARKERS.items():
        assert mech is None or mech in MECHANISMS, (marker, mech)


# ───────────────────────────── 3. behaviour ─────────────────────────────


class _Final:
    def __init__(self, content):
        self.content = content
        self.usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                                     cache_read_input_tokens=0,
                                     cache_creation_input_tokens=0)
        self.stop_reason = "tool_use" if any(
            getattr(b, "type", "") == "tool_use" for b in content) else "end_turn"


class _Stream:
    def __init__(self, final):
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def _gen():
            for b in self._final.content:
                if getattr(b, "type", "") == "text":
                    yield SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text=b.text))
        return _gen()

    async def get_final_message(self):
        return self._final


class _Client:
    def __init__(self, turns):
        self._turns, self._i = list(turns), 0
        self.messages = self

    def stream(self, **_kw):
        final = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return _Stream(final)


def _use(cid, name, args):
    return SimpleNamespace(type="tool_use", id=cid, name=name, input=args)


def _say(text):
    return SimpleNamespace(type="text", text=text)


_SLICE = [{"name": n, "description": "", "input_schema": {"type": "object"}}
          for n in ("run_op", "emit_card", "get_record")]


def _loop(monkeypatch, turns, *, dispatch=None, tools_=None, max_tool_turns=None,
          tags=None):
    monkeypatch.setattr(agent_loop, "dispatch",
                        dispatch or (lambda n, a, **_kw: {"ok": True, "echo": a}))
    monkeypatch.setattr(agent_loop, "_tier_for", lambda n, a: 1)
    provider = AnthropicProvider(model="fake", client=_Client(turns))

    async def go():
        return [e async for e in provider.stream(
            system="sys", messages=[Message(role="user", content="hi")],
            tools=_SLICE if tools_ is None else tools_,
            max_tool_turns=max_tool_turns, tags=tags)]

    return asyncio.run(go())


def _offer(cid="o1", card="playbook_offer"):
    return _use(cid, "emit_card", {"card_type": card, "payload": {"id": cid}})


def _fire_bad_args(mp):
    _loop(mp, [_Final([_use("c", "run_op", {agent_loop.BAD_ARGS_KEY: "x"})]),
               _Final([_say("done")])])


def _fire_not_in_slice(mp):
    _loop(mp, [_Final([_use("c", "nope", {})]), _Final([_say("done")])])


def _fire_max_tool_turns(mp):
    n = iter(range(100))
    turns = [_Final([_use(f"c{i}", "run_op", {"q": i})]) for i in range(3)]
    turns.append(_Final([_say("wrapped up")]))
    _loop(mp, turns, max_tool_turns=2,
          dispatch=lambda name, a: {"ok": True, "n": next(n)})


def _fire_budget_ask(mp):
    mp.setattr(agent_loop, "analyst_has_the_yaml", lambda h: True)
    turns = [_Final([_use(f"c{i}", "run_op", {"q": i})]) for i in range(3)]
    _loop(mp, turns, max_tool_turns=2)


def _fire_self_repair(mp):
    mp.setattr(agent_loop, "_fence_problem", lambda y: ("fix it: ", "bad yaml"))
    _loop(mp, [_Final([_say("```yaml\nname: x\n```")]), _Final([_say("ok")])])


def _fire_fence_neutralised(mp):
    mp.setattr(agent_loop, "_fence_problem", lambda y: ("", "bad yaml"))
    agent_loop._neutralise_failing_fences("```yaml\nname: x\n```")


def _fire_terminal_fence_verified(mp):
    mp.setattr(agent_loop, "_fence_problem", lambda y: None)
    mp.setattr(agent_loop, "is_authoring_slice", lambda a: True)
    tools_ = [{"name": n, "description": "", "input_schema": {"type": "object"}}
              for n in ("verify_playbook", "emit_card")]
    _loop(mp, [_Final([_say("```yaml\nname: x\n```")])], tools_=tools_)


def _fire_forced_containment(mp):
    mp.setattr(agent_loop, "forced_containment", lambda d: {"x": 1})
    ct = lh.ContainmentFollowThrough(enabled=True)
    mp.setattr(lh.ContainmentFollowThrough, "directive",
               lambda self, allowed: ("containment_follow_through", "stage it"))
    mp.setattr(lh.ContainmentFollowThrough, "mark_fired", lambda self: None)
    del ct
    verdict = {"card_type": "verdict", "payload": {"id": "v"}}
    _loop(mp, [_Final([_use("a", "emit_card", verdict)]), _Final([_say("done")]),
               _Final([_use("f", "emit_card", {"card_type": "action", "payload": {}})])])


def _triage(**kw) -> lh.TriageDiscipline:
    return lh.TriageDiscipline(**kw)


def _fire_triage_duplicate_search(_mp):
    d = _triage()
    a = {"module": "alerts", "query": "q"}
    d.evaluate("search_module_records", a)
    d.evaluate("search_module_records", dict(a))


def _fire_triage_hunt_floor(_mp):
    _triage().evaluate("emit_action_card", {})


def _dispatch_real(name, args):
    return tools.dispatch(name, args)


def _fire_tools_reserved_key(_mp):
    tools.dispatch("run_op", {"_approved": True, "connector": "x"})


def _fire_tools_read_only(_mp):
    token = tools.set_read_only_turn(True)
    try:
        name = sorted(tools.READ_ONLY_WITHHELD_TOOLS)[0]
        tools.dispatch(name, {})
    finally:
        tools.reset_read_only_turn(token)


def _with_plan(plan, name, args):
    token = turn_plan.set_turn_plan(plan)
    try:
        tools.dispatch(name, args)
    finally:
        turn_plan.reset_turn_plan(token)


def _fire_tools_not_a_playbook_tool(_mp):
    plan = turn_plan.TurnPlan(intent="build", prompt="", intent_stated=True)
    name = sorted(n for n in tools.REGISTRY if n == "run_op")[0]
    _with_plan(plan, name, {"connector": "x", "op": "y"})


def _fire_tools_state_unresolved(_mp):
    _with_plan(turn_plan.TurnPlan.failsafe("test"), "edit_playbook", {})


def _fire_tools_not_afforded(_mp):
    plan = turn_plan.TurnPlan(intent="triage", prompt="")
    _with_plan(plan, "edit_playbook", {})


def _answer_scope_loop(mp, turns, dispatch=None):
    from fsr_playbooks.llm import ask_scope
    token = ask_scope.bind_scope("answer")
    try:
        _loop(mp, turns, dispatch=dispatch)
    finally:
        ask_scope.reset_scope(token)


def _fire_tools_answer_scope(_mp):
    from fsr_playbooks.llm import ask_scope
    token = ask_scope.bind_scope("answer")
    try:
        tools.dispatch("siem_search", {})
    finally:
        ask_scope.reset_scope(token)


def _fire_dispatch_answer_scope(mp):
    n = ["get_record"] * 7
    turns = [_Final([_use(f"c{i}", "get_record", {"i": i})]) for i in range(len(n))]
    turns.append(_Final([_say("the answer")]))
    _answer_scope_loop(mp, turns)


def _fire_answer_scope_wrapup(mp):
    _answer_scope_loop(mp, [_Final([_use("c", "get_record", {})]),
                            _Final([_say("")]), _Final([_say("the answer")])])


def _fire_tools_invalid_args(_mp):
    tools.dispatch("run_op", {})


def _direct(fn):
    return lambda _mp: fn()


def _progress_flail(_mp):
    m = lh.ProgressMeter(error_rounds=1)
    m.note_result("run_op", {"a": 1}, {"ok": False, "error": "x"})
    m.end_round()


DRIVERS = {
    "EnhanceDeliveryGuard": _direct(lh.EnhanceDeliveryGuard().mark_forced),
    "EnhanceDeliveryGuard.failed_edit": _direct(lh.EnhanceDeliveryGuard().mark_fix_forced),
    "CreateDeliveryGuard": _direct(lh.CreateDeliveryGuard().mark_forced),
    "BuildProgressGuard": _direct(lh.BuildProgressGuard().mark_forced),
    "BuildProgressGuard.incomplete": _direct(lh.BuildProgressGuard().mark_incomplete_shown),
    "BuildProgressGuard.unverified_draft": _direct(lh.BuildProgressGuard().mark_verify_forced),
    "VerdictDeliveryGuard": _direct(lh.VerdictDeliveryGuard().mark_forced),
    "ContainmentFollowThrough": _direct(lh.ContainmentFollowThrough().mark_fired),
    "PromisedActionGuard": _direct(lh.PromisedActionGuard().mark_forced),
    "ProgressMeter.flail": _progress_flail,
    "dispatch.bad_tool_arguments": _fire_bad_args,
    "dispatch.not_in_slice": _fire_not_in_slice,
    "triage.duplicate_search": _fire_triage_duplicate_search,
    "triage.hunt_floor": _fire_triage_hunt_floor,
    "tools.reserved_key_rejected": _fire_tools_reserved_key,
    "tools.read_only_turn": _fire_tools_read_only,
    "tools.not_a_playbook_tool": _fire_tools_not_a_playbook_tool,
    "tools.state_unresolved": _fire_tools_state_unresolved,
    "tools.not_afforded": _fire_tools_not_afforded,
    "tools.invalid_tool_args": _fire_tools_invalid_args,
    "tools.answer_scope": _fire_tools_answer_scope,
    "dispatch.answer_scope": _fire_dispatch_answer_scope,
    "turn.answer_scope_wrapup": _fire_answer_scope_wrapup,
    "turn.self_repair": _fire_self_repair,
    "turn.fence_neutralised": _fire_fence_neutralised,
    "turn.terminal_fence_verified": _fire_terminal_fence_verified,
    "turn.forced_containment": _fire_forced_containment,
    "turn.max_tool_turns": _fire_max_tool_turns,
    "turn.budget_ask": _fire_budget_ask,
}


def test_every_registered_mechanism_has_a_driver():
    assert set(DRIVERS) == set(MECHANISMS), (
        f"missing a driver: {sorted(set(MECHANISMS) - set(DRIVERS))}; "
        f"driver for an unregistered mechanism: {sorted(set(DRIVERS) - set(MECHANISMS))}")


@pytest.mark.parametrize("mechanism", sorted(DRIVERS))
def test_mechanism_records_when_it_fires(mechanism, monkeypatch):
    DRIVERS[mechanism](monkeypatch)
    assert mechanism in snapshot_guard_fires(), (
        f"{mechanism} fired through its real site but is not in guards_fired: "
        f"{snapshot_guard_fires()}")


def test_a_refusal_returns_its_payload_unchanged():
    payload = {"ok": False}
    assert guard_fires.refusal("dispatch.not_in_slice", payload) is payload
    assert snapshot_guard_fires() == ["dispatch.not_in_slice"]


def test_the_list_is_bounded_for_a_process_with_no_turn_driver():
    for _ in range(guard_fires._MAX_FIRES + 50):
        guard_fires.record_guard_fire("dispatch.not_in_slice")
    assert len(snapshot_guard_fires()) == guard_fires._MAX_FIRES


def test_filtering_the_advertised_tools_is_not_a_refusal():
    """`advertised_for_turn` calls `turn_refusal` to filter the list; computing
    what is offered must not read as a guard firing."""
    token = tools.set_read_only_turn(True)
    try:
        tools.advertised_for_turn([{"name": n} for n in tools.READ_ONLY_WITHHELD_TOOLS])
    finally:
        tools.reset_read_only_turn(token)
    assert snapshot_guard_fires() == []


def test_registry_keys_are_the_mechanism_names():
    assert all(m.name == k for k, m in MECHANISMS.items())


def test_an_unattended_turn_never_ends_on_the_budget_ask(monkeypatch):
    """Nobody answers a card on an unattended turn (auto-triage, a scheduled
    hunt): with something delivered and the budget spent, it still wraps up
    instead of asking 'continue or deliver?'."""
    monkeypatch.setattr(agent_loop, "analyst_has_the_yaml", lambda h: True)
    turns = [_Final([_use(f"c{i}", "run_op", {"q": i})]) for i in range(3)]
    turns.append(_Final([_say("wrapped up")]))
    events = _loop(monkeypatch, turns, max_tool_turns=2, tags={"unattended": True})
    names = [getattr(e, "name", None) for e in events]
    assert "emit_choice_card" not in names
    assert events[-1].stop_reason == "end_turn"
    attended = _loop(monkeypatch, [_Final([_use(f"d{i}", "run_op", {"q": i})]) for i in range(3)],
                     max_tool_turns=2)
    assert "emit_choice_card" in [getattr(e, "name", None) for e in attended]
