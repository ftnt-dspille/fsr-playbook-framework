"""Replayed conversation history in each provider's native shape.

A caller that replays earlier turns hands the provider `Message`s whose
content is an Anthropic-style block list -- `text`, `tool_use` (with an `id`)
on an assistant turn, `tool_result` (with the matching `tool_use_id`) on the
user turn that follows. That is the provider-neutral form documented on
`Message`; the Anthropic provider sends it as-is and the OpenAI-compatible
providers translate it here.

Why replay calls natively at all: a model reads structured call/result pairs
as things that happened and answers with a real call. The same history
flattened to text (`[called edit_playbook(...)]`) teaches it that writing that
string IS calling a tool, and it starts writing the string instead of making
the call -- observed on a three-turn refine, 3 of 4 runs.

A list whose dicts carry a `role` is NOT block content: it is the
OpenAI-shaped carrier the providers append to their own in-loop history, and
it passes through untouched.
"""

from __future__ import annotations

import json
from typing import Any

_BLOCK_TYPES = frozenset({"text", "tool_use", "tool_result"})


def is_block_content(content: Any) -> bool:
    """True for an Anthropic-style block list (no per-item `role`)."""
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and "role" not in b
               and b.get("type") in _BLOCK_TYPES for b in content)


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # Anthropic nested text blocks
        parts = [str(b.get("text") or "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        if parts:
            return "\n".join(parts)
    return json.dumps(content, default=str)


def blocks_to_openai(role: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One block-list Message as OpenAI chat messages.

    assistant -> one message with `tool_calls` (text joined into `content`);
    user -> one `role: tool` message per tool_result, in order, then any text
    as a user message. Tool messages must directly follow the assistant
    message that called them, which is why results come before text."""
    if role == "assistant":
        text = "\n".join(str(b.get("text") or "") for b in blocks
                         if b.get("type") == "text" and b.get("text"))
        calls = [{
            "id": str(b.get("id") or ""),
            "type": "function",
            "function": {"name": str(b.get("name") or ""),
                         "arguments": json.dumps(b.get("input") or {}, default=str)},
        } for b in blocks if b.get("type") == "tool_use"]
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = calls
        elif not text:
            return []
        return [msg]
    out: list[dict[str, Any]] = [
        {"role": "tool", "tool_call_id": str(b.get("tool_use_id") or ""),
         "content": _result_text(b.get("content"))}
        for b in blocks if b.get("type") == "tool_result"]
    text = "\n".join(str(b.get("text") or "") for b in blocks
                     if b.get("type") == "text" and b.get("text"))
    if text:
        out.append({"role": role, "content": text})
    return out


def blocks_to_prose(role: str, blocks: list[dict[str, Any]]) -> str:
    """One block-list Message as plain text, for a transport with no native
    tool turns. Deliberately NOT call-shaped: the tools a turn used are named
    in a sentence a model cannot mistake for the syntax of a call. Tool
    results are dropped -- without the call they answer they are noise."""
    text = [str(b.get("text") or "") for b in blocks
            if b.get("type") == "text" and b.get("text")]
    if role == "assistant":
        names: list[str] = []
        for b in blocks:
            name = str(b.get("name") or "")
            if b.get("type") == "tool_use" and name and name not in names:
                names.append(name)
        if names:
            text.append("(Tools used in this reply: " + ", ".join(names) + ".)")
    return "\n".join(text)
