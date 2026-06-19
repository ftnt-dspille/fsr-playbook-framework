"""History routes — full chat replay, push log, user feedback.

The History tab needs to surface, per session:
  - the user's question + assistant text + every tool call
  - the steps the AI took (turns + tool sequence)
  - the final playbook YAML it produced (carried via the latest push)
  - thumb up/down + a free-form review summary so a future session can
    investigate problems or learn what went right.

All persistence lives in `web/backend/history.py` (sqlite). These
routes are read-mostly; the only mutation is feedback upsert/clear.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import history as history_db


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/sessions")
def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
    """List chat sessions newest-first, joined with feedback so the
    list view can render a thumb indicator + a teaser of the review."""
    return history_db.list_chat_sessions_with_feedback(limit=limit)


_YAML_TOOLS_WITH_TEXT = (
    "compile_yaml", "validate_yaml", "resolve_yaml",
    "assert_playbook_outcome", "diagnose_yaml_against_pb_execution",
    "step_through_playbook", "dry_run_playbook",
)
_YAML_FENCE_RE = re.compile(r"```yaml\s*\n([\s\S]*?)```", re.MULTILINE)


def _derive_final_yaml(detail: dict[str, Any]) -> tuple[str | None, str | None]:
    """Pull the most recent YAML the session settled on. Priority:
       1. push.source_yaml — what was actually deployed
       2. last YAML-bearing tool_use's `yaml_text` argument
       3. last fenced ```yaml block in any assistant_text row
    Returns (yaml, source_label) or (None, None) if nothing found."""
    push = detail.get("latest_push") or {}
    if push.get("source_yaml"):
        return push["source_yaml"], f"push #{push['id']}"
    messages = detail.get("messages") or []
    # Walk backwards so "most recent" wins.
    for m in reversed(messages):
        if m.get("kind") != "tool_use":
            continue
        if m.get("name") not in _YAML_TOOLS_WITH_TEXT:
            continue
        try:
            args = json.loads(m.get("content") or "{}")
        except Exception:
            continue
        text = args.get("yaml_text") if isinstance(args, dict) else None
        if isinstance(text, str) and text.strip():
            return text, f"tool: {m['name']}"
    for m in reversed(messages):
        if m.get("kind") != "assistant_text":
            continue
        text = m.get("content") or ""
        matches = _YAML_FENCE_RE.findall(text)
        if matches:
            block = matches[-1].strip()
            if block:
                return block, "assistant fenced block"
    return None, None


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Full session record: turns, tool calls, message transcript,
    latest push (with deployed YAML), feedback. Augments with
    `final_yaml` + `final_yaml_source` so the UI can show what the
    chat ended on even when no push happened."""
    s = history_db.get_chat_session(session_id, include_messages=True)
    if s is None:
        raise HTTPException(404, f"no chat session {session_id!r}")
    final_yaml, final_yaml_source = _derive_final_yaml(s)
    s["final_yaml"] = final_yaml
    s["final_yaml_source"] = final_yaml_source
    return s


class FeedbackBody(BaseModel):
    rating: str = Field(..., description="'up' or 'down'")
    summary: str | None = Field(
        None,
        description="Free-form review notes — what worked, what broke, "
                    "what a future session should investigate.",
    )
    tags: str | None = Field(
        None,
        description="Optional comma-separated short labels (e.g. "
                    "'wrong_step,missed_branch').",
    )


@router.post("/sessions/{session_id}/feedback")
def post_feedback(session_id: str, body: FeedbackBody) -> dict[str, Any]:
    try:
        return history_db.set_feedback(
            session_id, body.rating, body.summary, body.tags,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/sessions/{session_id}/feedback")
def delete_feedback(session_id: str) -> dict[str, Any]:
    cleared = history_db.clear_feedback(session_id)
    return {"cleared": cleared}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    deleted = history_db.delete_session(session_id)
    if not deleted:
        raise HTTPException(404, f"no session {session_id}")
    return {"deleted": True}


