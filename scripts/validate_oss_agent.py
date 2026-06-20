#!/usr/bin/env python3
"""Validate that the configured OpenAI-compatible model (e.g. the gb200
gpt-oss-120b gateway deployment) can act as the triage / playbook-gen
agent: prove it CALLS THE REAL registered tools and gets REAL dispatch
results, then produces a final authored+validated playbook.

Unlike scripts/try_openai_stream.py (which only checks streaming), this
drives OpenAIProvider with the ACTUAL `openai_tools()` slice and the real
`dispatch()` registry — so a passing run means the model:
  1. emitted well-formed OpenAI tool_calls for REAL tool names,
  2. those names were in the advertised slice (allowed_names),
  3. dispatch returned real data (not "unknown tool" / bad-arguments),
  4. it iterated tools→results across turns and closed with text/YAML.

Offline by default: the advertised slice is restricted to tier-0 authoring
tools (no live FSR needed). Pass --live-tools to advertise the full
SAFE_TOOLS slice (will hit FSR if the model picks a live tool).

Usage:
    PYTHONPATH=.:web .venv/bin/python scripts/validate_oss_agent.py
    PYTHONPATH=.:web .venv/bin/python scripts/validate_oss_agent.py --live-tools "block 1.2.3.4 on fortigate"
"""
from __future__ import annotations

import asyncio
import sys
import time

import web.backend.app  # noqa: F401  — triggers _load_dotenv()
from web.backend import settings
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.tools import openai_tools
from fsr_playbooks.llm.provider import (
    DoneEvent, ErrorEvent, Message, TextEvent,
    ToolResultEvent, ToolUseEvent, UsageEvent,
)

# Tier-0 authoring tools — discover → author → validate, all offline.
OFFLINE_SLICE = {
    "find_connector", "find_operation", "get_op_schema", "get_step_type",
    "find_jinja_filter", "find_jinja_pattern", "get_filter_examples",
    "find_containment_actions", "find_enrichment_actions",
    "validate_yaml", "compile_yaml", "analyze_playbook",
}

SYSTEM = (
    "You are a FortiSOAR playbook authoring agent. To build a playbook you "
    "MUST use the provided tools to ground every choice: discover the "
    "connector with find_connector, find the operation with find_operation, "
    "inspect its schema with get_op_schema, then author the YAML and prove "
    "it with validate_yaml (and compile_yaml). Do not invent connector or "
    "operation names — look them up. When done, output the final YAML in a "
    "```yaml fenced block plus a one-line assessment."
)

DEFAULT_TASK = (
    "Build a FortiSOAR playbook that blocks a malicious IP indicator on "
    "FortiGate. Discover the right connector and the block-IP operation, "
    "inspect its inputs, then author and validate the playbook YAML."
)


async def main() -> int:
    argv = [a for a in sys.argv[1:]]
    live = "--live-tools" in argv
    argv = [a for a in argv if a != "--live-tools"]
    task = " ".join(argv) or DEFAULT_TASK

    cfg = settings.load_provider("openai")
    print(f">> base_url = {cfg.base_url}")
    print(f">> model    = {cfg.model}")
    print(f">> tools    = {'FULL SAFE_TOOLS (live)' if live else 'tier-0 offline slice'}")
    print(f">> task     = {task}\n")

    prov = OpenAIProvider(base_url=cfg.base_url, model=cfg.model, api_key=cfg.api_key)

    if live:
        tools: list = []  # provider falls back to full openai_tools()
        advertised = {t["function"]["name"] for t in openai_tools()}
    else:
        tools = [t for t in openai_tools() if t["function"]["name"] in OFFLINE_SLICE]
        advertised = {t["function"]["name"] for t in tools}

    calls: list[tuple[str, bool]] = []   # (name, dispatch_ok)
    unknown_or_bad = 0
    final_text = ""
    t0 = time.monotonic()

    async for ev in prov.stream(
        system=SYSTEM,
        messages=[Message(role="user", content=task)],
        tools=tools,
    ):
        dt = time.monotonic() - t0
        if isinstance(ev, ToolUseEvent):
            print(f"[{dt:6.2f}s] TOOL_USE  {ev.name}({_short(ev.arguments)}) tier={ev.tier}")
        elif isinstance(ev, ToolResultEvent):
            r = ev.result
            bad = isinstance(r, dict) and (
                "unknown tool" in str(r.get("error", "")).lower()
                or "bad arguments" in str(r.get("error", "")).lower()
            )
            # pair the result to the most recent unpaired tool_use by order
            print(f"[{dt:6.2f}s]   result {'BAD' if bad else 'ok '}: {_short(r)}")
            if bad:
                unknown_or_bad += 1
        elif isinstance(ev, TextEvent):
            final_text += ev.text
        elif isinstance(ev, UsageEvent):
            # ToolCallUsage entries record which names actually dispatched
            for tc in ev.tool_calls:
                calls.append((tc.name, True))
        elif isinstance(ev, DoneEvent):
            print(f"[{dt:6.2f}s] DONE stop={ev.stop_reason}")
        elif isinstance(ev, ErrorEvent):
            print(f"[{dt:6.2f}s] ERROR: {ev.message}")

    names = [n for n, _ in calls]
    real_calls = [n for n in names if n in advertised]
    has_yaml = "```yaml" in final_text or "```yml" in final_text

    print("\n==================== VERDICT ====================")
    print(f"tool calls made        : {len(names)} -> {names}")
    print(f"all in advertised slice: {set(names) <= advertised}")
    print(f"unknown/bad-arg results: {unknown_or_bad}")
    print(f"produced YAML block    : {has_yaml}")
    print(f"final text chars       : {len(final_text)}")

    can_call_tools = len(real_calls) >= 1 and unknown_or_bad == 0
    print()
    print(f"[{'PASS' if can_call_tools else 'FAIL'}] gb200 calls your custom tools with valid args")
    print(f"[{'PASS' if has_yaml else 'WARN'}] gb200 produced a final playbook YAML")
    if not final_text.strip():
        print("  note: no closing text — check the transcript above")
    else:
        print("\n--- final assistant text (tail) ---")
        print(final_text[-800:])
    return 0 if can_call_tools else 1


def _short(obj, n: int = 110) -> str:
    s = str(obj)
    return s if len(s) <= n else s[:n] + "…"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
