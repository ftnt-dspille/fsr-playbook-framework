"""LLM provider configuration routes.

Browser flow: list providers → fill form → POST test → on success POST
save → GET models → POST active. Secrets never round-trip back to the
browser; reads expose only `api_key_set: bool`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import settings as _settings


router = APIRouter(prefix="/api/llm", tags=["llm-config"])


class ProviderPatch(BaseModel):
    base_url: str | None = None
    api_key: str | None = None  # None = leave unchanged. Empty string = clear.
    model: str | None = None
    clear_api_key: bool = False  # explicit "delete the saved secret"


class ProbeIn(BaseModel):
    """Inputs to the test/models endpoints. The form values, NOT the
    saved values — this lets the user probe before clobbering config."""
    base_url: str | None = None
    api_key: str | None = None


class SetActiveIn(BaseModel):
    name: str
    model: str | None = None


@router.get("/providers")
def list_providers() -> dict[str, Any]:
    return {
        **_settings.redacted_view(),
        "secrets": _settings.secrets_health(),
    }


@router.post("/providers/{name}")
def patch_provider(name: str, body: ProviderPatch) -> dict[str, Any]:
    if name not in _settings.list_provider_names():
        raise HTTPException(404, f"unknown provider: {name}")
    api_key_arg: Any = ...
    if body.clear_api_key:
        api_key_arg = None
    elif body.api_key is not None:
        if body.api_key == "":
            api_key_arg = None
        else:
            api_key_arg = body.api_key
    try:
        _settings.save_provider(
            name,
            base_url=body.base_url if body.base_url is not None else ...,
            model=body.model if body.model is not None else ...,
            api_key=api_key_arg,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _settings.redacted_view()["providers"][name]


@router.post("/providers/{name}/test")
async def test_provider(name: str, body: ProbeIn) -> dict[str, Any]:
    """Probe connectivity using the form values (or saved values if
    body fields are blank). Returns {ok, error?, latency_ms}.

    For OpenAI-compatible endpoints (lmstudio): hit /v1/models — 200 means
    reachable + auth ok in one round-trip. For Anthropic: a no-tool zero-
    token messages call would be billable; we just check key shape and
    SDK construct."""
    if name not in _settings.list_provider_names():
        raise HTTPException(404, f"unknown provider: {name}")

    saved = _settings.load_provider(name)
    base_url = body.base_url or saved.base_url
    api_key = body.api_key or saved.api_key

    import time
    start = time.monotonic()

    if name == "lmstudio":
        if not base_url:
            return {"ok": False, "error": "base_url is required"}
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=base_url, api_key=api_key or "lm-studio", timeout=4.0,
            )
            await client.models.list()
            return {"ok": True, "latency_ms": int((time.monotonic() - start) * 1000)}
        except Exception as e:
            return {"ok": False, "error": _friendly(e), "latency_ms": int((time.monotonic() - start) * 1000)}

    if name == "anthropic":
        if not api_key:
            return {"ok": False, "error": "api_key is required"}
        if not (api_key.startswith("sk-ant-") and len(api_key) > 20):
            return {"ok": False, "error": "doesn't look like an Anthropic key (expects sk-ant-…)"}
        return {"ok": True, "note": "shape check only; first chat will confirm"}

    return {"ok": False, "error": f"no test handler for provider {name!r}"}


@router.post("/providers/{name}/models")
async def list_models(name: str, body: ProbeIn | None = None) -> dict[str, Any]:
    """List models advertised by the configured endpoint.

    Accepts the same form overrides as `/test` so the UI can list
    models without forcing the user to Save first. Body fields fall
    back to saved config when blank.

    LM Studio / OpenAI-compatible: /v1/models. Anthropic: hardcoded
    catalog (their public list-models requires admin keys some users
    don't have)."""
    if name not in _settings.list_provider_names():
        raise HTTPException(404, f"unknown provider: {name}")

    body = body or ProbeIn()
    saved = _settings.load_provider(name)
    base_url = body.base_url or saved.base_url
    api_key = body.api_key or saved.api_key

    if name == "lmstudio":
        if not base_url:
            return {"ok": False, "models": [], "error": "base_url not configured"}
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=base_url, api_key=api_key or "lm-studio", timeout=8.0,
            )
            page = await client.models.list()
            ids = [m.id for m in page.data]
            return {"ok": True, "models": ids}
        except Exception as e:
            return {"ok": False, "models": [], "error": _friendly(e)}

    if name == "anthropic":
        return {
            "ok": True,
            "models": [
                "claude-sonnet-4-5-20250929",
                "claude-opus-4-1-20250805",
                "claude-haiku-4-5-20251001",
            ],
        }

    return {"ok": False, "models": [], "error": f"no model lister for {name!r}"}


@router.post("/active")
def set_active(body: SetActiveIn) -> dict[str, Any]:
    if body.name not in _settings.list_provider_names():
        raise HTTPException(404, f"unknown provider: {body.name}")
    _settings.set_active_provider(body.name, body.model)
    return _settings.redacted_view()


def _friendly(e: Exception) -> str:
    name = type(e).__name__
    msg = str(e)
    # Trim the noisier OpenAI tracebacks for UI display.
    if "Connection error" in msg or "ConnectError" in name or "ConnectionRefused" in msg:
        return "Connection refused — is the LLM server running and reachable at that URL?"
    if "401" in msg or "AuthenticationError" in name:
        return "401 — API key rejected."
    if "Timeout" in name:
        return "Timed out reaching the endpoint."
    return f"{name}: {msg[:240]}"
