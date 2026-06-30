"""Self-teaching diagnostics (PLAYBOOK_AUTHORING_DX_PLAN 0b).

When a compile error lands on one of the step types authors most often mis-shape
— ``manual_input``, ``workflow_reference`` (incl. its ``retry:`` do-until form) —
attach a minimal **compiling** YAML example to the error's ``suggestion``. The
error channel is the most reliable place an agent will read, so the fix travels
*with* the diagnostic instead of living in a guide the agent never opens.

The examples are deliberately tiny and are exercised by ``test_teaching.py`` so
they cannot drift out of "compiles". Keyed by the friendly step ``type:``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .errors import CompileError
    from .ir import Collection

# Minimal, compiling friendly-YAML for the high-foot-gun step types. Each is a
# single `- type: ...` block (the shape the author is getting wrong).
_TEACHING: dict[str, str] = {
    "manual_input": (
        "manual_input collects fields via `inputs:` and resumes on an `options:`\n"
        "button; the values land at vars.steps.<step>.input.<name>:\n"
        "    - name: AskNumber\n"
        "      type: manual_input\n"
        "      title: Enter a six digit number\n"
        "      inputs:\n"
        "      - {name: my_number, kind: integer, label: My Number, required: true}\n"
        "      options:\n"
        "      - {option: Submit, primary: true}\n"
        "      next: Validate"
    ),
    "workflow_reference": (
        "workflow_reference calls another playbook by `target:` (a name or UUID).\n"
        "Add `retry:` for a do-until loop; read the child's output as\n"
        "vars.steps.<step>.<var the child set>:\n"
        "    - name: CallChild\n"
        "      type: workflow_reference\n"
        "      apply_async: false            # synchronous: wait for the child\n"
        "      arguments:\n"
        "        target: Validate Six Digit Number\n"
        "      retry:                        # optional do-until\n"
        "        until: '{{ vars.steps.CallChild.is_valid_number == true }}'\n"
        "        times: 8\n"
        "        delay: 1\n"
        "      next: StampResult"
    ),
}


def _step_type_at(coll: "Collection", path: str) -> Optional[str]:
    """Resolve a ``playbooks[i].steps[j]...`` error path to that step's type."""
    import re

    m = re.match(r"playbooks\[(\d+)\]\.steps\[(\d+)\]", path or "")
    if not m:
        return None
    pi, si = int(m.group(1)), int(m.group(2))
    try:
        return coll.playbooks[pi].steps[si].type
    except (IndexError, AttributeError):
        return None


def enrich_diagnostics(coll: "Collection", errors: "list[CompileError]") -> None:
    """Append a teaching example to errors on high-foot-gun step types, in place.

    Only touches an error whose path resolves to a ``manual_input`` /
    ``workflow_reference`` step and whose ``suggestion`` doesn't already carry an
    example. Never raises.
    """
    for err in errors:
        try:
            stype = _step_type_at(coll, getattr(err, "path", "") or "")
            example = _TEACHING.get(stype or "")
            if not example:
                continue
            block = f"example ({stype}):\n{example}"
            if err.suggestion and "example (" in err.suggestion:
                continue
            err.suggestion = (
                f"{err.suggestion}\n\n{block}" if err.suggestion else block
            )
        except Exception:  # noqa: BLE001 - teaching must never break a compile
            continue
