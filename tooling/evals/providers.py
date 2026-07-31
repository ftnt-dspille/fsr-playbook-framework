"""Pluggable LLM callables for the eval harness.

A *provider* is a `Callable[[str, str], str]` returning the candidate
YAML for `(system_prompt, user_prompt)`. Real LLM providers (Anthropic,
OpenAI, LMStudio) sit behind the same interface as deterministic test
providers (echo / gold) so the harness CSV always has a "perfect"
control row to compare against.

Adding a new model: register a factory under a name and the harness
picks it up via `--models name1,name2,...`.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Iterable

ProviderFn = Callable[[str, str], str]

_YAML_FENCE = re.compile(r"```(?:yaml)?\s*\n(.*?)```", re.DOTALL)


def extract_yaml(text: str) -> str:
    """Pull a fenced ```yaml block out of an LLM response, falling back
    to the raw text if no fence is present (some local models forget)."""
    m = _YAML_FENCE.search(text or "")
    return (m.group(1) if m else text).strip()


# ---------------------------------------------------------------------------
# Deterministic providers (always available)
# ---------------------------------------------------------------------------

def gold_provider(gold_lookup: Callable[[str], str | None]) -> ProviderFn:
    """Returns the task's gold YAML verbatim -- a control row showing
    "the harness would score 4/4 if a model produced perfect output."

    `gold_lookup(prompt)` should return the gold YAML for the matching
    task, or None.
    """
    def _call(system: str, prompt: str) -> str:
        gold = gold_lookup(prompt)
        return gold if gold is not None else ""
    return _call


def echo_provider(system: str, prompt: str) -> str:  # noqa: ARG001
    """Always returns an empty playbook -- proves the harness scores
    failures cleanly. Useful as a smoke test in CI."""
    return "collection: Echo\nplaybooks: []\n"


# ---------------------------------------------------------------------------
# Real provider stubs -- wired only when the corresponding env / SDK is
# available. The harness never imports these eagerly so a missing key
# doesn't break offline runs.
# ---------------------------------------------------------------------------

def _anthropic_provider() -> ProviderFn:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    import anthropic  # type: ignore[import-not-found]
    client = anthropic.Anthropic()
    model = os.environ.get("EVAL_ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def _call(system: str, prompt: str) -> str:
        resp = client.messages.create(
            model=model, max_tokens=4096, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        chunks = [c.text for c in resp.content if getattr(c, "type", "") == "text"]
        return "\n".join(chunks)
    return _call


def _openai_provider() -> ProviderFn:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")
    from openai import OpenAI  # type: ignore[import-not-found]
    client = OpenAI()
    model = os.environ.get("EVAL_OPENAI_MODEL", "gpt-4o-mini")

    def _call(system: str, prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""
    return _call


def _lmstudio_provider() -> ProviderFn:
    """Local LMStudio via its OpenAI-compatible REST API.

    Uses `LMSTUDIO_BASE_URL` (default http://localhost:1234/v1) +
    `LMSTUDIO_MODEL` to talk to whatever model is currently loaded.
    """
    base_url = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    model = os.environ.get("LMSTUDIO_MODEL", "local-model")
    import requests  # type: ignore[import-untyped]

    def _call(system: str, prompt: str) -> str:
        r = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
    return _call


# ---------------------------------------------------------------------------
# Agentic providers -- full tool-use loop with the same MCP tool registry the
# Studio chat uses. Output is a dict {text, trace, turns} so the harness can
# score tool-budget / no-spiral / adherence empirically. The harness detects
# the dict return and routes it through the agentic gates.
# ---------------------------------------------------------------------------

# Cap on tool-use turns per agentic eval task. Mirrors MAX_TOOL_TURNS in
# web/backend/llm/_loop_helpers.py -- the eval provider should hit the same
# wall the chat path hits, so a runaway scoring config matches production.
_AGENTIC_MAX_TURNS = 12


# Per-task tool-slice override, set by the harness around each cell (see
# `tools_for_intent`). None = advertise the full SAFE_TOOLS registry, which is
# what every pre-existing task has always run under. Phase 1.2 needs this
# because the tool-selection number is only meaningful against the surface the
# user actually hits -- the connector serves an intent slice, not the registry.
_TOOL_SLICE: list[str] | None = None


def set_tool_slice(intent: str | None) -> None:
    """Restrict the advertised tools to `intents.tools_for_intent(intent)`.

    Pass None to restore the full registry. Resolved to names here (not tool
    dicts) so the provider keeps ownership of the cache_control marker."""
    global _TOOL_SLICE
    if intent is None:
        _TOOL_SLICE = None
        return
    from fsr_playbooks.llm.intents import tools_for_intent  # type: ignore
    _TOOL_SLICE = [t["name"] for t in tools_for_intent(intent)]


def _import_studio_tools():
    """Pull the same SAFE_TOOLS registry the chat backend uses, so agentic
    evals exercise the exact tool surface end users hit. Also returns
    the HITL audit-log helpers so the agentic providers can snapshot
    per-task escalation behavior."""
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    backend = repo / "web" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from fsr_playbooks.llm.tools import (  # type: ignore
        anthropic_tools, openai_tools, dispatch,
        clear_audit_log, snapshot_audit_log, set_eval_policy,
    )
    return (anthropic_tools, openai_tools, dispatch,
            clear_audit_log, snapshot_audit_log, set_eval_policy)


def _agentic_anthropic_provider() -> Callable:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    import anthropic  # type: ignore[import-not-found]
    import json as _json
    client = anthropic.Anthropic()
    model = os.environ.get("EVAL_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    anthropic_tools, _, dispatch, _clr, _snap, _set_pol = _import_studio_tools()
    raw_tools = anthropic_tools()

    def _tools_now() -> list[dict]:
        # Resolved per call so a per-task slice (set_tool_slice) applies.
        # Unsliced runs rebuild an identical list, so the prompt-cache
        # breakpoint below still hits across tasks.
        picked = ([t for t in raw_tools if t["name"] in _TOOL_SLICE]
                  if _TOOL_SLICE is not None else raw_tools)
        # Cache the tool list -- mark the last entry so the cache breakpoint
        # includes every preceding tool def.
        out = [dict(t) for t in picked]
        if out:
            out[-1] = {**out[-1], "cache_control": {"type": "ephemeral"}}
        return out

    def _call(system: str, prompt: str) -> dict:
        tools = _tools_now()
        # Anthropic accepts `system` as either a string or a list of
        # content blocks; the block form is required to attach
        # cache_control. Static across the whole eval run.
        system_blocks = [{
            "type": "text", "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
        history: list[dict] = [{"role": "user", "content": prompt}]
        trace: list[dict] = []
        text_chunks: list[str] = []
        usage_log: list[dict] = []
        turns = 0
        for _ in range(_AGENTIC_MAX_TURNS):
            turns += 1
            resp = client.messages.create(
                model=model, max_tokens=4096, system=system_blocks,
                messages=history, tools=tools,
            )
            u = getattr(resp, "usage", None)
            if u is not None:
                usage_log.append({
                    "input_tokens": getattr(u, "input_tokens", 0),
                    "output_tokens": getattr(u, "output_tokens", 0),
                    "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
                })
            assistant_blocks: list[dict] = []
            tool_uses: list[tuple[str, str, dict]] = []
            for b in resp.content:
                if b.type == "text":
                    assistant_blocks.append({"type": "text", "text": b.text})
                    text_chunks.append(b.text)
                elif b.type == "tool_use":
                    assistant_blocks.append({
                        "type": "tool_use", "id": b.id,
                        "name": b.name, "input": dict(b.input),
                    })
                    tool_uses.append((b.id, b.name, dict(b.input)))
            history.append({"role": "assistant", "content": assistant_blocks})
            if resp.stop_reason != "tool_use" or not tool_uses:
                break
            tool_results: list[dict] = []
            for call_id, name, args in tool_uses:
                result = dispatch(name, args)
                content = result if isinstance(result, str) else _json.dumps(
                    result, default=str)
                entry: dict[str, Any] = {
                    "name": name,
                    "args": args,
                    "args_chars": len(_json.dumps(args, default=str)),
                    "result_chars": len(content),
                }
                # Result envelope flags so the investigation-recall scorer
                # (and partial-failure assertions) can see what each pivot
                # returned without re-running it.
                if isinstance(result, dict):
                    entry["ok"] = result.get("ok")
                    entry["code"] = result.get("code")
                # Capture the verify_playbook envelope (small, structured)
                # so the scorer can compute verify-related metrics without
                # re-running the tool.
                if name == "verify_playbook" and isinstance(result, dict):
                    entry["verify"] = {
                        "ready_to_push": bool(result.get("ready_to_push")),
                        "required_fix_count": len(result.get("required_fixes") or []),
                        "warning_count": len(result.get("warnings") or []),
                    }
                trace.append(entry)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": content,
                })
            history.append({"role": "user", "content": tool_results})
        return {"text": "\n".join(text_chunks), "trace": trace,
                "turns": turns, "usage": usage_log,
                "audit": _snap()}
    return _call


def _agentic_openai_compatible(*, base_url: str, model: str,
                               headers: dict[str, str] | None = None,
                               ) -> Callable:
    """Agentic loop over any OpenAI-compatible chat-completions endpoint with
    function-calling. Mirrors `_agentic_anthropic_provider` so the same gates
    apply. Backs both LM Studio (local, no auth) and Frank (the Fortilab AI
    gateway, Bifrost virtual key)."""
    import json as _json
    import requests  # type: ignore[import-untyped]
    _, openai_tools, dispatch, _clr, _snap, _set_pol = _import_studio_tools()
    raw_tools = openai_tools()

    def _tools_now() -> list[dict]:
        # Per call so a per-task slice (set_tool_slice) applies -- the
        # tool-selection eval is only meaningful against the surface the
        # user actually hits.
        if _TOOL_SLICE is None:
            return raw_tools
        return [t for t in raw_tools
                if (t.get("function") or {}).get("name") in _TOOL_SLICE]

    def _call(system: str, prompt: str) -> dict:
        tools = _tools_now()
        history: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        trace: list[dict] = []
        text_chunks: list[str] = []
        turns = 0
        for _ in range(_AGENTIC_MAX_TURNS):
            turns += 1
            r = requests.post(
                f"{base_url}/chat/completions",
                json={"model": model, "messages": history, "tools": tools,
                      "temperature": 0.0},
                headers=headers or {},
                timeout=180,
            )
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            history.append(msg)
            if msg.get("content"):
                text_chunks.append(msg["content"])
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            for tc in calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = _json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                result = dispatch(name, args)
                content = result if isinstance(result, str) else _json.dumps(
                    result, default=str)
                entry: dict[str, Any] = {
                    "name": name,
                    "args": args,
                    "args_chars": len(_json.dumps(args, default=str)),
                    "result_chars": len(content),
                }
                # Result envelope flags so the investigation-recall scorer
                # (and partial-failure assertions) can see what each pivot
                # returned without re-running it.
                if isinstance(result, dict):
                    entry["ok"] = result.get("ok")
                    entry["code"] = result.get("code")
                if name == "verify_playbook" and isinstance(result, dict):
                    entry["verify"] = {
                        "ready_to_push": bool(result.get("ready_to_push")),
                        "required_fix_count": len(result.get("required_fixes") or []),
                        "warning_count": len(result.get("warnings") or []),
                    }
                trace.append(entry)
                history.append({
                    "role": "tool", "tool_call_id": tc.get("id", ""),
                    "content": content,
                })
        return {"text": "\n".join(text_chunks), "trace": trace,
                "turns": turns, "audit": _snap()}
    return _call


def _agentic_lmstudio_provider() -> Callable:
    """LM Studio's local OpenAI-compatible endpoint. No auth."""
    return _agentic_openai_compatible(
        base_url=os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        model=os.environ.get("LMSTUDIO_MODEL", "local-model"),
    )


def _agentic_frank_provider() -> Callable:
    """Frank -- the Fortilab AI gateway, via its Bifrost virtual key.

    Deliberately reads FRANK_* rather than the global OPENAI_* config so
    switching Frank's model can't silently move an eval baseline (the same
    isolation the .env comment calls for). Sends the key both as a Bearer
    token and as `x-bf-vk`, which is how Bifrost accepts a virtual key."""
    key = os.environ.get("FRANK_API_KEY")
    if not key:
        raise RuntimeError("FRANK_API_KEY not set (see .env)")
    # No default: the gateway is an internal host, and hardcoding it here puts
    # it in a tracked file that publishes to the public mirror. Required from
    # the environment like FRANK_API_KEY and FRANK_MODEL either side of it.
    base_url = os.environ.get("FRANK_BASE_URL")
    if not base_url:
        raise RuntimeError("FRANK_BASE_URL not set (see .env)")
    model = os.environ.get("FRANK_MODEL")
    if not model:
        raise RuntimeError("FRANK_MODEL not set (see .env)")
    return _agentic_openai_compatible(
        base_url=base_url, model=model,
        headers={"Authorization": f"Bearer {key}", "x-bf-vk": key},
    )


def _agentic_openai_api_provider() -> Callable:
    """The model FortiSOAR actually runs in production: gpt-4.1-mini.

    Deliberately does NOT read OPENAI_ENDPOINT. That variable points at the
    Fortilab gateway, which serves two self-hosted models (GLM-5.2, Qwen3.6)
    and no GPT -- pointing this at it would silently measure a different
    model than production, which is the exact mistake the first Frank
    baseline made. Override with EVAL_OPENAI_BASE_URL / EVAL_OPENAI_MODEL."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return _agentic_openai_compatible(
        base_url=os.environ.get("EVAL_OPENAI_BASE_URL",
                                "https://api.openai.com/v1"),
        model=os.environ.get("EVAL_OPENAI_MODEL", "gpt-4.1-mini"),
        headers={"Authorization": f"Bearer {key}"},
    )


_LAZY_FACTORIES: dict[str, Callable[[], ProviderFn]] = {
    "anthropic": _anthropic_provider,
    "openai": _openai_provider,
    "lmstudio": _lmstudio_provider,
    "agentic_anthropic": _agentic_anthropic_provider,
    "agentic_lmstudio": _agentic_lmstudio_provider,
    "agentic_frank": _agentic_frank_provider,
    "agentic_openai_api": _agentic_openai_api_provider,
}


def get_provider(name: str, *, gold_lookup=None) -> ProviderFn:
    """Resolve a provider by name. Lazy: real providers only import their
    SDK when first called."""
    if name == "echo":
        return echo_provider
    if name == "gold":
        if gold_lookup is None:
            raise ValueError("gold provider requires a gold_lookup callable")
        return gold_provider(gold_lookup)
    if name in _LAZY_FACTORIES:
        return _LAZY_FACTORIES[name]()
    raise ValueError(
        f"unknown provider {name!r}; known: gold, echo, "
        + ", ".join(_LAZY_FACTORIES))


def available_providers() -> Iterable[str]:
    return ["gold", "echo", *_LAZY_FACTORIES.keys()]
