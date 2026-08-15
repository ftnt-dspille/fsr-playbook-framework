"""Drive the connector the way the WIDGET drives it.

Harness rule paid for in blood: mirror the widget's payload exactly. Sending
`decision:"accept"` where the widget sends `"approve"` routes a patch_proposal
into the playbook_offer branch and comes back "no recorded actions in the
trace" -- which reads exactly like a product bug and is not one.

The payload shapes below are transcribed from
`fortiaiAgenticAssistant/widget/view.controller.js`:

  acceptPatchProposal   -> _runResumeAction(cardId, 'approve', null, null,
                             {reply_tool, workflow_iri})
                           => {session_id, decision, card_id, args,
                               reply_tool, workflow_iri, mode}
  acceptEnhancementOffer-> _runResumeOffer(offerId, 'accept', null, null, iri)
                           => {session_id, decision, offer_id, workflow_iri, mode}

If either handler changes, this file is wrong and the probes start lying.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

from evals.chat_drive import _execute, _unwrap  # noqa: E402
from probes._env import get_client  # noqa: E402

CONFIG = ""      # empty = the box's default config, the analyst's real surface
VERSION = ""     # empty = the ACTIVE installed version

# Every turn and resume this module drives, in order. A live drive costs a
# minute and credits, so the raw payloads are kept for offline re-reading --
# re-grade, never re-drive. `runner.py --dump DIR` writes them out.
LOG: list[dict] = []


def reset_log() -> None:
    LOG.clear()


def new_session(tag: str) -> str:
    return f"effect-{tag}-{int(time.time())}"


def open_playbook_entity(iri: str, uuid: str, name: str, yaml_text: str) -> dict:
    """The mounted-open-playbook context the widget sends from the designer.

    Unlike the enhance-delivery runner (which mounts a FABRICATED iri because
    it only grades the transcript), this carries the REAL record: the write
    target and the read-back target have to be the same row or the probe
    proves nothing.
    """
    return {"iri": iri, "module": "workflows", "uuid": uuid,
            "fields": {"name": name}, "playbook_yaml": yaml_text}


def turn(message: str, *, session: str, intent: str = "build",
         entity: dict | None = None, record: dict | None = None,
         config: str = CONFIG, version: str = VERSION) -> dict:
    client = get_client()
    params: dict[str, Any] = {
        "session_id": session,
        "messages": [{"role": "user", "content": message}],
        "intent": intent, "mode": "live", "detached": False,
    }
    if entity is not None:
        params["entity"] = entity
    if record is not None:
        params["record"] = record
    res = _unwrap(_execute(client, "chat_turn", params, version, config))
    LOG.append({"call": "chat_turn", "params": params, "result": res})
    if not isinstance(res, dict):
        raise RuntimeError(f"chat_turn returned non-dict: {res!r:.300}")
    return res


def resume(payload: dict, *, config: str = CONFIG, version: str = VERSION) -> dict:
    client = get_client()
    body = dict(payload, mode="live")
    res = _unwrap(_execute(client, "chat_resume", body, version, config))
    LOG.append({"call": "chat_resume", "params": body, "result": res})
    if not isinstance(res, dict):
        raise RuntimeError(f"chat_resume returned non-dict: {res!r:.300}")
    return res


def accept_patch_proposal(session: str, card: dict, workflow_iri: str) -> dict:
    """acceptPatchProposal, verbatim."""
    return resume({
        "session_id": session,
        "decision": "approve",
        "card_id": card.get("card_id") or card.get("id") or card.get("proposal_id"),
        "args": None,
        "reply_tool": card.get("reply_tool"),
        "workflow_iri": workflow_iri,
    })


def accept_enhancement_offer(session: str, card: dict, workflow_iri: str) -> dict:
    """acceptEnhancementOffer, verbatim."""
    return resume({
        "session_id": session,
        "decision": "accept",
        "offer_id": card.get("offer_id") or card.get("id"),
        "workflow_iri": workflow_iri,
    })


# ── transcript helpers ────────────────────────────────────────────────

def cards(res: dict, kind: str) -> list[dict]:
    """Every card of one type in a turn result's transcript."""
    return [e for e in (res.get("transcript") or [])
            if isinstance(e, dict) and e.get("type") == kind]


def first_card(res: dict, kind: str) -> dict | None:
    got = cards(res, kind)
    return got[0] if got else None


def tool_names(res: dict) -> list[str]:
    return [e.get("name") or "" for e in (res.get("transcript") or [])
            if isinstance(e, dict) and e.get("type") in ("tool_use", "tool_call")]


def final_text(res: dict) -> str:
    return "".join(e.get("text", "") for e in (res.get("transcript") or [])
                   if isinstance(e, dict) and e.get("type") == "text").strip()
