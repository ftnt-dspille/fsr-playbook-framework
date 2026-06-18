"""Chat-review heuristics — mine one session for known failure modes.

Used by both the `fsrpb chat-review <session_id>` CLI and the
`review_chat_session` MCP tool. Pure-python, no live FSR — operates
entirely on the rows already in `web/backend/history.db`.

Each pattern is a small detector that runs against the loaded session
and yields zero or more `Finding` records. The report aggregates them
plus a one-line headline so a human (or another Claude session) can
glance at the output and know whether to drill deeper.

Findings are ordered by severity (`error` > `warning` > `info`) then
by turn so the most actionable items are first.

Pattern reference (driven by the corpus audit
`MI_DECISION_VALIDATION_AUDIT.md` + the down-rated feedback rows):
  - validate-fix-validate spiral (3+ calls, error count not decreasing)
  - tool result empty (likely "search returned nothing")
  - tool result heavy (>5KB, suggests verbose default not used)
  - validate_yaml errors recurring across calls (e.g. missing collection)
  - agent emitted UUID-shaped step ids
  - agent used `set_variable: variables:` typo
  - session ended with no successful push (no YAML actually shipped)
  - feedback rating='down' — surface the user's note prominently
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


_DEFAULT_DB = Path(__file__).resolve().parents[1] / "web" / "backend" / "history.db"


@dataclass
class Finding:
    severity: str           # 'error' | 'warning' | 'info'
    code: str               # short slug for grouping
    title: str              # one-line headline
    detail: str             # multi-line explanation incl. evidence
    turn: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "title": self.title,
            "detail": self.detail,
            "turn": self.turn,
            "suggestion": self.suggestion,
        }


@dataclass
class Report:
    session_id: str
    headline: str
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "headline": self.headline,
            "findings": [f.to_dict() for f in self.findings],
            "stats": self.stats,
        }


# ---------------------------------------------------------------------------
# DB load
# ---------------------------------------------------------------------------

def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else Path(
        os.environ.get("STUDIO_HISTORY_DB", _DEFAULT_DB)
    )
    if not path.exists():
        raise FileNotFoundError(f"history db not found at {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_session(session_id: str,
                 db_path: Path | str | None = None) -> dict[str, Any]:
    """Return the full per-turn record for a session."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"no session {session_id!r}")
        out = dict(row)
        out["turns"] = [dict(r) for r in conn.execute(
            "SELECT * FROM chat_turns WHERE session_id=? ORDER BY turn",
            (session_id,),
        )]
        out["tool_calls"] = [dict(r) for r in conn.execute(
            "SELECT * FROM chat_tool_calls WHERE session_id=? ORDER BY turn, seq",
            (session_id,),
        )]
        out["messages"] = [dict(r) for r in conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY turn, seq",
            (session_id,),
        )]
        out["latest_push"] = None
        push = conn.execute(
            "SELECT * FROM pushes WHERE chat_session_id=? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if push:
            out["latest_push"] = dict(push)
        fb = conn.execute(
            "SELECT * FROM chat_feedback WHERE session_id=?", (session_id,)
        ).fetchone()
        out["feedback"] = dict(fb) if fb else None
    finally:
        conn.close()
    return out


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# Tool-result size thresholds (bytes / chars)
_RESULT_EMPTY_THRESHOLD = 50
_RESULT_HEAVY_THRESHOLD = 5_000
# Validate-spiral: 3+ validate_yaml calls and the error count never
# strictly decreases for two consecutive calls.
_SPIRAL_MIN_CALLS = 3


def _find_assistant_yaml_blocks(messages: list[dict]) -> list[tuple[int, str]]:
    """Yield (turn, yaml_text) for every fenced ```yaml block emitted
    by the assistant in this session.

    Streamed assistant text lands across many `assistant_text` rows
    within one chat turn (each SSE TextEvent → one row). We concatenate
    by turn before scanning so a fenced block split across rows is
    still matched.
    """
    by_turn: dict[int, list[str]] = {}
    for m in messages:
        if m.get("kind") != "assistant_text":
            continue
        by_turn.setdefault(m.get("turn", -1), []).append(m.get("content") or "")
    out: list[tuple[int, str]] = []
    for turn, parts in by_turn.items():
        joined = "".join(parts)
        for match in re.finditer(r"```yaml\s*\n([\s\S]*?)```", joined):
            out.append((turn, match.group(1)))
    return out


def _tool_result_for(messages: list[dict],
                     session_turn: int, after_seq: int) -> dict | None:
    """Return the next tool_result row in the same turn after a given seq."""
    for m in messages:
        if m.get("turn") != session_turn:
            continue
        if m.get("seq", -1) <= after_seq:
            continue
        if m.get("kind") == "tool_result":
            return m
    return None


def _detect_feedback(s: dict) -> Iterator[Finding]:
    fb = s.get("feedback") or {}
    if not fb:
        return
    rating = fb.get("rating")
    summary = fb.get("summary") or "(no summary written)"
    if rating == "down":
        yield Finding(
            severity="error",
            code="user_thumbs_down",
            title=f"User thumbed this session DOWN: {summary[:120]}",
            detail=(
                f"Full review summary:\n  {summary}\n\n"
                f"Tags: {fb.get('tags') or '-'}\n"
                f"Saved at: {fb.get('ts')}"
            ),
            suggestion=(
                "Read the user's summary above and treat it as the "
                "primary signal — the rest of the patterns below are "
                "supporting evidence."
            ),
        )
    elif rating == "up":
        yield Finding(
            severity="info",
            code="user_thumbs_up",
            title=f"User thumbed this session UP: {summary[:120]}",
            detail=f"Saved at: {fb.get('ts')}",
        )


def _detect_validate_spiral(s: dict) -> Iterator[Finding]:
    validates = [t for t in s.get("tool_calls", [])
                 if t.get("name") == "validate_yaml"]
    if len(validates) < _SPIRAL_MIN_CALLS:
        return
    # Pull error counts from each validate's tool_result.
    counts: list[int] = []
    for t in validates:
        r = _tool_result_for(
            s.get("messages", []), t["turn"], t["seq"] - 1
        )
        if r and r.get("content"):
            try:
                payload = json.loads(r["content"])
                errs = payload.get("errors") if isinstance(payload, dict) else None
                if isinstance(errs, list):
                    counts.append(len(errs))
                else:
                    counts.append(0 if payload.get("ok") else -1)
            except json.JSONDecodeError:
                counts.append(-1)
        else:
            counts.append(-1)
    # Heuristic: if we have 3+ calls and the count never goes to 0 AND
    # never drops by ≥2 between adjacent calls, the agent is spinning.
    if not any(c == 0 for c in counts):
        if all(
            counts[i + 1] >= counts[i] - 1 and counts[i] != -1
            for i in range(len(counts) - 1) if counts[i + 1] != -1
        ):
            yield Finding(
                severity="warning",
                code="validate_spiral",
                title=(
                    f"Validate-fix-validate spiral: {len(validates)} "
                    f"calls, error counts {counts}"
                ),
                detail=(
                    "validate_yaml fired 3+ times without converging "
                    "to zero errors. Each call sent ~3-4KB of error "
                    "JSON back to the agent — this is the dominant "
                    "context-eating failure mode. The new "
                    "`next_fix` field on validate_yaml should help "
                    "(landed I31); also consider whether the agent "
                    "needed to `get_step_type` first."
                ),
                suggestion=(
                    "If this session pre-dates I31, no action — the "
                    "fix is already shipped. If it's newer, the "
                    "agent ignored next_fix; tighten the system prompt."
                ),
            )


def _detect_tool_result_size(s: dict) -> Iterator[Finding]:
    empty: list[dict] = []
    heavy: list[dict] = []
    for t in s.get("tool_calls", []):
        rc = t.get("result_chars")
        if rc is None:
            continue
        if rc < _RESULT_EMPTY_THRESHOLD and t.get("name") in (
            "find_connector", "find_operation", "search_playbooks",
            "search_api_examples", "find_recipe",
        ):
            empty.append(t)
        if rc > _RESULT_HEAVY_THRESHOLD:
            heavy.append(t)
    if empty:
        names = ", ".join(sorted({t["name"] for t in empty}))
        yield Finding(
            severity="warning",
            code="empty_search_results",
            title=(
                f"{len(empty)} search call(s) returned essentially "
                f"nothing (<{_RESULT_EMPTY_THRESHOLD} chars): {names}"
            ),
            detail=(
                "When the agent searches for a connector/op that "
                "doesn't exist, it gets back `[]` and either retries "
                "with another guess (token waste) or gives up. The "
                "I32 fix added `near[]` close-matches to help; if this "
                "is an older session, the agent didn't have that hint."
            ),
            suggestion=(
                "If this is a recent session, check whether the agent "
                "used the `near[]` suggestion or kept guessing."
            ),
        )
    if heavy:
        top = sorted(heavy, key=lambda t: -t.get("result_chars", 0))[:3]
        lines = [
            f"  - {t['name']} (turn {t['turn']}): "
            f"{t.get('result_chars', 0):,} chars"
            for t in top
        ]
        yield Finding(
            severity="info",
            code="heavy_tool_results",
            title=(
                f"{len(heavy)} tool call(s) returned >5KB; "
                f"{sum(t.get('result_chars', 0) for t in heavy):,} "
                f"chars total"
            ),
            detail=(
                "Big tool responses burn context and the cache. Top:\n"
                + "\n".join(lines)
            ),
            suggestion=(
                "Pass `verbose=False` (default after I32) on "
                "find_connector/find_operation; for get_step_type, "
                "consider whether the agent needed verbose mode."
            ),
        )


def _detect_uuid_step_ids(s: dict) -> Iterator[Finding]:
    blocks = _find_assistant_yaml_blocks(s.get("messages", []))
    bad: list[tuple[int, list[str]]] = []
    for turn, yaml_text in blocks:
        # Look at lines starting with `- id: ` (and `id: ` after `-`).
        ids = re.findall(r"^\s*-?\s*id:\s*([A-Za-z0-9-]+)", yaml_text, re.M)
        uuids = [i for i in ids if _UUID_RE.fullmatch(i)]
        if uuids:
            bad.append((turn, uuids))
    if bad:
        first_turn, first_uuids = bad[0]
        yield Finding(
            severity="warning",
            code="uuid_step_ids",
            title=(
                f"Agent emitted UUID-shaped step ids "
                f"(turn {first_turn}, {len(first_uuids)} step(s))"
            ),
            detail=(
                "Step ids should be short slugs ('prompt_for_ip', "
                "'set_severity'), not UUIDs. The compiler generates "
                "the real UUIDs at emit time. Putting UUIDs into "
                "`id:` breaks every cross-reference. Examples:\n"
                + "\n".join(f"  - {u}" for u in first_uuids[:5])
            ),
            turn=first_turn,
            suggestion=(
                "I29 linter now warns on this; if the session post-"
                "dates the lint rule, the agent ignored the warning."
            ),
        )


def _detect_set_variable_typo(s: dict) -> Iterator[Finding]:
    """Catch `arguments.variables:` (or vars / set / values) on any
    set_variable step that the agent emitted."""
    blocks = _find_assistant_yaml_blocks(s.get("messages", []))
    typo_keys = ("variables", "vars", "set", "values")
    hits: list[tuple[int, str]] = []
    for turn, yaml_text in blocks:
        # Crude, doesn't parse YAML — just looks for `type: set_variable`
        # blocks followed within a window by the typo key.
        idx = 0
        while True:
            m = re.search(r"type:\s*set_variable\b", yaml_text[idx:])
            if not m:
                break
            window = yaml_text[idx + m.start(): idx + m.start() + 800]
            for k in typo_keys:
                if re.search(rf"^\s+{k}:", window, re.M):
                    hits.append((turn, k))
                    break
            idx += m.end()
    if hits:
        first_turn, first_key = hits[0]
        yield Finding(
            severity="warning",
            code="set_variable_typo",
            title=(
                f"set_variable used `{first_key}:` instead of "
                f"`arg_list:` (turn {first_turn})"
            ),
            detail=(
                "`variables` / `vars` / `set` / `values` get dropped "
                "silently at runtime, leaving the playbook with no "
                "variables set. Real-world bug from session 60743f70."
            ),
            turn=first_turn,
            suggestion=(
                "I28 trap now hard-errors on this. If post-I28, the "
                "agent ignored the error or pre-dates the fix."
            ),
        )


def _detect_missing_collection(s: dict) -> Iterator[Finding]:
    """Recurring `missing_field: collection` errors across validate calls."""
    count = 0
    for m in s.get("messages", []):
        if m.get("kind") != "tool_result":
            continue
        content = m.get("content") or ""
        if "\"path\": \"collection\"" in content and \
                "missing_field" in content:
            count += 1
    if count >= 2:
        yield Finding(
            severity="warning",
            code="missing_collection_recurring",
            title=(
                f"Agent forgot `collection:` {count} time(s) in this "
                f"session"
            ),
            detail=(
                "Most common compile error in the corpus. The agent "
                "drafted YAML without `collection:` at the top, then "
                "had to re-validate after fixing it. System-prompt "
                "rule #11 (added 2026-05-06) should remind the agent."
            ),
            suggestion="If session post-dates I30, the agent ignored the rule.",
        )


def _detect_no_push(s: dict) -> Iterator[Finding]:
    if s.get("latest_push"):
        return
    if (s.get("turn_count") or 0) >= 3:
        yield Finding(
            severity="info",
            code="no_deploy",
            title="Session never deployed a playbook",
            detail=(
                "3+ turns without a successful push. Either the user "
                "abandoned the work, or the agent could not produce "
                "a clean YAML. Check the final assistant message for "
                "the agent's exit reason."
            ),
        )


def _detect_unknown_connector(s: dict) -> Iterator[Finding]:
    """Tool results carrying compiler error code unknown_connector / op."""
    bad: list[tuple[int, str]] = []
    for m in s.get("messages", []):
        if m.get("kind") != "tool_result":
            continue
        c = m.get("content") or ""
        for code in ("unknown_connector", "unknown_operation"):
            if f'"code": "{code}"' in c:
                bad.append((m.get("turn", -1), code))
                break
    if bad:
        first_turn, _ = bad[0]
        codes = sorted({c for _, c in bad})
        yield Finding(
            severity="warning",
            code="unknown_connector_or_op",
            title=(
                f"Agent referenced unknown connector/operation "
                f"{len(bad)} time(s) (codes: {', '.join(codes)})"
            ),
            detail=(
                "Often means the agent guessed a vendor or op name "
                "instead of running find_connector/find_operation "
                "first. Check whether the agent followed the "
                "tool-use playbook in the system prompt."
            ),
            turn=first_turn,
        )


# Lower-case substrings that strongly suggest the user asked for
# playbook authoring/editing. Used to scope the "agent finished without
# emitting YAML" detector — it shouldn't fire on chitchat turns.
_AUTHORING_INTENT_HINTS = (
    "build a playbook", "create a playbook", "make a playbook",
    "build me a playbook", "write a playbook", "draft a playbook",
    "add a step", "modify the playbook", "fix the yaml",
    "edit the yaml", "update the playbook", "extend the playbook",
    "let's add", "add the", "include a", "build it",
)
# Tokens that look very much like FSR playbook YAML — used to detect
# fenced blocks the agent emitted with the wrong language tag (or no
# tag at all) so the frontend extractor missed them.
_YAML_SHAPED_TOKENS = (
    "collection:", "playbooks:", "type: connector",
    "type: set_variable", "type: decision", "type: manual_input",
    "arguments:", "steps:",
)


def _user_text_for_turn(messages: list[dict], turn: int) -> str:
    """Concatenate every user message that could have prompted this
    assistant turn. In live logging, user prompts and the assistant
    reply they triggered may be stamped with adjacent turn numbers
    (user n-1 → assistant n), so we scan back to the previous
    assistant turn boundary."""
    # Find the most recent assistant turn before `turn`; user messages
    # between that boundary and `turn` (inclusive) are this turn's
    # prompts.
    prior_assistant_turns = sorted({
        m.get("turn") for m in messages
        if m.get("kind") == "assistant_text"
        and isinstance(m.get("turn"), int) and m["turn"] < turn
    })
    boundary = prior_assistant_turns[-1] if prior_assistant_turns else -1
    return "\n".join(
        m.get("content") or ""
        for m in messages
        if m.get("kind") == "user"
        and isinstance(m.get("turn"), int)
        and boundary < m["turn"] <= turn
    ).lower()


def _detect_no_editor_update(s: dict) -> Iterator[Finding]:
    """Agent emitted text but no ```yaml block, so the editor never
    received a buffer replace. Frontend silently dropped the turn —
    looks like a hung agent from the user's perspective.

    Fires when: at least one assistant turn followed a user message
    that asked for authoring AND that turn produced no fenced ```yaml
    block.
    """
    messages = s.get("messages") or []
    if not messages:
        return
    # Index assistant text by turn (concatenated).
    by_turn: dict[int, list[str]] = {}
    for m in messages:
        if m.get("kind") == "assistant_text":
            by_turn.setdefault(m.get("turn", -1), []).append(m.get("content") or "")
    bad_turns: list[int] = []
    for turn, parts in by_turn.items():
        joined = "".join(parts)
        if not joined.strip():
            continue
        intent = _user_text_for_turn(messages, turn)
        if not intent:
            continue
        if not any(h in intent for h in _AUTHORING_INTENT_HINTS):
            continue
        if re.search(r"```ya?ml\s*\n[\s\S]*?```", joined, re.IGNORECASE):
            continue
        bad_turns.append(turn)
    if bad_turns:
        yield Finding(
            severity="error",
            code="no_editor_update",
            title=(
                f"Agent finished {len(bad_turns)} turn(s) without "
                f"emitting a ```yaml block — editor was never "
                f"updated (turns {bad_turns})"
            ),
            detail=(
                "From the user's perspective the agent 'didn't add "
                "the playbook to the UI'. The chat shows assistant "
                "text, but `extractYamlBlock` returned null because "
                "no ```yaml fenced block was present.\n\n"
                "Common causes:\n"
                "  - Agent answered in prose only ('here's how you'd '\n"
                "    do it…') without producing the YAML block.\n"
                "  - Fenced block used the wrong tag (```yml works,\n"
                "    ```YAML works, but plain ``` does NOT).\n"
                "  - Agent emitted partial YAML inside backticks\n"
                "    inline rather than a fenced block."
            ),
            turn=bad_turns[0],
            suggestion=(
                "Tighten the system prompt: 'Your output MUST end with "
                "a single fenced ```yaml block containing the COMPLETE "
                "current playbook YAML' is already there but worth "
                "moving higher. Also consider a UI warning when an "
                "authoring turn ends with no YAML."
            ),
        )


def _detect_yaml_in_wrong_fence(s: dict) -> Iterator[Finding]:
    """Agent put YAML-shaped content inside a code fence with the wrong
    language tag (or no tag), so `extractYamlBlock` missed it. Different
    failure from `no_editor_update` — here the YAML *was* produced, just
    in a fence the extractor couldn't see."""
    messages = s.get("messages") or []
    by_turn: dict[int, list[str]] = {}
    for m in messages:
        if m.get("kind") == "assistant_text":
            by_turn.setdefault(m.get("turn", -1), []).append(m.get("content") or "")
    hits: list[tuple[int, str]] = []
    for turn, parts in by_turn.items():
        joined = "".join(parts)
        # Look for any fenced block whose language tag is NOT yaml/yml.
        for match in re.finditer(
            r"```([A-Za-z0-9_+-]*)\s*\n([\s\S]*?)```", joined
        ):
            lang = (match.group(1) or "").lower()
            body = match.group(2)
            if lang in ("yaml", "yml"):
                continue
            # Does the body look like FSR playbook YAML?
            score = sum(1 for tok in _YAML_SHAPED_TOKENS if tok in body)
            if score >= 2:
                hits.append((turn, lang or "(no tag)"))
    if hits:
        first_turn, first_tag = hits[0]
        tags = sorted({tag for _, tag in hits})
        yield Finding(
            severity="warning",
            code="yaml_in_wrong_fence",
            title=(
                f"YAML-shaped content in a non-yaml fence — extractor "
                f"missed it (turn {first_turn}, fence tag(s): "
                f"{', '.join(repr(t) for t in tags)})"
            ),
            detail=(
                "The agent put what looks like FSR playbook YAML "
                "inside a code fence whose language tag isn't `yaml` "
                "or `yml`, so `extractYamlBlock` ignored it and the "
                "editor wasn't updated. From the user's perspective "
                "the playbook didn't land."
            ),
            turn=first_turn,
            suggestion=(
                "Loosening `extractYamlBlock` to accept untagged fences "
                "containing playbook-shaped content is risky (false "
                "positives). Better fix: tighten system prompt rule "
                "that the YAML block MUST be ```yaml-tagged."
            ),
        )


_DETECTORS = (
    _detect_feedback,
    _detect_validate_spiral,
    _detect_tool_result_size,
    _detect_uuid_step_ids,
    _detect_set_variable_typo,
    _detect_missing_collection,
    _detect_unknown_connector,
    _detect_no_editor_update,
    _detect_yaml_in_wrong_fence,
    _detect_no_push,
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def review_session(session_id: str,
                   db_path: Path | str | None = None) -> Report:
    """Run every detector against `session_id` and return a Report."""
    sess = load_session(session_id, db_path=db_path)
    findings: list[Finding] = []
    for det in _DETECTORS:
        findings.extend(det(sess))

    # Sort: error first, then warning, then info; turn ascending within
    # severity. Findings with no turn float to the end of their severity
    # bucket (they're session-wide).
    sev_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (
        sev_order.get(f.severity, 3),
        f.turn if f.turn is not None else 10**6,
    ))

    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    if n_err:
        headline = f"⚠ {n_err} critical issue(s) found"
    elif n_warn:
        headline = f"⚠ {n_warn} potential issue(s) found"
    else:
        headline = "✓ Session looks clean (no known failure patterns matched)"

    stats = {
        "turn_count": sess.get("turn_count"),
        "tool_call_count": len(sess.get("tool_calls") or []),
        "validate_yaml_calls": sum(
            1 for t in sess.get("tool_calls", [])
            if t.get("name") == "validate_yaml"
        ),
        "model": sess.get("model"),
        "deployed": bool(sess.get("latest_push")),
        "has_feedback": bool(sess.get("feedback")),
        "feedback_rating": (sess.get("feedback") or {}).get("rating"),
    }

    return Report(
        session_id=session_id,
        headline=headline,
        findings=findings,
        stats=stats,
    )


def render_text(report: Report) -> str:
    """Pretty-print a Report for terminal output."""
    out: list[str] = []
    out.append(f"Chat-review: session {report.session_id}")
    out.append(f"  {report.headline}")
    out.append("")
    s = report.stats
    out.append(
        f"  turns:{s.get('turn_count')}  "
        f"tools:{s.get('tool_call_count')}  "
        f"validate_yaml:{s.get('validate_yaml_calls')}  "
        f"deployed:{'yes' if s.get('deployed') else 'no'}  "
        f"model:{s.get('model')}  "
        f"feedback:{s.get('feedback_rating') or '-'}"
    )
    out.append("")
    if not report.findings:
        out.append("  (no findings — session looks clean)")
        return "\n".join(out)
    for i, f in enumerate(report.findings, 1):
        sev_tag = {"error": "[!]", "warning": "[~]", "info": "[i]"}.get(
            f.severity, "[?]"
        )
        out.append(f"  {sev_tag} {i}. {f.title}"
                   + (f"  (turn {f.turn})" if f.turn is not None else ""))
        for line in f.detail.splitlines():
            out.append(f"        {line}")
        if f.suggestion:
            out.append(f"        → {f.suggestion}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
