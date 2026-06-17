"""LM Studio (OpenAI-compatible) provider — streaming chat with tool use.

Same agent loop shape as AnthropicProvider, just translated to the
OpenAI Chat Completions wire format. Works against any OpenAI-compatible
endpoint (LM Studio, vLLM, Ollama-OpenAI, OpenAI proper) — the only
LM-Studio-specific bit is the default base_url and a permissive default
api_key (LM Studio's local server ignores it).

Tool-call streaming wrinkle: OpenAI delivers `tool_calls` as incremental
deltas keyed by `index`, with `function.arguments` arriving as
fragmented JSON-string chunks. We accumulate per-index and json.loads
once the chunk stream signals `finish_reason='tool_calls'`.

Usage tokens only show up in the final empty chunk when
`stream_options.include_usage=True`. Cache fields don't exist locally —
emit zeros, our UsageEvent schema tolerates that.
"""
from __future__ import annotations

import json
import os
import uuid as _uuid
from typing import Any, AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
)

from ._loop_helpers import (
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    compile_errors as _compile_errors,
    extract_yaml_block as _extract_yaml_block,
)
from .provider import (
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from .tools import dispatch, openai_tools


DEFAULT_BASE_URL = os.environ.get(
    "STUDIO_LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
)
DEFAULT_MODEL = os.environ.get("STUDIO_LMSTUDIO_MODEL", "")
# LM Studio's local server requires *something* in the api_key field but
# never validates it. A literal placeholder is the canonical thing to send.
DEFAULT_API_KEY = os.environ.get("STUDIO_LMSTUDIO_API_KEY", "lm-studio")


def _to_openai_messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    """Translate the route's normalized Messages into OpenAI chat shape.

    The chat route always feeds plain-string user/assistant turns, so the
    translation is a one-liner per message. Internal turns we append
    during the loop are already in OpenAI shape and get passed through
    untouched (Message.content is a list[dict] there)."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        else:
            # Already an OpenAI-shaped dict (assistant w/ tool_calls, or
            # tool result message). Trust it.
            for block in m.content:
                out.append(block)  # type: ignore[arg-type]
    return out


class LMStudioProvider:
    name = "lmstudio"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        client: AsyncOpenAI | None = None,
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL
        self._client = client or AsyncOpenAI(
            base_url=self.base_url, api_key=self.api_key, timeout=120.0
        )

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
    ) -> AsyncIterator[Event]:
        if not self.model:
            yield ErrorEvent(message="No LM Studio model selected — pick one in Settings.")
            return

        history = _to_openai_messages(system, messages)
        self_repair_turns = 0
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        tags = tags or {}
        if not tools:
            tools = openai_tools()

        for _turn in range(MAX_TOOL_TURNS):
            turn_idx += 1
            try:
                history_chars = len(json.dumps(history, default=str))
            except Exception:
                history_chars = 0

            text_buf = ""
            # tool_calls indexed by `.index` (an int the API uses to
            # disambiguate parallel calls). Each value is built up over
            # multiple chunks: id arrives once, name once, arguments
            # streams in fragments.
            tool_buf: dict[int, dict[str, Any]] = {}
            finish_reason: str | None = None
            input_tok = 0
            output_tok = 0

            try:
                stream = await self._client.chat.completions.create(
                    model=self.model,
                    messages=history,
                    tools=tools,
                    stream=True,
                    max_tokens=4096,
                    stream_options={"include_usage": True},
                )
                async for chunk in stream:
                    # The final usage chunk has empty choices.
                    if chunk.usage is not None:
                        input_tok = chunk.usage.prompt_tokens or 0
                        output_tok = chunk.usage.completion_tokens or 0
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if delta and delta.content:
                        text_buf += delta.content
                        yield TextEvent(text=delta.content)
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            slot = tool_buf.setdefault(
                                tc.index, {"id": "", "name": "", "args": ""}
                            )
                            if tc.id:
                                slot["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    slot["name"] = tc.function.name
                                if tc.function.arguments:
                                    slot["args"] += tc.function.arguments
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            except Exception as e:
                yield ErrorEvent(message=_friendly_error(e, self.base_url))
                return

            # Assemble the assistant message we just streamed and append
            # to history so the next turn sees it.
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if text_buf:
                assistant_msg["content"] = text_buf
            else:
                # OpenAI requires content to be present (can be null) on
                # tool-call assistant turns.
                assistant_msg["content"] = None
            tool_calls_for_msg: list[dict[str, Any]] = []
            for idx in sorted(tool_buf.keys()):
                slot = tool_buf[idx]
                tool_calls_for_msg.append({
                    "id": slot["id"] or f"call_{session_id}_{turn_idx}_{idx}",
                    "type": "function",
                    "function": {
                        "name": slot["name"],
                        "arguments": slot["args"] or "{}",
                    },
                })
            if tool_calls_for_msg:
                assistant_msg["tool_calls"] = tool_calls_for_msg
            history.append(assistant_msg)

            tool_call_usage: list[ToolCallUsage] = []
            stop_reason = finish_reason or ""

            if not tool_calls_for_msg or finish_reason != "tool_calls":
                # No tool calls → terminal turn. Try self-repair on the
                # YAML block in the assistant text (capped). Same logic
                # as the Anthropic loop.
                if self_repair_turns < MAX_SELF_REPAIR_TURNS and text_buf:
                    yaml_block = _extract_yaml_block(text_buf)
                    if yaml_block:
                        errors_text = _compile_errors(yaml_block)
                        if errors_text:
                            self_repair_turns += 1
                            history.append({
                                "role": "user",
                                "content": (
                                    "The YAML you just produced doesn't compile. "
                                    "Fix the errors and emit a corrected fenced "
                                    "```yaml block.\n\nErrors:\n" + errors_text
                                ),
                            })
                            yield UsageEvent(
                                session_id=session_id, turn=turn_idx, model=self.model,
                                input_tokens=input_tok, output_tokens=output_tok,
                                cache_read=0, cache_write=0,
                                history_chars=history_chars,
                                stop_reason=stop_reason,
                                self_repair_turn=self_repair_turns - 1,
                                tool_calls=tool_call_usage, tags=tags,
                            )
                            continue
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=0, cache_write=0,
                    history_chars=history_chars,
                    stop_reason=stop_reason,
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                )
                yield DoneEvent(stop_reason=stop_reason or "stop")
                return

            # Dispatch tool calls and append per-tool messages.
            for tc in tool_calls_for_msg:
                call_id = tc["id"]
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"] or "{}"
                try:
                    args = json.loads(raw_args)
                    if not isinstance(args, dict):
                        args = {}
                except Exception:
                    args = {}
                yield ToolUseEvent(name=name, arguments=args, call_id=call_id)
                result = dispatch(name, args)
                yield ToolResultEvent(call_id=call_id, result=result)
                content_str = _stringify(result)
                history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content_str,
                })
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars,
                    result_chars=len(content_str),
                ))

            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=0, cache_write=0,
                history_chars=history_chars,
                stop_reason=stop_reason or "tool_calls",
                self_repair_turn=self_repair_turns,
                tool_calls=tool_call_usage, tags=tags,
            )

        yield DoneEvent(stop_reason="max_tool_turns")


def _stringify(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


def _friendly_error(e: Exception, base_url: str) -> str:
    if isinstance(e, AuthenticationError):
        return "API key rejected by the LLM endpoint."
    if isinstance(e, APIConnectionError):
        return (f"Could not reach the LLM at {base_url} — is LM Studio "
                f"running with the local server enabled?")
    if isinstance(e, APITimeoutError):
        return "The LLM endpoint timed out. Try again, or shorten the prompt."
    if isinstance(e, BadRequestError):
        return f"LLM endpoint rejected the request: {getattr(e, 'message', str(e))[:200]}"
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", "?")
        return f"LLM endpoint returned HTTP {status}."
    return f"{type(e).__name__}: {e}"
