"""Pieces shared between the Anthropic and LM Studio agent loops.

Kept here (not in `provider.py`) because they're implementation details
of the loop, not part of the protocol contract a future provider has to
honor. A new provider can opt in to self-repair by importing these.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any


# Read-only reference tools: results are deterministic for the same
# args, so we can replace duplicate tool_results with a stub pointing
# back at the first call. Excludes anything that mutates remote state
# or depends on time-varying data (validate_yaml, run_op, push_*).
_IDEMPOTENT_TOOLS: frozenset[str] = frozenset({
    "find_connector",
    "find_operation",
    "get_op_schema",
    "get_step_type",
    "find_step_examples",
    "find_step_recipe",
    "find_jinja_filter",
    "find_jinja_pattern",
    "get_filter_examples",
    "picklist_for_field",
    "search_playbooks",
    "list_configured_connectors",
    "resolve_picklist_value",
})

# Tools whose `yaml_text` argument is large and re-sent every retry. We
# keep only the most recent N of each in the LLM context; older ones
# get their yaml_text stubbed since the agent only repairs from the
# latest draft.
_YAML_BODY_TOOLS: frozenset[str] = frozenset({"validate_yaml", "compile_yaml"})
_YAML_BODY_KEEP_LATEST = 1

# §2.3 output budgeting — cap oversized tool *result* bodies. A single large
# result (e.g. verify_playbook ~47KB, duplicate-enrichment ~40KB) is neither an
# idempotent dup nor a yaml arg body, so the two passes above never touch it; a
# short chain of them blows the context window. We keep the most recent
# `_RESULT_KEEP_LATEST` oversized results in full (the agent repairs/reasons from
# the freshest data) and clip older ones to a head+tail preview. Deterministic:
# a clipped body is under the threshold, so re-running shrink is a fixed point
# and the block stays byte-stable across turns.
_RESULT_CAP_CHARS = 8000
_RESULT_KEEP_LATEST = 1
_RESULT_HEAD_CHARS = 5000
_RESULT_TAIL_CHARS = 1500


def _args_hash(args: Any) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = str(args)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def shrink_history(history: list[Any]) -> int:
    """Compact the conversation in place to cut redundant tokens.

    Two passes, both cache-friendly (we only modify *older* turns; the
    most recent assistant + tool_result blocks stay byte-identical so
    Anthropic's prompt cache is preserved):

    1. Idempotent tool dedup — for whitelisted read-only tools, when the
       same (name, args) appears more than once, replace later
       tool_result blocks with a stub pointing at the first call. The
       agent still sees the call happened; it doesn't re-pay for the
       body.
    2. YAML body cap — for `validate_yaml`/`compile_yaml`, replace the
       `yaml_text` argument in older tool_use blocks with a stub. Only
       the latest call needs the full body; the agent repairs from
       there.

    Returns the number of bytes saved (rough estimate, useful for
    telemetry / tests).
    """
    saved = 0

    # Walk every assistant turn's tool_use blocks in order, indexing by
    # call_id → (name, args_hash). Then walk user turns' tool_result
    # blocks; if a tool_use has an earlier matching twin AND the tool is
    # idempotent, stub the duplicate's tool_result.
    seen_by_signature: dict[tuple[str, str], str] = {}
    canonical_for: dict[str, str] = {}  # call_id → original call_id (when dup)
    yaml_call_ids: list[str] = []  # in encounter order

    for msg in history:
        content = getattr(msg, "content", None)
        if not isinstance(content, list):
            continue
        if msg.role == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name") or ""
                cid = block.get("id") or ""
                if not cid:
                    continue
                if name in _YAML_BODY_TOOLS:
                    yaml_call_ids.append(cid)
                if name in _IDEMPOTENT_TOOLS:
                    sig = (name, _args_hash(block.get("input")))
                    prior = seen_by_signature.get(sig)
                    if prior:
                        canonical_for[cid] = prior
                    else:
                        seen_by_signature[sig] = cid

    # Stub duplicate tool_results.
    for msg in history:
        content = getattr(msg, "content", None)
        if msg.role != "user" or not isinstance(content, list):
            continue
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            cid = block.get("tool_use_id")
            orig = canonical_for.get(cid)
            if not orig:
                continue
            old = block.get("content") or ""
            if not isinstance(old, str):
                continue
            stub = (
                f'{{"_cached_dup_of": "{orig}", '
                f'"note": "identical args to an earlier call this session — '
                f'reuse that result"}}'
            )
            if old != stub:
                saved += max(0, len(old) - len(stub))
                block["content"] = stub

    # Cap older yaml_text bodies. Keep the most recent N call ids intact.
    keep = set(yaml_call_ids[-_YAML_BODY_KEEP_LATEST:]) if yaml_call_ids else set()
    if len(yaml_call_ids) > _YAML_BODY_KEEP_LATEST:
        for msg in history:
            content = getattr(msg, "content", None)
            if msg.role != "assistant" or not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") not in _YAML_BODY_TOOLS:
                    continue
                if block.get("id") in keep:
                    continue
                inp = block.get("input")
                if not isinstance(inp, dict):
                    continue
                body = inp.get("yaml_text")
                if not isinstance(body, str) or len(body) < 200:
                    continue
                stub = "<elided — superseded by a later validate_yaml call>"
                saved += len(body) - len(stub)
                inp["yaml_text"] = stub

    # Pass 3 — §2.3 cap oversized tool_result bodies. Collect every
    # tool_result with an over-threshold string body, in history order, then
    # clip all but the most recent `_RESULT_KEEP_LATEST` of them. Already-clipped
    # bodies are under the threshold so they're skipped (fixed point).
    oversized: list[tuple[Any, str]] = []  # (block, content) in encounter order
    for msg in history:
        content = getattr(msg, "content", None)
        if msg.role != "user" or not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content")
            if isinstance(body, str) and len(body) > _RESULT_CAP_CHARS:
                oversized.append((block, body))

    to_clip = (oversized[:-_RESULT_KEEP_LATEST]
               if _RESULT_KEEP_LATEST > 0 else oversized)
    for block, body in to_clip:
        clipped = len(body) - _RESULT_HEAD_CHARS - _RESULT_TAIL_CHARS
        new_body = (
            body[:_RESULT_HEAD_CHARS]
            + f"\n… [+{clipped} chars capped by the output budgeter — "
              f"a later turn superseded this result] …\n"
            + body[-_RESULT_TAIL_CHARS:]
        )
        saved += len(body) - len(new_body)
        block["content"] = new_body

    return saved


# Per-turn tool-round ceiling. Raised 12 → 16 so a live hunt that fans out
# across alerts/incidents/asset/identity lookups + multi-connector TI
# enrichment still has rounds left to stage its containment action card.
# §2.8 parallel dispatch collapses each independent fan-out into one round,
# so the effective headroom is much larger than the raw count suggests.
MAX_TOOL_TURNS = 16
# Cap on extra "fix the YAML" turns auto-issued when the assistant's
# final message contains a yaml block that fails to compile. Each repair
# turn is roughly one extra LLM round-trip; 2 keeps cost bounded.
MAX_SELF_REPAIR_TURNS = 2

# §2.8 — cap on read-only (tier ≤ 2) tool calls dispatched concurrently
# within a single turn. `dispatch`/`run_op` are sync and touch shared
# state (the connector requests session, in-process health/config caches,
# sqlite), so we bound fan-out rather than letting a turn open arbitrarily
# many upstream sockets at once.
MAX_PARALLEL_TOOLS = 8

# §2.2 — wall-clock deadline for a single Anthropic stream round-trip.
# A stalled network or overloaded upstream can block the `async for`
# indefinitely; this caps it so the turn fails cleanly instead of hanging.
# Overrideable via ANTHROPIC_STREAM_TIMEOUT_SECS env for local testing.
import os as _os
STREAM_TIMEOUT_SECS: int = int(_os.environ.get("ANTHROPIC_STREAM_TIMEOUT_SECS", "300"))


import asyncio as _asyncio


async def drain_with_idle_timeout(pump, *, timeout: float):
    """Yield items from the async generator ``pump`` live, bounded by a
    per-item *inactivity* timeout.

    Every provider's ``stream()`` needs the same scaffolding: surface each
    streamed delta to the consumer (and thus the connector's ``chat_poll``
    feed) the instant the upstream yields it, while still failing cleanly if
    the upstream stalls. Buffering the whole round-trip just to wrap it in one
    ``asyncio.wait_for`` — the old approach — defeated live streaming (the
    answer only appeared on turn completion). This helper keeps that timeout
    guarantee without the buffering, so the per-delta plumbing lives in ONE
    place and each provider only supplies its SDK-specific ``pump``.

    Mechanics: ``pump`` runs as a background task feeding a queue; the consumer
    reads the queue under ``asyncio.wait_for(timeout)`` (3.9-compatible — no
    ``asyncio.timeout()``).

    - Items from ``pump`` are re-yielded verbatim (the provider tags them,
      e.g. ``("text", str)`` / ``("final", msg)``).
    - If no item *or* completion arrives within ``timeout`` seconds, the pump
      is cancelled and ``asyncio.TimeoutError`` is raised.
    - An exception raised inside ``pump`` is re-raised in the consumer's
      context, so the provider's existing error mapping handles it unchanged.
    """
    q: _asyncio.Queue = _asyncio.Queue()

    async def _run() -> None:
        try:
            async for item in pump:
                await q.put(("item", item))
            await q.put(("end", None))
        except Exception as exc:  # surfaced to the consumer below
            await q.put(("error", exc))

    task = _asyncio.ensure_future(_run())
    try:
        while True:
            try:
                kind, payload = await _asyncio.wait_for(q.get(), timeout)
            except _asyncio.TimeoutError:
                task.cancel()
                raise
            if kind == "item":
                yield payload
            elif kind == "end":
                return
            else:  # ("error", exc)
                raise payload
    finally:
        if not task.done():
            task.cancel()


# ───────────────────────── triage discipline ─────────────────────────
#
# Model-agnostic guards layered on top of raw tool dispatch for the TRIAGE
# agent. All three rules were learned from live gpt-4o-mini runs (memory
# `openai_terse_triage_shallow`): a weak model under-weights the system prompt
# + pre-flight blocks and acts on the immediate user message, so depth swings
# wildly on phrasing. A terse opener shortcut to
#   get_record → find_containment_actions → emit_action_card  (3 calls, no hunt)
# while a richly-enumerated prompt over-hunted (16 calls) AND fired a forbidden
# VirusTotal lookup on an internal RFC1918 IP. Prose in system_prompt_triage.md
# can't hold a weak model; these guards enforce the same discipline structurally
# so behavior is consistent regardless of model or phrasing.
#
# All three fire only on triage-specific tool names, so build flows (whose tool
# slice excludes them) are unaffected.

# Containment-staging tools — refused until the hunt floor is met.
_CONTAINMENT_STAGING_TOOLS: frozenset[str] = frozenset({
    "find_containment_actions", "emit_action_card",
})
# Evidence-gathering tools that count toward the floor. get_record (the alert
# pull) and the find_* discovery meta-tools are deliberately EXCLUDED so the
# floor forces real evidence beyond pulling the record + listing actions.
_INVESTIGATION_TOOLS: frozenset[str] = frozenset({
    "search_module_records", "run_op",
    "siem_events_for_incident", "siem_search_host", "siem_search_ip",
    "get_host_context", "get_user_context", "get_ip_context",
    "get_device_info", "get_incident_details", "get_associated_events_new",
    "faz_get_alerts", "faz_search_ip", "faz_raw_query",
})
# Discovery tools that return their full set in one shot FOR A GIVEN INDICATOR
# TYPE — a second call with the SAME target_type is pure waste, but these tools
# are `target_type`-scoped (ip/domain/hash/endpoint/…) and filter their result
# by it, so a call for `ip` and a call for `endpoint` are DISTINCT and both
# legitimate. The call-once guard therefore keys on (name, target_type), not
# name alone (which used to wrongly block the second indicator type).
_CALL_ONCE_DISCOVERY: frozenset[str] = frozenset({
    "find_containment_actions", "find_enrichment_actions",
})


def _call_once_sig(name: str, args: Any) -> str:
    """Dedup key for the call-once discovery guard: name + normalized
    target_type, so each indicator type gets its own single call."""
    tt = str((args or {}).get("target_type") or "").strip().lower()
    return f"{name}\x00{tt}"
# External threat-intel connectors that should never be pointed at an internal
# (RFC1918 / loopback / link-local) IP — enriching a private source IP against
# public TI is the forbidden pivot the eval fixtures encode.
_TI_CONNECTOR_TOKENS: tuple[str, ...] = (
    "virustotal", "shodan", "ipqualityscore", "abuseipdb",
)
# Full pivot floor: record + cross-module search + external enrichment + a
# pivot ≈ 3 genuine evidence calls before containment may be staged.
MIN_INVESTIGATION_BEFORE_CONTAINMENT = 3

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _classify_ips(args: Any) -> tuple[set[str], set[str]]:
    """Return (internal, external) IPv4 literals found anywhere in ``args``."""
    internal: set[str] = set()
    external: set[str] = set()
    try:
        blob = json.dumps(args, default=str)
    except Exception:
        blob = str(args)
    for tok in _IP_RE.findall(blob):
        try:
            ip = ipaddress.ip_address(tok)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            internal.add(tok)
        else:
            external.add(tok)
    return internal, external


class TriageDiscipline:
    """Per-session triage guard. ``evaluate(name, args)`` atomically checks the
    three discipline rules and, when the call is allowed, records it — returning
    a guard envelope (``{"ok": False, …}``) to short-circuit dispatch or ``None``
    to proceed. ONE atomic call so the read-only parallel batch (dispatched
    across threads via ``asyncio.to_thread``) can't race the counter/seen-set.

    Attempts — not successes — count toward the hunt floor, so a config gap or a
    failing enrichment can't deadlock the floor (the model still gets credit for
    trying to investigate, and MAX_TOOL_TURNS bounds the loop).

    When initialized with an optional ``state`` (Investigation instance), the
    discipline seeds its counters from the state and mutates the shared state
    object as the turn progresses so the caller can persist it afterwards.

    ``capabilities`` (a Capabilities instance) adds the §E capability guard:
    a ``run_op`` against a connector already recorded unavailable this session
    short-circuits with a ``guard_redirect`` instead of re-probing; call
    ``note_result`` after each dispatched tool so outcomes keep the shared
    capabilities object current (the caller persists it post-turn)."""

    def __init__(
        self,
        *,
        floor: int = MIN_INVESTIGATION_BEFORE_CONTAINMENT,
        state: Any = None,  # Investigation | None
        capabilities: Any = None,  # Capabilities | None
        authoring: bool = False,
    ):
        import threading
        self.floor = floor
        self._shared_state = state  # None or an Investigation instance
        self._capabilities = capabilities  # None or a Capabilities instance
        # Authoring/build turns don't triage a live alert. `find_containment_actions`
        # is DISCOVERY ("which ops could block an IP?") that a build agent
        # legitimately uses while authoring — so the hunt-floor investigation gate
        # (no containment before N evidence calls) must not fire on it here. The
        # gate stays fully intact for triage (authoring=False). Actual staging
        # (`emit_action_card`) isn't in the build tool-slice at all, so nothing
        # containment is being STAGED — only discovered.
        self._authoring = authoring
        # Seed invest_attempts from state if provided
        if state is not None and hasattr(state, "invest_attempts"):
            self.invest_attempts = state.invest_attempts
        else:
            self.invest_attempts = 0
        # Pre-populate _called from state if provided
        self._called: set[str] = set()
        if state is not None and hasattr(state, "called_once_sigs"):
            self._called.update(state.called_once_sigs)
        # Hunt floor is permanently satisfied if state says so
        self._hunt_floor_met = state is not None and getattr(state, "hunt_floor_met", False)
        # How many distinct evidence tools remain before the floor lifts —
        # surfaced in the block message so the model knows it's making progress.
        self._lock = threading.Lock()

    def _check_locked(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        # 0. Capability guard (§E) — this session already learned the connector
        # is unavailable (not configured / unhealthy); don't burn a live
        # re-probe on it. `list_configured_connectors` success (the analyst's
        # "Re-check & continue") clears the entry via note_result.
        if name == "run_op" and self._capabilities is not None:
            connector = str((args or {}).get("connector") or "")
            unavailable = getattr(self._capabilities, "unavailable", None) or {}
            reason = unavailable.get(connector)
            if reason:
                why = ("has no active configuration"
                       if reason == "connector_not_configured"
                       else "is failing its healthcheck"
                       if reason == "connector_unhealthy"
                       else f"is unavailable ({reason})")
                return {
                    "ok": False,
                    "kind": "guard_redirect",
                    "capability_guard": True,
                    "connector": connector,
                    "reason": reason,
                    "error": (
                        f"Skipped: `{connector}` {why} — you already learned "
                        f"this earlier in the session, so the call was NOT "
                        f"re-attempted. Do not retry it. Either pick a "
                        f"configured alternative (`list_configured_connectors` "
                        f"shows what IS available), or surface the gap to the "
                        f"analyst via `emit_capability_gap_card` so they can "
                        f"fix the connector and resume."
                    ),
                }
        # 1. Forbidden pivot — external TI on an internal-only IP.
        if name == "run_op":
            connector = str((args or {}).get("connector") or "").lower()
            if any(tok in connector for tok in _TI_CONNECTOR_TOKENS):
                internal, external = _classify_ips(args)
                if internal and not external:
                    return {
                        "ok": False,
                        "kind": "guard_redirect",
                        "forbidden_pivot_guard": True,
                        "error": (
                            f"Skipped: {connector} is an EXTERNAL threat-intel "
                            f"lookup and the only IP in this call is internal "
                            f"(RFC1918) — {sorted(internal)[0]}. Private/internal "
                            f"addresses have no public TI reputation; enriching "
                            f"them wastes budget and pollutes the verdict. Pivot "
                            f"on internal hosts via the SIEM/CMDB context ops "
                            f"(get_ip_context / siem_search_ip) and reserve TI "
                            f"connectors for EXTERNAL, routable indicators."
                        ),
                    }
        # 2. Call-once discovery — the set is returned in one shot PER
        # target_type. Block only a repeat of the SAME (name, target_type);
        # a different indicator type is a distinct, legitimate call.
        if (name in _CALL_ONCE_DISCOVERY
                and _call_once_sig(name, args) in self._called):
            tt = str((args or {}).get("target_type") or "").strip().lower()
            scope = f" for target_type `{tt}`" if tt else ""
            return {
                "ok": False,
                "kind": "guard_redirect",
                "call_once_guard": True,
                "error": (
                    f"STOP calling `{name}`{scope} — you already called it this "
                    f"session{scope} and it returns the FULL set for that "
                    f"indicator type in one shot. Do not repeat it{scope}. Act on "
                    f"the result you already have: pick an op from it and proceed. "
                    f"(A DIFFERENT target_type is allowed.)"
                ),
            }
        # 3. Hunt floor — no containment before real investigation. Prescriptive:
        # weak models re-spam a blocked tool when told "retry later", so name the
        # ONE next call to make and forbid re-calling the blocked tool.
        if (name in _CONTAINMENT_STAGING_TOOLS
                and not (self._authoring and name == "find_containment_actions")
                and not self._hunt_floor_met
                and self.invest_attempts < self.floor):
            remaining = self.floor - self.invest_attempts
            if "search_module_records" not in self._called:
                next_step = (
                    "`search_module_records` on the `incidents` module for the "
                    "host and external IP from the alert (then again on `alerts`)"
                )
            else:
                next_step = (
                    "enrich the EXTERNAL (public) IP with a threat-intel "
                    "connector via `run_op` (VirusTotal / FortiGuard / Shodan), "
                    "or pivot the host with `siem_search_host` / `get_ip_context`"
                )
            return {
                "ok": False,
                "kind": "guard_redirect",
                "hunt_floor_guard": True,
                "investigation_calls": self.invest_attempts,
                "required": self.floor,
                "error": (
                    f"Do NOT call `{name}` yet — it was NOT executed. You've run "
                    f"{self.invest_attempts} of {self.floor} required "
                    f"investigation steps; staging containment now would act on "
                    f"an alert you haven't scoped. Do NOT repeat this call. Your "
                    f"NEXT call must be: {next_step}. After ~{remaining} more "
                    f"evidence call(s), staging will unlock automatically."
                ),
            }
        return None

    def evaluate(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Atomic check-and-record. Returns a guard envelope (block) or None
        (allowed — and the call is recorded as dispatched)."""
        with self._lock:
            guard = self._check_locked(name, args or {})
            if guard is not None:
                return guard
            # Record the call. Call-once discovery tools are recorded under their
            # (name, target_type) signature so a different indicator type isn't
            # blocked; every other tool records by bare name (the hunt-floor and
            # `search_module_records`-seen checks key on bare names).
            self._called.add(name)
            if name in _CALL_ONCE_DISCOVERY:
                self._called.add(_call_once_sig(name, args))
            if name in _INVESTIGATION_TOOLS:
                self.invest_attempts += 1
                # Once floor is met, mark it in the shared state
                if (self._shared_state is not None and
                        self.invest_attempts >= self.floor and
                        not self._hunt_floor_met):
                    self._hunt_floor_met = True
                    self._shared_state.hunt_floor_met = True
            # Mutate the shared state to keep invest_attempts in sync
            if self._shared_state is not None:
                self._shared_state.invest_attempts = self.invest_attempts
                # Keep called_once_sigs in sync
                self._shared_state.called_once_sigs = list(self._called)
            return None

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        """Record capability facts (§E) from a dispatched tool's result into the
        shared Capabilities object. Call after every successful dispatch; no-op
        when the discipline has no capabilities state.

        - ``run_op`` failing with ``connector_not_configured`` /
          ``connector_unhealthy`` marks the connector unavailable — the next
          ``run_op`` against it short-circuits instead of re-probing.
        - ``run_op`` succeeding confirms the connector (and clears any stale
          unavailable entry — a connector fixed mid-session works again).
        - ``list_configured_connectors`` succeeding clears ALL unavailable
          entries: it's the re-check gesture (capability-gap "Re-check &
          continue"), and a still-broken connector re-records itself on the
          next attempt anyway.
        """
        caps = self._capabilities
        if caps is None or not isinstance(result, dict):
            return
        import time
        with self._lock:
            if name == "run_op":
                connector = str((args or {}).get("connector") or "")
                if not connector:
                    return
                code = result.get("code")
                if (result.get("ok") is False
                        and code in ("connector_not_configured",
                                     "connector_unhealthy")):
                    caps.unavailable[connector] = code
                    caps.noted_at = time.time()
                elif result.get("ok") is True:
                    caps.unavailable.pop(connector, None)
                    if connector not in caps.confirmed:
                        caps.confirmed.append(connector)
                    caps.noted_at = time.time()
            elif name == "list_configured_connectors":
                if result.get("ok") is not False and caps.unavailable:
                    caps.unavailable.clear()
                    caps.noted_at = time.time()


def extract_yaml_block(text: str) -> str | None:
    """Return the contents of the LAST fenced ```yaml block, or None.
    Mirrors the frontend's extractYamlBlock so the in-chat YAML the user
    sees and the YAML we self-repair against are exactly the same string.
    """
    matches = list(re.finditer(r"```ya?ml\n([\s\S]*?)```", text, flags=re.IGNORECASE))
    return matches[-1].group(1) if matches else None


def compile_errors(yaml_text: str) -> str | None:
    """Run the same compiler the editor uses; return a bullet list of
    blocking errors or None if clean. Imported lazily so a missing
    compiler doesn't break test collection."""
    try:
        from fsr_playbooks.compiler import compile_yaml as _cy  # type: ignore
    except Exception as e:
        return f"compiler import failed: {e}"

    from .._db import default_db_path
    res = _cy(yaml_text, default_db_path())
    if res.ok:
        return None
    blocking = [e for e in res.errors if e.severity != "warning"]
    if not blocking:
        return None
    lines: list[str] = []
    for e in blocking:
        line = f"- [{e.code.value}] {e.message}"
        if e.path:
            line += f"  (path: {e.path})"
        if e.suggestion:
            line += f"  → {e.suggestion}"
        lines.append(line)
    return "\n".join(lines)
