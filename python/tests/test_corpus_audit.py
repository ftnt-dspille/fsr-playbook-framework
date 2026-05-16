"""Tests for probe_corpus_audit (I13 + I14).

Runs against the live `store/fsr_reference.db`. Tests assert the
audit's shape (not specific drift counts) so the suite isn't fragile
against corpus changes.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from probes import probe_corpus_audit as audit


def test_audit_step_keys_classifies_known_types(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_step_keys(conn)
    conn.close()
    # Every step_type_name that appears in EXPECTED_KEYS and has rows in
    # the corpus must be classified.
    for tname, spec in audit.EXPECTED_KEYS.items():
        if tname not in report:
            continue
        assert report[tname]["status"] == "classified", tname
        assert set(report[tname]["expected_keys"]) == (
            spec["friendly"] | spec["canonical"]
            | audit.UNIVERSAL_STEP_KEYS
        )


def test_audit_step_keys_friendly_keys_excluded_from_never_observed(
        db_path: Path):
    """Friendly keys are pre-resolver; the corpus is post-resolver, so
    'never_observed' must contain only canonical-side keys."""
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_step_keys(conn)
    conn.close()
    for tname, spec in audit.EXPECTED_KEYS.items():
        if tname not in report:
            continue
        never = set(report[tname]["never_observed"])
        assert never.isdisjoint(spec["friendly"]), (
            f"{tname}: friendly keys leaked into never_observed: "
            f"{never & spec['friendly']}"
        )
        assert never <= spec["canonical"]


def test_audit_input_field_kinds_returns_structure(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_input_field_kinds(conn)
    conn.close()
    assert "distinct_tuples" in report
    assert "uncovered_tuples" in report
    assert "kinds_never_observed" in report
    assert isinstance(report["distinct_tuples"], int)
    for entry in report["all"]:
        assert "tuple" in entry and len(entry["tuple"]) == 4
        assert "count" in entry


def test_audit_covers_canonical_text_kinds(db_path: Path):
    """Smoke: at least one observed tuple is covered. The corpus
    contains plenty of plain `text` MI inputs, so coverage must not be
    zero across the board."""
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_input_field_kinds(conn)
    conn.close()
    covered = [d for d in report["all"] if d["covered_by_kind"]]
    assert covered, "no MI inputVariable tuples matched _INPUT_FIELD_KINDS"


def test_run_writes_report(tmp_path: Path, db_path: Path):
    result = audit.run(db_path, tmp_path)
    assert (tmp_path / "corpus_audit.md").exists()
    payload = json.loads((tmp_path / "corpus_audit.json").read_text())
    assert "step_keys" in payload
    assert "input_field_kinds" in payload
    assert payload["step_keys"], "step_keys report is empty"


def test_template_url_is_advisory(db_path: Path):
    """Live FSR is inconsistent about templateUrl on inputVariables
    (the UI strips it or leaves stale values when authors switch
    field types). Covered() must match on (formType, dataType, type)
    even when templateUrl is None or non-canonical."""
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_input_field_kinds(conn)
    conn.close()
    # The dominant variant — bare text with templateUrl absent —
    # is a real corpus pattern; assert it's now covered.
    text_none = [
        d for d in report["all"]
        if d["tuple"] == ["text", "text", "string", None]
    ]
    if text_none:
        assert text_none[0]["covered_by_kind"] == "text", text_none[0]


def test_lookup_kind_treats_target_module_as_wildcard(db_path: Path):
    """lookup inputs carry their target module in `type` (people /
    indicators / etc.). The audit's `*lookup*` sentinel must absorb
    any non-empty target."""
    conn = sqlite3.connect(str(db_path))
    report = audit.audit_input_field_kinds(conn)
    conn.close()
    lookup_entries = [
        d for d in report["all"]
        if d["tuple"][0] == "lookup" and d["tuple"][1] == "lookup"
    ]
    if not lookup_entries:
        pytest.skip("corpus has no lookup-kind MI inputs")
    for d in lookup_entries:
        assert d["covered_by_kind"] == "lookup", d
