"""emit_patch_proposal normalizes what a model actually sends.

Live (effect probe A5): before/after arrived wrapped in ```yaml fences (the
card's diff showed them as lines, and no apply could match them), and the
first attempt was refused for tier "0" -- the payload rides inside emit_card,
which the arg gate does not type.
"""
from fsr_playbooks.mcp_server.tools_emit import emit_patch_proposal

BEFORE = "```yaml\nparams:\n  ip_addresses: 198.51.100.10\n```"
AFTER = "```yaml\nparams:\n  ip_addresses: 203.0.113.99\n```"


def test_fences_are_stripped_from_both_sides():
    res = emit_patch_proposal(id="p1", title="t", before_yaml=BEFORE,
                              after_yaml=AFTER)
    assert res["ok"], res
    assert res["card"]["before_yaml"] == "params:\n  ip_addresses: 198.51.100.10"
    assert res["card"]["after_yaml"] == "params:\n  ip_addresses: 203.0.113.99"


def test_a_fenced_noop_is_still_a_noop():
    res = emit_patch_proposal(id="p1", title="t", before_yaml=BEFORE,
                              after_yaml=BEFORE.replace("```yaml", "```"))
    assert res["ok"] is False and res["code"] == "noop_patch"


def test_integer_like_tiers_are_accepted():
    for tier in ("0", 0.0, " 3 "):
        res = emit_patch_proposal(id="p1", title="t", before_yaml=BEFORE,
                                  after_yaml=AFTER, tier=tier)
        assert res["ok"], (tier, res)
        assert res["card"]["tier"] == int(float(str(tier).strip()))


def test_a_non_numeric_tier_is_still_refused():
    for tier in ("high", -1, 1.5):
        res = emit_patch_proposal(id="p1", title="t", before_yaml=BEFORE,
                                  after_yaml=AFTER, tier=tier)
        assert res["ok"] is False and res["code"] == "bad_tier", tier
