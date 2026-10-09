"""What the host knows about the current turn, as ONE object.

Tools need a handful of facts the model is not the source of: the open
playbook's YAML and where it came from, the analyst's own message, their answer
to the modify-or-create choice, whether the turn carries a change affordance or
is read-only, the turn plan, the autonomy policy, the persona and the mounted
record. Each used to be its own ContextVar with its own set/reset pair, and a
host had to bind every one of them on every entry point -- a fresh turn AND a
resume after an approval or a choice. A resume path that forgot one ran with
the default instead (an ungated build on a card resume; a lost scope choice),
and a test had to classify every binding to catch it.

Now there is one immutable `SessionState` behind one ContextVar. A host builds
it in one place and binds it with `bound(state)`; the old `set_*`/`get_*`
functions are views onto it, so tool code is unchanged.

Per-call scratch (citation evidence, rename tracking, render hits) stays in
its own ContextVars: it lives and dies inside one call or one turn and is never
rebuilt on resume.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionState:
    #: The open playbook for the turn, as read from the appliance.
    grounded_yaml: str | None = None
    #: None: the analyst has it open. "draft" / "saved": the playbook this
    #: conversation offered or saved, bound when nothing is open.
    grounded_source: str | None = None
    #: The analyst's own words for the turn (derive intent, never ask for it).
    user_message: str | None = None
    #: Answer to the modify-or-create choice: "modify" | "create_new" | None.
    playbook_scope: str | None = None
    #: The turn came through a control we own (a change chip, an approved
    #: card). Default True: a host that never says otherwise is ungated.
    change_affordance: bool = True
    #: An explain / find-issues turn: the write frontier is refused.
    read_only: bool = False
    #: The TurnPlan whose gates dispatch consults (llm.turn_plan).
    turn_plan: Any = None
    #: Autonomy (llm.autonomy): the parsed policy, its rate counter, and the
    #: IRI of the record the turn is about.
    autonomy_policy: Any = None
    autonomy_counter: Callable[[str, str], tuple[int, int]] | None = None
    autonomy_subject: str | None = None
    #: The host's persona for the turn and the record it is mounted on.
    profile: Any = None
    record_iri: str | None = None


_STATE: ContextVar[SessionState] = ContextVar("_session_state", default=SessionState())


def current() -> SessionState:
    return _STATE.get()


def bind(state: SessionState) -> Token:
    """Make `state` the turn's state. Returns a token for `reset`."""
    return _STATE.set(state)


@dataclass(frozen=True)
class FieldToken:
    """What `update` changed: the fields and their previous values."""
    previous: dict[str, Any]


def update(**changes: Any) -> FieldToken:
    """Replace some fields of the current state. Returns a token that, given
    to `reset`, restores ONLY those fields -- so tokens can be reset in any
    order, exactly as the separate ContextVars this replaced could."""
    state = _STATE.get()
    previous = {k: getattr(state, k) for k in changes}
    _STATE.set(dataclasses.replace(state, **changes))
    return FieldToken(previous)


def reset(token: Any) -> None:
    """Undo a `bind` / `update`. Never raises: a token from another context
    (or None, from a host that bound nothing) has nothing to undo."""
    if token is None:
        return
    if isinstance(token, FieldToken):
        _STATE.set(dataclasses.replace(_STATE.get(), **token.previous))
        return
    try:
        _STATE.reset(token)
    except (ValueError, LookupError, RuntimeError, TypeError):
        pass


def reset_or(token: Any, **fail_open: Any) -> None:
    """`reset`, but if a whole-state token cannot be used, set `fail_open`
    instead of leaving a stale value latched for the worker's life."""
    if token is None:
        return
    if isinstance(token, FieldToken):
        reset(token)
        return
    try:
        _STATE.reset(token)
    except (ValueError, LookupError, RuntimeError, TypeError):
        if fail_open:
            update(**fail_open)


@contextmanager
def bound(state: SessionState) -> Iterator[SessionState]:
    """`with bound(state):` -- the turn runs with exactly this state."""
    token = bind(state)
    try:
        yield state
    finally:
        reset(token)
