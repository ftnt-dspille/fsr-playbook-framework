#!/usr/bin/env python3
"""Manual OpenAI-path smoke test: drives OpenAIProvider directly (no
FortiSOAR) and prints each streamed event with a wall-clock offset so you
can SEE text arriving incrementally rather than all at once on completion.

Works against the real OpenAI API or any OpenAI-compatible endpoint
(LM Studio, vLLM, Ollama `/v1`, Together, Groq, …).

Usage:
    # real OpenAI
    OPENAI_API_KEY=sk-... python scripts/try_openai_stream.py "say hi in 5 words"

    # local, no real key needed (LM Studio default)
    OPENAI_API_KEY=lm-studio \
    OPENAI_BASE_URL=http://localhost:1234/v1 \
    OPENAI_MODEL=local-model \
    python scripts/try_openai_stream.py "say hi in 5 words"

A PASS prints multiple `text` events with increasing time offsets (live
streaming) and ends with a `done`/usage line.
"""
import asyncio
import os
import sys
import time

from fsr_core.llm.openai_provider import OpenAIProvider
from fsr_core.llm.provider import (
    DoneEvent, ErrorEvent, Message, TextEvent, ToolUseEvent,
    ToolResultEvent, UsageEvent,
)


async def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "List three colors, one per line."
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY not set — point at OpenAI or a local /v1 endpoint.")
        return 2
    provider = OpenAIProvider(
        model=os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        api_key=key,
    )
    print(f">> model={provider.model} base_url={os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}")
    print(f">> prompt: {prompt}\n")

    t0 = time.monotonic()
    text_events = 0
    last_text_t = None

    async for ev in provider.stream(
        system="You are a terse assistant.",
        messages=[Message(role="user", content=prompt)],
        tools=[],
    ):
        dt = time.monotonic() - t0
        if isinstance(ev, TextEvent):
            text_events += 1
            last_text_t = dt
            sys.stdout.write(f"[{dt:6.2f}s] text: {ev.text!r}\n")
            sys.stdout.flush()
        elif isinstance(ev, ToolUseEvent):
            print(f"[{dt:6.2f}s] tool_use: {ev.name}")
        elif isinstance(ev, ToolResultEvent):
            print(f"[{dt:6.2f}s] tool_result (call {ev.call_id})")
        elif isinstance(ev, UsageEvent):
            print(f"[{dt:6.2f}s] usage: in={ev.input_tokens} out={ev.output_tokens} stop={ev.stop_reason}")
        elif isinstance(ev, DoneEvent):
            print(f"[{dt:6.2f}s] done: stop={ev.stop_reason}")
        elif isinstance(ev, ErrorEvent):
            print(f"[{dt:6.2f}s] ERROR: {ev.message}")

    print(f"\n>> {text_events} text event(s); last text at {last_text_t}s")
    if text_events >= 2:
        print(">> PASS: text streamed incrementally (live).")
        return 0
    print(">> note: <2 text events — short answer or non-streaming endpoint; "
          "check the offsets above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
