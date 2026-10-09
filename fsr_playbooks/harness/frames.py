"""Reading a chat turn's transcript: the one copy every harness uses.

`chat_turn` / `chat_resume` return a response ENVELOPE (a dict with
`transcript[]`, `stop_reason`, `tags`); some paths return a bare frame list.
Every accessor here takes either.
"""
from __future__ import annotations

import json
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


def frames(transcript: Any) -> list[dict]:
    if isinstance(transcript, dict):
        return [f for f in (transcript.get("transcript") or []) if isinstance(f, dict)]
    if isinstance(transcript, list):
        return [f for f in transcript if isinstance(f, dict)]
    return []


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
