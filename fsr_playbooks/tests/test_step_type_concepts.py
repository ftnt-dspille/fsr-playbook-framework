"""get_step_type answers `for_each` and `schedule` as CONCEPTS, not typos.

Both are real FortiSOAR ideas and neither is a step type: looping is the
`for_each:` key any step can carry, and scheduling is a platform feature
outside the playbook document. They used to fall through to the difflib arm,
which answered `for_each` with nothing at all and `schedule` with "did you
mean set_variable?" -- a near-match list reads as an answer, so the model
follows it and authors a step that does not exist.

The bar is the one find_operation already meets: when the exact thing is not
there, return what IS true plus the shape to author, not a guess.
"""
from fsr_playbooks.mcp_server.tools_discovery import get_step_type

_get = get_step_type.fn if hasattr(get_step_type, "fn") else get_step_type


def test_for_each_explains_that_looping_is_a_step_property():
    out = _get("for_each")
    assert out["not_a_step_type"] is True
    assert out["concept"] == "for_each"
    # The answer has to carry the authorable shape -- a definition alone
    # sends the model back to the tool.
    assert "for_each:" in out["yaml"] and "item:" in out["yaml"]
    assert any("vars.item" in n for n in out["notes"])


def test_schedule_points_at_the_platform_not_at_set_variable():
    out = _get("schedule")
    assert out["not_a_step_type"] is True
    assert out["concept"] == "schedule"
    assert "set_variable" not in str(out), \
        "the old near-match answer was a wrong lead, not a weak one"
    # `delay` is the thing it is genuinely confusable with, so name it.
    assert any("delay" in n for n in out["notes"])


def test_synonyms_land_on_the_same_concept():
    for alias in ("loop", "iterate", "FOREACH", "for-each"):
        assert _get(alias)["concept"] == "for_each", alias
    for alias in ("cron", "recurring", "Scheduled"):
        assert _get(alias)["concept"] == "schedule", alias


def test_a_real_step_type_is_never_shadowed_by_a_concept():
    """The concept map is consulted only after the step_types lookup misses,
    so `delay` (a real step) still returns its schema."""
    out = _get("delay")
    assert out.get("not_a_step_type") is None
    assert out["name"] == "Delay"


def test_an_actual_typo_still_gets_near_matches():
    out = _get("set_varible")
    assert out["ok"] is False and out["code"] == "not_found"
