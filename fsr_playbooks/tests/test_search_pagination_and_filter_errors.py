"""Pagination + unknown-filter-field contract for search_module_records.

Both behaviors were found live on a ZTPF box, and both had the same shape: the
tool knew the answer was incomplete and could not say how to complete it.

  * A device with 88 automation steps returned 25 with "state that it is a
    partial view" -- there was no page parameter, so "list every change on this
    device" had no reachable answer at any prompt quality.
  * Filtering on `label` -- the key this tool puts on every result row -- 400ed
    with FortiSOAR's raw "Field:label does not exist in module definition",
    while unknown sort fields and unknown module names both got named,
    actionable refusals.

These are pure-shaping tests: no box, no LLM.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server.tools_triage import (
    _shape_search_members,
    _unknown_field_in,
    _unknown_filter_field,
)


def _body(n_rows: int, total: int) -> dict:
    return {
        "hydra:totalItems": total,
        "hydra:member": [
            {"@id": f"/api/3/ztpf_device_automation_steps/uuid-{i}",
             "id": i, "name": f"step {i}"}
            for i in range(n_rows)
        ],
    }


def test_first_page_of_many_names_the_next_page():
    out = _shape_search_members(_body(25, 88), 25, "ztpf_device_automation_steps",
                                "/api/query/x", page=1)
    assert out["ok"] is True
    assert out["total"] == 88
    assert out["page"] == 1
    assert out["pages"] == 4          # 88 rows / 25 per page
    assert out["truncated"] is True
    assert out["has_more"] is True
    assert out["next_page"] == 2
    # The message must carry the instruction, not just the fact.
    assert "page=2" in out["message"]
    assert "1-25 of 88" in out["message"]


def test_middle_page_reports_its_true_offset():
    """Page 3 shows records 51-75 -- not 1-25. A page that mislabels its own
    offset makes any "I have read everything" claim unverifiable."""
    out = _shape_search_members(_body(25, 88), 25, "m", "/u", page=3)
    assert out["page"] == 3
    assert out["has_more"] is True
    assert out["next_page"] == 4
    assert "51-75 of 88" in out["message"]


def test_last_page_stops_the_loop():
    """88 = 3 full pages + 13. Page 4 must NOT advertise a page 5, or a
    page-until-has_more loop never terminates."""
    out = _shape_search_members(_body(13, 88), 25, "m", "/u", page=4)
    assert out["page"] == 4
    assert out["has_more"] is False
    assert "next_page" not in out
    assert out.get("truncated") is not True
    assert "LAST page" in out["message"]


def test_single_page_result_is_not_flagged_partial():
    out = _shape_search_members(_body(4, 4), 25, "m", "/u", page=1)
    assert out.get("truncated") is not True
    assert out.get("has_more") is not True
    assert out["pages"] == 1


@pytest.mark.parametrize("text,expected", [
    ("{'type': 'HttpException', 'message': 'Invalid query/body parameters "
     "[Field:label does not exist in module definition]'}", "label"),
    ("Invalid query/body parameters [Field:ztpfRunGroups.name does not exist "
     "in module definition]", "ztpfRunGroups.name"),
    ("500 Internal Server Error", None),
    ("", None),
])
def test_unknown_field_extraction(text, expected):
    assert _unknown_field_in(text) == expected


def test_label_refusal_names_the_real_field():
    """`label` is synthesized by this tool, so the model filtering on it is an
    error the tool INDUCED. The refusal has to say so and name `name`."""
    class _Client:
        base_url = "https://box"

    out = _unknown_filter_field(_Client(), "ztpf_device_automation_steps",
                                "label", "/api/query/x")
    assert out["ok"] is False
    assert out["code"] == "unknown_filter_field"
    assert out["field"] == "label"
    assert "synthesize" in out["message"].lower()
    assert "`name`" in out["message"]


def test_unknown_filter_field_survives_a_dead_suggestion_lookup():
    """The suggestion list is best-effort: if sampling the module fails, the
    refusal must still be a refusal, not an exception."""
    class _Boom:
        base_url = "https://box"

    out = _unknown_filter_field(_Boom(), "m", "nope", "/u")
    assert out["ok"] is False
    assert out["code"] == "unknown_filter_field"
    assert out["filterable"] == []
