"""Tier 3 first slice — terminal-type inference for Jinja filter chains.

Tier 1 / 2 validate connector param values *only* when the value is a
static literal. The moment the YAML carries `{{ … }}`, both tiers bail
because the resolved value isn't knowable at compile time.

Tier 3 plugs the most common subset of that gap: when the value is a
*pure* Jinja expression (one `{{ … }}` block with no surrounding text)
whose final filter has a declared output type, we can claim the
terminal type statically. `{{ vars.steps.x.count | int }}` is `int`;
`{{ alerts | length }}` is `int`; `{{ ip | string }}` is `str`. That
matches a number of real authoring mistakes (`| int` applied to a
list, target param is `text` but the value coerces to `int`).

The signature table lives in `jinja_macros.output_type_declared` (49
filters as of this commit). FSR's vocabulary maps onto the resolver's
`observed_type` vocabulary via `_FSR_TO_OBSERVED`.

This module is intentionally narrow:
  * **Only** infers the terminal type, not the chain's intermediate
    shapes (Tier 3.1 will need that for non-terminal validation).
  * **Only** runs against pure-Jinja values; mixed-text values like
    `"prefix-{{ x }}-suffix"` defer to runtime as before.
  * Returns `None` (not `"unknown"`) when it can't claim a type, so
    the resolver knows to fall back to the existing widget/observed_type
    static check.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Optional


# Matches a value that is *entirely* one `{{ … }}` block (with optional
# leading/trailing whitespace). Multi-line is fine. We anchor with `\A`/`\Z`
# so a value like `"{{ x }} extra"` does NOT match.
_PURE_JINJA_RE = re.compile(r"\A\s*\{\{\s*(.+?)\s*\}\}\s*\Z", re.DOTALL)

# Filter call inside an expression. Captures the filter name only; we
# don't care about args for terminal-type inference. Anchored on `|`
# so `{{ foo.bar }}` (no filters) doesn't match anything.
_FILTER_NAME_RE = re.compile(r"\|\s*([a-zA-Z_][a-zA-Z0-9_]*)")


# FSR's output_type vocabulary -> the resolver's observed_type vocab.
# `any` and unknown values stay None so callers know to fall through.
_FSR_TO_OBSERVED: dict[str, str] = {
    "string":  "str",
    "integer": "int",
    "number":  "float",   # numeric output; resolver's float check accepts ints
    "list":    "json_array",
    "boolean": "bool",
    "object":  "json_object",
}


def extract_pure_jinja(value: object) -> Optional[str]:
    """Return the inner expression when `value` is a *pure* Jinja block.

    Returns the trimmed expression text, or None when the value isn't
    a string or carries any surrounding non-Jinja content.
    """
    if not isinstance(value, str):
        return None
    m = _PURE_JINJA_RE.match(value)
    return m.group(1) if m else None


def terminal_filter(expr: str) -> Optional[str]:
    """Return the last filter name in the expression, or None when
    the expression has no filter chain (e.g. `{{ vars.x }}`)."""
    matches = _FILTER_NAME_RE.findall(expr or "")
    return matches[-1] if matches else None


def infer_terminal_observed_type(
    value: object,
    conn: sqlite3.Connection,
) -> Optional[str]:
    """Top-level entry point. Returns the resolver's `observed_type`
    vocabulary string when statically knowable, else None.

    Path:
      1. Is the value a pure Jinja block? Else None.
      2. Does it carry any filter? Else None (we'd be claiming the
         shape of a raw `vars.steps.x.y` reference, which is the
         walker's job, not this module's).
      3. Look up the terminal filter's declared output type in
         `jinja_macros`. Map to observed_type via `_FSR_TO_OBSERVED`.
    """
    expr = extract_pure_jinja(value)
    if expr is None:
        return None
    last = terminal_filter(expr)
    if last is None:
        return None
    try:
        row = conn.execute(
            "SELECT output_type_declared FROM jinja_macros WHERE name=?",
            (last,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    decl = row[0]
    return _FSR_TO_OBSERVED.get(decl) if decl else None
