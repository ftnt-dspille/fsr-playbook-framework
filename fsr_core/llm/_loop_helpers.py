"""Pieces shared between the Anthropic and LM Studio agent loops.

Kept here (not in `provider.py`) because they're implementation details
of the loop, not part of the protocol contract a future provider has to
honor. A new provider can opt in to self-repair by importing these.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
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
        from fsr_core.compiler import compile_yaml as _cy  # type: ignore
    except Exception as e:
        return f"compiler import failed: {e}"

    db = Path(__file__).resolve().parents[2] / "store" / "fsr_reference.db"
    res = _cy(yaml_text, db)
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
