"""Control-character hygiene for model-supplied YAML.

Deliberately dependency-free and low in the stack: BOTH the compiler
(`compiler/parser.py`) and the MCP tool layer (`mcp_server/_shared.py`) parse
YAML the model produced, and the compiler must not import from `mcp_server`.
Putting the primitive here is what lets the *write* path -- `compile_yaml`,
`validate_yaml`, `push_playbook` -- share the guard the read path got first.
"""
from __future__ import annotations

from typing import Any

# C0 control characters YAML forbids outright in a document. Tab/LF/CR are
# legal and MUST be preserved; everything else in C0 plus DEL makes the whole
# document unparseable.
_ILLEGAL_YAML_CTRL = "".join(
    chr(c) for c in list(range(0x00, 0x09)) + [0x0B, 0x0C]
    + list(range(0x0E, 0x20)) + [0x7F]
)
_YAML_CTRL_TABLE = {ord(c): None for c in _ILLEGAL_YAML_CTRL}


def sanitize_yaml_text(yaml_text: Any) -> tuple[str, int]:
    """Strip control characters that make model-supplied YAML unparseable.

    Returns ``(clean_text, removed_count)``.

    Why this exists: every `yaml_text` argument is the model RE-EMITTING a
    playbook it was already given, and a long verbatim copy comes back
    corrupted. Live on a .159 box, `analyze_playbook` on the real 6-step
    "Hunt Indicators" playbook died with

        yaml parse failed: unacceptable character #x0000: special characters
        are not allowed in "<unicode string>", position 15305

    because the model wrote the playbook's ``(R)`` sign as a malformed escape
    (``\\u0000AE`` rather than ``\\u00AE``), which JSON-decodes to NUL + "AE".
    The appliance record was clean and so was the YAML the widget sent; only
    the model's copy was damaged. One bad byte 15 kB into a 20 kB blob killed
    the whole turn.

    A control character can never be *meant* in authored YAML, so dropping it
    is always the right repair -- but callers report the count rather than
    swallowing it, so a recurring corruption stays visible.
    """
    if not isinstance(yaml_text, str):
        return "", 0
    if not any(c in yaml_text for c in _ILLEGAL_YAML_CTRL):
        return yaml_text, 0          # fast path: the overwhelming majority
    clean = yaml_text.translate(_YAML_CTRL_TABLE)
    return clean, len(yaml_text) - len(clean)
