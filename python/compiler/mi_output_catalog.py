"""ManualInput mode → output-keys catalog.

Source of truth for the C8 render-path check
(`render_analyzer._c8_mi_mode_mismatch`). Modeled after the corpus
mining documented in `docs/research/MI_OUTPUT_CATALOG.md` (2026-05-25).
"""
from __future__ import annotations

from typing import Any


# Resume-body metadata FSR injects on every MI output frame regardless
# of mode. Safe to read; not part of the declared form.
MI_SYSTEM_KEYS: frozenset[str] = frozenset({
    "userid",
    "username",
    "datetime",
})


# Per-mode shape descriptor.
#   form_key: top-level key under which declared inputVariables appear.
#             None means the mode has no input form.
#   allow_input_star: True iff `vars.steps.<MI>.input.<X>` is a legal
#                     pattern (subject to X ∈ declared inputVariables).
MI_OUTPUT_KEYS: dict[str, dict[str, Any]] = {
    "InputBased": {
        "form_key": "input",
        "allow_input_star": True,
    },
    "DecisionBased": {
        "form_key": None,
        "allow_input_star": False,
    },
}


# Aliases for legacy / typo'd `arguments.type` values seen in the corpus.
MI_MODE_ALIASES: dict[str, str] = {
    "":         "InputBased",
    "textarea": "InputBased",  # corpus typo
}


# Legacy step-type strings that should be treated as InputBased
# (is_approval overlay).
APPROVAL_MI_STEP_TYPES: frozenset[str] = frozenset({
    "ApprovalManualInput",
})


def normalize_mode(arg_type: str | None, step_type: str | None = None) -> str:
    """Resolve `arguments.type` (and step type for legacy MI variants)
    to a canonical mode string. Returns 'InputBased' or 'DecisionBased'.
    """
    if step_type in APPROVAL_MI_STEP_TYPES:
        return "InputBased"
    raw = (arg_type or "").strip()
    if raw in MI_OUTPUT_KEYS:
        return raw
    aliased = MI_MODE_ALIASES.get(raw)
    if aliased:
        return aliased
    # Unknown values fall back to InputBased (default UI mode).
    return "InputBased"


def declared_input_names(step_args: dict[str, Any] | None) -> list[str]:
    """Pull the declared `inputVariables[].name` list out of a manual_input
    step's `arguments` dict. Handles both the canonical wire shape
    (`arguments.input.schema.inputVariables`) and the friendlier
    `arguments.inputVariables` shorthand sometimes seen in YAML.
    """
    if not isinstance(step_args, dict):
        return []
    iv = (((step_args.get("input") or {}).get("schema") or {})
          .get("inputVariables")) or step_args.get("inputVariables") or []
    out: list[str] = []
    for v in iv:
        if isinstance(v, dict):
            name = v.get("name")
            if name:
                out.append(str(name))
    return out
