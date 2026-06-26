"""Generate the per-step-type argument reference from the wire-shape oracle.

Single source of truth = `docs/STEP_WIRE_SHAPES.json` (the editor-derived
oracle). `render_step_reference()` turns it into a markdown block that is
spliced into `docs/AUTHORING.md` between the GENERATED markers, so the
authoring reference can never drift from the oracle by hand.

`test_step_reference_in_sync.py` fails if the committed block is stale.
Regenerate with: `python -m fsr_playbooks.tests.step_reference_gen --write`.

This is a docs/test-time tool, not runtime compiler code — it lives under
`tests/` so it never gets vendored into the connector.
"""
from __future__ import annotations

import re
from pathlib import Path

from fsr_playbooks.compiler.resolver._constants import SHORT_TYPE_TO_FSR
from fsr_playbooks.tests.wire_shape_oracle import (
    EDITOR_ONLY_KEYS,
    StepShape,
    load_oracle,
)

_AUTHORING = Path(__file__).resolve().parents[2] / "docs" / "AUTHORING.md"
_BEGIN = "<!-- BEGIN GENERATED STEP REFERENCE (fsr_playbooks.tests.step_reference_gen) -->"
_END = "<!-- END GENERATED STEP REFERENCE -->"


def _short_aliases_by_canonical() -> dict[str, list[str]]:
    """canonical FSR name -> [short types], in SHORT_TYPE_TO_FSR order."""
    out: dict[str, list[str]] = {}
    for short, canonical in SHORT_TYPE_TO_FSR.items():
        out.setdefault(canonical, []).append(short)
    return out


def _clean_note(note: str) -> str:
    """Trim editor reverse-engineering noise (line numbers, instance counts)
    from a key's note so the table reads for authors, not bundle archaeologists.
    Keeps the leading meaning, drops the breadcrumbs, caps the length."""
    note = (note or "").strip()
    # Drop trailing reverse-engineering breadcrumbs — keep the first sentence(s).
    note = re.split(r"(?:\s*Set at line|\s*Present in ~?\d|\s*System key|"
                    r"\s*Standard playbook step field|\s*Becomes step variable|"
                    r"\s*\[system key\])", note)[0]
    # Strip inline editor line references: "(line 23754)", "(lines 23744-23750)",
    # " at line 37450", " line 23803".
    note = re.sub(r"\s*\(lines?\s+[\d\-, ]+\)", "", note)
    note = re.sub(r"\s*(?:at\s+)?lines?\s+[\d\-]+", "", note)
    note = re.sub(r"\s{2,}", " ", note)
    note = note.strip().rstrip(".;,").strip()
    note = note.replace("|", "\\|").replace("\n", " ")
    if len(note) > 200:
        note = note[:197].rstrip() + "…"
    return note


def _render_step(shape: StepShape, aliases: list[str]) -> list[str]:
    lines: list[str] = []
    alias_str = ", ".join(f"`{a}`" for a in aliases) if aliases else "_(no alias)_"
    lines.append(f"#### {shape.canonical_name} — {alias_str}")
    lines.append("")
    rows = []
    for key in sorted(shape.all_keys):
        if key in EDITOR_ONLY_KEYS:
            continue
        a = shape.arguments.get(key, {})
        typ = a.get("type", "") or ""
        req = "yes" if key in shape.required_keys else ""
        note = _clean_note(a.get("notes", ""))
        rows.append(f"| `{key}` | {typ} | {req} | {note} |")
    if shape.has_open_keys:
        rows.append("| `<user keys>` | any | | Arbitrary user-chosen keys at the "
                    "arguments root (e.g. variable names). |")
    if rows:
        lines.append("| Argument | Type | Required | Meaning |")
        lines.append("|----------|------|----------|---------|")
        lines.extend(rows)
    else:
        lines.append("_No documented arguments._")
    lines.append("")
    return lines


def render_step_reference() -> str:
    oracle = load_oracle()
    aliases_by_canon = _short_aliases_by_canonical()
    lines = [
        _BEGIN,
        "",
        "<!-- Generated from docs/STEP_WIRE_SHAPES.json — do not edit by hand.",
        "     Regenerate: python -m fsr_playbooks.tests.step_reference_gen --write -->",
        "",
        "### Per-step-type argument reference",
        "",
        "Editor-derived argument shapes for every step type, keyed by canonical "
        "FSR name with the friendly YAML alias(es). Editor-only/UI-state keys are "
        "omitted. Source of truth: `docs/STEP_WIRE_SHAPES.json`.",
        "",
    ]
    # Stable order: follow SHORT_TYPE_TO_FSR's canonical first-appearance order,
    # then any oracle-only canonicals not reachable from a short alias.
    seen: set[str] = set()
    ordered: list[str] = []
    for canonical in SHORT_TYPE_TO_FSR.values():
        if canonical not in seen and canonical in oracle:
            seen.add(canonical)
            ordered.append(canonical)
    for canonical in oracle:
        if canonical not in seen:
            seen.add(canonical)
            ordered.append(canonical)

    for canonical in ordered:
        lines.extend(_render_step(oracle[canonical],
                                  aliases_by_canon.get(canonical, [])))
    lines.append(_END)
    return "\n".join(lines)


def splice_into_authoring(text: str, block: str) -> str:
    """Replace the marked region in `text` with `block`. Appends a new region
    (before a trailing newline) when no markers exist yet."""
    if _BEGIN in text and _END in text:
        pre = text[: text.index(_BEGIN)]
        post = text[text.index(_END) + len(_END):]
        return pre + block + post
    sep = "" if text.endswith("\n") else "\n"
    return text + sep + "\n" + block + "\n"


def write_authoring(path: Path = _AUTHORING) -> None:
    block = render_step_reference()
    new = splice_into_authoring(path.read_text(), block)
    path.write_text(new)


if __name__ == "__main__":
    import sys

    block = render_step_reference()
    if "--write" in sys.argv:
        write_authoring()
        print(f"wrote step reference into {_AUTHORING}")
    else:
        print(block)
