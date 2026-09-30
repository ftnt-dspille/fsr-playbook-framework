"""LLM provider protocol.

Anthropic v1; OpenAI lands in Phase 5. The protocol normalizes the
event stream so the SSE route doesn't care which backend it's talking to.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant"]


@dataclass
class TextEvent:
    kind: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseEvent:
    name: str
    arguments: dict[str, Any]
    call_id: str
    # HITL Phase 2: server-resolved tier so the audit pane can colour
    # tier-3+ calls without re-resolving on the client. 0 = tier
    # unknown (e.g. provider didn't stamp it; defaults to "safe" badge).
    tier: int = 0
    # True for events synthesized by resume_agent_turn to represent tool
    # calls that were skipped because an earlier call in the same turn
    # triggered an approval gate.
    synthetic: bool = False
    kind: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultEvent:
    call_id: str
    result: Any
    # Server-side wall-time (ms) the tool dispatch took. None when the
    # result didn't pass through a measured dispatch (e.g. the approval-resume
    # path, which executes the tool before re-entering stream()). The widget
    # uses this to freeze a per-tool duration on the result chip.
    duration_ms: int | None = None
    # True for events synthesized by resume_agent_turn (see ToolUseEvent.synthetic).
    synthetic: bool = False
    kind: Literal["tool_result"] = "tool_result"


@dataclass
class ApprovalRequestEvent:
    """Emitted when a tier-3+ tool call needs human approval before the
    provider can continue. The loop is suspended on the server until
    `POST /api/approvals/{approval_id}` arrives with the decision.

    `tool_use_id` is the Anthropic tool_use block id that triggered the
    request -- frontend matches it back onto the assistant turn so the
    approval card renders inline with the call it gates."""
    approval_id: str
    tool_use_id: str
    tool: str
    tier: int
    preview: dict[str, Any]
    args_hash: str
    summary: str | None = None
    requires_step_up: bool = False
    # Further gated calls from the same turn that this one decision also
    # covers (`approvals.BatchedCall.card()` dicts), in run order. Empty for
    # a single-call approval.
    batch: list[dict[str, Any]] = field(default_factory=list)
    kind: Literal["approval_request"] = "approval_request"


@dataclass
class DoneEvent:
    stop_reason: str
    kind: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    message: str
    kind: Literal["error"] = "error"


@dataclass
class ToolCallUsage:
    """Per-tool-call accounting emitted with each UsageEvent. Lets the
    consumer attribute context bloat to a specific tool result."""
    name: str
    args_chars: int
    result_chars: int
    # Server-side wall-time (ms) of this tool's dispatch (None if unmeasured).
    # Folded into chat_turns.tool_calls_json for later profiling -- answers
    # "which tool was slow" from the authoritative turn record.
    duration_ms: int | None = None


@dataclass
class DroppedCall:
    """A tool call the model started but the round never ran -- it stopped on
    `length` / `max_tokens` mid-arguments. Kept so a runaway round (one live
    build round spent the whole 16384-token cap) shows WHAT it was writing;
    the call itself is dropped from history. `tail` is the last 200 chars."""
    name: str
    arg_chars: int
    tail: str


@dataclass
class UsageEvent:
    """One emitted per LLM round-trip. Providers populate the fields
    they have access to; consumers (telemetry, history.db) are the
    same regardless of provider. This is the contract that lets us
    swap providers without rewiring logging.

    `tags` is a free-form dict the route handler stamps in to attribute
    a turn to e.g. a specific playbook (`{"playbook_collection": "..."}`).
    """
    session_id: str
    turn: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int
    history_chars: int
    stop_reason: str
    self_repair_turn: int = 0
    tool_calls: list[ToolCallUsage] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)
    #: Digest of the CACHEABLE (tools, system) prefix -- see
    #: `fsr_playbooks.llm.cache_prefix`. Two turns of one session with
    #: different fingerprints could not have shared a prompt cache, which is
    #: what `cache_read` alone can never tell you. Empty when a provider does
    #: not cache (the FortiAI proxy) or has not been taught to report it.
    prefix_fingerprint: str = ""
    #: Calls this round started but never ran -- see `DroppedCall`.
    dropped_calls: list[DroppedCall] = field(default_factory=list)
    kind: Literal["usage"] = "usage"


# This is a runtime assignment (a type alias), so `|` executes at import time
# rather than being deferred by `from __future__ import annotations` -- it needs
# PEP 604 support in the interpreter, not just the annotation grammar. That is
# satisfied: the FortiSOAR runtime baseline is 3.11 and this package declares
# `requires-python = ">=3.10"`, so a 3.9 interpreter could never install it.
# (The Union form here used to be justified by a 3.9 baseline that was already
# stale -- see CLAUDE.md.)
Event = (
    TextEvent | ToolUseEvent | ToolResultEvent
    | DoneEvent | ErrorEvent | UsageEvent
    | ApprovalRequestEvent
)


# ─────────────────────── provider capability seam (A2) ───────────────────────
#
# Three of the four backends we ship are not Anthropic, so the reasoning /
# budget / pruning primitives cannot be wired straight into one provider: the
# surface that actually runs inside FortiSOAR would get none of them, and the
# two paths would drift. Instead every provider DECLARES what it serves
# natively, the loop asks for what it wants, and whatever the provider cannot
# serve comes back as `HostEmulation` -- the explicit instruction to run the
# host-side stand-in (`TurnBudget.note()`, `shrink_history`) for exactly those.
#
# The failure this shape is built against is `shipped-but-inert`: a provider
# that declares a capability and silently no-ops it. `capabilities` is data, so
# `fsr_playbooks/tests/test_provider_capability_matrix.py` can demand a probe
# proving each declared-true capability reaches the wire.

#: Every capability name, in declaration order. The capability-matrix test
#: iterates this, so adding a field here is enough to force a probe for it.
CAPABILITY_NAMES = (
    "reasoning_depth",
    "task_budget",
    "deferred_tools",
    "history_pruning",
)


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider serves NATIVELY. Default: nothing -- a provider only
    gets credit for a primitive by declaring it, and the matrix test then
    makes it prove it."""

    #: Native control over reasoning depth (`thinking` / `effort` /
    #: `reasoning_effort`), as opposed to prompt-level "think harder" tuning.
    reasoning_depth: bool = False
    #: Server-enforced turn budget (`output_config.task_budget`), as opposed
    #: to the host counting turns and injecting `budget_note`.
    task_budget: bool = False
    #: Tool search / deferred loading, as opposed to the host shipping the
    #: whole tool array every turn.
    deferred_tools: bool = False
    #: Context editing / compaction, as opposed to `shrink_history`.
    history_pruning: bool = False


@dataclass(frozen=True)
class TurnRequest:
    """What the loop ASKS for on this turn. Asking is provider-neutral; who
    honours it is not."""

    #: Reasoning depth to request ("low" / "medium" / "high"); None = default.
    reasoning: str | None = None
    #: Bound on tool turns. None = the loop's own MAX_TOOL_TURNS.
    max_tool_turns: int | None = None
    #: Keep the transcript inside the context window. TRI-STATE, and the
    #: tri-state is load-bearing: `None` (the default) means nobody asked, so
    #: the host-side `shrink_history` runs exactly as it did before this seam
    #: -- a framework MCP caller that never calls `request()` must not have its
    #: wire changed under it. `True` is an explicit ask, and only that lets a
    #: provider serve context editing natively. `False` means do not prune at
    #: all, host or provider.
    prune_history: bool | None = None
    #: Let the model discover tools instead of receiving the full array.
    defer_tools: bool = False


@dataclass(frozen=True)
class HostEmulation:
    """The RESIDUE of a `TurnRequest`: each flag is True when the loop asked
    for that capability and the provider does not serve it, so the host-side
    stand-in must run. A flag is False either because nothing asked for it or
    because the provider is handling it -- both mean "do not emulate"."""

    reasoning_depth: bool = False
    task_budget: bool = False
    deferred_tools: bool = False
    history_pruning: bool = False

    @classmethod
    def resolve(cls, caps: ProviderCapabilities, req: TurnRequest) -> HostEmulation:
        return cls(
            reasoning_depth=bool(req.reasoning) and not caps.reasoning_depth,
            # A native task budget is served only when the loop actually
            # HANDS one over (`max_tool_turns`). Treating it as always-asked
            # would change the wire for every existing caller the moment a
            # provider declared the capability -- and the host-side
            # `budget_note` must stay on for a turn nobody bounded.
            task_budget=not (caps.task_budget and req.max_tool_turns is not None),
            deferred_tools=req.defer_tools and not caps.deferred_tools,
            # Same rule as the budget above: native only when the loop
            # actually ASKED (`prune_history is True`). `None` keeps the
            # stand-in on; `False` turns both off.
            history_pruning=(
                req.prune_history is not False
                and not (caps.history_pruning and req.prune_history is True)
            ),
        )


class CapabilityMixin:
    """Default capability seam for a provider: declares nothing, emulates
    everything. A provider serving a primitive natively overrides
    `capabilities` and applies the request in `request()`.

    Providers that are never asked (the framework's own MCP callers construct
    a provider and call `stream` directly) still get the right answer: the
    default emulation is the one for a default `TurnRequest`, i.e. exactly the
    host-side behaviour that predates this seam.
    """

    capabilities: ProviderCapabilities = ProviderCapabilities()

    _turn_request: TurnRequest = TurnRequest()

    def request(self, req: TurnRequest) -> HostEmulation:
        """Ask for this turn's capabilities; get back what the host must
        emulate. Providers overriding this MUST still return the residue."""
        self._turn_request = req
        return self.emulation

    @property
    def emulation(self) -> HostEmulation:
        return HostEmulation.resolve(self.capabilities, self._turn_request)


@dataclass
class Message:
    role: Role
    content: str | list[dict[str, Any]]
    """Content is either a plain string (user msg) or Anthropic-style block list
    (assistant turn with text + tool_use blocks, or user turn with tool_result blocks)."""


class LLMProvider(Protocol):
    name: str
    #: Declared native primitives -- see the capability seam above.
    capabilities: ProviderCapabilities

    def request(self, req: TurnRequest) -> HostEmulation:
        """Ask for this turn's capabilities; return what the host must emulate."""
        ...

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any | None = None,
        max_tool_turns: int | None = None,
    ) -> AsyncIterator[Event]:
        """Stream events for one user turn. Implementations MUST emit
        a `UsageEvent` after each LLM round-trip (before any tool
        execution for that turn) so consumers can attribute cost
        independently of the provider.

        `tags` is opaque to the provider -- it just round-trips it on
        the UsageEvent so the route handler can stamp e.g. the active
        playbook collection name.

        `case_state` is optional CaseState for guard seeding (P2). When
        provided, the provider's discipline seeds from case_state.investigation
        and mutates it during the turn so the caller can persist it afterwards."""
        ...
