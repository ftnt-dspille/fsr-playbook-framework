"""Per-turn usage telemetry for the chat agent.

Each call to provider.stream() opens a session; each LLM round-trip
within that session writes one JSON line to STUDIO_USAGE_LOG (defaults
to web/backend/usage.jsonl). The log is append-only and safe to tail
or grep. Summarise with `fsrpb chat-stats <path>`.

Schema of one line:

    {
      "ts": "2026-05-03T20:11:42.318Z",
      "session": "8f3e…",            # uuid per stream() call
      "turn": 1,
      "model": "claude-sonnet-4-5-…",
      "input_tokens": 1234,           # billed
      "output_tokens": 256,           # billed
      "cache_read": 6800,             # cached prefix hit
      "cache_write": 0,               # ephemeral cache write
      "stop_reason": "tool_use",
      "self_repair_turn": 0,
      "history_chars": 14_280,        # serialised messages[] before this turn
      "history_est_tokens": 3570,     # chars/4 — rough eyeball
      "tool_calls": [
        {"name": "validate_yaml", "result_chars": 4096,
         "result_est_tokens": 1024, "args_chars": 320}
      ]
    }

Token estimates use the chars/4 heuristic — fine for spotting which
tool inflated context, useless for billing. Trust the API's
`input_tokens` / `output_tokens` for actual cost.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any


def default_log_path() -> Path:
    env = os.environ.get("STUDIO_USAGE_LOG")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[1] / "usage.jsonl"


def est_tokens(chars: int) -> int:
    """Rough chars→tokens. Anthropic's tokenizer averages ~3.6 chars/token
    for English; 4 is conservative and avoids over-claiming compression."""
    return chars // 4


def log_turn(record: dict[str, Any]) -> None:
    """Append one JSON line. Failures are swallowed — telemetry must
    never break the chat path."""
    try:
        path = default_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": _dt.datetime.now(_dt.timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            **record,
        }
        with path.open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass
