"""The one conversation driver for every harness that talks a SOC-assistant chat.

`drive()` sends a conversation's user steps and resume steps through a
transport, follows halts (approvals, cards, manual inputs) through an `answer`
policy, and returns one `TraceStep` per step. Who answers a halt, and whether
a turn is a scoreable answer, are the caller's policy; the loop is not.

Transports (what a turn physically is):

  FsrTransport   chat_turn / chat_resume through any `fsr` object that has
                 `.execute(op, params, timeout=)` returning something with
                 `ok`, `data`, `error` (the `Executor` protocol below). Sync, or
                 detached (the widget's path: chat_turn detached, then chat_poll
                 to done).

Callers bring their own `fsr`: the connector passes pyfsr-backed LiveFSR, the
framework's chat_drive and effect probes pass a raw-execute adapter. Callers
bring their own in-process transport too (the connector's LocalTransport), and
they keep their own connector-only helpers (the connector's mount_entity).

Policies that genuinely differ are arguments, not copies:
  history   "blocks" -- the assistant turn as the widget's block list (tool_use
            ids and results kept, so a native tool replay is what the next
            turn sees); "text" -- the assistant's prose only; a callable gets
            the step and returns the content it wants kept.
  answer    what to do with a halt. None stops the step at the halt and records
            it; a callable receives the halt frames and the envelope and returns
            the envelope of whatever it did (usually a chat_resume), or None.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .classify import TurnOutcome, classify_turn
from .frames import (
    HALT_FRAME_TYPES,
    assistant_summary,
    assistant_text,
    frames,
    guards_fired,
    pending_halt,
    stop_reason,
    tools_called,
)
from .frames import (
    halts as halt_frames,
)

#: Frame types a turn can halt on (the reader owns the set).
HALT_TYPES = HALT_FRAME_TYPES


class DriveError(RuntimeError):
    """The turn never ran (transport, auth, config). NOT a model failure.

    A drive error must abort, never score: a 403 graded as "the model authored
    no YAML" blames the model for a turn that never happened.
    """


class ExecResult(Protocol):
    """What `Executor.execute` returns: the operation's ok flag, its data dict,
    and its error (None when there is none)."""

    ok: Any
    data: Any
    error: Any


class Executor(Protocol):
    """The only thing the driver needs from its `fsr` object."""

    def execute(self, op: str, params: dict, *, timeout: int | None = None) -> ExecResult: ...


class Transport(Protocol):
    session_id: str

    def turn(self, params: dict) -> dict: ...

    def resume(self, params: dict) -> dict: ...


# ---------------------------------------------------------------- polling
def poll_to_done(fsr: Executor, session_id: str, since_turn: int, *, timeout: int = 480,
                 label: str = "turn") -> tuple[Any, list | None, str | None]:
    cursor, transcript, term_turn, stop = 0, None, None, None
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = fsr.execute("chat_poll", {"session_id": session_id,
                                      "cursor": cursor, "since_turn": since_turn})
        if not r.ok:
            raise DriveError(f"{label}: chat_poll failed: {r.error}")
        d = r.data
        if isinstance(d.get("cursor"), int):
            cursor = d["cursor"]
        for f in d.get("frames") or []:
            if f.get("type") == "stream_end":
                transcript = f.get("transcript")
                term_turn = d.get("turn")
                stop = f.get("stop_reason")
        if d.get("done"):
            return term_turn or d.get("turn"), transcript, stop or d.get("stop_reason")
        time.sleep(0.7)
    raise TimeoutError(f"{label}: never reached done within {timeout}s")


# ------------------------------------------------------------- transports
def detached_turn(fsr: Executor, *, session_id: str, intent: str, messages: list[dict],
                  entity: dict | None = None, since_turn: int = 0,
                  timeout: int = 480) -> tuple[Any, list, str | None]:
    """One detached turn, as the widget sends it: the ack, then chat_poll to
    done. Returns (terminal turn, transcript, stop_reason). A turn that did not
    answer (a provider error, a cut-off) is a drive error, not a grade."""
    t = FsrTransport(fsr, session_id=session_id, detached=True, poll_timeout=timeout)
    t.turn_no = since_turn
    params: dict[str, Any] = {"session_id": session_id, "intent": intent, "messages": messages}
    if entity:
        params["entity"] = entity
    env = t.turn(params)
    outcome = classify_turn(env)
    if outcome.kind not in ("answered", "halted"):
        raise DriveError(f"turn did not answer ({outcome.kind}): {outcome.detail}")
    return t.turn_no, env.get("transcript") or [], env.get("stop_reason")


class FsrTransport:
    """chat_turn / chat_resume on a box. `detached=True` is the widget's path:
    the turn is acknowledged, then polled to done. A resume is always
    synchronous: chat_resume returns the resumed transcript itself."""

    def __init__(self, fsr: Executor, *, session_id: str | None = None, detached: bool = False,
                 timeout: int = 300, poll_timeout: int = 480):
        self.fsr = fsr
        self.session_id = session_id or f"drive-{uuid.uuid4().hex[:10]}"
        self.detached = detached
        self.timeout = timeout
        self.poll_timeout = poll_timeout
        self.turn_no = 0

    def _call(self, op: str, params: dict) -> dict:
        r = self.fsr.execute(op, params, timeout=self.timeout)
        d = r.data or {}
        if not d and r.error:
            d = {"ok": False, "error": r.error}
        return d

    def turn(self, params: dict) -> dict:
        if not self.detached:
            return self._call("chat_turn", params)
        ack = self._call("chat_turn", {**params, "detached": True})
        if not (ack.get("ok") and (ack.get("accepted") or ack.get("stop_reason") == "accepted")):
            raise DriveError(f"chat_turn ack failed: {ack.get('error') or ack}")
        term, transcript, stop = poll_to_done(self.fsr, self.session_id, self.turn_no,
                                              timeout=self.poll_timeout)
        self.turn_no = term or self.turn_no
        return {"ok": True, "stop_reason": stop, "transcript": transcript or []}

    def resume(self, params: dict) -> dict:
        return self._call("chat_resume", params)


# --------------------------------------------------------------- the trace
@dataclass
class TraceStep:
    index: int
    kind: str                       # "user" | "resume"
    sent: Any                       # the message text, or the chat_resume params
    raw: dict | None = None      # the scenario step as written
    intent: str | None = None    # the tool slice the turn ran under (user steps)
    envelopes: list[dict] = field(default_factory=list)   # every envelope the step produced
    outcome: TurnOutcome | None = None
    error: str | None = None
    answered_halts: int = 0         # halts the answer policy resolved on this step

    @property
    def envelope(self) -> dict | None:
        return self.envelopes[-1] if self.envelopes else None

    @property
    def transcript(self) -> list:
        """Every frame the step produced, in order (all its envelopes)."""
        return [f for e in self.envelopes for f in frames(e)]

    @property
    def text(self) -> str:
        return "".join(assistant_text(e) for e in self.envelopes).strip()

    @property
    def tools(self) -> list[str]:
        return [t for e in self.envelopes for t in tools_called(e)]

    @property
    def stop(self) -> str | None:
        return stop_reason(self.envelope) if self.envelope else None

    @property
    def guards(self) -> list[str]:
        return [g for e in self.envelopes for g in guards_fired(e)]

    @property
    def halt(self) -> dict | None:
        return pending_halt(self.envelope) if self.envelope else None


# ----------------------------------------------------------------- drive
def drive(transport: Transport, spec: dict, *, steps: list[dict] | None = None,
          next_step: Callable[[list[TraceStep]], dict | None] | None = None,
          max_steps: int = 12, intent: str = "triage", entity: dict | None = None,
          history: str | Callable[[TraceStep], str | None] = "blocks",
          answer: Callable[[list[dict], dict], dict | None] | None = None,
          max_halts: int = 12,
          turn_params: Callable[[dict], dict] | None = None,
          resume_params: Callable[[dict, dict | None], dict | None] | None = None,
          on_step: Callable[[TraceStep], list[dict] | None] | None = None,
          resume_without_halt: bool = False,
          ) -> list[TraceStep]:
    """Drive a conversation and return its trace.

    `steps` (default spec["steps"]) run first; then `next_step`, when given,
    chooses each further step from the trace so far (the analyst simulator).
    A user step is one chat_turn over the whole history; a resume step answers
    the last halt (`resume_params` builds the chat_resume params, or the default
    decision-and-id shape is used). `answer` resolves halts after a user or
    resume step, up to `max_halts`. `on_step` sees each finished step and may
    return scenario steps to run next (a repeated approval).
    `turn_params` / `resume_params` let a caller add to a request or rewrite it
    from state it holds (a canvas that changed under an accepted offer).
    A resume step with no pending halt and no explicit id is recorded as an
    error and not sent, unless `resume_without_halt` is set: then it is sent
    anyway (a scripted decision the caller wants on the wire regardless).
    """
    if not callable(history) and history not in ("blocks", "text"):
        raise ValueError(f"history must be 'blocks', 'text' or a callable, not {history!r}")
    queue = list(steps if steps is not None else (spec.get("steps") or []))
    messages: list[dict] = []
    trace: list[TraceStep] = []
    last_env: dict | None = None
    while True:
        if not queue and next_step is not None and len(trace) < max_steps:
            nxt = next_step(trace)
            if nxt:
                queue.append(nxt)
        if not queue:
            break
        raw = queue.pop(0)
        i = len(trace) + 1
        if "user" in raw:
            messages.append({"role": "user", "content": raw["user"]})
            params = {"session_id": transport.session_id,
                      "intent": raw.get("intent", intent),
                      "messages": list(messages)}
            if entity is not None:
                params["entity"] = entity
            if turn_params is not None:
                params.update(turn_params(raw))
            step = TraceStep(index=i, kind="user", sent=raw["user"], raw=raw,
                             intent=params["intent"])
            env = transport.turn(params)
            step.envelopes.append(env)
        elif "resume" in raw:
            if last_env is None:
                raise DriveError(f"step {i} is a resume, but no turn preceded it")
            r = raw["resume"]
            halt = pending_halt(last_env)
            if halt is None and not r.get("id") and not resume_without_halt:
                # Nothing to resume is a scenario outcome, not a crash.
                step = TraceStep(index=i, kind="resume", sent=r, raw=raw,
                                 error="no pending halt to resume")
                trace.append(step)
                if on_step:
                    queue[0:0] = on_step(step) or []
                continue
            params = (resume_params(raw, halt) if resume_params is not None
                      else _default_resume(transport.session_id, raw, halt))
            step = TraceStep(index=i, kind="resume", sent=params, raw=raw)
            try:
                env = transport.resume(params)
            except Exception as e:  # a resume that throws is a real defect
                step.error = f"{type(e).__name__}: {e}"
                trace.append(step)
                if on_step:
                    queue[0:0] = on_step(step) or []
                continue
            step.envelopes.append(env)
        else:
            raise DriveError(f"step {i}: expected 'user' or 'resume', got {list(raw)}")

        # Halts: the policy answers each one, or the step stops at the halt.
        while answer is not None and step.envelope is not None \
                and step.answered_halts < max_halts:
            halts = halt_frames(step.envelope)
            if not halts:
                break
            nxt = answer(halts, step.envelope)
            if nxt is None:
                break
            step.envelopes.append(nxt)
            step.answered_halts += 1

        last_env = step.envelope
        step.outcome = classify_turn(step.envelope) if step.envelope is not None else None
        _append_assistant(messages, step, history)
        trace.append(step)
        if on_step:
            queue[0:0] = on_step(step) or []
    return trace


def _default_resume(session_id: str, raw: dict, halt: dict | None) -> dict:
    r = raw["resume"]
    params: dict[str, Any] = {"session_id": session_id,
                              "decision": r.get("decision", "approve")}
    if r.get("id"):
        params[r.get("key", "card_id")] = r["id"]
    elif halt is not None:
        params[halt["key"]] = halt["value"]
    if r.get("value") is not None:
        params["value"] = r["value"]
    return params


def _append_assistant(messages: list[dict], step: TraceStep, history) -> None:
    """The assistant's reply goes back into the history the next turn sees.
    Per envelope (a step answered mid-way keeps each envelope's reply), or one
    reply per step when the caller's history policy summarises the step."""
    if callable(history):
        content = history(step)
        if content is not None:
            messages.append({"role": "assistant", "content": content})
        return
    for env in step.envelopes:
        if history == "blocks":
            summary = assistant_summary(env)
            if summary:
                messages.append({"role": "assistant", "content": summary})
        else:
            said = assistant_text(env)
            if said:
                messages.append({"role": "assistant", "content": said})
