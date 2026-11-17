"""Multi-branch containment ops are steered toward the self-contained branch.

A branch can be valid in the schema and impossible to run on THIS device,
because it depends on objects somebody provisioned by hand. The agent cannot
see that from a schema, so it picks on vibes and fills the required params with
plausible placeholders -- staging a containment that reads real and cannot run.
That is worse than staging nothing: the analyst approves a block that never
happens.

Live case. `fortigate-firewall.block_ip_new` Policy Based needs a deny policy
AND an IPv4 address group that already exist, and the connector resolves the
group THROUGH the policy name. On a firewall enforcing an external threat feed
(zero address groups), the agent staged `ip_block_policy: default_policy` /
`ip_group_name: default_group` -- both invented. Quarantine Based needs only the
IP and a TTL, so it works anywhere.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import tools_connector_discovery as D


def test_the_fortigate_ip_block_prefers_quarantine():
    pref = D._PREFERRED_CONTAINMENT_PARAMS[("fortigate-firewall", "block_ip_new")]
    assert pref["params"] == {"method": "Quarantine Based"}


def test_unblock_mirrors_block():
    """An IP banned on the quarantine list is removed from the quarantine list.
    A block and its undo that disagree on branch leave the analyst unable to
    reverse their own containment."""
    block = D._PREFERRED_CONTAINMENT_PARAMS[("fortigate-firewall", "block_ip_new")]
    unblock = D._PREFERRED_CONTAINMENT_PARAMS[("fortigate-firewall", "unblock_ip")]
    assert block["params"]["method"] == unblock["params"]["method"]


def test_the_deprecated_alias_gets_the_same_steer():
    """A box still exposing the old `block_ip` has the same two branches and the
    same trap; a preference that only covers the new name silently stops
    applying on the boxes most likely to need it."""
    assert ("fortigate-firewall", "block_ip") in D._PREFERRED_CONTAINMENT_PARAMS


def test_every_preference_says_why():
    """The reason is the deliverable. A bare value looks like a default someone
    can 'improve' -- the why is what stops the next reader from reverting it,
    and it is what the agent is given to decide whether an explicit analyst
    request should override it."""
    for key, pref in D._PREFERRED_CONTAINMENT_PARAMS.items():
        assert pref.get("params"), f"{key} has no params"
        why = pref.get("why") or ""
        assert len(why) > 40, f"{key} has no usable reason: {why!r}"


def test_preferences_name_real_ops():
    """A preference for an op that does not exist is dead config that reads as
    coverage. Every key must be an op the store actually carries."""
    import sqlite3
    with sqlite3.connect(f"file:{D.DB_PATH}?mode=ro", uri=True) as conn:
        for connector, op in D._PREFERRED_CONTAINMENT_PARAMS:
            row = conn.execute(
                "SELECT 1 FROM operations WHERE connector_name=? AND op_name=?",
                (connector, op)).fetchone()
            assert row, f"{connector}.{op} is not in the reference store"


def test_the_preferred_method_is_a_value_the_op_accepts():
    """The steer has to survive the arg gate. A preferred value that is not one
    of the select's options would turn a guessed-params failure into a
    bad_params failure -- a different way to stage nothing."""
    import sqlite3
    with sqlite3.connect(f"file:{D.DB_PATH}?mode=ro", uri=True) as conn:
        for (connector, op), pref in D._PREFERRED_CONTAINMENT_PARAMS.items():
            sig = {p["name"]: p for p in D._param_sig(conn, connector, op)}
            for name, value in pref["params"].items():
                assert name in sig, f"{connector}.{op}: no param {name!r}"
                options = sig[name].get("options")
                if options:
                    assert value in options, (
                        f"{connector}.{op}: {name}={value!r} is not one of "
                        f"{options}")
