"""Which LLM a harness run talks to, resolved in one place.

`resolve_llm` turns a harness's `--llm` / `--model` / `--base-url` into a
`ResolvedLLM` that names where every value came from, so a run can print what
it actually measured. The fake provider is only ever chosen by name.

Read the environment once and pass it in (`env=`): a tool-using turn loads
the framework `.env` into `os.environ` as a side effect, so reading it live
after the first turn resolves a different model than the run started with.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: The local default (chosen by measurement on the known-answer and sweep
#: corpora: the only b200 backend 6/6 on known-answer, at ~240 tok/s). What a
#: virtual key permits rotates; check `make models` before trusting it.
DEFAULT_FRANK_MODEL = "coding-b200/qwen3.8-27b-nvfp4"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"

KINDS = ("fake", "frank", "openai", "anthropic")


class LLMConfigError(ValueError):
    """The run asked for a provider it has no endpoint or key for."""


@dataclass(frozen=True)
class ResolvedLLM:
    kind: str            # fake | frank | openai | anthropic
    model: str
    model_source: str    # "arg" | "env:<NAME>" | "default"
    base_url: str | None = None
    api_key: str | None = None

    @property
    def provider(self) -> str:
        """The connector's `llm_provider`: frank and openai are both the
        OpenAI-compatible provider."""
        return "openai" if self.kind in ("frank", "openai") else self.kind

    def describe(self) -> str:
        where = f" @ {self.base_url}" if self.base_url else ""
        return f"{self.kind}:{self.model} (model from {self.model_source}){where}"

    def connector_config(self) -> dict[str, Any]:
        """The connector config keys for this LLM (what local_turn sends)."""
        if self.kind == "fake":
            return {"anthropic_api_key": "sk-local-not-real", "model": self.model}
        if self.kind == "anthropic":
            return {"anthropic_api_key": self.api_key,
                    "anthropic_base_url": self.base_url, "model": self.model}
        # Offline evals stay on the model chosen here, so a tool weakness
        # still shows up as a failure: a persona's stronger model is not used.
        return {"llm_provider": "openai", "openai_api_key": self.api_key,
                "openai_base_url": self.base_url, "openai_model": self.model,
                "persona_models": False}

    def provider_instance(self) -> Any:
        """A framework provider, for harnesses that call `run_agent_turn`
        directly instead of going through the connector."""
        if self.kind == "anthropic":
            from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
            return AnthropicProvider(model=self.model)
        if self.kind in ("frank", "openai"):
            from fsr_playbooks.llm.openai_provider import OpenAIProvider
            return OpenAIProvider(base_url=self.base_url, api_key=self.api_key,
                                  model=self.model)
        raise LLMConfigError("the fake provider has no framework instance; "
                             "install it through the host's seam")


def _first(env: Mapping[str, str], *names: str) -> tuple[str | None, str | None]:
    for n in names:
        if env.get(n):
            return env[n], n
    return None, None


def api_key_for(kind: str, env: Mapping[str, str] | None = None) -> str | None:
    """Frank's key for frank, OpenAI's for openai, the other as fallback. One
    shared order once sent the Frank virtual key to api.openai.com."""
    env = os.environ if env is None else env
    order = (("FRANK_API_KEY", "OPENAI_API_KEY") if kind == "frank"
             else ("OPENAI_API_KEY", "FRANK_API_KEY"))
    return _first(env, *order)[0]


def resolve_llm(kind: str, model: str | None = None, base_url: str | None = None,
                *, env: Mapping[str, str] | None = None) -> ResolvedLLM:
    """Resolve a harness's LLM choice. Raises `LLMConfigError` when the
    endpoint or key is missing, rather than falling back to something else."""
    env = os.environ if env is None else env
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise LLMConfigError(f"unknown llm {kind!r} (want {'|'.join(KINDS)})")

    def pick(default: str, *names: str) -> tuple[str, str]:
        if model:
            return model, "arg"
        val, name = _first(env, *names)
        return (val, f"env:{name}") if val else (default, "default")

    if kind == "fake":
        m, src = pick("fake-1")
        return ResolvedLLM("fake", m, src)
    if kind == "anthropic":
        key = env.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMConfigError("anthropic needs ANTHROPIC_API_KEY")
        m, src = pick(DEFAULT_ANTHROPIC_MODEL, "ANTHROPIC_MODEL")
        return ResolvedLLM("anthropic", m, src, env.get("ANTHROPIC_BASE_URL") or None, key)
    base = base_url or _first(env, "FRANK_BASE_URL", "OPENAI_ENDPOINT")[0]
    if not base:
        raise LLMConfigError(f"{kind} needs a base URL (FRANK_BASE_URL / "
                             "OPENAI_ENDPOINT, or --base-url)")
    key = api_key_for(kind, env)
    if not key:
        raise LLMConfigError(f"{kind} needs FRANK_API_KEY or OPENAI_API_KEY")
    m, src = pick(DEFAULT_FRANK_MODEL, "FRANK_MODEL", "OPENAI_MODEL")
    return ResolvedLLM(kind, m, src, base, key)
