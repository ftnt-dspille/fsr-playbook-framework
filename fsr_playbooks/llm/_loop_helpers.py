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

# Per-turn OUTPUT-token ceiling, shared by every provider loop.
#
# This was a hardcoded 4096 in all three providers -- not configurable, not
# per-intent. A whole real playbook plus the prose that introduces it does not
# fit in 4096 output tokens, so a build turn physically could not return its
# document intact: the reply came back cut off mid-word with the token-cap stop
# reason, and the widget then had to defend against saving the fragment. That
# is a product limit, not a test artifact.
#
# Raised UNIFORMLY rather than per-intent because a cap is a ceiling, not an
# allocation -- you are billed on the tokens actually emitted, so a triage turn
# that answers in 300 tokens costs exactly the same under a 16k ceiling as
# under a 4k one. A per-intent budget would buy nothing, and would require
# plumbing `intent` down into the provider, which is deliberately unaware of it.
#
# 16384 is the smallest ceiling that comfortably fits a real playbook while
# staying within the output limit of every model on this path (gpt-4o caps at
# exactly 16384; gpt-4.1-mini at 32768). Each provider takes a
# `max_output_tokens` ctor override so a deployment pinned to a model with a
# lower limit can drop it without a release.
DEFAULT_MAX_OUTPUT_TOKENS = 16384


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

# §2.3 output budgeting -- cap oversized tool *result* bodies. A single large
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

    1. Idempotent tool dedup -- for whitelisted read-only tools, when the
       same (name, args) appears more than once, replace later
       tool_result blocks with a stub pointing at the first call. The
       agent still sees the call happened; it doesn't re-pay for the
       body.
    2. YAML body cap -- for `validate_yaml`/`compile_yaml`, replace the
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
                f'"note": "identical args to an earlier call this session -- '
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
                stub = "<elided -- superseded by a later validate_yaml call>"
                saved += len(body) - len(stub)
                inp["yaml_text"] = stub

    # Pass 3 -- §2.3 cap oversized tool_result bodies. Collect every
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
            + f"\n… [+{clipped} chars capped by the output budgeter -- "
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

# §2.8 -- cap on read-only (tier ≤ 2) tool calls dispatched concurrently
# within a single turn. `dispatch`/`run_op` are sync and touch shared
# state (the connector requests session, in-process health/config caches,
# sqlite), so we bound fan-out rather than letting a turn open arbitrarily
# many upstream sockets at once.
MAX_PARALLEL_TOOLS = 8

# §2.2 -- wall-clock deadline for a single Anthropic stream round-trip.
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
    ``asyncio.wait_for`` -- the old approach -- defeated live streaming (the
    answer only appeared on turn completion). This helper keeps that timeout
    guarantee without the buffering, so the per-delta plumbing lives in ONE
    place and each provider only supplies its SDK-specific ``pump``.

    Mechanics: ``pump`` runs as a background task feeding a queue; the consumer
    reads the queue under ``asyncio.wait_for(timeout)`` (3.9-compatible -- no
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

# Containment-staging tools -- refused until the hunt floor is met.
_CONTAINMENT_STAGING_TOOLS: frozenset[str] = frozenset({
    "find_containment_actions", "emit_action_card",
})
# Evidence-gathering tools that count toward the floor. get_record (the alert
# pull) and the find_* discovery meta-tools are deliberately EXCLUDED so the
# floor forces real evidence beyond pulling the record + listing actions.
#
# MUTABLE on purpose, same Option-A posture as `intents.TRIAGE_ONLY_TOOLS`: the
# connector registers its own read-only hunt tools at import
# (`fsr_soc_triage.registry`) and extends this set with them. An explicit list
# alone silently under-counts every tool the framework doesn't know by name --
# which is exactly how a real GA investigation that ran `fmg_get_device_status`,
# `fmg_get_ha_status`, `fmg_get_policy_package_status` and
# `faz_search_device_events` scored **0 of 3** evidence calls and left
# containment locked on the analyst's follow-up "isolate that host" turn.
_INVESTIGATION_TOOLS: set[str] = {
    "search_module_records", "run_op",
    "siem_search", "siem_events_for_incident",
    "get_host_context", "get_user_context", "get_ip_context",
    "get_device_info", "get_incident_details", "get_associated_events_new",
    "faz_search", "faz_get_alerts", "faz_raw_query",
    "fmg_device",
}
# Second line of defence against the same drift: whole read-only hunt FAMILIES
# count even when an individual name was never registered here. These prefixes
# are only ever used by SIEM / FortiAnalyzer / FortiManager query tools, all of
# which are genuine evidence gathering.
_INVESTIGATION_PREFIXES: tuple[str, ...] = ("siem_", "faz_", "fmg_")


def _is_read_only_mcp_evidence(name: str) -> bool:
    """True for a materialized `mcp_<server>__<tool>` that is read-only.

    Native MCP tools carry the same evidence weight as the curated hunt tools --
    `mcp_soc__enrich_indicator` and `mcp_fortisiem__get_context_by_entity` ARE
    investigation -- but they are materialized at runtime, so no static list can
    name them and the `siem_`/`faz_`/`fmg_` prefixes don't match. Tier is the
    honest signal: the materializer records tier 1 for a read-only server rule
    and 3 for a mutating one, so a containment tool like
    `mcp_soc__block_indicator` is excluded by construction rather than by name.

    Fail-closed: an unknown or untiered name credits nothing.
    """
    if not name.startswith("mcp_") or "__" not in name:
        return False
    try:
        from . import tools as _llm_tools
        return _llm_tools.TOOL_TIERS.get(name) == 1
    except Exception:  # noqa: BLE001 - never let crediting break a turn
        return False


def counts_as_investigation(name: str) -> bool:
    """True when `name` is evidence gathering and should credit the hunt floor."""
    if name in _CONTAINMENT_STAGING_TOOLS:
        return False
    return (name in _INVESTIGATION_TOOLS
            or name.startswith(_INVESTIGATION_PREFIXES)
            or _is_read_only_mcp_evidence(name))


def credit_as_investigation(*names: str) -> None:
    """Register extra tool names as hunt-floor evidence (used by the connector's
    triage registry so its hunt tools aren't invisible to the floor)."""
    _INVESTIGATION_TOOLS.update(n for n in names if n)
# Discovery tools that return their full set in one shot FOR A GIVEN INDICATOR
# TYPE -- a second call with the SAME target_type is pure waste, but these tools
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
# (RFC1918 / loopback / link-local) IP -- enriching a private source IP against
# public TI is the forbidden pivot the eval fixtures encode.
_TI_CONNECTOR_TOKENS: tuple[str, ...] = (
    "virustotal", "shodan", "ipqualityscore", "abuseipdb",
)
# Full pivot floor: record + cross-module search + external enrichment + a
# pivot ≈ 3 genuine evidence calls before containment may be staged.
MIN_INVESTIGATION_BEFORE_CONTAINMENT = 3


def _is_analyst_ordered(name: str, args: Any) -> bool:
    """True when the model DECLARED that the analyst explicitly ordered this
    containment (tracker #60).

    The floor exists to stop the agent from contain-first-scope-later. It was
    never meant to answer an explicit order with a refusal -- but that is what
    it did, because the guard sees only `(name, args)`: the analyst's "isolate
    that host" lives in the message text one layer up and is invisible here.

    NOTE: this is the SECONDARY path. It is kept because it costs nothing and
    an explicit declaration should be honored, but nothing may depend on it --
    the box model set `requested_by` on 0 of 4 live containment calls across 2
    runs. It does not lie about intent; it ignores an optional parameter. The
    path that actually fires is `_detect_analyst_order` over the user's own
    message -- see its docstring for why the original objection to reading the
    phrasing no longer holds.

    This exempts STAGING, not execution. The card still goes to a human, and
    the tier/approval gate is untouched -- that gate is what actually stops a
    bad action, and this changes nothing about it.

    Covers BOTH staging tools. Scoping it to `emit_action_card` alone was
    unreachable in practice: a card names a connector + operation, so the agent
    must call `find_containment_actions` first to discover them -- and that call
    is floor-gated too, so an explicit order died at step one and never reached
    the exempted step two. The live .159 matrix caught this (row TO: two
    `hunt_floor_guard` blocks on discovery, `terminal=end_turn`, no card) after
    the unit tests missed it by calling `emit_action_card` directly.

    Fails closed -- anything but the exact string keeps the floor.
    """
    if name not in _CONTAINMENT_STAGING_TOOLS:
        return False
    return str((args or {}).get("requested_by") or "").strip().lower() == "analyst"


# An imperative containment verb. Deliberately not every synonym in
# `_CONTAINMENT_VERBS` -- this reads human phrasing, not op names.
_ORDER_VERBS = (
    r"block|isolate|quarantine|contain|disable|suspend|revoke|ban|deactivate|"
    r"blacklist|block\s?list|kill|terminate|shut\s?down|"
    r"take\s+(?:\S+\s+){1,3}offline|"
    r"remediate|lock\s+out"
)
# Directive framing: the verb opens the clause, or follows a lead-in that makes
# it a request rather than a question about one.
_ORDER_RE = re.compile(
    r"(?:^|[.;!?\n]\s*|,\s*(?:then|and)\s+|\b(?:please|now|go\s+ahead\s+and|"
    r"i\s+want\s+you\s+to|i\s+need\s+you\s+to|you\s+(?:should|must|need\s+to)|"
    r"let'?s)\s+)"
    r"(?:please\s+|just\s+|immediately\s+)?"
    rf"(?:{_ORDER_VERBS})\b",
    re.IGNORECASE,
)
# Phrasings that use a containment verb WITHOUT ordering one: a question about
# whether to act, a hypothetical, or a description of something already done.
_NOT_AN_ORDER_RE = re.compile(
    r"\b(?:was|were|is|are|been|got|already)\s+(?:\w+\s+){0,2}"
    rf"(?:{_ORDER_VERBS})(?:ed|d)?\b"
    rf"|\b(?:should|shall|would|could|can|may|might|do|did|does)\s+(?:i|we|you|it|they)\b"
    rf"|\bif\s+(?:i|we|you|they)\s+(?:{_ORDER_VERBS})\b"
    rf"|\bwhy\s+(?:was|were|is|are)\b"
    rf"|\b(?:{_ORDER_VERBS})(?:ed|d)\s+by\b",
    re.IGNORECASE,
)


def latest_user_text(messages: Any) -> str:
    """The text of the most recent user message in a provider's history.

    Every provider builds `TriageDiscipline` from its own `messages` list, so
    this lives here rather than being open-coded three times -- three copies of
    a content-shape walk is exactly the parallel-list drift that has bitten
    this file before. `Message.content` is a plain string on a user turn but a
    block list on a tool-result turn; only the text blocks are the analyst's
    words. Returns "" when there is no user text to read.
    """
    for msg in reversed(list(messages or ())):
        if str(getattr(msg, "role", "") or "") != "user":
            continue
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            if content.strip():
                return content
            continue
        if isinstance(content, list):
            # A tool_result turn carries no analyst words; skip past it to the
            # message that actually prompted this turn.
            parts = [str(b.get("text") or "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            joined = "\n".join(p for p in parts if p)
            if joined.strip():
                return joined
    return ""


def _detect_analyst_order(user_text: str) -> bool:
    """True when the analyst's own message is an explicit order to contain.

    This is the path the exemption actually runs on. The original design put
    the declaration on the tool call instead, reasoning that "a regex over the
    user's wording would put a phrasing-dependent branch in a security gate,
    where a miss is another silent refusal." Live evidence inverts that:

      * The declared field misses 100% of the time (0 of 4 calls, 2 runs), so
        it *is* the silent-refusal path the objection warned about. A detector
        with imperfect recall is strictly better than one with zero.
      * A miss here costs exactly what today costs -- the floor holds and the
        agent is told to investigate first. It is the status quo, not a new
        failure mode.
      * A false positive costs a card staged early. It does NOT act: this
        exempts staging only, and the tier/approval gate still routes the card
        to a human. The gate that stops a bad action is untouched.

    Asymmetric costs, so this leans toward recall: it fires on an imperative
    containment verb in directive position, and stands down on the phrasings
    that use the same verbs without ordering anything -- a question about
    whether to act ("should we block it?"), a hypothetical ("if we block the
    IP..."), or a report of something already done ("the IP was blocked by the
    firewall"). Empty/None text is not an order.
    """
    text = (user_text or "").strip()
    if not text:
        return False

    # Evaluate clause-by-clause so one descriptive sentence in a long message
    # can't veto an order in another ("The IP was blocked yesterday. Block it
    # on the edge firewall too.").
    for clause in re.split(r"(?<=[.;!?\n])\s+", text):
        if not clause.strip():
            continue
        if _NOT_AN_ORDER_RE.search(clause):
            continue
        if _ORDER_RE.search(clause):
            return True
    return False

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
    three discipline rules and, when the call is allowed, records it -- returning
    a guard envelope to short-circuit dispatch or ``None`` to proceed. ONE
    atomic call so the read-only parallel batch (dispatched across threads via
    ``asyncio.to_thread``) can't race the counter/seen-set.

    Two guard *shapes* are returned, and the distinction is load-bearing
    (tracker #60):

    * ``kind: "guard_defer"`` (``ok: True``, ``directive``) -- a NON-terminal
      deferral. The hunt-floor guard uses this: "investigate first, then retry."
      It must NOT read as a tool failure, or the model ends the turn on a
      perfectly good reason to stop (an ``ok: false`` tool_result).
    * ``kind: "guard_redirect"`` (``ok: False``, ``error``) -- a TERMINAL
      redirect. The forbidden-pivot, call-once and capability guards use this:
      "don't do this; do something else."

    Attempts -- not successes -- count toward the hunt floor, so a config gap or a
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
        user_text: str = "",
    ):
        import threading
        self.floor = floor
        self._shared_state = state  # None or an Investigation instance
        self._capabilities = capabilities  # None or a Capabilities instance
        # Authoring/build turns don't triage a live alert. `find_containment_actions`
        # is DISCOVERY ("which ops could block an IP?") that a build agent
        # legitimately uses while authoring -- so the hunt-floor investigation gate
        # (no containment before N evidence calls) must not fire on it here. The
        # gate stays fully intact for triage (authoring=False). Actual staging
        # (`emit_action_card`) isn't in the build tool-slice at all, so nothing
        # containment is being STAGED -- only discovered.
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
        # Seeded from the analyst's OWN message, which is the path that fires;
        # `_is_analyst_ordered` can still set it later from a declared
        # `requested_by`, but nothing depends on the model doing so (it never
        # has -- 0 of 4 live calls). Turn-scoped: this instance is rebuilt per
        # turn, so an order never outlives the message that gave it.
        self._analyst_ordered = _detect_analyst_order(user_text)
        # Set by note_result once an approval card is successfully staged.
        # Turn-scoped like the rest of this object: a card staged on an earlier
        # turn was already answered (or expired) and must not gag the next one.
        self._action_card_staged = False
        # How many distinct evidence tools remain before the floor lifts --
        # surfaced in the block message so the model knows it's making progress.
        self._lock = threading.Lock()

    def _check_locked(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        # 0a. An approval card is staged: the ANALYST is the next actor, so the
        # agent stops acting. `emit_action_card`'s own contract is that the turn
        # halts until the user confirms or cancels -- the widget renders the card
        # and waits -- so every tool dispatched after it is work whose result no
        # one will ever see, on a turn the analyst has already been handed.
        # Measured on contain_block_ip_direct (run 20260815T160035Z): the card
        # was staged at call 14 of 26, and the eleven calls after it were TI
        # enrichment of an IP the analyst had already declared the confirmed C2.
        # Deferral, not failure: the model should close with its verdict, and an
        # `ok: false` here would read as a tool error worth retrying.
        if self._action_card_staged:
            return {
                "ok": True,
                "kind": "guard_defer",
                "action_card_staged": True,
                "directive": (
                    f"NOT RUN: `{name}` was skipped because an approval card is "
                    f"already staged for the analyst. They must approve, edit or "
                    f"cancel it before anything else runs -- you cannot act "
                    f"further on this turn. Do not call another tool. Close out "
                    f"with a short verdict describing what you staged and why."
                ),
            }
        # 0. Capability guard (§E) -- this session already learned the connector
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
                        f"Skipped: `{connector}` {why} -- you already learned "
                        f"this earlier in the session, so the call was NOT "
                        f"re-attempted. Do not retry it. Either pick a "
                        f"configured alternative (`list_configured_connectors` "
                        f"shows what IS available), or surface the gap to the "
                        f"analyst via `emit_capability_gap_card` so they can "
                        f"fix the connector and resume."
                    ),
                }
        # 1. Forbidden pivot -- external TI on an internal-only IP.
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
                            f"(RFC1918) -- {sorted(internal)[0]}. Private/internal "
                            f"addresses have no public TI reputation; enriching "
                            f"them wastes budget and pollutes the verdict. Pivot "
                            f"on internal hosts via the SIEM/CMDB context ops "
                            f"(get_ip_context / siem_search_ip) and reserve TI "
                            f"connectors for EXTERNAL, routable indicators."
                        ),
                    }
        # 2. Call-once discovery -- the set is returned in one shot PER
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
                    f"STOP calling `{name}`{scope} -- you already called it this "
                    f"session{scope} and it returns the FULL set for that "
                    f"indicator type in one shot. Do not repeat it{scope}. Act on "
                    f"the result you already have: pick an op from it and proceed. "
                    f"(A DIFFERENT target_type is allowed.)"
                ),
            }
        # 3. Hunt floor -- no containment before real investigation. Prescriptive:
        # weak models re-spam a blocked tool when told "retry later", so name the
        # ONE next call to make and forbid re-calling the blocked tool.
        # An explicit order declared on EITHER staging call covers the rest of
        # the turn. Without this, a model that correctly declares intent on
        # `find_containment_actions` (the tool whose docstring asks for it) then
        # loses the exemption on the `emit_action_card` that call exists to feed
        # -- and the order is refused one step later than before. Turn-scoped on
        # purpose: this instance is rebuilt per turn, so a declared order never
        # outlives the message that gave it.
        if _is_analyst_ordered(name, args):
            self._analyst_ordered = True
        if (name in _CONTAINMENT_STAGING_TOOLS
                and not (self._authoring and name == "find_containment_actions")
                and not self._analyst_ordered
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
                # A deferral is NOT a failure -- it is steering. The envelope
                # MUST read as "deferred, go investigate, then retry", not "this
                # call failed" (tracker #60). On the box model a deferral arrived
                # as {ok: false, error: ...} -- the same shape as an ordinary tool
                # failure -- and an ordinary failure is a good reason to end a
                # turn. That is exactly the 33% failure mode: the model read the
                # deferral as a failure and stopped. So the deferral gets its OWN
                # shape: ok: true (the guard succeeded in deferring), kind:
                # "guard_defer" (distinct from a terminal guard_redirect),
                # `directive` (not `error`), and `deferred`/`executed` flags so
                # the model can tell a deferred call from a failed one at a
                # glance. The terminal guards (forbidden pivot, call-once,
                # capability) keep the failure-shaped guard_redirect envelope.
                "ok": True,
                "kind": "guard_defer",
                "deferred": True,
                "executed": False,
                "hunt_floor_guard": True,
                "investigation_calls": self.invest_attempts,
                "required": self.floor,
                # The retry is the POINT of this guard: it defers containment,
                # it does not cancel it. Callers keep the block non-terminal for
                # exactly this reason (see the provider dispatch sites).
                "resume_call": name,
                "directive": (
                    f"Deferred, not cancelled: `{name}` was NOT executed yet. "
                    f"You've run {self.invest_attempts} of {self.floor} required "
                    f"investigation steps, and staging containment now would act "
                    f"on an alert you haven't scoped. Your NEXT call must be: "
                    f"{next_step}. Then, after ~{remaining} more evidence "
                    f"call(s), CALL `{name}` AGAIN with the same arguments -- "
                    f"that retry is required and will succeed. Do not call "
                    f"`{name}` again before those evidence calls, and do not end "
                    f"your turn without staging the card the analyst asked for."
                ),
            }
        return None

    def evaluate(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Atomic check-and-record. Returns a guard envelope (block) or None
        (allowed -- and the call is recorded as dispatched)."""
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
            if counts_as_investigation(name):
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
          ``connector_unhealthy`` marks the connector unavailable -- the next
          ``run_op`` against it short-circuits instead of re-probing.
        - ``run_op`` succeeding confirms the connector (and clears any stale
          unavailable entry -- a connector fixed mid-session works again).
        - ``list_configured_connectors`` succeeding clears ALL unavailable
          entries: it's the re-check gesture (capability-gap "Re-check &
          continue"), and a still-broken connector re-records itself on the
          next attempt anyway.
        """
        # Before the capabilities early-return: staging an approval card ends
        # the agent's half of the turn regardless of whether this session
        # tracks capabilities at all (see the guard in `_check_locked`).
        if (name == "emit_action_card" and isinstance(result, dict)
                and result.get("ok") is True):
            with self._lock:
                self._action_card_staged = True
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


# Tools whose YAML argument actually REACHES THE ANALYST: the offer/patch cards
# the widget renders, plus `push_playbook` (after which the playbook exists in
# FortiSOAR whether or not it was ever shown).
#
# `verify_playbook` / `verify_enhancement` are deliberately ABSENT, and that is
# the whole point of the distinction. They are gates: passing one means the
# bytes are good, not that anybody received them. Live shape -- a turn drafted a
# playbook, cleared `verify_playbook`, ran out of tool budget before calling
# `emit_playbook_offer`, and was then told "do not re-emit the YAML". The
# playbook was correct, verified, and invisible.
#
# `validate_yaml` / `compile_yaml` are absent for the same reason, one step
# earlier: they are the scratchpad.
#
# NOTE this list answers "did the user end up with it", which is NOT the same
# question as "what YAML did this turn produce, so I can compile it" -- the
# latter rightly includes the scratchpad tools above. Nothing currently pins
# the relationship between the two, so if a scoring-side carrier list is ever
# added, keep this one a subset of it and add a test that says so.
_DELIVERY_CARRIERS: dict[str, tuple[str, ...]] = {
    "emit_playbook_offer": ("yaml",),
    "emit_patch_proposal": ("after_yaml",),
    "push_playbook": ("yaml_text",),
}


def analyst_has_the_yaml(history: list[dict[str, Any]]) -> bool:
    """Would the user actually END UP with a playbook from this turn?

    Not "was a playbook written anywhere" -- the two come apart, and the gap is
    where the bug lives. A turn can draft YAML, push it through `validate_yaml`
    twice, and end with the analyst holding nothing, because a tool argument is
    not a deliverable. Observed live on `build_plain_request_no_record`: the
    fixed wrap-up correctly detected authoring, said "do not re-emit the YAML",
    and the playbook died inside the tool call it was validated in.

    So delivery means one of two things:
      * a fenced ```yaml block in assistant TEXT -- what the widget saves; or
      * a call to a DELIVERY carrier (see `_DELIVERY_CARRIERS`), because build
        turns are fenceless in practice and the offer card is the real product.

    Anything else -- research, validation, compilation -- is work in progress.
    """
    for msg in history:
        # ASSISTANT turns only. Tool results carry other people's playbooks --
        # `search_playbooks` returns the corpus, fenced -- and scanning every
        # role made "the model read a playbook" indistinguishable from "the
        # model wrote one". Observed: a 39-call research turn that authored
        # nothing scored as delivered, took the do-not-re-emit branch, and left
        # the analyst with a status paragraph. The user turn is excluded for
        # the same reason: YAML the analyst pasted in is input, not output.
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and extract_yaml_block(content):
            return True
        # OpenAI shape: tool calls carry a JSON-encoded arguments string.
        for call in (msg.get("tool_calls") or []):
            fn = (call or {}).get("function") or {}
            if _carries_delivery(fn.get("name"), fn.get("arguments")):
                return True
        # Anthropic shape: content is a block list with tool_use inputs.
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and extract_yaml_block(
                        str(block.get("text") or "")):
                    return True
                if block.get("type") == "tool_use" and _carries_delivery(
                        block.get("name"), block.get("input")):
                    return True
    return False


def _carries_delivery(name: Any, args: Any) -> bool:
    """True when THIS tool is a delivery carrier and its body is substantive.

    Accepts both the raw dict and the JSON string OpenAI sends. A stub body is
    ignored: `yaml_text: ""` on a probing call delivers nothing.
    """
    keys = _DELIVERY_CARRIERS.get(str(name or ""))
    if not keys:
        return False
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:  # noqa: BLE001 -- a malformed arg blob carries nothing
            return False
    if not isinstance(args, dict):
        return False
    return any(isinstance(args.get(k), str) and len(args[k].strip()) > 40
               for k in keys)


# One no-tools round is forced when the tool budget runs out, so the chat never
# just goes silent. What that round should SAY depends on whether anything was
# built, and conflating the two states is how a turn came to guarantee nothing.
_WRAPUP_HAVE_YAML = (
    "You've used the full tool-turn budget ({n} rounds) without finishing. "
    "Stop calling tools. In 2-4 sentences, tell the user: (1) what state the "
    "YAML is in (valid? warnings? errors?), (2) what specifically is left to "
    "do, and (3) one concrete next step they can take. Do not re-emit the YAML."
)

_WRAPUP_NO_YAML = (
    "You've used the full tool-turn budget ({n} rounds) and the user still has "
    "no playbook -- anything you only passed to validate_yaml does not count, "
    "they never saw it. Stop calling tools and deliver it now, from "
    "what you already know -- this is your last round, so anything you leave "
    "out the user does not get. Emit ONE complete playbook in a single ```yaml "
    "fence: every workflow, every step, no placeholders and no ellipses. Then "
    "in 1-2 sentences name what you could not verify and what to check first. "
    "A draft you flag as unverified is useful; silence is not."
)


def wrapup_directive(history: list[dict[str, Any]],
                     max_turns: int = MAX_TOOL_TURNS) -> tuple[str, int]:
    """The forced wrap-up round's directive and its token budget.

    Returns `(directive, max_tokens)`. Lives here rather than inline in each
    provider because both had their own copy of the same string, and a rule
    duplicated across providers drifts silently -- the failure then reads as a
    model difference between Frank and the box.

    The bug this fixes: the only directive that existed asked "what state is the
    YAML in?" and ended "Do not re-emit the YAML" -- sound advice when a
    playbook exists, and a guarantee of an empty turn when none does. An
    unmounted build request fans out across connector/step-type/Jinja lookups,
    exhausts all {n} rounds before authoring anything, and was then explicitly
    told not to deliver. The user asked for a playbook and got a paragraph
    about how the research went. 2/2 reproducible; the record-mounted rows are
    unaffected because grounding cuts the research roughly threefold.

    The no-YAML branch gets the FULL output ceiling, not a bespoke number. 512
    is ample for a status paragraph and 4096 is not enough for a real playbook
    either -- driven at 4096 the wrap-up delivered an unterminated ```yaml fence
    cut off mid-step, which is worse than silence because it looks like a
    deliverable. This round is an authoring round; a cap is a ceiling and not a
    spend (see DEFAULT_MAX_OUTPUT_TOKENS), so there is nothing to save by
    guessing lower.
    """
    if analyst_has_the_yaml(history):
        return _WRAPUP_HAVE_YAML.format(n=max_turns), 512
    return _WRAPUP_NO_YAML.format(n=max_turns), DEFAULT_MAX_OUTPUT_TOKENS


# ---------------------------------------------------------------------------
# Budget-ask: when the tool-turn budget runs out, ask the analyst before
# forcing wrap-up. The provider emits a `emit_choice_card` (tier 0) with the
# args from `budget_ask_card()`; the connector's _wire_transcript splices it
# into a `choice_card` event, and `_envelope_stop_reason` maps the turn to
# `awaiting_choice`. On resume:
#   - "continue" -> a fresh chat_turn with BUDGET_CONTINUE_ROUNDS extra rounds
#   - "deliver"  -> a fresh chat_turn with no tools (forced wrap-up)
# Both providers share this so the card text + options are identical.
# ---------------------------------------------------------------------------

_BUDGET_ASK_PROMPT = (
    "I've used all {n} of my tool-turn budget researching this. "
    "Would you like me to continue with more rounds, or deliver "
    "what I have so far?"
)

_BUDGET_ASK_OPTIONS = [
    {"label": "Continue with more rounds",
     "value": "continue",
     "hint": "Give the agent 8 more tool rounds to finish the work."},
    {"label": "Deliver now",
     "value": "deliver",
     "hint": "Stop researching and deliver the best draft from what was found."},
]

# Extra tool rounds granted on a "continue" resume. Deliberately less than the
# original budget: the turn was already long, and the analyst can ask again.
BUDGET_CONTINUE_ROUNDS = 8


def budget_ask_card(max_turns: int = MAX_TOOL_TURNS) -> dict[str, Any]:
    """The choice card args the provider emits at budget exhaustion.

    Returns the args dict for a `emit_choice_card` dispatch call. The provider
    dispatches this directly (tier 0) so the card lands in the transcript and
    the widget renders it. The turn ends after the card; the analyst's resume
    decision drives the next turn.
    """
    return {
        "id": "_budget_ask",
        "prompt": _BUDGET_ASK_PROMPT.format(n=max_turns),
        "options": list(_BUDGET_ASK_OPTIONS),
    }


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


# ─────────────────────── enhance-delivery guard ──────────────────────
#
# The enhance turn's terminal action -- `emit_enhancement_offer` -- is the ONLY
# thing that applies a verified edit to the playbook the analyst has open.
# System-prompt prose calls it "the MANDATORY terminal action", but a weak
# model routinely VERIFIES the edit (gets `ready_to_push: True` + a
# `verified_id`) and then, instead of calling the tool, writes a sentence like
# "Call emit_enhancement_offer with verified_id abc… to apply this" and ends
# the turn. From the analyst's seat nothing changed -- the exact live failure
# the offer tool was built to remove, resurfacing one layer up (narrated, not
# fenced). Grading it offline (`score_enhance_delivery`) catches it after the
# fact; this guard catches it structurally, in the loop, the same way the P1
# forced-assessment guard guarantees a written close.
#
# This is a DETECTOR only -- model-agnostic, no I/O. Each provider feeds it every
# executed tool result via `note_result`, and at the terminal exit asks
# `outstanding()` whether a verify passed with no offer to follow. If so the
# provider runs ONE `tool_choice`-pinned round forcing the call (and overrides
# `verified_id` with the handle recorded here, so a forced round can't deliver
# the wrong bytes). Capped at one force via `mark_forced()` so it can't loop.

# --- guard-fire telemetry ---------------------------------------------------
# Every guard forces through `mark_forced()`, so that is the one choke point
# worth counting. A guard is a compensation for the model not choosing the
# terminal tool on its own; whether it still earns its keep is an empirical
# question, and until now nothing recorded the answer. A guard that never
# fires across a corpus is dead weight that can be deleted; one that fires
# often is pointing at a description or prompt that still needs work.
#
# Process-local and best-effort, mirroring the HITL audit log
# (`tools.clear_audit_log` / `snapshot_audit_log`): callers clear before a
# turn and snapshot after. Never affects control flow.

_GUARD_FIRES: list[str] = []


def record_guard_fire(guard: str) -> None:
    """Note that `guard` forced a terminal tool call this turn."""
    _GUARD_FIRES.append(guard)


def snapshot_guard_fires() -> list[str]:
    """Guards that fired since the last clear, in order."""
    return list(_GUARD_FIRES)


def clear_guard_fires() -> None:
    _GUARD_FIRES.clear()


_ENHANCE_VERIFY_TOOL = "verify_enhancement"
_ENHANCE_OFFER_TOOL = "emit_enhancement_offer"


class EnhanceDeliveryGuard:
    """Tracks whether an enhance turn verified an edit but never delivered it.

    Fires only when the offer tool is in the advertised slice AND a
    verify_enhancement passed. Triage never advertises the offer tool. A build
    turn WITH an open playbook (enhance) advertises it; a from-scratch CREATE
    build does NOT -- the connector's _intent_drop_set drops ENHANCE_ONLY_TOOLS
    when no playbook is mounted (see fsr_playbooks.llm.intents.ENHANCE_ONLY_TOOLS).
    So the guard is inert on triage and on create, and active on enhance --
    exactly where a verified edit could be narrated instead of delivered.
    (The earlier "build-new-playbook never advertises it" claim was wrong: the
    build slice DID advertise the offer tool until that gate was added.)
    """

    def __init__(self) -> None:
        # The most recent PASSING verify's handle + a summary hint from its
        # diff. Latest wins: a turn may verify several times while iterating,
        # and only the last blessed bytes are what the analyst should get.
        self._verified_id: str | None = None
        self._summary_hint: str = ""
        self._delivered = False
        self._forced = False

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        """Fold one executed tool result into the delivery state."""
        if name == _ENHANCE_OFFER_TOOL:
            # An offer was attempted. Only a genuinely successful one counts as
            # delivery; a rejected handle (`unknown_verified_id`) still needs a
            # forced re-delivery, so leave `_delivered` False in that case.
            if not (isinstance(result, dict) and result.get("ok") is False):
                self._delivered = True
            return
        if name != _ENHANCE_VERIFY_TOOL or not isinstance(result, dict):
            return
        if result.get("ready_to_push") and result.get("verified_id"):
            self._verified_id = str(result["verified_id"])
            diff = result.get("diff_summary")
            if isinstance(diff, dict) and diff.get("summary"):
                self._summary_hint = str(diff["summary"])

    def outstanding(self, allowed_names: set[str]) -> str | None:
        """The verified_id that a passing verify blessed but no offer applied,
        or None. Returns None once forced, so the guard fires at most once."""
        if _ENHANCE_OFFER_TOOL not in allowed_names:
            return None
        if self._forced or self._delivered or not self._verified_id:
            return None
        return self._verified_id

    @property
    def summary_hint(self) -> str:
        return self._summary_hint

    def mark_forced(self) -> None:
        self._forced = True
        record_guard_fire(type(self).__name__)


# ─────────────────────── create-delivery guard ───────────────────────
#
# The CREATE counterpart to EnhanceDeliveryGuard, and it exists for the same
# reason: `emit_playbook_offer` is the mandatory terminal action of a
# from-scratch build turn -- the card is what carries the YAML and gives the
# analyst the one-click "Save as Playbook" CTA. A weak model routinely runs the
# research tools, passes `verify_playbook`, and then writes "Next, I will author
# a playbook that ..." and ends the turn. From the analyst's seat the chat
# produced prose and no card, so there is nothing to accept -- the exact failure
# the enhance guard already fixes one path over.
#
# This was an ASYMMETRY, not a design: the enhance guard's docstring notes it is
# "inert on triage and on create", and nothing covered create. Live on the box
# the same prompt would sometimes deliver the card and sometimes narrate,
# because only the model's whim decided it.
#
# Same contract as the enhance guard: detector only, no I/O, fires at most once
# via `mark_forced()`. The provider runs ONE `tool_choice`-pinned round and
# overrides `yaml` with the bytes the gate actually blessed, so a forced round
# can't ship YAML that never passed verify.

_CREATE_VERIFY_TOOL = "verify_playbook"
_CREATE_OFFER_TOOL = "emit_playbook_offer"


class CreateDeliveryGuard:
    """Tracks whether a build turn verified a NEW playbook but never offered it.

    Fires only when `emit_playbook_offer` is in the advertised slice AND a
    `verify_playbook` returned `ready_to_push`. The triage slice advertises the
    offer tool too (its trace-compiled close), but triage never calls
    `verify_playbook`, so the guard stays inert there -- it needs BOTH halves of
    the pair.
    """

    def __init__(self) -> None:
        # Bytes from the most recent PASSING verify. Latest wins: a build turn
        # commonly verifies, repairs, and re-verifies, and only the last blessed
        # YAML is what the analyst should be offered.
        self._verified_yaml: str | None = None
        self._summary_hint: str = ""
        self._delivered = False
        self._forced = False

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        """Fold one executed tool result into the delivery state."""
        if name == _CREATE_OFFER_TOOL:
            # Only a genuinely successful offer counts as delivery; a rejected
            # one still needs forcing, so leave `_delivered` False there.
            if not (isinstance(result, dict) and result.get("ok") is False):
                self._delivered = True
            return
        if name != _CREATE_VERIFY_TOOL or not isinstance(result, dict):
            return
        if not result.get("ready_to_push"):
            return
        # The blessed bytes are the ones that went IN to verify -- the result is
        # a punch list, not the document.
        yaml_text = args.get("yaml_text") or args.get("yaml")
        if isinstance(yaml_text, str) and yaml_text.strip():
            self._verified_yaml = yaml_text
            summary = result.get("summary")
            if isinstance(summary, str) and summary:
                self._summary_hint = summary

    def outstanding(self, allowed_names: set[str]) -> str | None:
        """The verified YAML a passing verify blessed but no offer delivered,
        or None. Returns None once forced, so the guard fires at most once."""
        if _CREATE_OFFER_TOOL not in allowed_names:
            return None
        if self._forced or self._delivered or not self._verified_yaml:
            return None
        return self._verified_yaml

    @property
    def summary_hint(self) -> str:
        return self._summary_hint

    def mark_forced(self) -> None:
        self._forced = True
        record_guard_fire(type(self).__name__)


# ─────────────────────── build-progress guard ────────────────────────
#
# The failure the delivery guards CANNOT catch: a build turn that researches
# and then never drafts. Live on .159 (connector 0.5.65, fsr_playbooks 0.6.5,
# gpt-4.1-mini) a "build me a playbook that ..." turn ran
#
#     get_step_type x4 -> find_connector x3 -> find_operation x2 -> get_op_schema x2
#
# and ended with prose ("Next, I will author a playbook that ...") -- no
# validate_yaml, no verify_playbook, no offer. 11 tool calls of pure research
# against a 16-call budget, so it did not run out of turns; it just stopped.
#
# CreateDeliveryGuard is correctly inert here: with no passing verify there are
# no blessed bytes, and forcing an offer would hand the analyst UNVERIFIED YAML
# -- the precise thing that guard exists to prevent. So this is a distinct
# problem with a distinct fix. It is not a delivery failure (nothing was ready
# to deliver); it is a PROGRESS failure -- the turn never entered the authoring
# half of the loop at all.
#
# Hence: don't force the terminal action, force the NEXT one. The provider
# injects a directive and CONTINUES the loop rather than terminating, so the
# model drafts -> verifies -> offers naturally, with CreateDeliveryGuard still
# backstopping the delivery end. Fires at most once per turn.

# Tools that prove a turn actually entered the authoring half of the loop.
_AUTHORING_PROGRESS_TOOLS = frozenset({
    "validate_yaml", "compile_yaml", "verify_playbook",
    "emit_playbook_offer", "build_playbook_from_trace",
    # Enhance authors too -- its own pair means the turn is not stalled.
    "verify_enhancement", "emit_enhancement_offer", "emit_patch_proposal",
})

# Tools that mean the analyst asked to RUN or DIAGNOSE an existing playbook, not
# to author a new one. This is load-bearing, not defensive, and it is now the
# ONLY thing covering that case.
#
# There used to be a second mechanism ("Lever 2"): an LLM call per build turn
# classified run-vs-author and narrowed the slice to `run_playbook` alone. It
# was deleted because it never actually carried the case it was written for --
# it failed OPEN to normal build behavior, and was observed doing exactly that
# live ("Run the Link Similar Alerts playbook." kept the full build slice and
# called find_connector / list_playbook_runs / find_operation). This check was
# written for that fail-open path, i.e. for the common case, so removing the
# classifier removes a per-turn LLM round-trip and no protection.
#
# On the full build slice, without this check, a RUN request gets nudged to
# "draft the full playbook YAML now" -- authoring something nobody asked for,
# which is worse than the stall being fixed.
_RUN_INTENT_TOOLS = frozenset({
    "run_playbook", "list_playbook_runs", "why_did_playbook_fail",
    "get_run_env", "dry_run_playbook", "step_through_playbook",
    "diagnose_yaml_against_pb_execution",
})


class BuildProgressGuard:
    """Tracks a build turn that ran only research tools and never authored.

    Fires only when the slice is genuinely a BUILD slice (it advertises
    `emit_playbook_offer` AND `verify_playbook`) and at least one tool ran. A
    turn that ran no tools at all is a conversational reply, not a stalled
    build, and forcing YAML out of "what can you do?" would be worse than the
    bug -- so `outstanding()` requires prior tool use.
    """

    def __init__(self) -> None:
        self._any_tool = False
        self._authored = False
        self._run_intent = False
        self._forced = False

    def note_result(self, name: str, args: dict[str, Any], result: Any) -> None:
        self._any_tool = True
        if name in _AUTHORING_PROGRESS_TOOLS:
            self._authored = True
        if name in _RUN_INTENT_TOOLS:
            self._run_intent = True

    def outstanding(self, allowed_names: set[str]) -> bool:
        """True when a build turn is ending with research but no authoring."""
        if _CREATE_OFFER_TOOL not in allowed_names:
            return False
        if _CREATE_VERIFY_TOOL not in allowed_names:
            return False
        # Both providers treat "emit_action_card is advertised" as "this is a
        # triage turn" (`_authoring = "emit_action_card" not in allowed_names`).
        # Reuse that one discriminator rather than inventing a second: when a
        # caller passes NO tool slice the providers substitute the FULL registry,
        # which advertises the build pair AND emit_action_card -- and a
        # research-heavy triage turn on that slice would otherwise be nudged to
        # go author YAML it was never asked for.
        if "emit_action_card" in allowed_names:
            return False
        if self._forced or self._authored or not self._any_tool:
            return False
        # A run/diagnose turn is not a stalled build -- see _RUN_INTENT_TOOLS.
        if self._run_intent:
            return False
        return True

    def mark_forced(self) -> None:
        self._forced = True
        record_guard_fire(type(self).__name__)
