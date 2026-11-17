"""A trigger filter on a picklist sub-key (`severity.itemValue`) never fires on
8.0.1 reliably (live-tested); the compiler must refuse it and point at the IRI form."""
import pytest

from fsr_playbooks.compiler.typed_args.trigger import expand_when


def _compile(field, value):
    errs = []
    out = expand_when({"logic": "AND", "filters": [{"field": field, "op": "eq", "value": value}]},
                      "start_on_create", "steps[0]", errs)
    return out, errs


@pytest.mark.parametrize("field", ["severity.itemValue", "status.@id", "priority.display"])
def test_picklist_subkey_is_refused(field):
    out, errs = _compile(field, "Critical")
    assert not (out or {}).get("filters")
    assert errs and "does not fire reliably" in errs[0].message
    assert "resolve_picklist" in errs[0].message
    assert errs[0].path == "steps[0].arguments.when.filters[0].field"


def test_iri_and_plain_fields_still_compile():
    for field, value in [("severity", "/api/3/picklists/7efa2220-39bb-44e4-961f-ac368776e3b0"),
                         ("name", "Agent Lab%")]:
        out, errs = _compile(field, value)
        assert out is not None and not [e for e in errs if e.severity != "warning"]
