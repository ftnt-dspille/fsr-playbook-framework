"""A state-changing op that reports success while acting on nothing must fail.

Containment ops report per-target OUTCOME BUCKETS -- one list per thing that
could happen, every target landing in exactly one. FortiGate's `block_ip_new`
returns `{already_blocked, newly_blocked, error_with_block, vdom_not_exist}`.
All four empty means the target list it iterated was empty: nothing attempted,
nothing errored, envelope still `status: Success`.

Live-verified on 8.0.0: passing the Policy branch's `ip` where the Quarantine
branch wants `ip_addresses` returns exactly that, with the appliance's ban list
unchanged; the correct param returns `{"newly_blocked": ["<ip>"]}` and really
blocks. The platform does not catch it -- required-field validation reaches
top-level params but not the conditional children under a param's `onchange`.

The P2 stake: gated correctly, approved by a human, reported as done, nobody
contained. In a compiled playbook the value is usually a Jinja ref, so an
upstream enrichment step that returns no rows produces this on its own.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_execution import _acted_on_nothing

BLOCK_IP_BUCKETS = ["already_blocked", "newly_blocked", "error_with_block",
                    "vdom_not_exist"]


def test_all_empty_buckets_is_a_no_op():
    data = {k: [] for k in BLOCK_IP_BUCKETS}
    reason = _acted_on_nothing(data)
    assert reason is not None
    # The reason names the buckets so the failure message is self-explaining.
    for k in BLOCK_IP_BUCKETS:
        assert k in reason


def test_one_populated_bucket_is_a_real_action():
    data = {k: [] for k in BLOCK_IP_BUCKETS}
    data["newly_blocked"] = ["203.0.113.9"]
    assert _acted_on_nothing(data) is None


def test_already_blocked_counts_as_acted():
    """Re-blocking a known-bad IP is a legitimate success, not a no-op."""
    data = {k: [] for k in BLOCK_IP_BUCKETS}
    data["already_blocked"] = ["203.0.113.9"]
    assert _acted_on_nothing(data) is None


def test_errored_bucket_is_not_a_no_op():
    """It did attempt the target; the execute path reports the error itself."""
    data = {k: [] for k in BLOCK_IP_BUCKETS}
    data["error_with_block"] = ["203.0.113.9"]
    assert _acted_on_nothing(data) is None


def test_guard_is_narrow():
    """Only the bucket-envelope shape qualifies. Plenty of ops legitimately
    return nothing, and this must never fire on one of those."""
    assert _acted_on_nothing([]) is None                    # bare empty list
    assert _acted_on_nothing({}) is None                    # empty dict
    assert _acted_on_nothing({"results": []}) is None       # single-key result
    assert _acted_on_nothing(None) is None
    assert _acted_on_nothing("") is None
    # Mixed types are not an outcome-bucket envelope.
    assert _acted_on_nothing({"results": [], "status": "ok"}) is None
    assert _acted_on_nothing({"results": [], "count": 0}) is None
