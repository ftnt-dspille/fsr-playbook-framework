"""Unit tests for trigger field and value validation.

Tests the FieldValueValidator against the reference catalog:
  - Field existence checks with suggestions
  - Picklist value validation
  - Type checking for integer/text fields
  - Nested filter group handling
  - Jinja template pass-through
  - Empty/unwarmed catalog handling
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args import FieldValueValidator


def _get_db():
    """Get the reference database connection."""
    db_path = (
        Path(__file__).resolve().parents[1].parent
        / "data" / "fsr_reference.db"
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


class TestFieldValidatorBasics:
    """Basic field existence and error reporting."""

    def test_valid_field_passes(self):
        """A field that exists in the module should not error."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": "High",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # No errors for a valid field
            assert not errors
        finally:
            conn.close()

    def test_unknown_field_warns_with_suggestion(self):
        """An unknown field should warn with a 'did you mean' suggestion."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "serverity",  # typo
                "value": "High",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should have a warning with a suggestion
            assert len(errors) == 1
            assert errors[0].code == ErrorCode.BAD_VALUE
            assert "serverity" in errors[0].message.lower()
            assert errors[0].severity == "warning"
            assert errors[0].near is not None or errors[0].suggestion is not None
        finally:
            conn.close()

    def test_field_validation_path_is_correct(self):
        """Error path should point to the field location."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "unknownfield123",
                "value": "X",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            assert errors[0].path.endswith(".field")
        finally:
            conn.close()


class TestPicklistValidation:
    """Picklist-backed field value validation."""

    def test_valid_picklist_value_passes(self):
        """A value in a picklist should pass validation."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            # severity is a picklist field on alerts
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": "High",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # May have field warning but not value warning
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()

    def test_invalid_picklist_value_warns(self):
        """A value not in the picklist should warn."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            # Use a real picklist field but invalid value
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": "NotAValidSeverity",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should have a warning for the invalid value
            value_warnings = [e for e in errors if ".value" in e.path and e.severity == "warning"]
            assert len(value_warnings) > 0
            assert "NotAValidSeverity" in value_warnings[0].message
        finally:
            conn.close()

    def test_picklist_list_values_validated(self):
        """Array values (for `in` operator) should each be validated."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "severity",
                "value": ["High", "Critical", "InvalidValue"],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should warn about the invalid value in the list
            value_warnings = [e for e in errors if "InvalidValue" in e.message]
            assert len(value_warnings) > 0
        finally:
            conn.close()

    def test_picklist_null_value_passes(self):
        """Null/empty values are valid (used for isnull/isnotnull)."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": None,
                "operator": "isnull",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # No value error for null
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()


class TestTypeValidation:
    """Type checking for non-picklist fields."""

    def test_integer_field_with_numeric_value(self):
        """Integer field with a numeric value should pass."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            # Use an integer field from alerts
            filters = [{
                "type": "primitive",
                "field": "ackDate",  # integer field
                "value": 1234567890,
                "operator": "gt",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # No type error
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()

    def test_integer_field_with_string_number(self):
        """Integer field with a numeric string may pass (type coercion)."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "ackDate",
                "value": "1234567890",
                "operator": "gt",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # String that looks like a number is acceptable
            value_errors = [e for e in errors if ".value" in e.path and "not a valid integer" in e.message]
            assert not value_errors
        finally:
            conn.close()

    def test_integer_field_with_non_numeric_string(self):
        """Integer field with a non-numeric string should warn."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "ackDate",
                "value": "not-a-number",
                "operator": "gt",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should warn about the type mismatch
            value_warnings = [e for e in errors if ".value" in e.path and "not a valid integer" in e.message]
            assert len(value_warnings) > 0
        finally:
            conn.close()

    def test_text_field_with_string(self):
        """Text field with a string should pass."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "closureNotes",  # text field
                "value": "Some notes",
                "operator": "like",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # No type error
            value_errors = [e for e in errors if ".value" in e.path and "not a string" in e.message]
            assert not value_errors
        finally:
            conn.close()

    def test_integer_list_values(self):
        """Integer field with list of integers (for `in` operator)."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "ackDate",
                "value": [1, 2, 3, 4],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # No type error for valid integer list
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()


class TestJinjaPassthrough:
    """Jinja expressions should bypass validation."""

    def test_jinja_expression_passes_validation(self):
        """A Jinja expression should not be validated."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": "{{ vars.custom_severity }}",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Jinja should bypass value validation
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()

    def test_jinja_in_list_passes(self):
        """Jinja in a list should be allowed."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "severity",
                "value": ["High", "{{ vars.dynamic_severity }}"],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Jinja in list should bypass validation
            value_errors = [e for e in errors if ".value" in e.path and "dynamic_severity" in e.message]
            assert not value_errors
        finally:
            conn.close()


class TestNestedGroups:
    """AND/OR nested group handling."""

    def test_nested_group_validation(self):
        """Filters in nested groups should be validated."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [
                {
                    "type": "primitive",
                    "field": "severity",
                    "value": "High",
                    "operator": "eq",
                },
                {
                    "logic": "OR",
                    "filters": [
                        {
                            "type": "primitive",
                            "field": "state",
                            "value": "Open",
                            "operator": "eq",
                        },
                        {
                            "type": "primitive",
                            "field": "unknownfield",
                            "value": "X",
                            "operator": "eq",
                        },
                    ],
                },
            ]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should report the unknown field in the nested group
            unknown_errors = [e for e in errors if "unknownfield" in e.message]
            assert len(unknown_errors) > 0
        finally:
            conn.close()

    def test_deeply_nested_groups(self):
        """Multiple levels of nesting should all be validated."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [
                {
                    "logic": "AND",
                    "filters": [
                        {
                            "logic": "OR",
                            "filters": [
                                {
                                    "type": "primitive",
                                    "field": "badfield999",
                                    "value": "X",
                                    "operator": "eq",
                                },
                            ],
                        },
                    ],
                },
            ]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Should find the bad field deep in the tree
            bad_field_errors = [e for e in errors if "badfield999" in e.message]
            assert len(bad_field_errors) > 0
        finally:
            conn.close()


class TestUnwarmedCatalog:
    """Handling of empty/unwarmed catalog tables."""

    def test_empty_module_fields_table_silent(self):
        """An empty module should not produce validation errors."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create schema but leave empty
        conn.execute("CREATE TABLE module_fields (module_name, field_name, type, picklist_name)")
        conn.commit()

        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "anyfield",
                "value": "X",
                "operator": "eq",
            }]
            # Should silently pass when no module fields exist
            validator.validate_trigger_filters(
                filters, "nonexistent", "p.arguments.when", errors
            )
            # No errors for unwarmed catalog
            assert not errors
        finally:
            conn.close()

    def test_empty_picklist_table_silent(self):
        """An empty picklist should not produce validation errors."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create schema
        conn.execute(
            "CREATE TABLE module_fields (module_name, field_name, type, picklist_name)"
        )
        conn.execute(
            "CREATE TABLE picklists (list_name, item_value, item_iri)"
        )
        # Add a field but no picklist values
        conn.execute(
            "INSERT INTO module_fields VALUES (?, ?, ?, ?)",
            ("test", "status", "text", "statuslist"),
        )
        conn.commit()

        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "status",
                "value": "AnyValue",
                "operator": "eq",
            }]
            # Should silently pass when picklist is empty
            validator.validate_trigger_filters(
                filters, "test", "p.arguments.when", errors
            )
            # No errors for unwarmed picklist
            assert not errors
        finally:
            conn.close()


class TestEmptyValue:
    """Handling of empty/None values."""

    def test_empty_string_passes(self):
        """Empty string should be valid (nullable fields)."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "severity",
                "value": "",
                "operator": "isnotnull",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Empty value should not error
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()

    def test_empty_list_passes(self):
        """Empty list should be valid."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "severity",
                "value": [],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "playbooks[0].steps[0].arguments.when", errors
            )
            # Empty list should not error
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()
