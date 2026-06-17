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


# Hand-curated filter signatures — covers the long tail of macros whose
# `jinja_macros.output_type_declared` is NULL on the live store but
# whose behaviour is obvious from the upstream definition. Each entry
# is (input_type, output_type) in the FSR vocab; either side may be
# None to mean "any" / "unknown / don't claim".
#
# Adding entries: when in doubt, prefer None on whichever side is
# polymorphic (e.g. `default`, `mandatory` — pass-through filters).
# False positives waste agent loop budget; false negatives just fall
# through to the existing widget/observed_type check.
_HAND_CURATED: dict[str, tuple[str | None, str | None]] = {
    # ── Standard Jinja string filters — input is `string`, output too.
    # The live DB has these with output_type_declared='string' but no
    # input_type_hint; we add the input so chain validation can flag
    # `| int | upper` and friends as the type error they really are.
    "upper":      ("string", "string"),
    "lower":      ("string", "string"),
    "title":      ("string", "string"),
    "capitalize": ("string", "string"),
    "trim":       ("string", "string"),
    "replace":    ("string", "string"),
    "truncate":   ("string", "string"),
    "wordwrap":   ("string", "string"),
    "wordcount":  ("string", "integer"),
    "striptags":  ("string", "string"),
    "escape":     ("string", "string"),
    "center":     ("string", "string"),
    "indent":     ("string", "string"),
    "urlize":     ("string", "string"),
    "format":     ("string", "string"),
    "split":      ("string", "list"),
    "tojson":     (None,     "string"),
    "string":     (None,     "string"),

    # Container filters: input is a list, output varies.
    "first":      ("list", None),
    "last":       ("list", None),
    "length":     (None,   "integer"),   # input is any sequence/string/dict
    "min":        ("list", None),
    "max":        ("list", None),
    "sum":        ("list", "number"),
    "list":       (None,   "list"),
    "sort":       ("list", "list"),
    "reverse":    (None,   None),
    "unique":     ("list", "list"),
    "groupby":    ("list", "list"),
    "select":     ("list", "list"),
    "reject":     ("list", "list"),
    "selectattr": ("list", "list"),
    "rejectattr": ("list", "list"),
    "map":        ("list", "list"),
    "batch":      ("list", "list"),
    "slice":      ("list", "list"),
    "dictsort":   ("object", "list"),
    "items":      ("object", "list"),
    "attr":       ("object", None),

    # Numeric:
    "int":        (None,   "integer"),
    "float":      (None,   "number"),
    "abs":        ("number", "number"),
    "round":      ("number", "number"),

    "join":       ("list",   "string"),
    "pprint":     (None,     "string"),


    # ── Encoding / formatting (always produce strings) ─────────────────
    "b64decode":      (None, "string"),
    "b64encode":      (None, "string"),
    "basename":       (None, "string"),
    "checksum":       (None, "string"),
    "comment":        (None, "string"),
    "dirname":        (None, "string"),
    "e":              (None, "string"),       # markupsafe.escape
    "expanduser":     (None, "string"),
    "expandvars":     (None, "string"),
    "filesizeformat": ("number", "string"),
    "forceescape":    (None, "string"),
    "hash":           (None, "string"),
    "hash_salt":      ("string", "string"),
    "html2text":      ("string", "string"),
    "htmltotext":     ("string", "string"),
    "html2texthash":  ("string", "string"),
    "json2html":      ("object", "string"),
    "markdown2html":  ("string", "string"),
    "logParse":       ("string", "object"),
    "urlencode":      (None, "string"),
    "urlsplit":       ("string", "object"),

    # ── Network / IP filters (Ansible netcommon — return strings or
    # lists of strings depending on call shape; we claim string for
    # the scalar form since that's the common usage in connector args)
    "ipaddr":         (None, "string"),
    "ipv4":           (None, "string"),
    "ipv6":           (None, "string"),
    "ipwrap":         (None, "string"),
    "ipmath":         (None, "string"),
    "ipsubnet":       (None, "string"),
    "ip4_hex":        (None, "string"),
    "hwaddr":         (None, "string"),
    "macaddr":        (None, "string"),
    "cidr_merge":     ("list", "list"),
    "ip_range":       ("string", "list"),

    # ── Collections / sequence transforms ──────────────────────────────
    "combinations":   ("list", "list"),
    "combine":        (None, "object"),       # variadic dict merge
    "dict2items":     ("object", "list"),
    "items2dict":     ("list", "object"),
    "flatten":        ("list", "list"),
    "from_yaml_all":  ("string", "list"),
    "from_yaml":      ("string", None),       # could be any YAML doc shape
    "from_json":      ("string", None),       # likewise
    "intersect":      ("list", "list"),
    "difference":     ("list", "list"),
    "symmetric_difference": ("list", "list"),
    "union":          ("list", "list"),
    "extract":        (None, None),           # polymorphic lookup
    "fileglob":       ("string", "list"),
    "json_query":     (None, None),           # JMESPath: output type depends on expr
    "to_yaml":        (None, "string"),
    "to_nice_yaml":   (None, "string"),
    "to_nice_json":   (None, "string"),
    "to_datetime":    ("string", "string"),   # FSR keeps these as ISO strings

    # ── Numeric / boolean ──────────────────────────────────────────────
    "bool":           (None, "boolean"),
    "count":          (None, "integer"),      # alias of length
    "log":            ("number", "number"),
    "logarithm":      ("number", "number"),
    "pow":            ("number", "number"),
    "human_readable": ("number", "string"),
    "human_to_bytes": ("string", "integer"),

    # ── Pass-through / polymorphic — keep both None ────────────────────
    "d":              (None, None),
    "default":        (None, None),
    "mandatory":      (None, None),
    "ternary":        (None, None),
    "safe":           (None, "string"),

    # ── FSR-specific (workflow.jinja) ──────────────────────────────────
    "fromIRI":            ("string", "object"),
    "iriToLink":          ("string", "string"),
    "loadRelationships":  ("string", "object"),
    "find_indicators":    (None, "list"),
    "extract_artifacts":  ("string", "list"),
    "extract_cef":        ("string", "object"),
    "count_occurrence":   (None, "object"),
    "counter":            (None, "object"),
    "getRelativeDate":    (None, "string"),   # returns ISO timestamp
    "resolveRange":       ("string", "object"),
    "picklist":           ("string", "string"),
}


def filter_signature(
    name: str, conn: Optional[sqlite3.Connection],
) -> tuple[Optional[str], Optional[str]]:
    """Look up `(input_type, output_type)` for a filter, FSR vocab.

    Resolution order: hand-curated map (highest authority, ships in
    code), then `jinja_macros` row (DB-derived). Returns (None, None)
    when nothing matches; callers should treat both Nones as `any`.
    """
    hand = _HAND_CURATED.get(name)
    if hand is not None:
        return hand
    if conn is None:
        return (None, None)
    try:
        row = conn.execute(
            "SELECT input_type_hint, output_type_declared "
            "FROM jinja_macros WHERE name=?", (name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return (None, None)
    if not row:
        return (None, None)
    return (row[0], row[1])


def chain_filters(expr: str) -> list[str]:
    """Return every filter name in the expression's chain, in order.

    Empty list when the expression has no `|`. Used by chain
    validation to walk each transition.
    """
    return _FILTER_NAME_RE.findall(expr or "")


def _types_satisfy(producer_out: Optional[str], consumer_in: Optional[str]) -> bool:
    """True iff a filter producing `producer_out` can feed one expecting
    `consumer_in`. Both in FSR vocab. None on either side means
    "unknown" and we accept (silence-is-acceptance).

    Stricter than the resolver-boundary check: filter-internal chaining
    rarely coerces silently (`int().upper()` raises), so we only allow
    numeric promotion and `any`/None.
    """
    if producer_out is None or consumer_in is None:
        return True
    if producer_out == consumer_in:
        return True
    # Numeric promotion in either direction.
    if {producer_out, consumer_in} <= {"integer", "number"}:
        return True
    return False


def validate_chain(
    expr: str, conn: Optional[sqlite3.Connection],
) -> Optional[tuple[str, str, str]]:
    """Walk filter transitions; return the first (producer, consumer,
    consumer_input_type) that produces an incompatibility, or None
    when the chain checks out.

    Producer's *output* type drives the comparison; consumer's *input*
    type is what we check against. Unknown sides accept.
    """
    fs = chain_filters(expr)
    if len(fs) < 2:
        return None
    prev_out: Optional[str] = None
    for i, fname in enumerate(fs):
        in_t, out_t = filter_signature(fname, conn)
        if i > 0 and not _types_satisfy(prev_out, in_t):
            return (fs[i - 1], fname, in_t or "")
        prev_out = out_t
    return None


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
    _, out_t = filter_signature(last, conn)
    return _FSR_TO_OBSERVED.get(out_t) if out_t else None
