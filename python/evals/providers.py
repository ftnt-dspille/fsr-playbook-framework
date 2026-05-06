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
from typing import Callable, Iterable

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
    """Returns the task's gold YAML verbatim — a control row showing
    "the harness would score 4/4 if a model produced perfect output."

    `gold_lookup(prompt)` should return the gold YAML for the matching
    task, or None.
    """
    def _call(system: str, prompt: str) -> str:
        gold = gold_lookup(prompt)
        return gold if gold is not None else ""
    return _call


def echo_provider(system: str, prompt: str) -> str:  # noqa: ARG001
    """Always returns an empty playbook — proves the harness scores
    failures cleanly. Useful as a smoke test in CI."""
    return "collection: Echo\nplaybooks: []\n"


# ---------------------------------------------------------------------------
# Real provider stubs — wired only when the corresponding env / SDK is
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


_LAZY_FACTORIES: dict[str, Callable[[], ProviderFn]] = {
    "anthropic": _anthropic_provider,
    "openai": _openai_provider,
    "lmstudio": _lmstudio_provider,
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
