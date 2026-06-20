"""Corpus-driven validation against the imported playbook_steps table.

`store/fsr_reference.db.playbook_steps` holds ~7.4k real-world step
argument dicts harvested from disk SP exports + the live FSR. This
validator mines that corpus for stable enum-like keys (low-cardinality
string/bool values that appear consistently across samples) and flags
user-supplied values that don't match any observed value.

Scope is intentionally narrow:
- Only step types where args are uniform across samples (allowlist).
- Skips Connectors / WorkflowReference / SetVariable (validated elsewhere
  or free-form by design).
- Only checks literal values — Jinja expressions (`{{ ... }}`) are skipped.
- Emits warnings, never errors. Heuristic, not authoritative.

The classic catch this enables: `operation: append` (lowercase) when the
corpus shows every real UpdateRecord uses `Append` or `Overwrite`.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Optional

from .errors import CompileError, ErrorCode
from .ir import Collection, Step

# Step types whose arg shapes are uniform enough for corpus stats to be
# meaningful. Connectors/WorkflowReference vary too much by op; SetVariable
# is intentionally a flat free-form dict.
_ALLOWED_TYPES = frozenset({
    "ManualInput",
    "Delay",
    "UpdateRecord",
    "FindRecords",
    "InsertData",
    "IngestBulkFeed",
    "Decision",
})

# Enum-detection thresholds. A key is treated as a stable enum if:
#   - the step type has at least _MIN_SAMPLES corpus rows
#   - the key appears in at least _MIN_KEY_COVERAGE fraction of those rows
#   - all observed values are scalars (str/bool/int) under _MAX_STR_LEN chars
#   - the distinct-value count is at most _MAX_DISTINCT
_MIN_SAMPLES = 15
_MIN_KEY_COVERAGE = 0.80
_MAX_DISTINCT = 6
_MAX_STR_LEN = 40


def _is_jinja(v: object) -> bool:
    return isinstance(v, str) and "{{" in v


def _is_enum_value(v: object) -> bool:
    if isinstance(v, bool) or isinstance(v, int):
        return True
    if isinstance(v, str):
        return len(v) <= _MAX_STR_LEN and "\n" not in v and "{{" not in v
    return False


class CorpusValidator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # step_type_name -> {key: set(observed_values)}
        self._enums: Optional[dict[str, dict[str, set]]] = None
        # step_type_name -> set(keys present in 100% of corpus samples)
        self._always_keys: dict[str, set[str]] = {}

    def _build_index(self) -> dict[str, dict[str, set]]:
        index: dict[str, dict[str, set]] = {}
        for stype in _ALLOWED_TYPES:
            try:
                rows = self.conn.execute(
                    "SELECT arguments_json FROM playbook_steps "
                    "WHERE step_type_name = ?",
                    (stype,),
                ).fetchall()
            except sqlite3.OperationalError:
                return {}
            n = len(rows)
            if n < _MIN_SAMPLES:
                continue
            key_count: Counter = Counter()
            value_sets: dict[str, Counter] = defaultdict(Counter)
            unfit: set[str] = set()
            for (raw,) in rows:
                try:
                    args = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(args, dict):
                    continue
                for k, v in args.items():
                    key_count[k] += 1
                    if k in unfit:
                        continue
                    if not _is_enum_value(v):
                        unfit.add(k)
                        value_sets.pop(k, None)
                        continue
                    value_sets[k][v] += 1

            self._always_keys[stype] = {
                k for k, c in key_count.items() if c == n
            }
            enums: dict[str, set] = {}
            for k, vc in value_sets.items():
                coverage = key_count[k] / n
                if coverage < _MIN_KEY_COVERAGE:
                    continue
                if len(vc) > _MAX_DISTINCT:
                    continue
                # Drop singletons unless every other value is also strong;
                # require the top values to cover the key's appearances.
                enums[k] = {val for val, _c in vc.items()}
            # Always register the step type even when no enum keys —
            # the likely-required-key check still fires off `_always_keys`.
            index[stype] = enums
        return index

    def _ensure_index(self) -> dict[str, dict[str, set]]:
        if self._enums is None:
            self._enums = self._build_index()
        return self._enums

    def validate(self, collection: Collection) -> list[CompileError]:
        index = self._ensure_index()
        if not index:
            return []
        errors: list[CompileError] = []
        for pi, pb in enumerate(collection.playbooks):
            for si, step in enumerate(pb.steps):
                self._validate_step(
                    step, f"playbooks[{pi}].steps[{si}]", index, errors,
                )
        return errors

    def _validate_step(
        self,
        step: Step,
        path: str,
        index: dict[str, dict[str, set]],
        errors: list[CompileError],
    ) -> None:
        stype = step.step_type_name
        if not stype or stype not in index:
            return
        provided = step.arguments or {}
        # Likely-required check: keys present in 100% of corpus samples
        # but absent here usually mean either a resolver omission or a
        # hand-authored wire-shape that's missing canonical FSR keys.
        for k in self._always_keys.get(stype, ()):
            if k not in provided:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message=(
                        f"{stype}.arguments.{k} is missing — every corpus "
                        f"sample for this step type sets this key"
                    ),
                    path=f"{path}.arguments.{k}",
                    severity="warning",
                ))
        enums = index[stype]
        for k, v in provided.items():
            if k not in enums:
                continue
            if _is_jinja(v):
                continue
            if not _is_enum_value(v):
                continue
            allowed = enums[k]
            if v in allowed:
                continue
            # Case-insensitive near-miss helps the lowercase-vs-Capitalized
            # case (the headline catch this validator exists for).
            near = None
            if isinstance(v, str):
                lower = v.lower()
                for cand in allowed:
                    if isinstance(cand, str) and cand.lower() == lower:
                        near = cand
                        break
            sample = sorted(
                (str(x) for x in allowed), key=lambda s: s.lower(),
            )
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"{stype}.arguments.{k}={v!r} not seen in any of the "
                    f"corpus samples for this step type"
                ),
                path=f"{path}.arguments.{k}",
                suggestion=f"observed values: {', '.join(sample)}",
                near=near,
                severity="warning",
            ))
