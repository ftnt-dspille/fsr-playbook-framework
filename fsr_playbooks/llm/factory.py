"""LLM provider factory.

Routes ask for `get_provider()` (active per settings) or
`get_provider("lmstudio")` (explicit). Either way we hydrate the provider
from a consumer-supplied `ConfigProvider` so URL/key/model live in one
place. Tests can register a `FakeProvider` to bypass settings entirely.

The web backend installs its `backend.settings`-backed provider at app
startup via `set_config_provider(...)`; the FortiSOAR connector installs
one backed by the platform-decrypted `config` dict.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fsr_playbooks.protocols import ConfigProvider
from .provider import LLMProvider


_REGISTRY: dict[str, Callable[..., LLMProvider]] = {}
_CONFIG_PROVIDER: Optional[ConfigProvider] = None


def set_config_provider(provider: ConfigProvider) -> None:
    """Consumer hook — call once at startup with the implementation that
    knows how to resolve provider configs in this environment."""
    global _CONFIG_PROVIDER
    _CONFIG_PROVIDER = provider


def _settings() -> ConfigProvider:
    if _CONFIG_PROVIDER is None:
        raise RuntimeError(
            "fsr_playbooks.llm.factory: no ConfigProvider installed. "
            "Call set_config_provider(...) at app startup."
        )
    return _CONFIG_PROVIDER


def register(name: str, factory: Callable[..., LLMProvider]) -> None:
    """Bind a name to a constructor. The constructor receives kwargs
    matching ProviderConfig fields (base_url, api_key, model). Tests use
    this to inject a FakeProvider."""
    _REGISTRY[name] = factory


def get_provider(name: str | None = None, **overrides: Any) -> LLMProvider:
    """Return a configured provider.

    `name=None` → active per the installed ConfigProvider.
    `overrides` → override any ProviderConfig field for this call only
      (used in tests; the route handler passes nothing).
    """
    cfg_provider = _settings()
    chosen = name or cfg_provider.get_active_provider_name()
    fac = _REGISTRY.get(chosen)
    if fac is None:
        raise KeyError(
            f"unknown LLM provider {chosen!r}; "
            f"registered: {sorted(_REGISTRY)}"
        )

    cfg = cfg_provider.load_provider(chosen)
    kwargs: dict[str, Any] = {
        "model": cfg.model or None,
        "api_key": cfg.api_key,
    }
    if cfg.base_url is not None:
        kwargs["base_url"] = cfg.base_url
    kwargs.update(overrides)
    # Drop Nones so the provider's own defaults kick in.
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    # Tolerate factories that don't accept all of these (e.g. test
    # fixtures that pre-bind args via lambda). Inspect the signature
    # and pass only what the callable knows about; **kwargs-style
    # callables still receive everything.
    import inspect
    try:
        sig = inspect.signature(fac)
        accepts_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if not accepts_var_kw:
            kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    except (TypeError, ValueError):
        pass  # builtins / C-callables; just hand them what we have
    return fac(**kwargs)


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def reset_registry() -> None:
    """Test helper — wipes the registry. Production code should never
    call this."""
    _REGISTRY.clear()


def _register_builtins() -> None:
    try:
        from .anthropic_provider import AnthropicProvider
        register("anthropic", AnthropicProvider)
    except Exception:
        pass
    try:
        from .lmstudio_provider import LMStudioProvider
        register("lmstudio", LMStudioProvider)
    except Exception:
        pass
    try:
        from .openai_provider import OpenAIProvider
        register("openai", OpenAIProvider)
    except Exception:
        pass


_register_builtins()
