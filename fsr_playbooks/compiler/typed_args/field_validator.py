"""Field and value validation for trigger conditions against the catalog.

Validates trigger filter fields against module schema and values against
field type/picklist constraints. Designed to be called from resolver/validator
when the database connection is available, keeping trigger.py database-free.

The validation runs AFTER structural validation (expand_when) completes with
valid WhenGroup/WhenLeaf objects, and pairs with module-name validation to
resolve which module's fields to check against.
"""
from __future__ import annotations

import difflib
import sqlite3
from typing import Any

from ..errors import CompileError, ErrorCode


class FieldValueValidator:
    """Query the reference DB for field and picklist validation.

    Initialized with a sqlite3 connection; methods validate trigger leaf
    filters (field existence, value type/picklist membership).

    Operators where the ``value`` is semantically meaningless
    (``isnull`` / ``isnotnull`` / ``changed``) skip value validation -- FSR's
    own designer emits a placeholder (e.g. ``"true"``) there, and flagging it
    as a type mismatch is a false positive.
    """

    _VALUE_IRRELEVANT_OPS: frozenset[str] = frozenset({
        "isnull", "isnotnull", "changed",
    })

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def validate_trigger_filters(
        self,
        filters: list[dict],
        module_name: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Walk the expanded `fieldbasedtrigger` filter tree and validate fields.

        Recursively handles nested groups. Each leaf filter's field is validated
        against the module's `module_fields` table, and picklist-backed fields
        have their values checked against the corresponding picklist.

        `filters` is the list from `fieldbasedtrigger["filters"]` (already
        normalized by expand_when).
        """
        for i, filt in enumerate(filters):
            fpath = f"{path}.filters[{i}]"
            self._validate_filter(filt, module_name, fpath, errors)

    def _validate_filter(
        self,
        filt: dict,
        module_name: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Validate a single filter (leaf or group)."""
        if not isinstance(filt, dict):
            return

        # Nested group (has logic/filters)
        if "logic" in filt and "filters" in filt:
            self.validate_trigger_filters(
                filt["filters"], module_name, path, errors
            )
            return

        # Leaf filter -- validate field + value
        field = filt.get("field")
        if not isinstance(field, str) or not field:
            # Missing field already caught by structural validation
            return

        self._validate_field(field, filt, module_name, path, errors)

    def _validate_field(
        self,
        field: str,
        filt: dict,
        module_name: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Validate a field name and (if found) its value."""
        if filt.get("template") == "tags":
            return

        row = self.conn.execute(
            "SELECT field_name, type, picklist_name FROM module_fields "
            "WHERE module_name=? AND field_name=?",
            (module_name, field),
        ).fetchone()

        if not row:
            known = [r[0] for r in self.conn.execute(
                "SELECT field_name FROM module_fields WHERE module_name=?",
                (module_name,),
            ).fetchall()]
            if not known:
                return

            sug = difflib.get_close_matches(field, known, n=1, cutoff=0.6)
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"field {field!r} does not exist on module {module_name!r} "
                    f"(valid: {', '.join(sorted(known)[:8])}"
                    f"{'…' if len(known) > 8 else ''})"
                ),
                path=f"{path}.field",
                near=sug[0] if sug else None,
                suggestion=(f"did you mean {sug[0]!r}?" if sug else None),
                severity="warning",
            ))
            return

        operator = filt.get("operator")
        if operator in self._VALUE_IRRELEVANT_OPS:
            return

        field_type = row["type"]
        picklist_name = row["picklist_name"]

        value = filt.get("value")

        if isinstance(value, str) and "%" in value:
            return

        if picklist_name:
            self._validate_picklist_value(
                value, picklist_name, field, path, errors
            )
        else:
            self._validate_field_value(value, field_type, field, path, errors)

    def _validate_picklist_value(
        self,
        value: Any,
        picklist_name: str,
        field: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Validate that a value (or list of values) exists in the picklist.

        Object-typed picklist filters carry the canonical
        ``/api/3/picklists/<uuid>`` IRI as ``value`` (not the display label),
        so a value is accepted when it matches either an ``item_value`` (the
        friendly label) or an ``item_iri`` (the canonical IRI) in the warmed
        ``picklists`` table. The suggestion list shows labels, since those are
        what an author writes.
        """
        if value is None or value == "":
            return
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            return
        if isinstance(value, list) and not value:
            return

        values_to_check = value if isinstance(value, list) else [value]
        values_to_check = [
            v for v in values_to_check
            if isinstance(v, str) and not ("{{" in v or "{%" in v)
        ]

        if not values_to_check:
            return

        rows = self.conn.execute(
            "SELECT item_value, item_iri FROM picklists WHERE list_name=?",
            (picklist_name,),
        ).fetchall()
        valid_values = {r[0] for r in rows if r[0]}
        valid_iris = {r[1] for r in rows if r[1]}

        if not valid_values and not valid_iris:
            return

        for v in values_to_check:
            if v in valid_values or v in valid_iris:
                continue
            sug = difflib.get_close_matches(
                v, list(valid_values) or list(valid_iris), n=1, cutoff=0.6,
            )
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"value {v!r} is not in picklist {picklist_name!r} "
                    f"for field {field!r} (valid: "
                    f"{', '.join(sorted(valid_values)[:8])}"
                    f"{'…' if len(valid_values) > 8 else ''})"
                ),
                path=f"{path}.value",
                near=sug[0] if sug else None,
                suggestion=(f"did you mean {sug[0]!r}?" if sug else None),
                severity="warning",
            ))

    def _validate_field_value(
        self,
        value: Any,
        field_type: str,
        field: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Type-check a value against its field type."""
        if value is None or value == "":
            # Null/empty is always valid (operators like isnull/isnotnull require it)
            return
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            # Jinja template -- defer to runtime
            return

        def _is_numeric_string(s: str) -> bool:
            """Check if a string can be coerced to an integer."""
            try:
                int(s)
                return True
            except (ValueError, TypeError):
                return False

        # Basic type validation
        if field_type == "integer":
            if isinstance(value, list):
                # List of integers (e.g., for `in` operator)
                for i, v in enumerate(value):
                    if isinstance(v, str) and ("{{" in v or "{%" in v):
                        # Jinja in list -- pass through
                        continue
                    if not isinstance(v, int) and not (
                        isinstance(v, str) and _is_numeric_string(v)
                    ):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"field {field!r} is type integer; "
                                f"value[{i}] {v!r} is not a valid integer"
                            ),
                            path=f"{path}.value",
                            severity="warning",
                        ))
            elif isinstance(value, str) and not _is_numeric_string(value):
                # String that's not a number (and not int)
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"field {field!r} is type integer; "
                        f"value {value!r} is not a valid integer"
                    ),
                    path=f"{path}.value",
                    severity="warning",
                ))
            elif not isinstance(value, (int, str)):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"field {field!r} is type integer; "
                        f"value {value!r} is not a valid integer"
                    ),
                    path=f"{path}.value",
                    severity="warning",
                ))

        elif field_type in ("text", "string"):
            if isinstance(value, list):
                for i, v in enumerate(value):
                    if not isinstance(v, str):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"field {field!r} is type text; "
                                f"value[{i}] {v!r} is not a string"
                            ),
                            path=f"{path}.value",
                            severity="warning",
                        ))
            elif not isinstance(value, str):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"field {field!r} is type text; "
                        f"value {value!r} is not a string"
                    ),
                    path=f"{path}.value",
                    severity="warning",
                ))

        elif field_type == "boolean":
            _BOOL_STRINGS = {"true", "false", "1", "0"}

            def _is_booly(v: Any) -> bool:
                if isinstance(v, bool):
                    return True
                if isinstance(v, int) and not isinstance(v, bool) and v in (0, 1):
                    return True
                return (
                    isinstance(v, str)
                    and v.strip().lower() in _BOOL_STRINGS
                )

            if isinstance(value, list):
                for i, v in enumerate(value):
                    if isinstance(v, str) and ("{{" in v or "{%" in v):
                        continue
                    if not _is_booly(v):
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"field {field!r} is type boolean; "
                                f"value[{i}] {v!r} is not a valid boolean "
                                f"(use true/false or 1/0)"
                            ),
                            path=f"{path}.value",
                            severity="warning",
                        ))
            elif not _is_booly(value):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"field {field!r} is type boolean; "
                        f"value {value!r} is not a valid boolean "
                        f"(use true/false or 1/0)"
                    ),
                    path=f"{path}.value",
                    severity="warning",
                ))
