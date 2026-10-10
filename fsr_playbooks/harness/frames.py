"""Reading a chat turn's transcript: the one copy every harness uses.

`chat_turn` / `chat_resume` return a response ENVELOPE (a dict with
`transcript[]`, `stop_reason`, `tags`); some paths return a bare frame list.
Every accessor here takes either.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

#: How a halted turn is resumed: the card type and the key `chat_resume`
#: routes on. Mirrors the connector's card-stop vocabulary; the connector's
#: conv-grader tests assert the two agree.
CARD_RESUME_KEY = {
    "choice_card": "choice_id",
    "capability_gap": "choice_id",
    "action_card": "card_id",
    "manual_input": "card_id",
    "playbook_offer": "card_id",
    "enhancement_offer": "card_id",
}


#: Frame types that halt a turn for an answer (a card the user decides, or a
#: tier-gated approval). `drive` and `live_writes` answer these; `pending_halt`
#: resumes on the same set.
HALT_FRAME_TYPES = frozenset({
    "approval_request", "action_card", "manual_input", "choice_card",
    "capability_gap", "playbook_offer", "enhancement_offer",
})

#: Card frames whose YAML is the playbook a turn delivered (offer cards carry
#: it as `final_yaml`).
OFFER_CARD_TYPES = frozenset({"playbook_offer", "enhancement_offer"})


def frames(transcript: Any) -> list[dict]:
    """Every frame of a turn, from an envelope or a bare frame list.

    The one place that reads a turn's frame list. Callers test `f.get("type")`
    through the accessors in this module, never on the raw list."""
    if isinstance(transcript, dict):
        return [f for f in (transcript.get("transcript") or []) if isinstance(f, dict)]
    if isinstance(transcript, list):
        return [f for f in transcript if isinstance(f, dict)]
    return []


def frames_of(transcript: Any, *types: str) -> list[dict]:
    """The frames whose `type` is one of `types`, in order."""
    return [f for f in frames(transcript) if f.get("type") in types]


def frame_types(transcript: Any) -> list[str | None]:
    """The `type` of each frame, in order (None for a frame without one)."""
    return [f.get("type") for f in frames(transcript)]


def assistant_text(transcript: Any) -> str:
    """The streamed text deltas coalesced into the assistant's message."""
    return "".join(str(f.get("text") or "") for f in frames(transcript)
                   if f.get("type") == "text").strip()


def assistant_summary(transcript: Any) -> list[dict]:
    """The assistant's turn as the block list the widget sends back in
    `messages[]` (its `_serializeMessagesForServer`): coalesced text,
    `tool_use` with its id, `tool_result` with its `tool_use_id`. The
    connector replays those as native tool turns, so a harness that sent
    prose instead would test a history the product never builds."""
    content: list[dict] = []
    text_buf: list[str] = []

    def flush() -> None:
        joined = "".join(text_buf).strip()
        text_buf.clear()
        if joined:
            content.append({"type": "text", "text": joined})

    for f in frames(transcript):
        ftype = f.get("type")
        if ftype == "text":
            text_buf.append(str(f.get("text") or ""))
            continue
        flush()
        if ftype == "tool_use":
            content.append({"type": "tool_use", "id": f.get("id"),
                            "name": f.get("name", "tool"),
                            "input": f.get("input") or {}})
        elif ftype == "tool_result":
            res = f.get("content")
            res = res if isinstance(res, str) else json.dumps(res, default=str)
            content.append({"type": "tool_result", "tool_use_id": f.get("tool_use_id"),
                            "content": res[:2048]})
    flush()
    return content


def tools_called(transcript: Any) -> list[str]:
    return [f["name"] for f in frames(transcript)
            if f.get("type") == "tool_use" and f.get("name")]


def stop_reason(transcript: Any) -> str | None:
    return transcript.get("stop_reason") if isinstance(transcript, dict) else None


def guards_fired(transcript: Any) -> list[str]:
    """Terminal-action guards the connector recorded on the envelope
    (`tags.guards_fired`). An empty list is an observation, not a gap."""
    if not isinstance(transcript, dict):
        return []
    return [g for g in ((transcript.get("tags") or {}).get("guards_fired") or [])
            if isinstance(g, str)]


def _card_blobs(transcript: Any) -> list[tuple[Any, dict]]:
    """(frame type, card dict) for every card frame. A card is either a frame
    of a card type itself, or a frame carrying a nested `card` dict."""
    out = []
    for f in frames(transcript):
        blob = f.get("card") if isinstance(f.get("card"), dict) else None
        if blob is None and f.get("type") in CARD_RESUME_KEY:
            blob = f
        if isinstance(blob, dict):
            out.append((f.get("type"), blob))
    return out


def cards(transcript: Any) -> list[dict]:
    """Every card the turn produced, as its card dict."""
    return [blob for _, blob in _card_blobs(transcript)]


def pending_halt(transcript: Any) -> dict | None:
    """What the turn is waiting on and how to resume it:
    `{"key": "approval_id" | "card_id" | "choice_id", "value", "kind"}`.

    Two mechanisms, mirroring chat_resume: a tier-gated approval (carries
    approval_id) wins over a card halt (an emit_* card whose id is echoed)."""
    approval_id = None
    card: tuple[str, str] | None = None
    for f in frames(transcript):
        if not approval_id and f.get("approval_id"):
            approval_id = f["approval_id"]
        if isinstance(f.get("approval"), dict) and f["approval"].get("approval_id"):
            approval_id = f["approval"]["approval_id"]
        if f.get("pending_approval") and f.get("approval_id"):
            approval_id = f["approval_id"]
    for ftype, blob in _card_blobs(transcript):
        # A nested card may omit its own type; the frame's type then names it.
        ctype = blob.get("type") or ftype
        if ctype in CARD_RESUME_KEY and blob.get("id"):
            card = (ctype, blob["id"])
    if approval_id:
        return {"key": "approval_id", "value": approval_id, "kind": "approval"}
    if card:
        return {"key": CARD_RESUME_KEY[card[0]], "value": card[1], "kind": card[0]}
    return None


@dataclass(frozen=True)
class ToolCall:
    """One tool call of a turn, paired with its result.

    `name` and `args` come from the `tool_use` frame. The wire's `tool_result`
    carries only `tool_use_id`, so the name is taken from the matching
    `tool_use`, never from the result frame (which has no `name` or `tool`).
    `result` is the decoded body (a JSON string is parsed). `ok` is the
    body's own `ok` flag when it has one, else None."""

    id: str | None
    name: str
    args: dict
    result: Any = None
    has_result: bool = False

    @property
    def ok(self) -> bool | None:
        if isinstance(self.result, dict) and isinstance(self.result.get("ok"), bool):
            return self.result["ok"]
        return None


def _decode(body: Any) -> Any:
    if isinstance(body, str):
        try:
            return json.loads(body)
        except ValueError:
            return body
    return body


@dataclass(frozen=True)
class ToolResult:
    """One `tool_result` frame: its `tool_use_id` and the decoded body. The
    result frame has no name; use `tool_calls` to pair it with its call."""

    tool_use_id: str | None
    body: Any


def tool_results(transcript: Any) -> list[ToolResult]:
    """Every tool result of the turn, in order, body decoded. A result whose
    body is a JSON string is parsed; a body that is not JSON stays a string."""
    out = []
    for f in frames(transcript):
        if f.get("type") != "tool_result":
            continue
        raw = f.get("content") or f.get("output") or f.get("result")
        out.append(ToolResult(f.get("tool_use_id"), _decode(raw)))
    return out


def tool_calls(transcript: Any) -> list[ToolCall]:
    """Every tool call the turn made, in order, each with its result paired by
    `tool_use_id`. A call with no result yet has `has_result=False`."""
    fs = frames(transcript)
    results: dict[str, Any] = {}
    for r in tool_results(fs):
        if r.tool_use_id is not None:
            results[r.tool_use_id] = r.body
    out: list[ToolCall] = []
    for f in fs:
        if f.get("type") != "tool_use":
            continue
        cid = f.get("id")
        args = f.get("input") or {}
        out.append(ToolCall(
            id=cid, name=str(f.get("name") or ""),
            args=args if isinstance(args, dict) else {},
            result=results.get(cid), has_result=cid in results))
    return out


def halts(transcript: Any) -> list[dict]:
    """The frames that halt the turn for an answer, in order."""
    return [f for f in frames(transcript) if f.get("type") in HALT_FRAME_TYPES]


# -- the delivered playbook -------------------------------------------------

_FENCE = re.compile(r"```ya?ml\s*\n([\s\S]*?)```", re.I)

#: The argument each YAML-carrying tool takes its playbook in. `emit_card`
#: nests the card's fields under `payload` (playbook_offer's `yaml`), so
#: `delivered_yaml` looks inside it.
YAML_CARRIER: dict[str, str] = {
    # build
    "emit_playbook_offer": "yaml",
    "verify_playbook": "yaml_text",
    "push_playbook": "yaml_text",
    # enhance
    "verify_enhancement": "after_yaml",
    "emit_card": "payload",
}


def extracted_yaml(transcript: Any) -> str:
    """The YAML the widget would push: the LAST ```yaml fence in the turn's
    streamed text.

    Mirrors `view.controller.js#_extractYaml`, including the reason it
    concatenates first: text arrives as streamed deltas, so a fence routinely
    spans several frames and a per-frame regex finds nothing. LAST fence, not
    first: the assistant often shows the current playbook before the revision.
    """
    combined = "".join(str(f.get("text") or "") for f in frames(transcript)
                       if f.get("type") == "text")
    found = _FENCE.findall(combined)
    return found[-1].strip() if found else ""


def is_offer_call(f: dict) -> bool:
    """A tool_use frame that delivers a playbook to the analyst."""
    if f.get("name") == "emit_playbook_offer":
        return True
    return (f.get("name") == "emit_card"
            and (f.get("input") or {}).get("card_type") in OFFER_CARD_TYPES)


def refused_tool_use_ids(transcript: Any) -> set:
    """ids of tool calls whose result came back `ok: false`."""
    out = set()
    for f in frames(transcript):
        if f.get("type") != "tool_result":
            continue
        body = _decode(f.get("content"))
        if isinstance(body, dict) and body.get("ok") is False:
            out.add(f.get("tool_use_id"))
    return out


def delivered_yaml(transcript: Any) -> str:
    """The playbook one turn delivered to the analyst. Order, first match wins
    in this order:

    1. the LAST offer card's `final_yaml` (playbook_offer / enhancement_offer);
    2. the LAST ```yaml fence in the streamed text;
    3. the LAST YAML-carrying tool argument (`YAML_CARRIER`), where an offer the
       tool REFUSED does not count and resets the carry.

    Shared by t1 scenarios and the conversation tier, so both agree on what a
    turn delivered."""
    fs = frames(transcript)
    offered = ""
    for f in fs:
        if f.get("type") in OFFER_CARD_TYPES:
            body = f.get("final_yaml")
            if isinstance(body, str) and body.strip():
                offered = body       # last delivered offer wins
    if offered:
        return offered
    fenced = extracted_yaml(fs)
    if fenced.strip():
        return fenced

    refused = refused_tool_use_ids(fs)
    carried = ""
    for f in fs:
        if f.get("type") != "tool_use":
            continue
        # An offer the tool REFUSED was never delivered, so it cannot pass as
        # the playbook. Drafts carried BEFORE the refusal are superseded too:
        # only what comes after it can count.
        if f.get("id") in refused and is_offer_call(f):
            carried = ""
            continue
        arg = YAML_CARRIER.get(f.get("name"))
        if not arg:
            continue
        body = (f.get("input") or {}).get(arg)
        if f.get("name") == "emit_card" and isinstance(body, dict):
            body = body.get("yaml") or body.get("after_yaml")
        if isinstance(body, str) and body.strip():
            carried = body  # last one wins, mirroring the fence rule
    return carried

