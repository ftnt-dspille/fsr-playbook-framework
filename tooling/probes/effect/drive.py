"""Drive the connector the way the WIDGET drives it.

Harness rule paid for in blood: mirror the widget's payload exactly. Sending
`decision:"accept"` where the widget sends `"approve"` once routed a card into
the playbook_offer branch and came back "no recorded actions in the trace" --
which reads exactly like a product bug and is not one.

The payload shape below is transcribed from
`fortiaiAgenticAssistant/widget/view.controller.js`:

  acceptEnhancementOffer-> _runResumeOffer(offerId, 'accept', null, null, iri)
                           => {session_id, decision, offer_id, workflow_iri, mode}

If that handler changes, this file is wrong and the probes start lying.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

from evals.chat_drive import BoxExec  # noqa: E402

from fsr_playbooks.harness import frames  # noqa: E402
from fsr_playbooks.harness.drive import FsrTransport  # noqa: E402
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


def _transport(config: str, version: str) -> FsrTransport:
    # The shared driver's sync transport over the raw-execute adapter: the
    # version is omitted when empty, the config is always sent.
    return FsrTransport(BoxExec(get_client(), version=version or None,
                                config=config), session_id="effect-probe")


def turn(message: str, *, session: str, intent: str = "build",
         entity: dict | None = None, record: dict | None = None,
         config: str = CONFIG, version: str = VERSION) -> dict:
    params: dict[str, Any] = {
        "session_id": session,
        "messages": [{"role": "user", "content": message}],
        "intent": intent, "mode": "live", "detached": False,
    }
    if entity is not None:
        params["entity"] = entity
    if record is not None:
        params["record"] = record
    try:
        res = _transport(config, version).turn(params)
    except RuntimeError as exc:  # a non-dict answer: keep it in the dump, then fail
        LOG.append({"call": "chat_turn", "params": params, "result": str(exc)})
        raise
    LOG.append({"call": "chat_turn", "params": params, "result": res})
    return res


def resume(payload: dict, *, config: str = CONFIG, version: str = VERSION) -> dict:
    body = dict(payload, mode="live")
    try:
        res = _transport(config, version).resume(body)
    except RuntimeError as exc:
        LOG.append({"call": "chat_resume", "params": body, "result": str(exc)})
        raise
    LOG.append({"call": "chat_resume", "params": body, "result": res})
    return res


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
    return [c for c in frames.cards(res) if c.get("type") == kind]


def first_card(res: dict, kind: str) -> dict | None:
    got = cards(res, kind)
    return got[0] if got else None


def tool_names(res: dict) -> list[str]:
    return frames.tools_called(res)


def final_text(res: dict) -> str:
    return frames.assistant_text(res)
