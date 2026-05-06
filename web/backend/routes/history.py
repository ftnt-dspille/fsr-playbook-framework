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


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Full session record: turns, tool calls, message transcript,
    latest push (with deployed YAML), feedback."""
    s = history_db.get_chat_session(session_id, include_messages=True)
    if s is None:
        raise HTTPException(404, f"no chat session {session_id!r}")
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


@router.get("/feedback")
def list_feedback(rating: str | None = None,
                  limit: int = 100) -> list[dict[str, Any]]:
    """All sessions that have user feedback. Useful when a future
    session wants to mine 'what went wrong' across the corpus."""
    return history_db.list_feedback(rating=rating, limit=limit)


@router.get("/pushes")
def list_pushes(limit: int = 100,
                coll_uuid: str | None = None) -> list[dict[str, Any]]:
    return history_db.list_pushes(limit=limit, coll_uuid=coll_uuid)


@router.get("/pushes/{push_id}")
def get_push(push_id: int) -> dict[str, Any]:
    p = history_db.get_push(push_id)
    if p is None:
        raise HTTPException(404, f"no push {push_id}")
    return p


@router.get("/timeline")
def timeline(limit: int = 50) -> list[dict[str, Any]]:
    """Combined chat-session + push timeline."""
    return history_db.timeline(limit=limit)
