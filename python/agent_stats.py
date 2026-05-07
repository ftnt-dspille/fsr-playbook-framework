"""Phase 1 analyzer for AGENT_QUALITY_PLAN.md.

Mines `web/backend/history.db` and emits three artifacts:
  - docs/AGENT_TOOL_USAGE.md       (1A: per-tool census)
  - docs/AGENT_DATA_GAPS.md        (1B: empty-result + repeated-call signals)
  - docs/AGENT_PROMPT_ADHERENCE.md (1C: structural prompt-rule checks)

Read-only against history.db. Reuses chat_review._connect for the ro
sqlite handle. Designed to keep working as session count grows.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import chat_review  # type: ignore

# --- result-size thresholds (chars) -----------------------------------
EMPTY_THRESHOLD = 50
HEAVY_THRESHOLD = 5_000
TOKENS_PER_CHAR = 0.25  # 4 chars per token rough est


# ---------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------

@dataclass
class ToolStat:
    name: str
    calls: int = 0
    result_sizes: list[int] = field(default_factory=list)
    arg_sizes: list[int] = field(default_factory=list)
    error_count: int = 0
    empty_count: int = 0
    follow_up: Counter = field(default_factory=Counter)  # next-tool-within-2 names
    by_rating: Counter = field(default_factory=Counter)  # up/down/none -> calls
    arg_shapes: Counter = field(default_factory=Counter) # shape signature -> n

    @property
    def median_result(self) -> int:
        return int(statistics.median(self.result_sizes)) if self.result_sizes else 0

    @property
    def p95_result(self) -> int:
        if not self.result_sizes:
            return 0
        s = sorted(self.result_sizes)
        i = max(0, int(round(0.95 * (len(s) - 1))))
        return s[i]


# ---------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------

def _all_session_ids(conn) -> list[str]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM chat_sessions ORDER BY ts_first"
    )]


def _load_all(db_path: str | os.PathLike | None = None) -> list[dict]:
    """Return every session as a dict (same shape as chat_review.load_session)."""
    conn = chat_review._connect(db_path)
    try:
        ids = _all_session_ids(conn)
    finally:
        conn.close()
    return [chat_review.load_session(sid, db_path=db_path) for sid in ids]


# ---------------------------------------------------------------------
# Phase 1A — tool-call census
# ---------------------------------------------------------------------

_ERROR_HINTS = ("\"ok\": false", "\"ok\":false", "\"error\"", "error:",
                "not_found", "no results", "couldn't find")


def _tool_use_args_index(messages: list[dict]) -> dict[tuple[int, int], dict]:
    """(turn, seq) -> parsed args dict, only for tool_use rows with content."""
    out: dict[tuple[int, int], dict] = {}
    for m in messages:
        if m.get("kind") != "tool_use":
            continue
        c = m.get("content")
        if not c:
            continue
        try:
            args = json.loads(c)
            if isinstance(args, dict):
                out[(m["turn"], m["seq"])] = args
        except json.JSONDecodeError:
            pass
    return out


def _tool_result_index(messages: list[dict]) -> dict[tuple[int, int], str]:
    """tool_use (turn, seq) -> tool_result.content (best-effort by next-after).

    Tool_result rows reference the tool_use via name=toolu_id, but we can
    reliably pair by sequence-after-tool_use within the same turn.
    """
    out: dict[tuple[int, int], str] = {}
    by_turn: dict[int, list[dict]] = defaultdict(list)
    for m in messages:
        by_turn[m.get("turn", -1)].append(m)
    for turn, rows in by_turn.items():
        rows.sort(key=lambda r: r["seq"])
        for i, r in enumerate(rows):
            if r.get("kind") != "tool_use":
                continue
            for nxt in rows[i + 1:]:
                if nxt.get("kind") == "tool_result":
                    out[(turn, r["seq"])] = nxt.get("content") or ""
                    break
    return out


def _arg_shape(args: dict) -> str:
    """Stable signature of arg shape: keys + jinja/literal hint per str."""
    parts: list[str] = []
    for k in sorted(args.keys()):
        v = args[k]
        if isinstance(v, str):
            kind = "<jinja>" if "{{" in v else "<str>"
        elif isinstance(v, bool):
            kind = "<bool>"
        elif isinstance(v, (int, float)):
            kind = "<num>"
        elif isinstance(v, list):
            kind = "<list>"
        elif isinstance(v, dict):
            kind = "<dict>"
        else:
            kind = "<null>"
        parts.append(f"{k}={kind}")
    return ", ".join(parts) or "(no args)"


def _is_error_result(content: str) -> bool:
    if not content:
        return True
    head = content[:300].lower()
    return any(h in head for h in _ERROR_HINTS)


def tool_census(sessions: list[dict]) -> dict[str, ToolStat]:
    stats: dict[str, ToolStat] = {}

    for s in sessions:
        rating = (s.get("feedback") or {}).get("rating") or "none"
        tcs = s.get("tool_calls", [])
        msgs = s.get("messages", [])
        args_idx = _tool_use_args_index(msgs)
        result_idx = _tool_result_index(msgs)
        # build ordered call list for follow-up coupling
        ordered = sorted(tcs, key=lambda t: (t["turn"], t["seq"]))

        for i, t in enumerate(ordered):
            name = t["name"]
            st = stats.setdefault(name, ToolStat(name=name))
            st.calls += 1
            if t.get("result_chars") is not None:
                st.result_sizes.append(t["result_chars"])
                if t["result_chars"] < EMPTY_THRESHOLD:
                    st.empty_count += 1
            if t.get("args_chars") is not None:
                st.arg_sizes.append(t["args_chars"])
            st.by_rating[rating] += 1

            args = args_idx.get((t["turn"], t["seq"] - 1)) \
                or args_idx.get((t["turn"], t["seq"]))
            if args is not None:
                st.arg_shapes[_arg_shape(args)] += 1

            res = result_idx.get((t["turn"], t["seq"] - 1)) \
                or result_idx.get((t["turn"], t["seq"]))
            if res is not None and _is_error_result(res):
                st.error_count += 1

            # follow-up coupling: next 2 calls in any subsequent turn
            for j in range(i + 1, min(i + 3, len(ordered))):
                st.follow_up[ordered[j]["name"]] += 1

    return stats


# ---------------------------------------------------------------------
# Phase 1B — data-gap signals
# ---------------------------------------------------------------------

@dataclass
class GapSignal:
    tool: str
    needle: str
    miss_count: int
    sessions: set[str] = field(default_factory=set)
    reason: str = "empty_or_error"


def data_gaps(sessions: list[dict]) -> list[GapSignal]:
    """Aggregate (tool, key-arg-needle) where the result was empty/error."""
    by_key: dict[tuple[str, str], GapSignal] = {}

    for s in sessions:
        sid = s["id"]
        msgs = s.get("messages", [])
        args_idx = _tool_use_args_index(msgs)
        result_idx = _tool_result_index(msgs)
        tcs = sorted(s.get("tool_calls", []), key=lambda t: (t["turn"], t["seq"]))

        # repeated identical calls within session
        seen_calls: Counter = Counter()
        for t in tcs:
            args = args_idx.get((t["turn"], t["seq"] - 1)) \
                or args_idx.get((t["turn"], t["seq"]))
            needle = _needle(args) if args else f"<no-args:size={t.get('args_chars',0)}>"
            seen_calls[(t["name"], needle)] += 1

            res = result_idx.get((t["turn"], t["seq"] - 1)) \
                or result_idx.get((t["turn"], t["seq"]))
            empty = (t.get("result_chars") or 0) < EMPTY_THRESHOLD
            errored = res is not None and _is_error_result(res)
            if empty or errored:
                key = (t["name"], needle)
                g = by_key.setdefault(key,
                    GapSignal(tool=t["name"], needle=needle, miss_count=0,
                              reason="empty" if empty else "error"))
                g.miss_count += 1
                g.sessions.add(sid)

        for (name, needle), n in seen_calls.items():
            if n >= 3:
                key = (name, needle)
                g = by_key.setdefault(key,
                    GapSignal(tool=name, needle=needle, miss_count=0,
                              reason="repeated"))
                g.reason = "repeated" if g.reason == "empty_or_error" else g.reason
                g.sessions.add(sid)

    return sorted(by_key.values(), key=lambda g: -g.miss_count)


def _needle(args: dict) -> str:
    """Shorten args to a recognizable lookup key for grouping."""
    for k in ("name", "q", "connector", "operation", "step_type",
              "module", "picklist"):
        if k in args and isinstance(args[k], (str, int)):
            return f"{k}={args[k]!s}"
    # fall back to short json
    try:
        s = json.dumps(args, sort_keys=True)
    except TypeError:
        s = str(args)
    return s[:80]


# ---------------------------------------------------------------------
# Phase 1C — prompt adherence (structural detectors)
# ---------------------------------------------------------------------

@dataclass
class AdherenceCheck:
    rule: str
    passed: int = 0
    violated: int = 0
    sample_sessions: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.violated

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


def prompt_adherence(sessions: list[dict]) -> list[AdherenceCheck]:
    checks = [
        AdherenceCheck(rule="find_connector before get_op_schema"),
        AdherenceCheck(rule="find_step_examples or get_op_schema before vars.steps.X.Y reference"),
        AdherenceCheck(rule="YAML wrapped in ```yaml fenced block"),
        AdherenceCheck(rule="No tool-call streak > 8 without assistant text"),
        AdherenceCheck(rule="validate_yaml errors monotonically non-increasing"),
    ]

    for s in sessions:
        sid = s["id"]
        msgs = s.get("messages", [])
        tcs = sorted(s.get("tool_calls", []), key=lambda t: (t["turn"], t["seq"]))
        result_idx = _tool_result_index(msgs)

        # --- 1: find_connector before get_op_schema ---
        seen_fc = False
        viol = False
        for t in tcs:
            if t["name"] == "find_connector":
                seen_fc = True
            if t["name"] == "get_op_schema" and not seen_fc:
                viol = True
                break
            if t["name"] == "get_op_schema":
                seen_fc = False  # reset per-op
        _bump(checks[0], sid, viol)

        # --- 2: vars.steps.X.Y reference w/o prior find_step_examples or get_op_schema ---
        prior_lookup_turns: set[int] = set()
        for t in tcs:
            if t["name"] in ("find_step_examples", "get_op_schema"):
                prior_lookup_turns.add(t["turn"])
        viol2 = False
        for m in msgs:
            if m.get("kind") != "assistant_text":
                continue
            if not m.get("content"):
                continue
            if "vars.steps." in m["content"]:
                if not any(pt <= m["turn"] for pt in prior_lookup_turns):
                    viol2 = True
                    break
        _bump(checks[1], sid, viol2)

        # --- 3: yaml block fenced as ```yaml ---
        viol3 = False
        text_by_turn: dict[int, str] = defaultdict(str)
        for m in msgs:
            if m.get("kind") == "assistant_text":
                text_by_turn[m["turn"]] += m.get("content") or ""
        for turn, joined in text_by_turn.items():
            # any generic fence containing yaml-looking content (id:/name:)?
            for match in re.finditer(r"```([a-zA-Z]*)\s*\n([\s\S]*?)```", joined):
                lang, body = match.group(1), match.group(2)
                if re.search(r"^\s*(id|name|playbooks)\s*:", body, re.M) and lang.lower() != "yaml":
                    viol3 = True
                    break
            if viol3:
                break
        _bump(checks[2], sid, viol3)

        # --- 4: no run of >8 tool-uses without assistant text ---
        seq_kinds = sorted(
            ((m["turn"], m["seq"], m["kind"]) for m in msgs
             if m.get("kind") in ("tool_use", "assistant_text")),
            key=lambda x: (x[0], x[1]),
        )
        streak = 0
        viol4 = False
        for _, _, k in seq_kinds:
            if k == "tool_use":
                streak += 1
                if streak > 8:
                    viol4 = True
                    break
            else:
                streak = 0
        _bump(checks[3], sid, viol4)

        # --- 5: validate_yaml errors non-increasing ---
        validates = [t for t in tcs if t["name"] == "validate_yaml"]
        counts: list[int] = []
        for t in validates:
            r = result_idx.get((t["turn"], t["seq"] - 1)) \
                or result_idx.get((t["turn"], t["seq"]))
            if not r:
                continue
            try:
                payload = json.loads(r)
                errs = payload.get("errors") if isinstance(payload, dict) else None
                if isinstance(errs, list):
                    counts.append(len(errs))
            except (json.JSONDecodeError, TypeError):
                pass
        viol5 = False
        for i in range(1, len(counts)):
            if counts[i] > counts[i - 1]:
                viol5 = True
                break
        if len(counts) >= 2:
            _bump(checks[4], sid, viol5)

    return checks


def _bump(c: AdherenceCheck, sid: str, violated: bool) -> None:
    if violated:
        c.violated += 1
        if len(c.sample_sessions) < 5:
            c.sample_sessions.append(sid)
    else:
        c.passed += 1


# ---------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------

def render_tool_usage(stats: dict[str, ToolStat]) -> str:
    lines = ["# Agent tool usage census",
             "",
             "Auto-generated by `fsrpb agent-stats`. Re-run any time.",
             "",
             "## Per-tool summary (sorted by call count)",
             "",
             "| Tool | Calls | Median res | p95 res | ~p95 tok | Errors | Empty | Up | Down |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for st in sorted(stats.values(), key=lambda s: -s.calls):
        lines.append(
            f"| `{st.name}` | {st.calls} | {st.median_result} | {st.p95_result} | "
            f"{int(st.p95_result * TOKENS_PER_CHAR)} | {st.error_count} | "
            f"{st.empty_count} | {st.by_rating.get('up',0)} | "
            f"{st.by_rating.get('down',0)} |"
        )

    lines += ["", "## Argument-shape histogram (top tools)", ""]
    for st in sorted(stats.values(), key=lambda s: -s.calls)[:10]:
        if not st.arg_shapes:
            continue
        lines.append(f"### `{st.name}`")
        lines.append("")
        for shape, n in st.arg_shapes.most_common(8):
            lines.append(f"- `{shape}` × {n}")
        lines.append("")

    lines += ["## Follow-up coupling (top 5 tools, next-2 calls)",
              ""]
    for st in sorted(stats.values(), key=lambda s: -s.calls)[:5]:
        if not st.follow_up:
            continue
        top = ", ".join(f"`{n}`×{c}" for n, c in st.follow_up.most_common(5))
        lines.append(f"- **{st.name}** → {top}")
    lines.append("")
    return "\n".join(lines)


def render_data_gaps(gaps: list[GapSignal]) -> str:
    lines = ["# Agent data gaps",
             "",
             "Auto-generated by `fsrpb agent-stats`. Each row is a "
             "(tool, lookup-needle) where the result was empty, errored, "
             "or repeated 3+ times within one session.",
             "",
             "| Tool | Needle | Misses | Sessions | Reason |",
             "|---|---|---:|---:|---|"]
    for g in gaps[:200]:
        lines.append(
            f"| `{g.tool}` | `{g.needle}` | {g.miss_count} | "
            f"{len(g.sessions)} | {g.reason} |"
        )
    if not gaps:
        lines.append("| — | (no gap signals detected) | 0 | 0 | — |")
    lines.append("")
    return "\n".join(lines)


def render_adherence(checks: list[AdherenceCheck]) -> str:
    lines = ["# Agent prompt adherence",
             "",
             "Auto-generated by `fsrpb agent-stats`. Structural detectors "
             "for rules in `python/agent/system_prompt.md`.",
             "",
             "| Rule | Sessions | Pass | Violated | Pass rate | Sample violators |",
             "|---|---:|---:|---:|---:|---|"]
    for c in checks:
        samples = ", ".join(f"`{s}`" for s in c.sample_sessions) or "—"
        rate = f"{c.pass_rate * 100:.0f}%" if c.total else "n/a"
        lines.append(
            f"| {c.rule} | {c.total} | {c.passed} | {c.violated} | {rate} | {samples} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Top-level entrypoint
# ---------------------------------------------------------------------

def run(out_dir: Path, db_path: str | os.PathLike | None = None) -> dict[str, Path]:
    sessions = _load_all(db_path)
    stats = tool_census(sessions)
    gaps = data_gaps(sessions)
    checks = prompt_adherence(sessions)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "usage": out_dir / "AGENT_TOOL_USAGE.md",
        "gaps": out_dir / "AGENT_DATA_GAPS.md",
        "adherence": out_dir / "AGENT_PROMPT_ADHERENCE.md",
    }
    paths["usage"].write_text(render_tool_usage(stats))
    paths["gaps"].write_text(render_data_gaps(gaps))
    paths["adherence"].write_text(render_adherence(checks))
    return paths
