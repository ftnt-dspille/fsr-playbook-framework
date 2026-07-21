"""Compile-time normalization of connector-output Jinja references.

A connector step's result is an ENVELOPE — `{data: <op output>, status,
message, operation}` — so an op output field is reached at
`vars.steps.<step>.data.<field>`, NOT `vars.steps.<step>.<field>`. The build
model frequently drops the `.data` (writing `vars.steps.Convert.minutes`) or
substitutes an alias (`.result`, `.outputs.result`) — all of which render EMPTY
at runtime. The S3 build-persona eval caught this on a live box: the connector
op ran fine, but the record field it fed was blank.

Because the envelope is a fixed, known shape, the fix is deterministic: rewrite
the reference to the `.data.<field>` path whenever the target field is
unambiguous. This is warn-and-fix (never blocks), mirroring the parser's
step-key hoists and the decision-`next:` auto-synthesis — mechanical translation
over prompt rules, which the box's gpt-4.1-class model follows far more reliably
than a grounding sentence (a prose fix moved the eval only 0→1/3).

Shape source, most-accurate first (per the "static schema is often incomplete;
execution history is more accurate" reality):

  1. the grounded-shape store — the op's output as MEASURED from a real run
     (`grounded_shapes.json`, populated by the safe live-probe / ground CLI);
  2. the static `output_schema` in the operations table — a last resort.

Only the `.data` *subkeys* are needed (to know the field names under the
envelope); the envelope wrapper itself is universal and assumed.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .errors import CompileError, ErrorCode
from .ir import Collection

# The connector envelope's own top-level keys — a reference whose first segment
# is one of these is already correct and left untouched. Note `result` is NOT
# here: FSR does not expose `.result` on a connector step, so `.result` is one of
# the broken forms this pass repairs (the S3 run-3 failure).
_ENVELOPE_KEYS = {"data", "status", "message", "operation"}
# Truly universal per-step keys FSR adds regardless of handler — never rewrite.
_UNIVERSAL_KEYS = {"id", "name", "uuid", "@id", "@type", "step_id"}
# Aliases the model reaches for when it means "the op's output" — safe to
# collapse to `.data.<field>` only when the op has exactly one output field.
_RESULT_ALIASES = {"result", "output", "outputs", "response", "results"}


def _jinja_key(name: str, step_id: str) -> str:
    """FSR builds `vars.steps.<key>` from the display name, spaces → underscores
    (falling back to id). Mirrors typed_walker._jinja_key."""
    base = (name or step_id or "").strip()
    return base.replace(" ", "_")


def _store_data_subkeys(db_path: Path, connector: str, op: str) -> Optional[set[str]]:
    """`.data` subkeys as MEASURED from a real run, via the grounded store
    co-located with the reference DB. None if unknown."""
    try:
        from .grounded_shapes import GroundedShapeStore
        store = GroundedShapeStore.load(Path(db_path).parent / "grounded_shapes.json")
        shape = store.shape_for(connector, op)
    except Exception:  # noqa: BLE001 — never let grounding break a compile
        return None
    if not isinstance(shape, dict):
        return None
    data = (shape.get("keys") or {}).get("data")
    if isinstance(data, dict) and data.get("kind") == "object":
        keys = data.get("keys")
        if isinstance(keys, dict) and keys:
            return set(keys.keys())
    return None


def _schema_data_subkeys(conn: sqlite3.Connection, connector: str, op: str) -> Optional[set[str]]:
    """`.data` subkeys from the static `output_schema` — a last resort (these
    schemas are frequently incomplete or absent)."""
    try:
        row = conn.execute(
            "SELECT output_schema_observed, output_schema_json "
            "FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    for blob in row:  # observed wins
        if not blob:
            continue
        try:
            shape = json.loads(blob)
        except Exception:  # noqa: BLE001
            continue
        # An op's output_schema describes what sits UNDER `data`. Some are
        # already enveloped (a `data` key); unwrap when so.
        if isinstance(shape, dict) and shape:
            inner = shape.get("data") if isinstance(shape.get("data"), dict) else shape
            if isinstance(inner, dict) and inner:
                return set(inner.keys())
    return None


def _data_subkeys(db_path: Path, conn: Optional[sqlite3.Connection],
                  connector: str, op: str) -> Optional[set[str]]:
    """Best available `.data` subkeys: measured run first, static schema next."""
    keys = _store_data_subkeys(db_path, connector, op)
    if keys:
        return keys
    if conn is not None:
        return _schema_data_subkeys(conn, connector, op)
    return None


def _connector_steps(coll: Collection) -> dict[str, dict[str, tuple[str, str]]]:
    """Per playbook: jinja-key → (connector, op) for every connector step."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for pb in coll.playbooks:
        m: dict[str, tuple[str, str]] = {}
        for s in pb.steps:
            if (s.type or "").lower() != "connector":
                continue
            args = s.arguments if isinstance(s.arguments, dict) else {}
            conn = args.get("connector")
            op = args.get("operation")
            if isinstance(conn, str) and isinstance(op, str) and conn and op:
                m[_jinja_key(s.name, s.id)] = (conn, op)
        if m:
            out[pb.name] = m
    return out


def rewrite_connector_output_refs(
    coll: Collection, db_path: Path,
    conn: Optional[sqlite3.Connection] = None,
) -> list[CompileError]:
    """Rewrite `vars.steps.<connstep>.<x>` → `.data.<field>` in place; return
    warn-and-fix diagnostics. Only rewrites when the target field is
    unambiguous; anything else is left for the reference lint to warn on.
    """
    fixes: list[CompileError] = []
    by_pb = _connector_steps(coll)
    if not by_pb:
        return fixes

    _own_conn = None
    if conn is None:
        try:
            _own_conn = sqlite3.connect(str(db_path))
            conn = _own_conn
        except Exception:  # noqa: BLE001
            conn = None
    try:
        for pb in coll.playbooks:
            steps_map = by_pb.get(pb.name)
            if not steps_map:
                continue
            # subkeys cache per (connector, op) for this playbook
            cache: dict[tuple[str, str], Optional[set[str]]] = {}
            for s in pb.steps:
                if not isinstance(s.arguments, dict):
                    continue
                _rewrite_in_node(s.arguments, s, steps_map, cache, db_path, conn, fixes)
    finally:
        if _own_conn is not None:
            _own_conn.close()
    return fixes


def _rewrite_in_node(node: Any, step, steps_map, cache, db_path, conn, fixes) -> Any:
    """Walk a step's arguments, rewriting Jinja leaf strings in place."""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            node[k] = _rewrite_in_node(v, step, steps_map, cache, db_path, conn, fixes)
        return node
    if isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = _rewrite_in_node(v, step, steps_map, cache, db_path, conn, fixes)
        return node
    # `steps.` not `vars.steps.`: the bare form (a missing `vars.` prefix) is
    # itself one of the broken references this pass repairs, so gating on the
    # correct prefix would skip exactly the strings that need fixing.
    if isinstance(node, str) and "steps." in node:
        return _rewrite_string(node, step, steps_map, cache, db_path, conn, fixes)
    return node


def _subkeys(cache, db_path, conn, connector, op) -> Optional[set[str]]:
    key = (connector, op)
    if key not in cache:
        cache[key] = _data_subkeys(db_path, conn, connector, op)
    return cache[key]


def _rewrite_string(text, step, steps_map, cache, db_path, conn, fixes) -> str:
    for sname, (connector, op) in steps_map.items():
        s_re = re.escape(sname)

        # PREFIX form first: `steps.<step>...` with the `vars.` dropped. FSR
        # exposes step output only under `vars`, so a bare `steps.` renders
        # EMPTY — the same silent-blank failure as a missing `.data`, and an
        # observed S3 authoring error.
        #
        # It must be normalized BEFORE the alias/bare-field passes below, both
        # because those anchor on `vars.steps.` and because the repaired
        # reference may ALSO need a `.data` fix (`steps.X.result` needs both).
        #
        # This is also why the reference lint never flagged it: every check in
        # validator.py anchors on `\bvars\.steps\.`, so omitting `vars.` makes
        # the mistake invisible to the machinery built to catch it — the one
        # error that consists of not matching the anchor.
        def _prefix_sub(mobj):
            fixes.append(CompileError(
                code=ErrorCode.BAD_VALUE, severity="warning",
                message=(f"rewrote `steps.{sname}` → `vars.steps.{sname}`: "
                         f"step output is exposed under `vars`, so a bare "
                         f"`steps.` reference renders empty at runtime"),
                path=f"{step.id}",
            ))
            return f"vars.steps.{sname}"

        # The lookbehind keeps this off `vars.steps.` (already correct) and off
        # any `<word>steps.` / `<x>.steps.` that is not the bare form.
        text = re.sub(rf"(?<![\w.])steps\.{s_re}(?![A-Za-z0-9_])",
                      _prefix_sub, text)

        # Alias forms first: `.result`, `.outputs.result`, etc. → `.data.<sole>`
        # only when the op has exactly one output field (unambiguous).
        def _alias_sub(mobj):
            subkeys = _subkeys(cache, db_path, conn, connector, op)
            if subkeys and len(subkeys) == 1:
                field = next(iter(subkeys))
                fixes.append(CompileError(
                    code=ErrorCode.BAD_VALUE, severity="warning",
                    message=(f"rewrote `vars.steps.{sname}.{mobj.group(1)}` → "
                             f"`vars.steps.{sname}.data.{field}`: a connector "
                             f"result is an envelope, the op's output is under "
                             f"`.data` (single output field {field!r})"),
                    path=f"{step.id}",
                ))
                return f"vars.steps.{sname}.data.{field}"
            return mobj.group(0)  # ambiguous — leave for the reference lint

        text = re.sub(
            rf"vars\.steps\.{s_re}\.({'|'.join(_RESULT_ALIASES)})\b(?:\.[A-Za-z_][A-Za-z0-9_]*)*",
            _alias_sub, text)

        # Bare-field form: `.<field>` where <field> is a real `.data` subkey.
        def _field_sub(mobj):
            first = mobj.group(1)
            if first in _ENVELOPE_KEYS or first in _UNIVERSAL_KEYS:
                return mobj.group(0)  # already correct
            subkeys = _subkeys(cache, db_path, conn, connector, op)
            if subkeys and first in subkeys:
                fixes.append(CompileError(
                    code=ErrorCode.BAD_VALUE, severity="warning",
                    message=(f"rewrote `vars.steps.{sname}.{first}` → "
                             f"`vars.steps.{sname}.data.{first}`: a connector "
                             f"result is an envelope, op output fields are "
                             f"under `.data`"),
                    path=f"{step.id}",
                ))
                return f"vars.steps.{sname}.data.{first}"
            return mobj.group(0)  # not a known field — don't guess

        text = re.sub(rf"vars\.steps\.{s_re}\.([A-Za-z_][A-Za-z0-9_]*)",
                      _field_sub, text)
    return text
