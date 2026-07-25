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


class TestPicklistIRIValues:
    """Object-typed filters carry canonical /api/3/picklists/<uuid> IRIs."""

    def test_object_typed_iri_value_passes(self):
        """A canonical picklist IRI (as emitted for object-typed filters)
        should be accepted, not flagged as 'not in picklist'."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            row = conn.execute(
                "SELECT p.item_iri, p.item_value FROM picklists p "
                "JOIN module_fields m ON m.picklist_name = p.list_name "
                "WHERE m.module_name='alerts' AND m.field_name='severity' "
                "LIMIT 1"
            ).fetchone()
            assert row, "catalog has no severity picklist IRI to test against"
            iri, label = row[0], row[1]
            errors: list[CompileError] = []
            filters = [{
                "type": "object",
                "field": "severity",
                "value": iri,
                "_value": {"@id": iri, "display": label, "itemValue": label},
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors, (
                f"valid picklist IRI {iri!r} should pass; got {value_errors!r}"
            )
        finally:
            conn.close()

    def test_bogus_iri_warns(self):
        """An IRI-shaped value not in the picklist should still warn."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "object",
                "field": "severity",
                "value": "/api/3/picklists/00000000-0000-0000-0000-000000000000",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_warnings = [
                e for e in errors if ".value" in e.path
                and e.severity == "warning"
            ]
            assert len(value_warnings) == 1
            assert "not in picklist" in value_warnings[0].message
        finally:
            conn.close()

    def test_iri_in_list_passes(self):
        """Array-typed picklist filter with IRI values should pass."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            row = conn.execute(
                "SELECT p.item_iri FROM picklists p "
                "JOIN module_fields m ON m.picklist_name = p.list_name "
                "WHERE m.module_name='alerts' AND m.field_name='severity' "
                "LIMIT 1"
            ).fetchone()
            assert row
            iri = row[0]
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "severity",
                "value": [iri],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()


class TestValueIrrelevantOperators:
    """isnull/isnotnull/changed carry placeholder values that must not be type-checked."""

    def test_isnull_on_integer_with_placeholder_skips(self):
        """`isnull` with a placeholder string on an integer field must not warn."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "datetime",
                "field": "dueBy",  # integer-typed (epoch) on alerts
                "value": "true",   # FSR designer placeholder for isnull
                "operator": "isnull",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            assert not errors, (
                f"isnull placeholder should not type-check; got {errors!r}"
            )
        finally:
            conn.close()

    def test_isnotnull_on_integer_with_placeholder_skips(self):
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "ackDate",
                "value": "not-a-number",
                "operator": "isnotnull",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()

    def test_eq_on_integer_still_type_checks(self):
        """A non-placeholder operator must still type-check the value."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "ackDate",
                "value": "not-a-number",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_warnings = [
                e for e in errors if ".value" in e.path
                and "not a valid integer" in e.message
            ]
            assert len(value_warnings) == 1
        finally:
            conn.close()

    def test_isnull_on_picklist_field_skips_value(self):
        """`isnull` on a picklist field with a placeholder must skip picklist check."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "object",
                "field": "severity",
                "value": "true",
                "operator": "isnull",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()


class TestBooleanValidation:
    """Boolean field value validation (previously unvalidated)."""

    def test_boolean_true_passes(self):
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            for val in [True, False, "true", "false", "True", "False", 1, 0, "1", "0"]:
                errors: list[CompileError] = []
                filters = [{
                    "type": "primitive",
                    "field": "resolvedAutomatedly",
                    "value": val,
                    "operator": "eq",
                }]
                validator.validate_trigger_filters(
                    filters, "alerts", "p.when", errors
                )
                value_errors = [e for e in errors if ".value" in e.path]
                assert not value_errors, f"value={val!r} should pass"
        finally:
            conn.close()

    def test_boolean_invalid_value_warns(self):
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "resolvedAutomatedly",
                "value": "maybe",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_warnings = [
                e for e in errors if ".value" in e.path
                and "boolean" in e.message
            ]
            assert len(value_warnings) == 1
            assert "maybe" in value_warnings[0].message
        finally:
            conn.close()

    def test_boolean_list_validates_each(self):
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "resolvedAutomatedly",
                "value": [True, "maybe"],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            bad = [e for e in errors if "maybe" in e.message]
            assert len(bad) == 1
            assert "value[1]" in bad[0].message
        finally:
            conn.close()

    def test_boolean_jinja_deferred(self):
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "primitive",
                "field": "resolvedAutomatedly",
                "value": "{{ vars.flag }}",
                "operator": "eq",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            value_errors = [e for e in errors if ".value" in e.path]
            assert not value_errors
        finally:
            conn.close()


class TestTagFilters:
    """Array tag filters (template: tags) reference /api/3/tags/, not module_fields."""

    def test_tag_template_skips_field_existence(self):
        """recordTags is a system field not in module_fields; tag filters must
        not produce a 'field does not exist' false positive."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "recordTags",
                "value": ["/api/3/tags/FortiRecon", "/api/3/tags/EASM"],
                "module": "recordTags",
                "operator": "in_all",
                "template": "tags",
                "OPERATOR_KEY": "$",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            assert not errors, (
                f"tag filter should skip validation; got {errors!r}"
            )
        finally:
            conn.close()

    def test_non_tag_array_field_still_validated(self):
        """An array filter without template: tags should still check field existence."""
        conn = _get_db()
        try:
            validator = FieldValueValidator(conn)
            errors: list[CompileError] = []
            filters = [{
                "type": "array",
                "field": "totallyBogusField",
                "value": ["x"],
                "operator": "in",
            }]
            validator.validate_trigger_filters(
                filters, "alerts", "p.when", errors
            )
            field_errors = [e for e in errors if ".field" in e.path]
            assert len(field_errors) == 1
            assert "totallyBogusField" in field_errors[0].message
        finally:
            conn.close()
