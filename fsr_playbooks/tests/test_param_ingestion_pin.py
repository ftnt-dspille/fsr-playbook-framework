"""Phase 4b (STATIC_TYPE_FLOW) — pin the live connector-param ingestion matrix.

The live probe (`python/probes/probe_param_ingestion.py`) proved two things on
FortiCloud SOAR (build 7.6.5), captured in
`store/probe_results/param_ingestion_coercion.json`:

  1. **Widget type is irrelevant** — a value sent into a text param and into an
     integer param arrives as the SAME python type. The widget type does NOT
     drive runtime coercion (it is a UI hint only).
  2. **Ingestion applies the identical smart-cast as set_variable** (the Phase
     1b matrix): `"123"`→int, `"true"`→bool, `"TRUE"`→str, `"007"`→str,
     `'["a"]'`→list, `"null"`→None, dates→str.

This test pins both against the committed artifact so an FSR upgrade that
changes the behavior fails here (re-run the probe, update the matrix). It is
offline — it reads the committed JSON, no live calls. Skips if the artifact is
absent (e.g. a checkout that never ran the probe).

Consequence for the analyzer (why Phase 4 ships NO extra scalar→scalar rule):
because the received type equals the Phase 1b cast and the widget does not
coerce, a `string`-typed source can still be a python-`int()`-able string
(e.g. "007"→str but int("007")==7), so flagging string→numeric would
false-positive. Phase 4's conservative rules (shape-into-scalar via connector
intent + numeric/bool crossings) remain correct and sufficient.
"""
import json

import pytest

from fsr_playbooks.compiler.typed_walker import _infer_literal_shape

# Resolve the repo-root store/ path from this file (…/fsr_playbooks/tests/…).
from pathlib import Path
_ARTIFACT = (Path(__file__).resolve().parents[2]
             / "data" / "probe_results" / "param_ingestion_coercion.json")

# String-input rows → the literal string the probe sent, so we can re-derive
# the expected type via the Phase 1b classifier and prove the two casts agree.
_STR_INPUTS = {
    "str_123": "123", "str_1p5": "1.5", "str_true": "true",
    "str_false": "false", "str_TRUE": "TRUE", "str_list": '["a","b"]',
    "str_obj": '{"k":1}', "str_null": "null", "str_hello": "hello",
    "str_007": "007", "str_date": "2026-06-06",
}

_SHAPE_TO_PYTYPE = {
    ("scalar", "integer"): "int", ("scalar", "float"): "float",
    ("scalar", "boolean"): "bool", ("scalar", "string"): "str",
    ("scalar", "null"): "NoneType", ("list", None): "list",
    ("object", None): "dict",
}


def _expected_pytype(value: str) -> str:
    sh = _infer_literal_shape(value)
    kind = sh.get("kind")
    return _SHAPE_TO_PYTYPE[(kind, sh.get("type") if kind == "scalar" else None)]


@pytest.fixture(scope="module")
def matrix():
    if not _ARTIFACT.exists():
        pytest.skip(f"ingestion probe artifact absent: {_ARTIFACT}")
    return json.loads(_ARTIFACT.read_text())


def test_widget_type_is_irrelevant(matrix):
    # every widget received the same type for every value
    assert matrix["widget_type_independent"] is True
    for label, row in matrix["matrix"].items():
        assert len(set(row.values())) == 1, (label, row)


def test_ingestion_cast_matches_phase1b_classifier(matrix):
    for label, value in _STR_INPUTS.items():
        row = matrix["matrix"].get(label)
        if row is None:
            continue
        received = next(iter(row.values()))  # uniform across widgets
        assert received == _expected_pytype(value), (
            f"{label}={value!r}: ingestion received {received!r} but the "
            f"Phase 1b classifier predicts {_expected_pytype(value)!r}")
