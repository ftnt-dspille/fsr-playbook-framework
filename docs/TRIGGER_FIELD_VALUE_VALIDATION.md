# Trigger Field/Value Validation

## Overview

The trigger field/value validation system validates trigger conditions against the reference catalog:
- **Field validation**: Ensures trigger filter fields exist in the module's schema
- **Value validation**: Checks values against field type (integer, text) and picklist constraints
- **Jinja support**: Defers validation for Jinja expressions (evaluated at runtime)
- **Unwarmed catalog**: Silent when catalog tables are empty (installation not warmed yet)

## Implementation

### Location
- **Core validator**: `fsr_playbooks/compiler/typed_args/field_validator.py`
- **Public API**: Exported via `fsr_playbooks.compiler.typed_args.FieldValueValidator`

### Architecture

The validation runs in **two phases**:

1. **Phase 1 - Structural Validation** (already implemented):
   - Runs in `expand_when()` in `typed_args/trigger.py`
   - Validates YAML shape, operator tokens, and nested group structure
   - Produces normalized FSR wire `fieldbasedtrigger` dict
   - Catches typos via `extra="forbid"` pydantic config

2. **Phase 2 - Field/Value Validation** (NEW):
   - Runs after `expand_when()` via `FieldValueValidator.validate_trigger_filters()`
   - Queries the reference database for field existence and type/picklist
   - Produces descriptive warnings with "did you mean" suggestions
   - Needs to be called from the resolver or validator when a database connection is available

## Usage

### Direct Usage (for testing/tooling)

```python
import sqlite3
from fsr_playbooks.compiler.typed_args import FieldValueValidator, expand_when

# 1. Structural validation
errors = []
when_dict = {...}  # YAML-loaded when block
expanded = expand_when(when_dict, "start_on_create", "playbooks[0].steps[0].arguments.when", errors)

# 2. Field/value validation (if expanded successfully)
if expanded:
    conn = sqlite3.connect("data/fsr_reference.db")
    validator = FieldValueValidator(conn)
    validator.validate_trigger_filters(
        expanded["filters"],
        "alerts",  # module name
        "playbooks[0].steps[0].arguments.when",
        errors,
    )
    conn.close()

# All errors accumulated in `errors` list
```

### Integration into Resolver/Validator (TODO)

Field/value validation should be called **after** the field-based-trigger step is resolved. The ideal place is:

#### Option A: In the Resolver (during step normalization)

In `fsr_playbooks/compiler/resolver/normalizers.py`, add validation to the trigger/field-based-trigger normalizer:

```python
from ..typed_args import expand_when, FieldValueValidator

def _normalize_field_based_trigger_args(self, ...):
    # Existing normalizer code...
    when = a.get("when")
    if when:
        when_path = f"{path}.arguments.when"
        expanded = expand_when(when, step.type, when_path, errors)
        if expanded:
            # NEW: Field/value validation against catalog
            validator = FieldValueValidator(self.conn)
            validator.validate_trigger_filters(
                expanded["filters"],
                module_name,  # resolved from step arguments
                when_path,
                errors,
            )
            a["when"] = expanded
```

#### Option B: In the Validator (cross-cutting validation)

In `fsr_playbooks/compiler/validator.py`, add a new validation pass:

```python
from ..typed_args import FieldValueValidator

def _check_trigger_fields(pb: Playbook, pi: int, errors: list[CompileError]) -> None:
    """Validate trigger filter fields against the module catalog."""
    validator = FieldValueValidator(_DB_PATH)
    for si, step in enumerate(pb.steps):
        if step.type not in ("start_on_create", "start_on_update", ...):
            continue
        # Extract module name from step
        module = resolve_trigger_module(step)
        if not module:
            continue
        # Validate filters
        a = step.arguments if isinstance(step.arguments, dict) else {}
        when = a.get("fieldbasedtrigger", {})
        if isinstance(when, dict) and "filters" in when:
            path = f"playbooks[{pi}].steps[{si}].arguments"
            validator.validate_trigger_filters(when["filters"], module, path, errors)
```

**Recommendation**: Option A (resolver) is preferred because:
- Runs closer to parsing → earlier feedback
- Has natural access to module resolution logic
- Follows the pattern of other field-based validators (picklists, etc.)

## Error Model

All errors use the `CompileError` accumulation model (warnings, not blocking):

| Scenario | Code | Severity | Example |
|----------|------|----------|---------|
| Unknown field | `BAD_VALUE` | warning | "field 'serverity' does not exist on module 'alerts'" |
| Invalid picklist value | `BAD_VALUE` | warning | "value 'Bad' is not in picklist 'Severity'" |
| Type mismatch | `BAD_VALUE` | warning | "field 'ackDate' is type integer; value 'abc' is not valid" |
| Empty catalog | (no error) | — | Silently passes (catalog may not be warmed) |

## Catalog Dependencies

Validation queries two tables:

- `module_fields` (stable, shipped): field name, type, picklist_name
- `picklists` (dynamic, warmed): list_name, item_value, item_iri

Both tables are populated from the reference database. If empty:
- Field lookups return no results → no field validation
- Picklist lookups return no results → no value validation

This is intentional: an unwarmed catalog (fresh install, offline mode) should not block compilation.

## Test Coverage

Comprehensive unit tests in `tooling/tests/test_trigger_field_value_validation.py`:

- ✓ Field existence checks with suggestions
- ✓ Picklist value validation (single and list)
- ✓ Type checking (integer, text)
- ✓ Jinja expression pass-through
- ✓ Nested AND/OR group handling
- ✓ Empty/unwarmed catalog handling
- ✓ Null/empty value handling

Run tests:
```bash
pytest tooling/tests/test_trigger_field_value_validation.py -v
```

## Known Limitations

1. **Type coverage**: Currently validates `integer` and `text` types. Other FSR types (relationship, datetime, etc.) are recognized but not validated. Extend `_validate_field_value()` to add more types.

2. **Negative numbers**: Accepted in numeric strings (e.g., "-42") via `int()` coercion.

3. **Floating-point**: Not validated (FSR integers cover most use cases; floats are rare).

4. **Relationship fields**: Fields with type like "alerts" (IRI reference) are not validated here. The wire shape already enforces IRIs.

5. **Custom modules**: Unknown modules pass silently (may exist on target install).

## Future Enhancements

- [ ] Validate `datetime` type (format checks, parsability)
- [ ] Validate relationship field IRIs (must be valid `/api/3/...`)
- [ ] Operator compatibility (e.g., `like` requires string, `gt` requires numeric)
- [ ] Performance: Cache field lookups per module
- [ ] Auto-fix: Suggest renames if field exists with different case (already done in resolver)
