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
    """

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

        # Leaf filter — validate field + value
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
        # Query the field definition
        row = self.conn.execute(
            "SELECT field_name, type, picklist_name FROM module_fields "
            "WHERE module_name=? AND field_name=?",
            (module_name, field),
        ).fetchone()

        if not row:
            # Unknown field — suggest alternatives
            known = [r[0] for r in self.conn.execute(
                "SELECT field_name FROM module_fields WHERE module_name=?",
                (module_name,),
            ).fetchall()]
            if not known:
                # Module has no fields in catalog (shouldn't happen if module exists)
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

        # Field exists — validate its value
        field_type = row["type"]
        picklist_name = row["picklist_name"]

        value = filt.get("value")

        # Wildcard/substring operators (like/contains) carry `%`-wrapped
        # partial values, not exact field values — exact picklist/type checks
        # would spuriously reject them, so skip value validation for those.
        if isinstance(value, str) and "%" in value:
            return

        # Validate value based on field type
        if picklist_name:
            self._validate_picklist_value(
                value, picklist_name, field, path, errors
            )
        else:
            # Non-picklist field — type-check the value
            self._validate_field_value(value, field_type, field, path, errors)

    def _validate_picklist_value(
        self,
        value: Any,
        picklist_name: str,
        field: str,
        path: str,
        errors: list[CompileError],
    ) -> None:
        """Validate that a value (or list of values) exists in the picklist."""
        if value is None or value == "":
            # Null/empty is valid for nullable fields (isnull/isnotnull checks)
            return
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            # Jinja template — defer to runtime
            return
        if isinstance(value, list) and not value:
            # Empty list is valid
            return

        # Value(s) to check
        values_to_check = value if isinstance(value, list) else [value]
        # Filter out Jinja expressions and non-strings
        values_to_check = [
            v for v in values_to_check
            if isinstance(v, str) and not ("{{" in v or "{%" in v)
        ]

        if not values_to_check:
            return

        valid = {r[0] for r in self.conn.execute(
            "SELECT item_value FROM picklists WHERE list_name=?",
            (picklist_name,),
        ).fetchall()}

        if not valid:
            # Empty picklist — catalog may not be warmed
            return

        for v in values_to_check:
            if v not in valid:
                sug = difflib.get_close_matches(v, list(valid), n=1, cutoff=0.6)
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"value {v!r} is not in picklist {picklist_name!r} "
                        f"for field {field!r} (valid: "
                        f"{', '.join(sorted(valid)[:8])}"
                        f"{'…' if len(valid) > 8 else ''})"
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
            # Jinja template — defer to runtime
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
                        # Jinja in list — pass through
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
