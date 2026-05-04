"""LLM provider factory.

The chat route asks for a provider by name; tests can register a fake.
This is the single point where wiring decisions land — adding an
OpenAI / Bedrock / etc. provider is `register("openai", OpenAIProvider)`
plus reading `STUDIO_LLM_PROVIDER=openai` at startup.

Every provider must conform to the LLMProvider Protocol and emit a
UsageEvent per LLM round-trip — that's how cost accounting stays
provider-agnostic.
"""
from __future__ import annotations

import os
from typing import Callable

from .provider import LLMProvider


_REGISTRY: dict[str, Callable[..., LLMProvider]] = {}


def register(name: str, factory: Callable[..., LLMProvider]) -> None:
    """Bind a name to a constructor (zero-arg callable returning an
    LLMProvider). Tests use this to inject a FakeProvider."""
    _REGISTRY[name] = factory


def get_provider(name: str | None = None, **kwargs) -> LLMProvider:
    """Return a provider by name. If `name` is None, falls back to
    `STUDIO_LLM_PROVIDER` env var, then 'anthropic'."""
    chosen = name or os.environ.get("STUDIO_LLM_PROVIDER", "anthropic")
    fac = _REGISTRY.get(chosen)
    if fac is None:
        raise KeyError(
            f"unknown LLM provider {chosen!r}; "
            f"registered: {sorted(_REGISTRY)}"
        )
    return fac(**kwargs)


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def reset_registry() -> None:
    """Test helper — wipes the registry. Production code should never
    call this."""
    _REGISTRY.clear()


# ---- built-in registrations --------------------------------------
# Imported lazily so a missing provider SDK (e.g. the openai package)
# doesn't blow up the whole module.

def _register_builtins() -> None:
    try:
        from .anthropic_provider import AnthropicProvider
        register("anthropic", AnthropicProvider)
    except Exception:
        pass


_register_builtins()
