"""The grown grounded store catches bad output refs on the newly-grounded ops.

Growing the store is only worthwhile if it converts real runtime-only bugs into
statically-caught ones. These ops were grounded from live read-only runs:
  cyops_utilities.get_email_templates  -> data is a list[str]
  cyops_utilities.get_ioc_parsing_regex-> data is a list[object]
A bare `.attr` on either list renders empty at runtime; verify must now flag it.
"""
from __future__ import annotations

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.mcp_server import tools_verify
from fsr_playbooks.mcp_server.tools_verify import verify_playbook

# (connector, op, expected data kind) -- grounded from live read-only runs.
_GROWN = [
    ("cyops_utilities", "get_email_templates", "list"),
    ("cyops_utilities", "get_ioc_parsing_regex", "list"),
    ("fortinet-fortiguard-threat-intelligence", "get_country_list", "list"),
    ("fortinet-fortiguard-threat-intelligence", "get_industry_list", "list"),
    ("fortinet-fortiguard-threat-intelligence", "get_threat_categories", "list"),
    ("fortinet-fortiguard-threat-intelligence", "threat_intel_search", "object"),
    ("fortinet-fortiguard-ioc", "get_risk_distribution", "list"),
    ("mitre-attack", "get_mitre_data_sample", "list"),
]


@pytest.mark.parametrize("connector,op,kind", _GROWN)
def test_op_is_grounded_with_expected_kind(connector, op, kind):
    shape = tools_verify._grounded_store().shape_for(connector, op)
    assert shape, f"{connector}:{op} not grounded"
    data = (shape.get("keys") or {}).get("data")
    assert isinstance(data, dict) and data.get("kind") == kind, (op, data)


def test_grounded_shapes_carry_no_captured_values():
    """Every grounded entry must be structure only: scalar leaves are a type
    name, never a captured value. A leaked value would ship box data."""
    store = tools_verify._grounded_store().as_dict()

    def _check(node):
        if isinstance(node, dict):
            if node.get("kind") == "scalar":
                # only type + structural flags (e.g. optional); never a value.
                assert set(node) <= {"kind", "type", "optional"}, node
                assert node.get("type") in {"string", "integer", "float", "boolean",
                                            "null", "any", "unknown"}, node
            for v in node.values():
                _check(v)
        elif isinstance(node, list):
            for v in node:
                _check(v)
    for entry in store.values():
        _check(entry)


def _pb(op: str, ref: str) -> str:
    return f"""collection: G
visible: true
playbooks:
- name: P
  is_active: true
  steps:
  - {{name: Start, type: start, next: Call}}
  - {{name: Call, type: connector, connector: cyops_utilities, operation: {op}, config: "", params: {{}}, next: Rec}}
  - name: Rec
    type: create_record
    module: alerts
    resource: {{name: D, severity: Low, description: "{{{{ vars.steps.Call.data{ref} }}}}"}}
"""


def test_bad_attr_on_grown_list_op_is_caught():
    db = str(default_db_path())
    # `.data.anything` is an attr on a list -> empty at runtime -> must be caught
    v = verify_playbook(_pb("get_email_templates", ".anything | join(', ')"), db_path=db)
    fixes = [f.get("code") for f in (v.get("required_fixes") or [])]
    assert not v.get("ready_to_push") and "missing_field_on_step_output" in fixes, (v.get("ready_to_push"), fixes)


def test_correct_ref_on_grown_op_stays_clean():
    db = str(default_db_path())
    v = verify_playbook(_pb("get_email_templates", " | join(', ')"), db_path=db)
    assert v.get("ready_to_push"), v.get("required_fixes")
