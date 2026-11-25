"""FMG writes / installs and FortiGate execute_command must need approval.

The catalog files these ops under `investigation` and op_safety is empty, so
they used to resolve to tier 2 (auto-run, no card). Reads stay auto-run.
"""
import pytest

from fsr_playbooks.llm.tools import _resolve_tier, _tier_for_run_op

FMG = "fortinet-fortimanager-json-rpc"


@pytest.mark.parametrize("conn,op", [
    (FMG, "json_rpc_execute"), (FMG, "json_rpc_set"), (FMG, "json_rpc_add"),
    (FMG, "json_rpc_delete"), (FMG, "json_rpc_freeform"), (FMG, "json_rpc_gui"),
    ("fortinet-fortimanager", "install_policy"),
    ("fortinet-fortimanager", "reinstall_policy"),
    ("fortigate-firewall", "execute_command"),
    ("fortinet-fortigate", "execute_command"),
])
def test_network_writes_require_approval(conn, op, monkeypatch):
    # A warmed box catalogs these ops as `investigation` with no op_safety row
    # (the packaged DB does not carry the FMG connectors at all): simulate it.
    import fsr_playbooks.llm.tools as T
    monkeypatch.setattr(T, "_lookup_op_metadata", lambda c, o: (None, "investigation"))
    assert _tier_for_run_op({"connector": conn, "op": op}) >= 3
    assert _resolve_tier("run_op", {"connector": conn, "op": op}) >= 3


def test_fmg_read_is_not_gated_by_the_write_rule():
    # json_rpc_get keeps whatever tier the catalog gives it (the fmg_device
    # tool calls it internally, tier 1); the write rule must not touch it.
    from fsr_playbooks.llm.tools import _is_net_write_op
    assert not _is_net_write_op({"connector": FMG, "op": "json_rpc_get"})
    assert not _is_net_write_op({"connector": "fortigatev2",
                                 "op": "execute_api_request",
                                 "params": {"method": "GET"}})


def test_fortigate_rest_gated_only_for_writes():
    base = {"connector": "fortigatev2", "op": "execute_api_request"}
    assert _tier_for_run_op({**base, "params": {"method": "POST"}}) >= 3
