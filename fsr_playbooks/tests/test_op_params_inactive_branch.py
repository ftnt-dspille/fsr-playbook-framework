"""A param from another conditional branch is named, not silently ignored.

Live: 16 sessions sent FortiGate `block_ip_new` an `ip` with
method="Quarantine Based", whose branch takes `ip_addresses`. `ip` IS a
parameter -- of the "Policy Based" branch -- so the unknown-param check passed
it, the op would have ignored it, and the refusal named only the missing
`ip_addresses`, never the key the model believed it had sent. Always
recovered, always one wasted round.

Seeded with its own schema (the real op's branch shape), so it does not depend
on what the local reference store happens to hold.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server import _shared as S

# (param_name, title, type, required, options_json, parent, condition_value)
_ROWS = [
    ("method", "Method", "select", 1, '["Policy Based", "Quarantine Based"]', None, None),
    ("ip_type", "IP Type", "select", 1, '["IPv4", "IPv6"]', "method", "Policy Based"),
    ("ip", "IP", "text", 1, None, "ip_type", "IPv4"),
    ("ip", "IP", "text", 1, None, "ip_type", "IPv6"),
    ("ip_addresses", "IP Addresses", "text", 1, None, "method", "Quarantine Based"),
    ("time_to_live", "TTL", "text", 0, None, "method", "Quarantine Based"),
]


@pytest.fixture(autouse=True)
def seeded(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE operation_params (connector_name, op_name, "
                 "param_name, title, type, required, options_json, "
                 "parent_param_name, condition_value)")
    conn.executemany("INSERT INTO operation_params VALUES ('fgt','block',?,?,?,?,?,?,?)",
                     _ROWS)

    class _Keep:                       # `with _db() as conn:` must not close it
        def __enter__(self):
            return conn

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(S, "_db", lambda: _Keep())


def _issues(params):
    out = S._validate_op_params("fgt", "block", params)
    return {i["param"]: i for i in (out or {}).get("issues", [])}


def test_the_other_branchs_param_is_named_with_its_branch():
    got = _issues({"method": "Quarantine Based", "ip": "198.51.100.7"})
    assert got["ip"]["problem"] == "inactive_branch"
    assert "ip_type='IPv4'" in got["ip"]["detail"]


def test_the_rename_is_spelled_out():
    got = _issues({"method": "Quarantine Based", "ip": "198.51.100.7"})
    assert "send your 'ip' value as 'ip_addresses'" in got["ip_addresses"]["detail"]
    assert got["ip_addresses"]["rename_from"] == "ip"


def test_with_several_strays_the_name_overlap_picks_the_rename():
    got = _issues({"method": "Quarantine Based", "ip": "198.51.100.7",
                   "ip_type": "IPv4"})
    assert got["ip_addresses"]["rename_from"] == "ip"


def test_a_complete_call_on_its_branch_passes():
    assert S._validate_op_params(
        "fgt", "block", {"method": "Quarantine Based",
                         "ip_addresses": "198.51.100.7"}) is None


def test_the_active_branch_is_not_flagged():
    got = _issues({"method": "Policy Based", "ip_type": "IPv4"})
    assert "ip_type" not in got                # it IS on the selected branch
    assert got["ip"]["problem"] == "missing_required"


def test_off_branch_params_do_not_block_a_complete_call():
    """Real payloads carry every branch's fields, blank. On a complete call an
    off-branch param explains nothing and must not refuse it."""
    assert S._validate_op_params(
        "fgt", "block", {"method": "Quarantine Based",
                         "ip_addresses": "198.51.100.7",
                         "ip_type": "IPv4", "ip": ""}) is None


# --- the same rename, said by the compiler for a playbook step --------------
# Live: edit_playbook refused a FortiGate block step's `ip` ten times with
# "only valid when ip_type=..." and the turn never found `ip_addresses`.

from fsr_playbooks.compiler.resolver.connector_args import renamed_param  # noqa: E402
from fsr_playbooks.compiler.resolver.normalizers import NormalizerMixin  # noqa: E402


class _Rules(NormalizerMixin):
    def operation_param_required_rules(self, connector, op):
        return [(name, parent, cond, bool(req), None)
                for name, _t, _ty, req, _o, parent, cond in _ROWS]


def _step_errors(params):
    errors = []
    _Rules()._check_conditional_required("fgt", "block", params, "steps[0]", errors)
    return errors


def test_a_step_with_the_other_branchs_param_is_told_the_rename():
    (err,) = _step_errors({"method": "Quarantine Based", "ip": "198.51.100.7"})
    assert err.path.endswith(".ip_addresses")
    assert "send your 'ip' value as 'ip_addresses'" in err.message
    assert err.suggestion == "rename 'ip' to 'ip_addresses'"


def test_a_step_missing_a_param_with_nothing_stray_gets_no_rename():
    (err,) = _step_errors({"method": "Quarantine Based"})
    assert "send your" not in err.message


def test_both_paths_pick_the_same_rename():
    for strays, want, pick in ((["ip"], "ip_addresses", "ip"),
                               (["ip", "ttl"], "ip_addresses", "ip"),
                               (["a", "b"], "ip_addresses", None)):
        assert renamed_param(strays, want) == pick
    got = _issues({"method": "Quarantine Based", "ip": "198.51.100.7"})
    assert got["ip_addresses"]["rename_from"] == renamed_param(["ip"], "ip_addresses")
