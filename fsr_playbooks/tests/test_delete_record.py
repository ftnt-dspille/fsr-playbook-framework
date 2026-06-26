"""Phase 2 coverage — `delete_record` short type.

FortiSOAR has no dedicated delete step type (the editor palette is
Create/Update/Find only). Record deletion is performed by a connector step
calling `cyops_utilities.make_cyops_request` with HTTP `method: DELETE` —
verified against 4 real corpus playbooks (single-record IRI and
`delete-with-query` bulk forms). `delete_record` is a friendly short type that
compiles to exactly that call.

The normalizer transform is unit-tested directly (no connector metadata
needed). End-to-end compilation is exercised against the full reference DB when
present (the packaged slim DB ships no `cyops_utilities`, exactly like
`stop`/`end`).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.ir import Step
from fsr_playbooks.compiler.resolver import Resolver
from fsr_playbooks._db import PACKAGED_SLIM_DB

_FULL_DB = Path(__file__).resolve().parents[2] / "data" / "fsr_reference.db"


def _normalize(arguments: dict) -> tuple[dict, list]:
    """Run only the delete_record normalizer against a step, return its args."""
    r = Resolver(PACKAGED_SLIM_DB)
    step = Step(id="d", type="delete_record", name="Del", arguments=dict(arguments))
    errors: list = []
    r._normalize_delete_record_args(step, "p.steps[1]", errors)
    return step.arguments, [e for e in errors if e.severity != "warning"]


def test_single_record_iri():
    args, errs = _normalize({"record": "/api/3/alerts/abc"})
    assert not errs
    assert args["connector"] == "cyops_utilities"
    assert args["operation"] == "make_cyops_request"
    assert args["params"]["method"] == "DELETE"
    assert args["params"]["iri"] == "/api/3/alerts/abc"
    assert args["params"]["body"] == ""


def test_module_plus_record_id():
    args, errs = _normalize({"module": "alerts", "record_id": "{{ vars.x }}"})
    assert not errs
    assert args["params"]["iri"] == "/api/3/alerts/{{ vars.x }}"
    assert args["params"]["method"] == "DELETE"


def test_query_bulk_delete_with_query():
    args, errs = _normalize({
        "module": "threat_intel_feeds",
        "query": {"logic": "AND", "filters": [{"field": "expiresOn",
                                               "operator": "lte", "value": "x"}]},
    })
    assert not errs
    assert args["params"]["iri"] == \
        "/api/3/delete-with-query/threat_intel_feeds?$showDeleted=true"
    # body is the json-encoded filter tree
    assert '"logic": "AND"' in args["params"]["body"]
    assert args["params"]["method"] == "DELETE"


def test_requires_exactly_one_target():
    _, errs = _normalize({})
    assert errs and "exactly one target" in errs[0].message
    _, errs2 = _normalize({"record": "/api/3/alerts/a",
                           "module": "alerts",
                           "query": {"logic": "AND", "filters": []}})
    assert errs2 and "exactly one target" in errs2[0].message


def test_raw_escape_hatch_passthrough():
    args, errs = _normalize({"params": {"iri": "/api/wf/api/custom/1/",
                                        "method": "DELETE", "body": ""}})
    assert not errs
    assert args["params"]["iri"] == "/api/wf/api/custom/1/"


@pytest.mark.skipif(not _FULL_DB.exists(),
                    reason="full reference DB (with cyops_utilities) not present")
def test_end_to_end_compile_against_full_db():
    yaml_text = """
collection: T
playbooks:
  - name: P
    steps:
      - {name: S, type: start, next: D}
      - name: D
        type: delete_record
        record: "{{ vars.input.records[0]['@id'] }}"
"""
    res = compile_yaml(yaml_text, str(_FULL_DB))
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]

    found = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("@type") == "WorkflowStep" and o.get("name") == "D":
                found.update(o.get("arguments") or {})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(res.fsr_json)
    assert found["connector"] == "cyops_utilities"
    assert found["params"]["method"] == "DELETE"
