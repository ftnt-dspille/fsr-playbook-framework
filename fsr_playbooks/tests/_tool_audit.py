"""Audit of what the model is sent per advertised tool versus the docstring.

`tool_description` caps a description and drops Args/Returns sections, so a
call contract written in the docstring can silently never reach the model.
`audit()` reproduces that loss per tool; `scripts/audit_tool_descriptions.py`
prints it and `test_tool_contracts_sent.py` ratchets on it.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass

from fsr_playbooks.llm import tools as T


@dataclass
class ToolAudit:
    name: str
    full: int          # docstring length
    sent: int          # description length sent, approval line excluded
    cut_text: str      # docstring text that is not in the description
    schema_chars: int  # json length of the input schema sent

    @property
    def lost_pct(self) -> float:
        return 100.0 * (self.full - self.sent) / self.full if self.full else 0.0


def _tier_tail(name: str) -> str:
    return "\n\n" + T._tier_line(name, T.TOOL_TIERS.get(name, 0))


def advertised_names() -> list[str]:
    return [t["name"] for t in T.advertised_for_turn(T.anthropic_tools())]


def audit_tool(name: str) -> ToolAudit:
    spec = T.REGISTRY[name]
    doc = (inspect.getdoc(spec.fn) or "").strip()
    sent = spec.description
    tail = _tier_tail(name)
    if sent.endswith(tail):
        sent = sent[: -len(tail)]
    # The sent text is a prefix of the docstring (a tested invariant), except
    # that Args/Returns sections are dropped; locate the cut from the prefix.
    cut = doc[len(sent):].strip() if doc.startswith(sent) else doc
    return ToolAudit(name, len(doc), len(sent), cut,
                     len(json.dumps(spec.input_schema, sort_keys=True)))


def audit() -> list[ToolAudit]:
    return [audit_tool(n) for n in advertised_names()]


def advertised_chars() -> int:
    """Characters sent per turn: descriptions plus input schemas."""
    return sum(len(t["description"]) + len(json.dumps(t["input_schema"]))
               for t in T.advertised_for_turn(T.anthropic_tools()))
