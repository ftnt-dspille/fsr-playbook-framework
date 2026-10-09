"""FortiAI Proxy provider -- on-box LLM adapter.

Drives the agent loop through the `fortinet-fortiai-proxy` connector
(`agent_chat_completions` operation). Non-streaming: one HTTP call per
round-trip, tool calls round-tripped as flattened text.

**Reasoning depth is selectable.** `feature` picks the backend profile
(`AI_MODEL_MEDIUM` / `AI_MODEL_LARGE`) and `reasoning_effort` sets the depth,
both sent per call via `params.config`; see `_resolve_llm_config` for the one
compatibility rule (effort implies LARGE). The stock appliance ships the same
choice as two connector configurations, "Low Reasoning" and "High Reasoning".

**Tool calls can arrive in batches** -- see `_normalize_tool_calls`.

No customer-supplied API key: the connector holds its own credential. It is
NOT, however, egress-free -- the stock configuration points at FortiAI on
FortiCloud, so an air-gapped deployment requires FortiAI itself to be on-prem.

Phase B of docs/plans/FORTIAI_PROXY_PROVIDER_PLAN.md; corrected by
docs/plans/FORTIAI_PROXY_CAPABILITY_CORRECTION.md.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from . import approvals as _approvals
from ._loop_helpers import DEFAULT_MAX_OUTPUT_TOKENS
from .agent_loop import (
    BAD_ARGS_KEY,
    Round,
    RoundUsage,
    ToolCall,
    ToolOutcome,
    parse_tool_arguments,
    resume_loop,
    run_loop,
)
from .provider import (
    CapabilityMixin,
    Event,
    HostEmulation,
    Message,
    ProviderCapabilities,
    TurnRequest,
)
from .replay import blocks_to_prose, is_block_content
from .tools import anthropic_tools as _anthropic_tools

#: FortiAI ``feature`` values, i.e. which backend profile serves the call.
#: These are what the appliance's connector *configurations* set as
#: ``config.model`` -- the stock box ships "Low Reasoning" (MEDIUM, default)
#: and "High Reasoning" (LARGE). Live-verified on 8.0.0.
FEATURE_MEDIUM = "AI_MODEL_MEDIUM"
FEATURE_LARGE = "AI_MODEL_LARGE"
FEATURE_SMALL = "AI_MODEL_SMALL"
#: The FSOC default. On an FSR box it answers 404 -30008 "Assistant not found",
#: so it is deliberately not offered.
FEATURE_LOCAL = "AI_MODEL_LOCAL"


def _resolve_llm_config(feature: str | None,
                        reasoning_effort: str | None) -> dict[str, Any]:
    """Build the per-call ``params.config`` overlay -- THE one place the
    effort/model compatibility rule lives.

    The proxy merges ``params["config"]`` over the connector configuration
    (``operations.py``: ``merged_config = {**config, **params.get("config")}``),
    so a caller can pick the backend profile and the reasoning depth per call
    without switching the connector's config UUID. Auth and server address are
    NOT overridable this way -- the client is still constructed from the
    stored config -- which is exactly the seam we want.

    **effort implies LARGE.** ``reasoning_effort`` on ``AI_MODEL_MEDIUM`` is a
    hard ``400 -30000 "The request payload is invalid."`` every time
    (live-verified, 2 reps per cell). Asking for reasoning depth and getting a
    silent empty turn is the worst available outcome, so requesting an effort
    without naming a feature -- or naming a non-LARGE one -- upgrades to LARGE
    here rather than failing at the wire.

    Returns ``{}`` when nothing is set, so the default path sends no ``config``
    key at all and the connector configuration decides, exactly as before.
    """
    overlay: dict[str, Any] = {}
    effort = (reasoning_effort or "").strip() or None
    feat = (feature or "").strip() or None
    if effort:
        if feat != FEATURE_LARGE:
            feat = FEATURE_LARGE
        overlay["reasoning_effort"] = effort
    if feat:
        overlay["model"] = feat
    return overlay


def _collapse_union_types(node: Any) -> Any:
    """Rewrite JSON-Schema union types to a single type, recursively.

    The gateway rejects ``{"type": ["integer", "null"]}`` outright -- the whole
    request 400s with ``-30000 "The request payload is invalid"``, naming
    nothing, so ONE nullable property poisons the entire tool payload. Plain
    ``{"type": "integer"}`` is accepted (live-verified on 8.0.0, both
    directions). Optionality is already carried by ``required``, so dropping
    the ``"null"`` member loses nothing the proxy can act on.

    Recurses through ``properties``/``items``/``$defs`` because a union nested
    inside an array's ``items`` fails exactly the same way as a top-level one.
    """
    if isinstance(node, list):
        return [_collapse_union_types(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _collapse_union_types(v) for k, v in node.items()}
    t = out.get("type")
    if isinstance(t, list):
        # Prefer the first non-"null" member; a type list of only "null" is
        # degenerate, so fall back to "string" rather than emitting a list.
        concrete = [x for x in t if x != "null"]
        out["type"] = concrete[0] if concrete else "string"
    return out


def _normalize_tools_fortiai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate tool schemas into the fortiai-proxy shape: ``{name, description, schema}``.

    The connector advertises an intent tool-slice using the Anthropic shape
    (``{name, description, input_schema}``) regardless of the active provider.
    The proxy rejects both OpenAI's ``{type: function, function: {parameters}}``
    and Anthropic's ``{name, description, input_schema}`` -- it requires the
    plain ``schema`` key.  Already-correct shapes pass through untouched.

    Union types are collapsed here too -- see :func:`_collapse_union_types`.
    """
    out: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        # OpenAI-wrapped tools have name inside function:
        if not name and t.get("type") == "function" and isinstance(t.get("function"), dict):
            name = t["function"].get("name")
        if not name:
            continue
        schema = (t.get("schema") or t.get("input_schema")
                  or t.get("parameters") or {"type": "object", "properties": {}})
        # If this is an OpenAI-wrapped tool, extract the inner schema
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            schema = (t["function"].get("parameters") or schema)
        out.append({
            "name": name,
            "description": t.get("description", ""),
            "schema": _collapse_union_types(schema),
        })
    return out


def _normalize_tool_calls(tool_name: Any, tool_args: Any,
                          tools_field: Any) -> list[tuple[str, Any]]:
    """Every tool call the proxy elected, as ``[(name, raw_args), ...]``.

    The response carries the FULL batch in ``tools``
    (``[{"name": ..., "args": {...}}, ...]``); ``tool_name``/``tool_args`` are
    only the FIRST of them, kept for back-compat. Reading the singular pair
    alone -- which this provider did until now -- silently discarded every call
    after the first: the model asked for two things, one ran, and nothing
    reported the drop. Live-verified on 8.0.0 that a two-tool prompt returns
    both entries.

    Falls back to the singular pair when ``tools`` is absent or unusable, so an
    older proxy build behaves exactly as before. ``raw_args`` is passed through
    untouched -- the caller parses it and reports its own failures (the proxy
    sometimes hands args back as a JSON *string*).
    """
    calls: list[tuple[str, Any]] = []
    if isinstance(tools_field, list):
        for entry in tools_field:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name:
                calls.append((name, entry.get("args")))
    if calls:
        return calls
    if isinstance(tool_name, str) and tool_name:
        return [(tool_name, tool_args)]
    return []


def _describe_proxy_error(err: Any) -> str:
    """Render the proxy's error envelope as one readable line.

    The dict form carries `error_desc` + `error_code`; anything else (a bare
    string, or a shape we have not seen) is stringified rather than dropped."""
    if isinstance(err, dict):
        desc = err.get("error_desc") or err.get("message") or ""
        code = err.get("error_code") or err.get("status_code") or ""
        if desc and code:
            return f"{desc} (code {code})"
        return str(desc or code or err)
    return str(err)


def _stringify(result: Any) -> str:
    """Convert a tool result to a compact text representation for the
    flattened-text round-trip."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


def _is_error_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    # Guard redirects and deferrals are steering, not errors (parity with
    # the Anthropic provider; tracker #60).
    if result.get("kind") in ("guard_redirect", "guard_defer"):
        return False
    return result.get("ok") is False or "error" in result


class FortiAIProxyProvider(CapabilityMixin):
    """Non-streaming LLM provider for the FortiAI proxy.

    Calls ``agent_chat_completions`` on the ``fortinet-fortiai-proxy``
    connector via ``POST /api/integration/execute/``. No customer-supplied API
    key (the connector holds its own credential); egress depends on where
    FortiAI itself is deployed. One HTTP round-trip per LLM turn. A turn may
    carry a BATCH of tool calls, which round-trip as flattened-text messages.

    ``feature`` + ``reasoning_effort`` select the backend profile and reasoning
    depth per call -- see :func:`_resolve_llm_config`.
    """

    name = "fortiai-proxy"
    #: Native reasoning depth ONLY: `reasoning_effort` (plus the effort-implies-
    #: LARGE rule) rides in `params.config` on every call -- see
    #: :func:`_resolve_llm_config`. The proxy has no server-side turn budget,
    #: no tool search and no context editing, so the host emulates those.
    capabilities = ProviderCapabilities(reasoning_depth=True)
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        feature: str | None = None,
        reasoning_effort: str | None = None,
        approval_gateway: Any = None,
        max_output_tokens: int | None = None,
        client: Any = None,  # httpx.AsyncClient or compatible, for testing
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._auth = api_key
        # `model` is the COSMETIC params.model -- the proxy echoes it back in
        # data.model and does not route on it. `feature`/`reasoning_effort` are
        # the ones that select a backend profile; see _resolve_llm_config.
        self.model = model or "fortiai-proxy"
        self.feature = feature
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        self._approval_gateway = approval_gateway
        self._client = client or httpx.AsyncClient(timeout=120.0)

    # -- the loop's seam (see agent_loop) ----------------------------------

    label = "FortiAI proxy"

    def precheck(self) -> str | None:
        return None

    def open_turn(self, *, system: str, messages: list[Message],
                  tools: list[dict[str, Any]] | None, turn_budget: int) -> _FortiAITurn:
        return _FortiAITurn(self, system, messages, tools)

    def rehydrate(self, suspended: _approvals.SuspendedSession,
                  outcomes: list[ToolOutcome]) -> list[Message]:
        # The proxy only takes flat user/assistant/system messages, so the
        # tool round-trip is carried as text pairs.
        carried: list[dict[str, Any]] = list(suspended.history_snapshot)
        for item in suspended.prior_tool_result_blocks:   # each is a text pair
            carried += item if isinstance(item, list) else [item]
        for o in outcomes:
            carried += _text_pair(o)
        return [Message(role="user", content=carried)]

    def contract_stop(self, raw: str | None) -> str:
        return "end_turn"

    def friendly_error(self, exc: Exception) -> str:
        return f"FortiAI proxy error: {exc}"

    def request(self, req: TurnRequest) -> HostEmulation:
        """Serve reasoning depth NATIVELY, emulate the rest.

        The depth is not a prompt nudge here: it becomes `reasoning_effort` in
        `params.config` on the next call, and `_resolve_llm_config` promotes
        the feature to AI_MODEL_LARGE with it (effort on MEDIUM answers with a
        silent empty turn). An unasked-for depth leaves the configured one
        alone -- `request()` is per turn, not a reconfiguration.
        """
        if req.reasoning:
            self.reasoning_effort = req.reasoning
        return super().request(req)

    async def call_proxy(self, history: list[dict[str, Any]],
                         tool_defs: list[dict[str, Any]]
                         ) -> tuple[str | None, list[tuple[str, Any]], dict[str, int]]:
        """One `agent_chat_completions` call.

        Returns (content, calls, usage). ``calls`` is EVERY tool call the proxy
        elected, as ``[(name, raw_args), ...]`` (see _normalize_tool_calls),
        empty on a text turn. Raises RuntimeError on any error envelope.
        """
        body: dict[str, Any] = {
            "connector": "fortinet-fortiai-proxy",
            "operation": "agent_chat_completions",
            "params": {"messages": history, "tools": tool_defs},
        }
        if self.model:
            body["params"]["model"] = self.model
        overlay = _resolve_llm_config(self.feature, self.reasoning_effort)
        if overlay:
            body["params"]["config"] = overlay
        headers = {"Authorization": f"Bearer {self._auth}"} if self._auth else {}
        resp = await self._client.post(f"{self.base_url}/api/integration/execute/",
                                       json=body, headers=headers)
        if resp.status_code != 200:
            try:
                err_data = resp.json()
                err_body = err_data.get("message", str(err_data))[:600]
            except Exception:
                err_body = resp.text[:600]
            raise RuntimeError(f"FortiAI proxy returned HTTP {resp.status_code}: {err_body}")

        data = resp.json()
        if data.get("status", "") not in ("Success", "success", "Completed", "completed", ""):
            raise RuntimeError(f"FortiAI proxy execution failed: {data.get('message', str(data)[:600])}")
        payload = data.get("data", data)
        # ANY truthy `error` is an error, whatever its type: the live envelope
        # is a DICT ({"status": "Failure", "error_code": "-30000", ...}), and a
        # string-only check let the turn continue on empty content.
        err = payload.get("error")
        if err:
            raise RuntimeError(f"FortiAI proxy LLM error: {_describe_proxy_error(err)}")
        # `tool_args` passes through UNCHANGED: the proxy hands args back as a
        # JSON *string* at times, and coercing a non-dict to {} here produced
        # `run_op({})` dispatches. The caller parses and reports failures.
        calls = _normalize_tool_calls(payload.get("tool_name"), payload.get("tool_args"),
                                      payload.get("tools"))
        return payload.get("content"), calls, payload.get("usage") or {}

    # -- LLMProvider -------------------------------------------------------

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,
        max_tool_turns: int | None = None,
    ) -> AsyncIterator[Event]:
        async for ev in run_loop(self, system=system, messages=messages, tools=tools,
                                 tags=tags, case_state=case_state,
                                 max_tool_turns=max_tool_turns):
            yield ev

    async def resume(self, *, suspended: _approvals.SuspendedSession,
                     decision: str) -> AsyncIterator[Event]:
        async for ev in resume_loop(self, suspended=suspended, decision=decision):
            yield ev

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        if hasattr(self._client, "aclose"):
            await self._client.aclose()

    def __del__(self):
        # Best-effort cleanup; may not run if gc is disabled
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            pass


def _text_pair(o: ToolOutcome) -> list[dict[str, Any]]:
    """One call and its result as the flat messages the proxy accepts."""
    return [
        {"role": "assistant",
         "content": f"[called {o.name}({json.dumps(o.args, default=str)})]"},
        {"role": "user", "content": f"Tool result: {o.name} = {o.content}"},
    ]


def _parse_proxy_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return parse_tool_arguments(raw)
    return {BAD_ARGS_KEY: f"arguments must be a JSON object, got {type(raw).__name__}"}


class _FortiAITurn:
    """One stream's flat-message history for the proxy.

    Non-streaming: a round is one HTTP call. The proxy has no native tool
    turns, so calls and results replay as text pairs and replayed block
    history becomes prose that is not call-shaped (see llm/replay.py)."""

    def __init__(self, provider: FortiAIProxyProvider, system: str,
                 messages: list[Message], tools: list[dict[str, Any]] | None) -> None:
        self.p = provider
        # `is not None`: the budget-ask "deliver" path passes [] to force a
        # no-research turn.
        self.plain_tools = _normalize_tools_fortiai(
            tools if tools is not None else _anthropic_tools())
        self.allowed_names = {t["name"] for t in self.plain_tools}
        self.history: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if isinstance(m.content, str):
                self.history.append({"role": m.role, "content": m.content})
            elif is_block_content(m.content):
                prose = blocks_to_prose(m.role, m.content)
                if prose:
                    self.history.append({"role": m.role, "content": prose})
            else:
                # Internal turns carried as block lists (from resume); each
                # block carries its own role.
                for block in m.content:
                    self.history.append(block if isinstance(block, dict)
                                        else {"role": "user", "content": str(block)})
        self._round = 0

    def before_round(self) -> None:
        self._round += 1

    def history_chars(self) -> int:
        try:
            return len(json.dumps(self.history, default=str))
        except Exception:
            return 0

    def history_dicts(self) -> list[dict[str, Any]]:
        return self.history

    def has_tool(self, name: str) -> bool:
        return name in self.allowed_names

    def usage_extra(self) -> dict[str, Any]:
        return {}

    async def stream_round(self) -> AsyncIterator[tuple[str, Any]]:
        content, calls, usage = await self.p.call_proxy(self.history, self.plain_tools)
        tool_calls = [
            # The index keeps ids unique within a batch; the widget matches
            # results to calls by id.
            ToolCall(f"call_{id(self):x}_{self._round}_{i}", name, _parse_proxy_args(raw))
            for i, (name, raw) in enumerate(calls)
        ]
        if content and not tool_calls:
            yield ("text", content)
        yield ("final", Round(
            text=content or "", tool_calls=tool_calls,
            stop_reason="tool_calls" if tool_calls else "end_turn",
            usage=RoundUsage(usage.get("prompt_tokens", 0) or 0,
                             usage.get("completion_tokens", 0) or 0),
            assistant=({"role": "assistant", "content": content}
                       if content and not tool_calls else None)))

    async def wrapup_round(self, max_tokens: int) -> AsyncIterator[tuple[str, Any]]:
        content, _calls, usage = await self.p.call_proxy(self.history, [])
        if content:
            yield ("text", content)
        yield ("final", RoundUsage(usage.get("prompt_tokens", 0) or 0,
                                   usage.get("completion_tokens", 0) or 0))

    async def forced_call(self, name: str) -> ToolCall | None:
        # The proxy cannot pin tool_choice; offering the one tool is as close
        # as it gets.
        schema = [t for t in self.plain_tools if t["name"] == name]
        _content, calls, _usage = await self.p.call_proxy(self.history, schema)
        hit = next(((n, raw) for n, raw in calls if n == name), None)
        if hit is None:
            return None
        args = _parse_proxy_args(hit[1])
        return ToolCall(f"call_{id(self):x}_{self._round}_forced", name,
                        {} if BAD_ARGS_KEY in args else args)

    def append_assistant(self, rnd: Round) -> None:
        if rnd.assistant is not None:
            self.history.append(rnd.assistant)

    def append_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def append_tool_call(self, call: ToolCall) -> None:
        # Nothing to write yet: a call replays together with its result as one
        # text pair (append_tool_results).
        return None

    def result_wire(self, outcome: ToolOutcome) -> list[dict[str, Any]]:
        return _text_pair(outcome)

    def append_tool_results(self, outcomes: list[ToolOutcome], *,
                            note: str | None = None, note_role: str = "user") -> None:
        for o in outcomes:
            self.history += _text_pair(o)
        if note:
            # The proxy takes no mid-conversation system message.
            self.history.append({"role": "user", "content": note})

    def snapshot(self) -> list[Any]:
        # Without the leading system message: stream() re-prepends it.
        return list(self.history[1:])
