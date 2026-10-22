"""Playbook runs: ``run_playbook``, ``resume_playbook``, ``list_module_playbooks``.

Mechanism only. ``run_playbook`` triggers a deployed FortiSOAR playbook through
pyfsr's typed :meth:`PlaybooksAPI.trigger` / ``trigger_action`` (name->uuid
resolve, POST, completion poll) on whichever live client is configured: the
crudhub loopback on-box, a ``.env`` pyfsr client off-box
(``_shared._live_client()``). A record-context playbook typically PAUSES on a
manual-input step; ``run_playbook`` surfaces that as an ``awaiting_input``
result carrying the run pk AND the paused step's form (its ``fields`` +
response ``options``), and ``resume_playbook`` continues it by picking a
response option and (optionally) submitting values for those fields.
``list_module_playbooks`` discovers what a module's Execute menu can run.

Policy belongs to the host, through ``_shared`` hooks:

  * ``set_playbook_run_gate`` -- may this run / resume proceed at all (the SOC
    assistant refuses an unattended run with no persona). No gate: permitted;
    the LLM path is still governed by tier 3 (an approval card).
  * ``set_playbook_run_annotator`` -- extra fields on a finished run's result
    (the SOC assistant flags a playbook outside the persona's allowlist).
  * ``llm.tools.set_run_playbook_auto_resolver`` -- which runs skip the card.

A human approval reaches the body inside :func:`approved_dispatch`, which the
gate is told about: an approval is authorization.
"""
from __future__ import annotations

import contextlib
import contextvars
import re
import time
from collections import OrderedDict
from typing import Any

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server._record_lookup import live_request, unknown_record
from fsr_playbooks.mcp_server._shared import mcp

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _jsonable(obj: Any) -> Any:
    """Coerce a pyfsr TriggerResponse / RunSummary (pydantic or dataclass) into a
    plain JSON-able dict, without assuming which model flavor pyfsr returns."""
    if obj is None or isinstance(obj, (str, int, float, bool, list, dict)):
        return obj
    for attr in ("model_dump", "dict", "_asdict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    try:
        import dataclasses
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
    except Exception:  # noqa: BLE001
        pass
    return getattr(obj, "__dict__", str(obj))


def _run_pk_of(run: Any) -> str:
    """Normalize a run reference to its bare pk. Accepts the pk itself ("2971")
    or the run ``@id`` (``/wf/api/workflows/2971/``). Returns "" if unparseable."""
    if isinstance(run, int):
        return str(run)
    if not isinstance(run, str) or not run.strip():
        return ""
    run = run.strip()
    if run.isdigit():
        return run
    segs = [s for s in run.split("/") if s]
    if segs and segs[-1].isdigit():
        return segs[-1]
    return ""


def _shape_field(v: dict) -> dict:
    """Shape one manual-input ``inputVariables`` entry into the compact field the
    widget card renders. Carries the render hint (``data_type`` -- ``dynamicList``,
    ``checkbox``, ``text`` ...) and, for a ``dynamicList``, the runtime-COMPUTED
    ``options``.

    Note: in the playbook *definition* a dynamicList's ``options`` is a Jinja
    template string (``{{vars....}}``); in the *retrieved* live manual input it has
    been rendered to the real array -- ``[{"value": <manager>, "options": [<device>,
    ...]}]``. We only forward ``options`` when it's a list (rendered), never the raw
    template string, so the card always has concrete choices or none."""
    field = {"name": v.get("name"),
             "label": v.get("label") or v.get("title"),
             "type": v.get("type"),
             "data_type": v.get("dataType") or v.get("formType"),
             "tooltip": v.get("tooltip") or v.get("description")}
    # Carry `required` through: the widget blocks submit on an unfilled required
    # control, and dropping the flag let an unanswered gate submit empty.
    if v.get("required") is not None:
        field["required"] = bool(v.get("required"))
    opts = v.get("options")
    if isinstance(opts, list) and opts:
        field["options"] = opts
    # Forward the field's default/prefill so the card seeds it -- FortiSOAR's native
    # Pending-Inputs panel shows these (a YAML default in a textarea, a pre-checked
    # checkbox); dropping them made our textareas blank and checkboxes unchecked.
    # The retrieved manual input carries the default in `value` (fallback `default`).
    default = v.get("value")
    if default is None:
        default = v.get("default")
    if default is not None:
        field["default"] = default
    return field


# manual_input_id -> the run pk it belongs to, for the last few gates this
# process surfaced. `awaiting_input` hands the model two bare ints side by side
# (`run_pk` and `awaiting.manual_input_id`) and the model has picked the wrong
# one live (resume_playbook(run='508') for run 9046 -> `not_awaiting`, an
# error that reads as "the run is finished" when the run was plainly parked).
# P2 doctrine: the gate belongs in dispatch, not in the prompt -- so we recognize
# the id here and name the confusion instead of relaying a misleading platform
# error. Bounded and in-memory: a miss just falls through to the old behavior.
_MANUAL_INPUT_RUNS: OrderedDict[str, str] = OrderedDict()
_MANUAL_INPUT_RUNS_CAP = 64


def _note_manual_input(mid: Any, run_pk: str) -> None:
    """Remember that ``mid`` identifies a manual-input FORM on run ``run_pk``."""
    if mid is None or not run_pk:
        return
    key = str(mid).strip()
    if not key:
        return
    _MANUAL_INPUT_RUNS.pop(key, None)
    _MANUAL_INPUT_RUNS[key] = str(run_pk)
    while len(_MANUAL_INPUT_RUNS) > _MANUAL_INPUT_RUNS_CAP:
        _MANUAL_INPUT_RUNS.popitem(last=False)


def _misused_manual_input_id(pk: str) -> str | None:
    """The run pk ``pk`` really belongs to, when ``pk`` is a manual_input_id we
    handed out rather than a run. None when it isn't one (or when it is ALSO a
    known run pk -- ids come from different tables and can collide, and refusing
    a valid resume would be worse than the error we're replacing)."""
    if not pk:
        return None
    key = str(pk).strip()
    owner = _MANUAL_INPUT_RUNS.get(key)
    if not owner or owner == key or key in set(_MANUAL_INPUT_RUNS.values()):
        return None
    return owner


def _pending_input(client: Any, playbooks: Any, run_pk: str) -> dict | None:
    """Fetch the manual-input a run (by pk) is paused on and shape a compact form
    summary: the fields to fill (``input.schema.inputVariables``) + the response
    options (Ok/Cancel ...). Best-effort -> None if nothing pending / unreachable.

    Run->pending join by pk: the ``manual-wf-input`` list's ``workflow`` field is an
    encrypted token (can't match by pk client-side), but the endpoint accepts a
    ``workflow=<pk>`` server-side filter -- the same join pyfsr's ``approval()``
    uses. Then ``retrieve_manual_input(id)`` returns the full prompt (schema +
    response_mapping)."""
    if not run_pk:
        return None
    try:
        resp = client.get("/api/wf/api/manual-wf-input/",
                          params={"workflow": run_pk, "format": "json",
                                  "ordering": "-id"})
        members = (resp.get("hydra:member") if isinstance(resp, dict)
                   else resp if isinstance(resp, list) else []) or []
        if not members:
            return None
        mid = members[0].get("id")
        full = _jsonable(playbooks.retrieve_manual_input(str(mid)))
    except Exception:  # noqa: BLE001 -- surfacing is best-effort; omit on any error
        return None
    if not isinstance(full, dict):
        return None
    schema = full.get("input") if isinstance(full.get("input"), dict) else {}
    schema = (schema or {}).get("schema") or {}
    fields = [_shape_field(v) for v in (schema.get("inputVariables") or [])
              if isinstance(v, dict)]
    options = [{"option": o.get("option"), "primary": bool(o.get("primary"))}
               for o in (full.get("response_mapping") or {}).get("options", [])
               if isinstance(o, dict)]
    _note_manual_input(mid, run_pk)
    out = {"manual_input_id": mid,
           "title": schema.get("title") or full.get("title"),
           "description": schema.get("description"),
           "is_approval": bool(full.get("is_approval")),
           "fields": fields,
           "options": options}
    # The gate's own DEADLINE. A manual_input step can carry a `timeout` (the
    # ZTPF metadata-source playbook sets ONE MINUTE), after which the platform
    # resolves the step down its timeout branch and the run moves on. Nothing
    # used to surface that, so the chat leg -- render card, analyst reads,
    # fills, submits -- routinely lost the race and the forward came back
    # `no_response_options` on a run that had already finished. The record
    # carries an absolute deadline, in the SAME call, so this costs nothing.
    expires_at = full.get("timeout")
    if expires_at:
        out["expires_at"] = expires_at
        secs = _seconds_until(expires_at)
        if secs is not None:
            out["expires_in_seconds"] = secs
    return out


def is_analyst_form(form: Any) -> bool:
    """A pause the analyst answers, not the agent: it has fields to fill, or
    two or more buttons to choose between (Ok / Save Example, Yes / No). A
    single button ("Ok", "Close") only acknowledges, and the agent may press it.
    The chat cards exactly these, and the agent loop stops acting on them."""
    if not isinstance(form, dict):
        return False
    if any(isinstance(f, dict) for f in (form.get("fields") or [])):
        return True
    return len([o for o in (form.get("options") or []) if isinstance(o, dict)]) >= 2


def _seconds_until(when: Any) -> int | None:
    """Whole seconds from now until an ISO-8601 UTC instant; negative once past.
    None when it can't be parsed -- never raises, never blocks a card."""
    if not when:
        return None
    try:
        from datetime import datetime, timezone
        s = str(when).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int((dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:  # noqa: BLE001
        return None


def _decision_to_option_label(options: list[dict], decision: str) -> str | None:
    """Map a resume ``decision`` to a response-option LABEL for pyfsr's
    ``manual_input.answer(option=...)``: ``approve`` -> the primary option, ``reject``
    -> the first non-primary, anything else -> treated as an explicit label."""
    d = (decision or "").strip().lower()
    if d == "approve":
        prim = next((o for o in options if o.get("primary")),
                    options[0] if options else None)
        return prim.get("option") if prim else None
    if d == "reject":
        nonprim = next((o for o in options if not o.get("primary")), None)
        return nonprim.get("option") if nonprim else None
    return decision or None


def _awaiting_or_slow(client: Any, playbooks: Any, playbook: str, pb_uuid: str,
                      timeout: int) -> dict[str, Any]:
    """After a followed record-action run fails to reach terminal within
    ``timeout``, read the newest run's pk/status (pyfsr ``execution_history``) and
    shape the seam: ``awaiting_input`` (paused on a manual-input step -> resumable
    via :func:`resume_playbook`, carrying ``run_pk``) vs ``not_finished_awaiting_
    or_slow`` (still running / unknown). Fail-open to the generic slow seam."""
    run_pk = None
    status = None
    try:
        hist = playbooks.execution_history(playbook_uuid=pb_uuid, limit=1)
        run0 = _jsonable(hist[0]) if hist else {}
        if isinstance(run0, dict):
            run_pk = run0.get("pk") or run0.get("id")
            status = (run0.get("status") or "").lower()
    except Exception:  # noqa: BLE001 -- best effort; fall through to the slow seam
        pass
    if status == "awaiting":
        rpk = str(run_pk) if run_pk else None
        # The `manual-wf-input` record can lag the run reaching the manual_input
        # step by a beat: `execution_history` already reads "awaiting" while the
        # form isn't queryable yet. A single `_pending_input` call then misses it,
        # so `awaiting` is omitted and the caller can't synthesize the in-chat
        # manual_input CARD (`_manual_input_card_from_awaiting` needs `.fields`) --
        # the widget shows a plain text ask instead of a fillable form. Poll
        # briefly so the form is reliably attached. Stops as soon as the record
        # materializes (a form gate OR a bare approval gate), so it adds no
        # latency once present.
        form = None
        if rpk:
            for _attempt in range(8):
                form = _pending_input(client, playbooks, rpk)
                if form:
                    break
                time.sleep(1)
        out = {"ok": False, "code": "awaiting_input", "playbook": playbook,
               "triggered": True, "run_pk": rpk, "status": "awaiting",
               "message": (f"{playbook!r} paused awaiting manual input. Resume it "
                           f"with resume_playbook(run={rpk!r}, "
                           f"decision='approve'|'reject' or an option label, and "
                           f"inputs={{field: value}} for any fields below).")}
        if form:
            # The form the run is waiting on: `fields` are the values to collect
            # (submit via resume_playbook inputs=), `options` are the buttons.
            out["awaiting"] = form
        return out
    return {"ok": False, "code": "not_finished_awaiting_or_slow",
            "playbook": playbook, "triggered": True,
            "run_pk": str(run_pk) if run_pk else None,
            "message": (f"{playbook!r} was triggered but did not finish within "
                        f"{timeout}s (status {status or 'unknown'!r}) -- still "
                        f"running or paused.")}


# How long an UNFOLLOWED trigger still watches for the run to park. See
# `_park_probe` -- small enough that `follow=False` keeps meaning "don't wait for
# this run", big enough that a manual-input gate (which materializes in about a
# second) is never missed.
_PARK_PROBE_SECONDS = 10


def _pb_uuid(playbooks: Any, playbook: str) -> str | None:
    """``playbook`` as a uuid (resolving a name), or None if it can't be read."""
    try:
        if _UUID_RE.match(playbook):
            return playbook
        return playbooks._resolve_uuid(playbook) or None
    except Exception:  # noqa: BLE001 -- best effort; caller degrades gracefully
        return None


def _park_probe(client: Any, playbooks: Any, playbook: str,
                pb_uuid: str | None) -> dict[str, Any] | None:
    """Watch an unfollowed run briefly and shape the ``awaiting_input`` seam if it
    PARKS; return ``None`` in every other case so the caller's normal
    "triggered, didn't wait" outcome stands.

    Why this exists, and why it is dispatch rather than a docstring. `follow`
    defaults to True, but the agent can pass ``follow=False`` -- and a live
    model did exactly that for the *Manual Input Demo - Collect Note* demo
    arc. The unfollowed branch returned ``{"triggered": True}`` and stopped, so
    the run parked on a manual-input gate that this turn never learned about: no
    ``awaiting_input``, no ``manual_input`` card, and an approval card that
    truthfully reported "Approved and executed" because ``ok`` really was true.
    Every layer behaved as written and the analyst still got no form -- the arc's
    whole visible behaviour hung on one model-supplied argument.

    A parked run is not a run you can decline to wait for: nobody else is coming
    to answer its gate. So the park is detected regardless of what was asked for.
    ``follow=False`` still means what it says for every other outcome -- a run
    that is merely slow, or that finishes inside the probe window, is reported
    exactly as before.
    """
    if not pb_uuid:
        return None
    try:
        _run, reason = _wait_run_or_awaiting(playbooks, pb_uuid,
                                             _PARK_PROBE_SECONDS, poll_interval=1)
    except Exception:  # noqa: BLE001 -- a probe must never sink a successful trigger
        return None
    if reason != "awaiting":
        return None
    return _awaiting_or_slow(client, playbooks, playbook, pb_uuid,
                             _PARK_PROBE_SECONDS)


# Statuses that END the initial trigger wait as a completed run. `awaiting` is
# deliberately NOT here -- a run paused on a manual-input gate has its form ready
# immediately, so we settle on `awaiting` separately (see `_wait_run_or_awaiting`)
# rather than blocking out the full timeout the way pyfsr's `wait_for_run` does.
_RUN_WAIT_TERMINAL = frozenset({"finished", "failed", "error", "cancelled",
                                "aborted"})


def _wait_run_or_awaiting(playbooks: Any, pb_uuid: str, timeout: int,
                          poll_interval: float = 3) -> tuple[dict | None, str]:
    """Poll the newest run of ``pb_uuid`` until it reaches a terminal status OR
    pauses on a manual-input gate (``awaiting``), whichever comes first.

    Returns ``(run, reason)`` -- ``reason`` is ``"terminal"`` (``run`` is the shaped
    completion), ``"awaiting"`` (the run paused; caller surfaces the resumable
    seam), or ``"timeout"`` (neither within ``timeout``; ``run`` is the last read
    or ``None``).

    Why not pyfsr's :meth:`wait_for_run`: its terminal set excludes ``awaiting``,
    so a run that pauses on a manual-input step within seconds keeps it blocking
    for the *entire* ``timeout`` before it raises -- the analyst stares at a
    spinner for up to ``timeout`` seconds even though the input form is ready at
    once. Settling on ``awaiting`` too makes the form appear as soon as the run
    pauses; a genuinely slow (still-running) run is the only case that waits out
    the timeout, exactly as before.
    """
    deadline = time.monotonic() + max(0, timeout)
    last: dict | None = None
    while True:
        try:
            hist = playbooks.execution_history(playbook_uuid=pb_uuid, limit=1)
            if hist:
                last = _jsonable(hist[0])
        except Exception:  # noqa: BLE001 -- best effort; retry until the deadline
            pass
        status = (last.get("status") or "").lower() if isinstance(last, dict) else ""
        if status in _RUN_WAIT_TERMINAL:
            return last, "terminal"
        if status == "awaiting":
            return last, "awaiting"
        if time.monotonic() >= deadline:
            return last, "timeout"
        time.sleep(poll_interval)


# Run statuses that keep the post-resume poll ALIVE -- the run is still moving
# toward its next gate (or terminus). Anything else (awaiting, terminal, unknown,
# None) settles the poll immediately: we only wait through the transient window
# between accepting a resume and the next step materializing. FortiSOAR 8.0
# reports a resumed, still-running workflow as `active`; without it the poll
# settled at once and the model told the analyst the run "ended with status
# active" while it was seconds from its next pause.
_TRANSIENT_STATUSES = {"running", "executing", "queued", "awaiting_execution",
                       "in_progress", "pending", "active"}


_REAWAIT_CAP_S = 45


def _reawait_after_resume(client: Any, playbooks: Any, run_pk: str, timeout: int,
                          answered: Any = None) -> tuple[dict | None, str | None]:
    """After a resume is accepted, poll briefly for the run to settle, and if it
    PAUSED AGAIN on a fillable manual-input step, shape the next form.

    Returns ``(form, status)``: ``form`` is the pending-input summary (fields +
    options, via :func:`_pending_input`) when the run is waiting on a NEW
    manual_input gate -- so ``resume_playbook`` can re-emit the same
    ``awaiting_input`` seam it returned for the first gate and a CHAIN of gates
    keeps surfacing a form instead of dead-ending after the first submit. ``form``
    is None when the run finished or is still running; a buttons-only pause is
    returned too (:func:`is_analyst_form` says which pauses the analyst answers).
    ``status`` is the last read.

    Only a *transient* (still-running) status keeps the loop alive -- an
    ``awaiting`` with no fillable form (a button-only/approval gate the model
    resumes itself), a terminal status, or an unknown/absent status all settle
    immediately. The resume is asynchronous, so this rides out the short window
    between accepting the resume and the next gate materializing (~2s cadence,
    capped at ``_REAWAIT_CAP_S``, independent of the larger resume ``timeout``).

    ``answered`` is the manual-input id the caller just answered. The resume is
    asynchronous, so the first reads still show the run ``awaiting`` on THAT
    pause, or ``awaiting`` with no pending form once it is consumed. Live, that
    stale read settled the wait on its first poll and the run's next pause
    ("Data Collected", ~12s later) never surfaced. With ``answered`` set, both
    count as still running."""
    iters = max(1, min(int(timeout or 0), _REAWAIT_CAP_S) // 2)
    status = None
    for i in range(iters + 1):
        try:
            run_now = _jsonable(playbooks.get_execution(run_pk))
            status = (run_now.get("status") if isinstance(run_now, dict) else None)
        except Exception:  # noqa: BLE001 -- status read is best-effort
            status = None
        low = (status or "").lower()
        if low == "awaiting":
            # Every pause comes back, buttons-only included: a results gate
            # ("Data Collected", Ok / Save Example) carries the run's output in
            # its description, and dropping it left the agent saying "the run
            # continued" with the answer sitting unread on the box.
            form = _pending_input(client, playbooks, run_pk)
            stale = answered is not None and (
                not form or str(form.get("manual_input_id")) == str(answered))
            if not stale:
                return (form or None), status
        elif low not in _TRANSIENT_STATUSES:
            # terminal / unknown / absent -- nothing more to wait for.
            return None, status
        if i < iters:
            time.sleep(2)
    return None, status


def _action_route_of(playbooks: Any, playbook: str) -> dict[str, Any] | None:
    """The record-action trigger of ``playbook`` (``{playbook_uuid, route,
    resources}``), or ``None`` when it isn't a record-action playbook.

    Split out of :func:`_record_action_trigger` so the "does this playbook NEED
    a record?" question can be asked BEFORE we have one -- firing a record-action
    playbook down the recordless ``notrigger`` route is a guaranteed failure
    (see that function's docstring), so it has to be refused up front rather
    than discovered from a dead run.
    """
    try:
        pb_uuid = playbook if _UUID_RE.match(playbook) else playbooks._resolve_uuid(playbook)
        if not pb_uuid:
            return None
        defn = playbooks.get_definition(pb_uuid, relationships=True)
    except Exception:  # noqa: BLE001 -- lookup best-effort; fall back to manual
        return None
    steps = (defn.get("steps") if hasattr(defn, "get") else None) or []
    for s in steps:
        st = s.get("stepType") if isinstance(s, dict) else None
        name = st.get("name") if isinstance(st, dict) else None
        args = s.get("arguments") if isinstance(s, dict) else None
        route = args.get("route") if isinstance(args, dict) else None
        if name == "cybersponse.action" and route:
            resources = args.get("resources") if isinstance(args, dict) else None
            form = args.get("inputVariables") if isinstance(args, dict) else None
            return {"playbook_uuid": pb_uuid, "route": route,
                    "resources": resources if isinstance(resources, list) else [],
                    "input_variables": [v for v in (form or []) if isinstance(v, dict)]}
    return None


_INT_TYPES = frozenset({"integer", "int"})
_NUM_TYPES = frozenset({"decimal", "float", "number"})
_BOOL_TYPES = frozenset({"checkbox", "boolean", "bool"})


def _trigger_form(inputs: dict | None,
                  declared: list[dict]) -> tuple[dict, dict | None]:
    """The record-action trigger's form values, typed as the trigger declares.

    The Execute dialog posts its fields at the TOP level of the trigger body, and
    the playbook reads them as ``vars.request.data["<name>"]``. ``inputs`` used to
    be dropped on this route entirely, so "Move Step Number" ran with no
    ``newStepNumber``, failed half way, and left a profile renumbered to -1..-7.
    The dialog also sends an integer field as a number; a model sends "2", which
    the playbook's ``new_step < 1`` then refuses. So: coerce by the declared type,
    and refuse an unknown name, an unconvertible value or a missing required
    field before anything runs, naming the fields the form has.
    """
    fields = {str(v.get("name")): v for v in declared if v.get("name")}
    names = ", ".join(f"{n} ({(v.get('type') or v.get('dataType') or 'text')}"
                      f"{', required' if v.get('required') else ''})"
                      for n, v in fields.items()) or "none"
    out: dict[str, Any] = {}
    for k, val in (inputs or {}).items():
        spec = fields.get(str(k))
        if spec is None:
            return {}, {"ok": False, "code": "unknown_input", "triggered": False,
                        "message": f"this playbook's run form has no field {k!r}; "
                                   f"its fields are: {names}. Nothing was run."}
        kind = str(spec.get("type") or spec.get("dataType") or "").lower()
        try:
            if kind in _INT_TYPES and not isinstance(val, bool):
                f = float(val)
                if f != int(f):
                    raise ValueError
                val = int(f)
            elif kind in _NUM_TYPES and not isinstance(val, bool):
                val = float(val)
            elif kind in _BOOL_TYPES and isinstance(val, str):
                low = val.strip().lower()
                if low not in ("true", "false"):
                    raise ValueError
                val = low == "true"
        except (TypeError, ValueError):
            return {}, {"ok": False, "code": "bad_input", "triggered": False,
                        "message": f"{k!r} takes a {kind} value; {val!r} is not one. "
                                   f"Fields: {names}. Nothing was run."}
        out[str(k)] = val
    missing = [n for n, v in fields.items()
               if v.get("required") and _is_blank(out.get(n))]
    if missing:
        return {}, {"ok": False, "code": "missing_input", "triggered": False,
                    "message": f"this playbook's run form requires {', '.join(missing)}; "
                               f"pass inputs={{...}}. Fields: {names}. Nothing was run."}
    return out, None


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _record_action_trigger(playbooks: Any, playbook: str,
                           record: str) -> dict[str, Any] | None:
    """If ``playbook`` fires from a *record-action* trigger (``cybersponse.action``
    -- the "Execute" list on a selected record) and a ``record`` IRI is supplied,
    return the kwargs for :meth:`PlaybooksAPI.trigger_action`; else ``None`` (use
    the manual ``notrigger`` route via :meth:`trigger`).

    Why: the manual ``notrigger`` route does NOT populate ``vars.input.records`` --
    a playbook whose Jinja reads ``input.records[0]`` (typical for record-context
    validation playbooks) fails ``list object has no element 0`` when fired that
    way. The ``/api/triggers/1/action/<route>`` route builds ``input.records`` from
    the selected record, which is what those playbooks expect.
    """
    if not record:
        return None
    parts = [p for p in record.split("/") if p]
    if len(parts) < 2:
        return None
    module, record_uuid = parts[-2], parts[-1]
    if not _UUID_RE.match(record_uuid):
        return None
    act = _action_route_of(playbooks, playbook)
    if not act:
        return None
    return {"route_uuid": act["route"], "module": module,
            "record_uuid": record_uuid, "playbook_uuid": act["playbook_uuid"],
            "input_variables": act.get("input_variables") or []}


def _run_failure_detail(playbooks: Any, run: Any) -> dict[str, Any] | None:
    """Why a run failed: ``{failing_step, error_message, pk}`` -- or ``None``.

    The run body returned by the trigger/poll path is shaped from the run LIST,
    whose ``error_message`` is always null; the real message and the failing
    step come from the step-detail fetch, read through the one run-failure
    implementation (``fsr_playbooks.run_failure``).
    """
    from fsr_playbooks.run_failure import failure_of, run_pk_of

    pk = run_pk_of(run)
    failure = failure_of(playbooks, pk=pk) if pk else None
    if not failure or not (failure["failing_step"] or failure["error_message"]):
        return None
    return {"failing_step": failure["failing_step"],
            "error_message": failure["error_message"], "pk": str(pk)}


_APPROVED_DISPATCH: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "fsrpb_approved_dispatch", default=False)


@contextlib.contextmanager
def approved_dispatch():
    """Mark the enclosed dispatch as one a human explicitly approved.

    Set by the host's approved-card path around the tool call it makes after
    the analyst clicks approve. A ContextVar rather than a tool parameter
    because FastMCP rejects any parameter starting with ``_``, and a public
    ``approved=`` argument would be model-settable -- the model could then
    approve its own runs, which is exactly what the HITL gate exists to
    prevent. Only the resume path, which the model cannot reach, can set this.
    """
    token = _APPROVED_DISPATCH.set(True)
    try:
        yield
    finally:
        _APPROVED_DISPATCH.reset(token)


def approved_dispatch_active() -> bool:
    """True while inside :func:`approved_dispatch`."""
    return bool(_APPROVED_DISPATCH.get())


# A record IRI's module and uuid are interpolated into request URLs, so only
# plain identifiers pass: a '/', '?' or '..' is refused before any lookup.
_IDENT_RE = re.compile(r"[A-Za-z0-9_]+")
_RECORD_UUID_RE = re.compile(r"[A-Za-z0-9-]+")


def _record_parts(record: str) -> tuple[str, str] | None:
    """``(module, uuid)`` of a plain ``/api/3/<module>/<uuid>`` IRI, else None."""
    parts = record.strip().split("/")
    if (len(parts) != 5 or parts[0] or parts[1:3] != ["api", "3"]
            or not _IDENT_RE.fullmatch(parts[3])
            or not _RECORD_UUID_RE.fullmatch(parts[4])):
        return None
    return parts[3], parts[4]


def _bad_record(record: str) -> dict[str, Any] | None:
    """A refusal when a non-empty ``record`` is not a plain record IRI."""
    if not record or _record_parts(record) is not None:
        return None
    return {"ok": False, "code": "bad_record", "record": record, "triggered": False,
            "message": (f"{record!r} is not a record IRI; pass it as "
                        "'/api/3/<module>/<uuid>' (letters, digits, '_' in the "
                        "module; letters, digits, '-' in the uuid). Nothing was run.")}


def _workflow_by_name(client: Any, playbook: str) -> dict | None:
    """The workflow record matching ``playbook`` exactly by name (or ``None``).

    One call that yields BOTH identity and state (`uuid` + `isActive`), which is
    what the pre-card check needs: pyfsr's ``_resolve_uuid`` answers only "does a
    name resolve", and a deactivated playbook resolves fine yet cannot run.
    Raises on transport/HTTP trouble -- the caller distinguishes "the box says no
    such playbook" (a clean empty result) from "the box didn't answer".
    """
    from urllib.parse import urlencode
    qs = urlencode({"name": playbook, "$limit": 5})
    resp = client.get(f"/api/3/workflows?{qs}")
    members = (resp.get("hydra:member") if isinstance(resp, dict) else None) or []
    for m in members:
        if _field_of(m, "name") == playbook:
            return m
    return members[0] if members else None


def _field_of(obj: Any, name: str) -> Any:
    """Read ``name`` off a crudhub row whether it arrived as a dict or a typed
    pyfsr model. ``playbooks.get_definition`` returns a ``Workflow`` object while
    the raw ``?name=`` lookup returns dicts -- an ``isinstance(x, dict)`` check
    silently skipped the model path, so a deactivated playbook referenced BY UUID
    sailed through the pre-card check (caught only by probing a live box; the
    offline stub returned dicts for both)."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def precard_validate(args: dict) -> dict | None:
    """Pre-card hook for `run_playbook`: the playbook must exist and be active
    (`_precard_playbook`), and a `record` it names must exist
    (`_precard_record`). Either refusal happens before an approval card."""
    return _precard_playbook(args) or _precard_record(args)


def _precard_record(args: dict) -> dict | None:
    """HARDEN-4: an invented `record` IRI used to card, be approved, and fail
    inside the run. A `record` that is not a plain `/api/3/<module>/<uuid>` IRI
    is refused outright (its parts reach request URLs); a well-formed one is
    refused only on a clean 404. Fail-open otherwise, like the playbook check."""
    record = (args or {}).get("record")
    if not isinstance(record, str) or not record.strip():
        return None
    bad = _bad_record(record)
    if bad is not None:
        return bad
    module, uuid = _record_parts(record)
    return unknown_record(_shared._live_client(), module, uuid,
                          active_iri=_shared.active_record_iri())


def _precard_playbook(args: dict) -> dict | None:
    """Framework pre-card hook: refuse a `run_playbook` that CANNOT run, before
    it becomes an approval card.

    Why this is a gate concern and not a prompt concern: a tier-3 call is
    suspended into a card *without* the tool body running, so an invented name
    was never resolved -- it reached the analyst looking legitimate and could only
    fail after approval. Live, a ztpf session carded
    ``run_playbook("Create Next SingleLo Interface")``: that is a *step label*,
    not a playbook, and the persona's own rule ("never invent a playbook name --
    discover it first") had already been ignored. Bouncing here hands the model
    the real candidate list instead, which it can act on unaided.

    Two refusals, both un-runnable by construction:
      * the name/uuid resolves to nothing -> ``unknown_playbook``;
      * it resolves but is deactivated -> ``playbook_inactive`` (absent from the
        real Execute menu; a trigger on it cannot succeed).

    **Fail-open**, in the exact shape the framework requires: we refuse ONLY on a
    successful lookup that came back empty. No client, no playbooks API, or any
    exception ⇒ ``None`` (card as before) -- refusing a legitimate run because the
    box blinked is worse than carding a doomed one.
    """
    playbook = ((args or {}).get("playbook") or "").strip()
    if not playbook:
        return None  # the arg gate owns "missing playbook"

    client = _shared._live_client()
    if client is None:
        return None

    # Every lookup below is wrapped: the framework hook also swallows, but a
    # validator that owns its own fail-open is the one whose contract can be
    # tested directly -- and "the box blinked" must never read as "no such
    # playbook", which is the one way this check could do damage.
    if _UUID_RE.match(playbook):
        # A uuid is already resolved identity; only liveness is worth checking,
        # and get_definition is the cheapest truthful probe.
        playbooks = getattr(client, "playbooks", None)
        if playbooks is None:
            return None
        try:
            defn = playbooks.get_definition(playbook)
        except Exception:  # noqa: BLE001 -- unreachable ⇒ card as before
            return None
        if defn is not None and _field_of(defn, "isActive") is False:
            return _inactive_error(_field_of(defn, "name") or playbook)
        return None

    try:
        wf = _workflow_by_name(client, playbook)
    except Exception:  # noqa: BLE001 -- the lookup didn't answer; do NOT refuse
        return None
    if wf is not None:
        if _field_of(wf, "isActive") is False:
            return _inactive_error(_field_of(wf, "name") or playbook)
        return None

    # The lookup SUCCEEDED and matched nothing -- the name does not exist.
    return {
        "ok": False,
        "code": "unknown_playbook",
        "playbook": playbook,
        "message": (
            f"no playbook named {playbook!r} exists -- nothing was run and no "
            "approval was requested. Do NOT retry with a guessed variation: "
            "call `list_module_playbooks` and use a name it returns. (A record's "
            "automation-step label is not a playbook name.)"),
        "candidates": _runnable_candidates(),
    }


def _inactive_error(name: str) -> dict[str, Any]:
    return {
        "ok": False,
        "code": "playbook_inactive",
        "playbook": name,
        "message": (
            f"playbook {name!r} is deactivated -- it is absent from the record "
            "Execute menu and cannot be triggered. Nothing was run. Pick an "
            "active playbook from `list_module_playbooks`."),
        "candidates": _runnable_candidates(),
    }


def _runnable_candidates(limit: int = 12) -> list[str]:
    """Names of the playbooks actually runnable on the mounted module, for the
    refusal message. Best-effort -- an empty list just means the model must call
    `list_module_playbooks` itself, which the message already tells it to do."""
    try:
        listed = list_module_playbooks()
        if not (isinstance(listed, dict) and listed.get("ok")):
            return []
        return [p["name"] for p in (listed.get("playbooks") or [])
                if isinstance(p, dict) and p.get("name")][:limit]
    except Exception:  # noqa: BLE001 -- a suggestion list is a bonus, never a blocker
        return []


def _run_playbook_impl(playbook: str = "",
                 record: str = "",
                 inputs: dict | None = None,
                 follow: bool = True,
                 timeout: int = 180) -> dict[str, Any]:
    """Trigger a deployed FortiSOAR playbook and (by default) wait for it to
    finish.

    The intended use is *validation*: after editing a metadata-source script (or
    similar), run the persona's designated validation playbook -- e.g.
    *Get Metadata Source Data on Device* -- against a device to prove the script
    actually returns data before saving.

    Gated by approval, not refusal: a run is surfaced as an approval card
    unless the host designates the playbook auto-runnable (the SOC assistant:
    the persona's ``run_playbook.auto`` subset).

    Args:
      playbook: playbook name or uuid to trigger (must have a manual trigger).
      record: optional record IRI to pass as the selected record
        (e.g. ``/api/3/ztpf_devices/<uuid>``); the validation playbook reads it.
      inputs: optional manual-input field values for the trigger.
      follow: when true (default), block until the run reaches a terminal status
        and return the shaped run; when false, return once triggered.
      timeout: seconds to wait for completion when ``follow`` is true.

    Returns: ``{ok, playbook, triggered, run}`` on success (``run`` is the shaped
      completion when followed), else ``{ok: false, code, message}`` --
      ``run_not_permitted`` when the host's policy refuses the run,
      ``bad_record`` when ``record`` is not a plain record IRI, or
      ``record_required`` when it runs against a selected record and none is
      bound (pass ``record=``; firing it recordless cannot succeed).
      A followed run that did NOT finish also carries ``failure:
      {failing_step, error_message, pk}`` -- report that reason, don't just say
      the run failed.
    """
    if not playbook or not isinstance(playbook, str):
        return {"ok": False, "code": "missing_playbook",
                "message": "run_playbook requires a playbook name or uuid"}
    gate = _shared.playbook_run_gate(playbook, approved_dispatch_active())
    if gate is not None:
        return gate
    bad = _bad_record(record or "")
    if bad is not None:
        return {**bad, "playbook": playbook}
    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured to run playbooks"}
    playbooks = getattr(client, "playbooks", None)
    if playbooks is None:
        return {"ok": False, "code": "no_playbooks_api",
                "message": ("the live client has no typed playbooks API "
                            "(pyfsr PlaybooksAPI not attached)")}
    # Default the selected record to the one the turn is mounted on. A record-
    # action validation playbook (e.g. "Get Metadata Source Data on Device")
    # fails when fired with no record -- the agent said "run it" about the record
    # on screen but didn't restate its IRI. Fall back to the mounted entity so
    # "validate this" just works. An explicit `record` arg always wins.
    if not record:
        record = _shared.active_record_iri() or ""
        if _bad_record(record) is not None:
            record = ""  # an unusable mounted IRI is no selection at all

    # A record-context validation playbook fires from a record-ACTION trigger; the
    # manual `notrigger` route wouldn't populate `input.records[0]` it reads. Route
    # those through `/triggers/1/action/<route>` (module + record_uuid) so the
    # selected record actually reaches the run. Manual playbooks fall through.
    if record:
        action = _record_action_trigger(playbooks, playbook, record)
    else:
        # No record in hand. If this playbook fires from a record-action trigger
        # it reads `vars.input.records[0]`, and the recordless `notrigger` route
        # leaves that empty -- the run dies with "list object has no element 0"
        # (observed 3x live: "Validate this metadata source..." -> run pk 6800,
        # `env.input.records: []`). Refuse with the module to select instead of
        # firing a run that cannot succeed.
        act = _action_route_of(playbooks, playbook)
        if act:
            mods = act.get("resources") or []
            return {"ok": False, "code": "record_required",
                    "playbook": playbook, "triggered": False,
                    "modules": mods,
                    "message": (
                        f"{playbook!r} runs against a selected record and no "
                        "record is bound to this conversation, so it would fail "
                        "reading `input.records[0]`. Pass the record IRI, e.g. "
                        "run_playbook(playbook=..., record='/api/3/"
                        f"{(mods[0] if mods else '<module>')}/<uuid>') -- find one "
                        "with search_module_records"
                        + (f"(module={mods[0]!r})" if mods else "") + ".")}
        action = None
    form: dict = {}
    if action:
        form, bad = _trigger_form(inputs, action.get("input_variables") or [])
        if bad is not None:
            return {**bad, "playbook": playbook}
    try:
        if action:
            playbooks.trigger_action(
                action["route_uuid"],
                module=action["module"],
                record_uuid=action["record_uuid"],
                playbook_uuid=action["playbook_uuid"],
                env=form or None,
            )
            if not follow:
                parked = _park_probe(client, playbooks, playbook,
                                     action["playbook_uuid"])
                if parked is not None:
                    return parked
                result = {"triggered": True}
            else:
                # The /action/ route's task_id does NOT correlate via log_list, so
                # follow by playbook instead -- poll the newest run. A run PAUSED on
                # a manual-input step never reaches terminal; we settle on `awaiting`
                # the instant it pauses (its input form is ready immediately) and
                # surface the resumable `awaiting_input` seam, instead of blocking
                # the whole timeout the way pyfsr's wait_for_run would.
                pb_uuid = action["playbook_uuid"]
                run0, reason = _wait_run_or_awaiting(playbooks, pb_uuid, timeout)
                if reason == "terminal":
                    result = run0
                else:
                    # `awaiting` (paused on a manual-input gate) or still running
                    # after `timeout` -- shape the resumable/slow seam.
                    return _awaiting_or_slow(client, playbooks, playbook, pb_uuid,
                                             timeout)
        else:
            result = playbooks.trigger(
                playbook,
                records=(record or None),
                inputs=(inputs or None),
                follow=bool(follow),
                timeout=timeout,
            )
            if not follow:
                # Same reasoning as the record-action branch above: a manual
                # playbook can park on a manual_input step too, and an unfollowed
                # trigger would leave that gate unreachable from chat.
                parked = _park_probe(client, playbooks, playbook,
                                     _pb_uuid(playbooks, playbook))
                if parked is not None:
                    return parked
    except ValueError as exc:  # not found / bad trigger response
        return {"ok": False, "code": "not_triggerable",
                "message": str(exc), "playbook": playbook}
    except TimeoutError as exc:
        # Manual (`trigger` follow) path timed out. The common benign cause is a
        # playbook PAUSED on a mid-run `manual_input` step -- waiting for a human,
        # not failed. pyfsr's terminal set excludes `awaiting`, so it raises here
        # for a parked run exactly as it does for a slow one, and the two look
        # identical from this frame.
        #
        # READ THE RUN before shaping the outcome. Saying "may be paused ... or
        # still running" is the same defect `_park_probe` exists for, one branch
        # over: the gate really is open, its form really is ready, and the reply
        # neither carries the fields nor a `run_pk` to resume -- so the analyst
        # cannot answer it and nobody else is coming to. Found by the argument-
        # space matrix in tests/test_tools_playbook_properties.py (the
        # manual/follow=True/parked cells), which is the whole argument for
        # testing the cross product: the 0.5.100 fix covered `follow=False` and
        # stopped at the branch the author was looking at.
        pb_uuid_now = _pb_uuid(playbooks, playbook)
        if pb_uuid_now:
            try:
                return _awaiting_or_slow(client, playbooks, playbook,
                                         pb_uuid_now, timeout)
            except Exception:  # noqa: BLE001 -- never sink a real trigger
                pass
        return {"ok": False, "code": "not_finished_awaiting_or_slow",
                "playbook": playbook, "triggered": True,
                "message": (f"{playbook!r} was triggered but did not finish within "
                            f"{timeout}s -- it may be paused on a manual-input step "
                            f"or still running. ({exc})")}
    except Exception as exc:  # noqa: BLE001 -- transport/other
        return {"ok": False, "code": "trigger_error",
                "message": f"triggering {playbook!r} failed: {exc}",
                "playbook": playbook}

    run = _jsonable(result)
    status = run.get("status") if isinstance(run, dict) else None
    # When we didn't wait, "triggered" is the whole outcome. When we did, a run
    # is a success only if it reached `finished` (or pyfsr already set ok=True);
    # any other terminal status (failed/finished_with_error/...) is ok=False so the
    # agent sees the validation didn't pass.
    if not follow:
        ran_ok = True
    elif isinstance(run, dict):
        ran_ok = bool(run.get("ok")) or status == "finished"
    else:
        ran_ok = True
    out = {"ok": ran_ok, "playbook": playbook, "triggered": True,
           "followed": bool(follow), "status": status, "run": run}
    if not ran_ok and follow:
        # A followed run that didn't finish is the ONE case where the agent has
        # to explain itself, and the run LIST body it was shaped from carries
        # `error_message: null` -- the populated message and the failing step
        # live only on the step-detail fetch. Without this the agent could only
        # say "it failed" (3 live sessions did exactly that). Best-effort:
        # a diagnosis lookup must never turn a failure report into an exception.
        why = _run_failure_detail(playbooks, run)
        if why:
            out["failure"] = why
    # Host annotations (the SOC assistant flags a playbook outside the
    # persona's advisory allowlist, for the audit trail and the summary).
    for k, v in _shared.playbook_run_annotations(playbook).items():
        out.setdefault(k, v)
    return out


def _record_label(client: Any, iri: str) -> str | None:
    """The name (or title / subject) of the record at ``iri``; None if unreadable."""
    try:
        r = live_request("get", client, f"{getattr(client, 'base_url', '') or ''}{iri}")
        rec = r.json() if getattr(r, "status_code", None) == 200 else {}
    except Exception:  # noqa: BLE001 -- a label is a courtesy, never a failure
        return None
    for k in ("name", "title", "subject"):
        if isinstance(rec, dict) and isinstance(rec.get(k), str) and rec[k].strip():
            return rec[k]
    return None


def run_playbook(playbook: str = "",
                 record: str = "",
                 inputs: dict | None = None,
                 follow: bool = True,
                 timeout: int = 180) -> dict[str, Any]:
    out = _run_playbook_impl(playbook=playbook, record=record, inputs=inputs,
                             follow=follow, timeout=timeout)
    # Which record the run actually got, by name. Live, the analyst asked to
    # render a template the chat had just created; the model passed the record
    # on screen instead, and reported that output as the new template's. The
    # result held only an IRI, so nothing showed the mismatch. With the name
    # here, the model can see it ran on a different record.
    target = record or _shared.active_record_iri() or ""
    if (isinstance(out, dict) and out.get("triggered")
            and _record_parts(target) is not None and "ran_on" not in out):
        client = _shared._live_client()
        name = _record_label(client, target) if client is not None else None
        out["ran_on"] = {"iri": target, "name": name}
    return out


run_playbook.__doc__ = _run_playbook_impl.__doc__
run_playbook = mcp.tool()(run_playbook)


@mcp.tool()
def resume_playbook(run: str = "",
                    decision: str = "approve",
                    inputs: dict | None = None,
                    follow: bool = True,
                    timeout: int = 180) -> dict[str, Any]:
    """Resume a playbook run that PAUSED on a manual-input / approval step.

    When ``run_playbook`` returns ``code: "awaiting_input"`` (with a ``run_pk`` and
    an ``awaiting`` form block), the run stopped on a ``manual_input`` step waiting
    for a human -- e.g. the *Get Metadata Source Data on Device* validation playbook
    pauses to have a device selected. This picks one of the step's response options
    and (optionally) submits values for the step's fields, driving the run onward.

    Backed by pyfsr's typed manual-input API: a button-only choice goes through
    :meth:`PlaybooksAPI.approval`; when ``inputs`` are supplied they are submitted
    via :meth:`ManualInputAPI.answer` (fills the fields + picks the option +
    resumes via ``wfinput_resume`` in one call).

    Args:
      run: the paused run's pk (the ``run_pk`` from run_playbook's awaiting
        result), or its ``@id`` (``/wf/api/workflows/<pk>/``).
      decision: which response option to pick -- ``"approve"`` (default -> the
        primary option, e.g. "Ok"), ``"reject"`` (first non-primary, e.g.
        "Cancel"), or an exact option label.
      inputs: values for the step's fields, keyed by the field ``name`` from the
        awaiting form (``awaiting.fields[].name``), e.g.
        ``{"managerAndDevice": [...]}``. Omit for a button-only / approval step.
      follow: when true (default), read back the run's status after resuming.
      timeout: reserved for follow polling (currently a single status read).

    Returns: ``{ok, run_pk, resumed, ack, status}`` -- ``ack`` is pyfsr's resume
      acknowledgement (task_id + message); ``status`` is the run's status right
      after the async resume was accepted. On failure ``{ok: false, code, ...}``:
      ``resume_not_permitted`` (host policy), ``missing_run``, ``not_awaiting``
      (nothing pending / already finished / legacy approval step), ``bad_decision``
      (option label matched nothing), or ``resume_error``.
    """
    # Same host policy as run_playbook, asked about a resume: an approved resume
    # is authorized whatever the policy says about unattended ones.
    gate = _shared.playbook_run_gate("", approved_dispatch_active(), action="resume")
    if gate is not None:
        return gate
    run_pk = _run_pk_of(run)
    if not run_pk:
        return {"ok": False, "code": "missing_run",
                "message": ("resume_playbook requires the paused run's pk (the "
                            "run_pk from run_playbook's awaiting_input result)")}
    _owner = _misused_manual_input_id(run_pk)
    if _owner:
        return {"ok": False, "code": "bad_run_reference", "run_pk": run_pk,
                "manual_input_id": run_pk, "run": _owner,
                "message": (
                    f"{run_pk!r} is a `manual_input_id` (the input FORM), not a "
                    f"workflow run. It belongs to run {_owner!r} -- retry with "
                    f"resume_playbook(run={_owner!r}, ...) if that run is still "
                    "awaiting input.")}
    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured to run playbooks"}
    playbooks = getattr(client, "playbooks", None)
    if playbooks is None:
        return {"ok": False, "code": "no_playbooks_api",
                "message": ("the live client has no typed playbooks API "
                            "(pyfsr PlaybooksAPI not attached)")}
    answered = None  # the pause this call answers; see _reawait_after_resume
    try:
        if inputs:
            # Submitting field values: resolve the pending input, map decision->an
            # option, and resume via that option's step_iri with the values.
            # NOT pyfsr's one-call `answer()`: it retrieves with `owners=<user>`,
            # and through the connector's on-box crudhub transport that owner-
            # scoped retrieve returns EMPTY response options -> "exposes no response
            # options" on a resumable run (live-observed). A no-`owners`
            # retrieve returns them (same path `_pending_input` uses), so we
            # retrieve->pick->`mi.resume` explicitly. Still pyfsr typed methods.
            mi = getattr(client, "manual_input", None)
            form = _pending_input(client, playbooks, run_pk)
            if mi is None or not form:
                return {"ok": False, "code": "not_awaiting", "run_pk": run_pk,
                        "message": (f"run {run_pk} has no pending manual input to "
                                    f"submit values to (finished, or manual-input "
                                    f"API unavailable)")}
            answered = form.get("manual_input_id")
            label = _decision_to_option_label(form.get("options") or [], decision)
            if label is None:
                return {"ok": False, "code": "bad_decision", "run_pk": run_pk,
                        "message": (f"decision {decision!r} matched no response "
                                    f"option on run {run_pk}")}
            full = mi.retrieve(form["manual_input_id"], typed=False)
            full = full if isinstance(full, dict) else {}
            options = (full.get("response_mapping") or {}).get("options") or []
            chosen = next((o for o in options if o.get("option") == label), None)
            if not chosen or not chosen.get("step_iri"):
                return {"ok": False, "code": "bad_decision", "run_pk": run_pk,
                        "message": (f"decision {decision!r} (option {label!r}) has "
                                    f"no resumable step on run {run_pk}")}
            ack = mi.resume(full.get("workflow"), step_iri=chosen["step_iri"],
                            step_id=full.get("step_id"),
                            manual_input_id=form["manual_input_id"],
                            user=mi._resolve_user_iri(), input=inputs)
        else:
            if follow:
                pre = _pending_input(client, playbooks, run_pk)
                answered = (pre or {}).get("manual_input_id")
            ack = playbooks.approval(run_pk, decision=decision)
    except ValueError as exc:  # no pending manual-wf-input (finished / legacy approval)
        return {"ok": False, "code": "not_awaiting", "run_pk": run_pk,
                "message": str(exc)}
    except LookupError as exc:  # decision matched no response option
        return {"ok": False, "code": "bad_decision", "run_pk": run_pk,
                "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- transport/other
        # A pk that is not a workflow run reaches the platform as
        # `manual-wf-input/?workflow=<pk>` and is rejected as an invalid FORM
        # CHOICE -- "Select a valid choice. That choice is not one of the
        # available choices." That message describes a field, so it reads as
        # "the analyst picked something invalid" when the real fault is a
        # wrong identifier. `awaiting_input` returns a run_pk AND a nested
        # `awaiting.manual_input_id` (two bare ints side by side), and live on
        # a box the model passed the latter: resume_playbook(run='388') for run
        # 6839. Re-map that signature to a code that names the confusion.
        # Detected from the platform's own rejection rather than a pre-flight
        # existence check: get_execution returning nothing means "no status
        # snapshot", NOT "no such run", so pre-checking would refuse valid
        # resumes on a transient read -- a worse failure than the one fixed.
        text = str(exc)
        if "Select a valid choice" in text and "workflow=" in text:
            return {"ok": False, "code": "bad_run_reference", "run_pk": run_pk,
                    "message": (
                        f"{run_pk!r} is not a workflow run -- the platform "
                        "rejected it as an invalid `workflow` reference. `run` "
                        "must be the TOP-LEVEL `run_pk` from run_playbook's "
                        "awaiting_input result (e.g. '6839'), NOT the nested "
                        "`awaiting.manual_input_id` (e.g. '388'), which "
                        "identifies the input form and not the run. Re-read "
                        f"the awaiting_input result and pass its run_pk. "
                        f"(platform said: {text})")}
        return {"ok": False, "code": "resume_error", "run_pk": run_pk,
                "message": f"resuming run {run_pk} failed: {exc}"}

    out: dict[str, Any] = {"ok": True, "run_pk": run_pk, "resumed": True,
                           "decision": decision, "ack": _jsonable(ack)}
    if follow:
        # Resume is asynchronous; poll for the run to settle (get_execution).
        form, status = _reawait_after_resume(client, playbooks, run_pk, timeout,
                                             answered=answered)
        if form is not None:
            # The run PAUSED AGAIN on a new manual_input gate. Re-emit the SAME
            # `awaiting_input` seam run_playbook returns for the FIRST pause --
            # same shape `_manual_input_card_from_awaiting` consumes -- so the
            # transcript splice synthesizes the next manual_input card. Without
            # this the chain dead-ended after gate 1 (the widget got no second
            # form even though the run was plainly waiting on one).
            return {"ok": False, "code": "awaiting_input", "run_pk": run_pk,
                    "triggered": True, "resumed": True, "decision": decision,
                    "status": "awaiting", "ack": _jsonable(ack), "awaiting": form,
                    "message": (f"resumed run {run_pk}; it paused again awaiting "
                                f"more manual input "
                                f"({form.get('title') or 'input needed'}). Resume "
                                f"with resume_playbook(run={run_pk!r}, "
                                f"decision='approve'|'reject', inputs={{field: "
                                f"value}} for the fields below).")}
        out["status"] = status
    return out


# How many record-action playbooks `list_module_playbooks` scans in one pass.
# Discovery has to pull steps inline to read each trigger's `resources`, so the
# scan is bounded; when the bound is hit the result says so (see `truncated`).
_PB_SCAN_CAP = 200


def _module_of_iri(iri: str) -> str:
    parts = [p for p in (iri or "").split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


@mcp.tool()
def list_module_playbooks(module: str = "",
                          include_disabled: bool = False) -> dict[str, Any]:
    """List the playbooks a user can run from a module's record-action menu.

    The discovery primitive for "what can I run on this record?". A FortiSOAR
    playbook appears on a module's right-click / Execute menu when its start
    step is a record-action trigger (``cybersponse.action``) whose ``resources``
    array names that module. This tool finds exactly those, so the agent can
    pick the right playbook to ``run_playbook`` instead of guessing a name.

    Defaults ``module`` to the record the turn is mounted on, so on a ztpf
    device "which playbooks can I run here?" needs no argument.

    **DISABLED playbooks are excluded.** A playbook with ``isActive=false`` does
    not appear on the real Execute menu and ``run_playbook`` on it cannot
    succeed, so listing one is an offer the agent can't honor. Discovery filters
    server-side on ``isActive=true``; pass ``include_disabled=True`` only when
    the analyst is explicitly auditing what is turned off; those come back in a
    separate ``disabled`` list, never in ``playbooks``.

    This tool is deliberately GENERIC: it does not encode site conventions like
    "hide anything named 'deprecated'". Such preferences live in the module
    persona / skill, which instructs the agent to filter
    the returned list -- so the same tool serves every deployment and the rule is
    editable without a connector release.

    Args:
      module: bare module name (e.g. ``ztpf_devices``). Omit to use the
        mounted record's module.
      include_disabled: also return deactivated playbooks (default ``False``).
        They are NOT runnable -- never offer one as an action.

    Returns:
      ``{ok, module, playbooks: [{name, uuid, description, execute_button,
      single_record, is_active}], count}`` (+ ``disabled`` when asked for) --
      each ``playbooks`` entry is directly runnable via
      ``run_playbook(playbook=<name or uuid>)``. Empty ``playbooks`` means no
      record-action playbook targets that module. A ``truncated`` flag means
      discovery hit its scan cap and the list may be incomplete -- say so rather
      than presenting it as the complete set.
    """
    bare = (module or "").split("?", 1)[0].strip()
    if not bare:
        bare = _module_of_iri(_shared.active_record_iri() or "")
    if bare and not _IDENT_RE.fullmatch(bare):
        return {"ok": False, "code": "bad_module",
                "message": f"{bare!r} is not a module name (letters, digits, _)"}
    if not bare:
        return {"ok": False, "code": "missing_module",
                "message": ("list_module_playbooks needs a module (none mounted) "
                            "-- e.g. list_module_playbooks(module='ztpf_devices')")}

    client = _shared._live_client()
    if client is None:
        return {"ok": False, "code": "no_fsr_configured",
                "message": "no FSR instance is configured to list playbooks"}
    playbooks = getattr(client, "playbooks", None)
    if playbooks is None:
        return {"ok": False, "code": "no_playbooks_api",
                "message": "the live client has no typed playbooks API"}

    try:
        # `manual` == cybersponse.action (the record Execute menu). Pull the
        # start steps inline so we can read each trigger's `resources` binding.
        # `active=True` is a SERVER-side `isActive` filter: a deactivated
        # playbook is absent from the real Execute menu and run_playbook on it
        # cannot succeed, so surfacing one is an unhonorable offer (live:
        # 'Queue Device Actions - deprecated' came back as runnable). Filtering
        # on the flag -- not on "deprecated" appearing in the title -- is the
        # durable test; a title substring is a naming convention, not state.
        find_kwargs: dict[str, Any] = {"trigger_type": "manual",
                                       "relationships": True,
                                       "limit": _PB_SCAN_CAP}
        if not include_disabled:
            find_kwargs["active"] = True
        found = playbooks.find(**find_kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "discovery_failed",
                "message": f"listing playbooks for {bare!r} failed: {exc}"}

    out: list[dict[str, Any]] = []
    disabled: list[dict[str, Any]] = []
    for pb in found or []:
        if not isinstance(pb, dict):
            continue
        for s in (pb.get("steps") or []):
            st = s.get("stepType") if isinstance(s, dict) else None
            if not (isinstance(st, dict) and st.get("name") == "cybersponse.action"):
                continue
            args = s.get("arguments") if isinstance(s, dict) else None
            resources = args.get("resources") if isinstance(args, dict) else None
            if isinstance(resources, list) and bare in resources:
                # Belt-and-braces: keep the flag test local too, so a client
                # that silently drops the `active` filter can't leak a disabled
                # playbook back into an "you can run these" answer.
                is_active = pb.get("isActive")
                if is_active is False and not include_disabled:
                    break
                # A disabled playbook never joins the runnable list, even when
                # asked for: mixed in, the model listed it under "you can run
                # these" with a "not runnable" footnote (live replay of a ZTP
                # engineer's question, who had asked for it to be hidden).
                (disabled if is_active is False else out).append({
                    "name": pb.get("name"),
                    "uuid": pb.get("uuid") or (pb.get("@id") or "").rsplit("/", 1)[-1],
                    "description": (pb.get("description") or "")[:200] or None,
                    "execute_button": args.get("executeButtonText") or "Execute",
                    "single_record": bool(args.get("singleRecordExecution")),
                    "is_active": bool(is_active) if is_active is not None else None,
                })
            break  # only the trigger step matters

    res: dict[str, Any] = {"ok": True, "module": bare, "playbooks": out,
                           "count": len(out)}
    if not include_disabled:
        res["excludes"] = "disabled (isActive=false) playbooks"
    else:
        res["disabled"] = disabled
        res["disabled_note"] = ("turned off: not on the Execute menu and not "
                                "runnable. Mention them only if the user asked "
                                "what is disabled.")
    # The scan itself is capped. Hitting the cap means "there may be more" --
    # say so instead of letting a partial scan read as the complete menu.
    if len(found or []) >= _PB_SCAN_CAP:
        res["truncated"] = True
        res["message"] = (
            f"scanned the first {_PB_SCAN_CAP} record-action playbooks -- there "
            "may be more targeting this module. Tell the user this list may be "
            "incomplete rather than presenting it as exhaustive.")
    if not out:
        res["hint"] = (
            f"no active record-action playbook targets {bare!r}. It may be a "
            "child module reached only via its parent's playbooks, or every "
            "such playbook is deactivated (retry with include_disabled=True "
            "to check).")
    return res
