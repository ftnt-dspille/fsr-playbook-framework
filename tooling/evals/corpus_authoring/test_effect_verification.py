"""effect_verification scores write->readback discipline, order-aware."""
from __future__ import annotations

from tooling.evals.corpus_authoring import effect_verification as ev


def test_write_then_verify_effect_is_right():
    g = ev.grade_effect_verification(
        ["orient", "create_record", "verify_effect"])
    assert g["wrote"] and g["verified"] and g["verified_right"]
    assert g["used_intended"] is True


def test_write_then_plain_readback_counts_but_not_intended():
    g = ev.grade_effect_verification(["update_record", "get_record"])
    assert g["verified"] is True
    assert g["used_intended"] is False


def test_write_with_no_readback_is_a_miss():
    g = ev.grade_effect_verification(["create_record"])
    assert g["wrote"] is True
    assert g["verified"] is False
    assert g["verified_right"] is False


def test_readback_BEFORE_write_does_not_count():
    # order matters: a read before the write did not observe the effect.
    g = ev.grade_effect_verification(["get_record", "update_record"])
    assert g["wrote"] is True
    assert g["verified"] is False


def test_last_write_is_the_anchor():
    # a verify between two writes doesn't cover the second write.
    g = ev.grade_effect_verification(
        ["create_record", "verify_effect", "update_record"])
    assert g["verified"] is False


def test_no_write_makes_the_dimension_not_apply():
    g = ev.grade_effect_verification(["orient", "build_playbook", "get_record"])
    assert g["wrote"] is False
    assert g["verified_right"] is None


def test_mcp_prefixes_stripped():
    g = ev.grade_effect_verification(
        ["mcp__fsr__create_record", "mcp__fsr__verify_effect"])
    assert g["used_intended"] is True


def test_aggregate_rates_over_writing_drives_only():
    rows = [
        ev.grade_effect_verification(["create_record", "verify_effect"]),
        ev.grade_effect_verification(["update_record"]),          # miss
        ev.grade_effect_verification(["orient", "get_record"]),   # no write
    ]
    agg = ev.aggregate(rows)
    assert agg["drives_that_wrote"] == 2
    assert agg["verified_effect"] == "1/2"
    assert agg["used_verify_effect"] == "1/2"
    assert agg["tool_histogram"]["create_record"] == 1
