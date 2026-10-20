"""compose_playbook: the model declares a typed plan, code compiles the YAML.

The point of E6 is that the model never authors free-form YAML, so the failure
surface at the close (bad fences, stepType typos, orphan steps, guessed jinja
paths) cannot occur, and a wrong connector param is caught deterministically
instead of shipped. These tests pin the compile, the wiring translation, the
honest-failure signal, the containment gate and the registration.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import compose_playbook as _cp

compose_playbook = getattr(_cp, "fn", _cp)


def _good_plan():
    return [
        {"kind": "connector", "name": "Query Ip", "connector": "virustotal",
         "operation": "query_ip",
         "inputs": {"ip": {"from_step": "__input__", "output": "sourceIp"}}},
        {"kind": "decision", "name": "Malicious",
         "conditions": [{"condition": "{{ vars.steps.Query_Ip.data.malicious > 0 }}",
                         "next": "Block Ip"}],
         "default": ""},
        {"kind": "connector", "name": "Block Ip", "connector": "fortigate-firewall",
         "operation": "block_ip_new",
         # `method` is the selector that makes `ip_addresses` a visible param.
         "inputs": {"method": "Quarantine Based",
                    "ip_addresses": {"from_step": "Query Ip",
                                     "output": "network_addr"}}},
    ]


def test_typed_plan_compiles_clean_and_wires_without_authored_yaml():
    r = compose_playbook(steps=_good_plan(), name="Block Malicious IP",
                         module="alerts")
    assert r["ok"] is True
    assert r["compile_summary"]["ok"] is True  # imports clean
    assert not r["static_errors"]
    y = r["yaml"]
    # The trigger-record reference was written for the model, correctly.
    assert "vars.input.records[0].sourceIp" in y
    # A cross-step reference resolved to the source step's data envelope.
    assert "vars.steps.Query_Ip.data.network_addr" in y
    # It is a connector step, not a hand-typed fence.
    assert "operation: query_ip" in y


def test_wrong_connector_param_is_caught_not_shipped():
    plan = _good_plan()
    # fortigate block takes `ip_addresses`; a plausible wrong name must be caught.
    plan[2]["inputs"] = {"ip_address": {"from_step": "Query Ip",
                                        "output": "network_addr"}}
    r = compose_playbook(steps=plan, name="P", module="alerts")
    errs = r["compile_summary"].get("errors") or []
    assert any("ip_address" in (e.get("message") or "") for e in errs)
    # and it points at the right name instead of silently dropping it.
    assert any("ip_addresses" in str(e.get("suggestions") or e.get("suggestion"))
               for e in errs)


def test_param_hidden_without_its_selector_is_surfaced_not_dropped():
    # block_ip_new hides `ip_addresses` until `method` is set; omitting method
    # must surface the dropped param in `pruned`, never silently lose it.
    plan = [{"kind": "connector", "name": "Block Ip",
             "connector": "fortigate-firewall", "operation": "block_ip_new",
             "inputs": {"ip_addresses": {"from_step": "__input__",
                                         "output": "sourceIp"}}}]
    r = compose_playbook(steps=plan, name="P", module="alerts")
    assert "ip_addresses" in r["pruned"].get("Block Ip", [])


def test_containment_op_is_gated_behind_a_confirm():
    y = compose_playbook(steps=_good_plan(), name="P", module="alerts")["yaml"]
    # The compiler inserts a human confirm before a containment op.
    assert "manual_input" in y
    assert "Confirm Containment" in y


def test_unknown_kind_is_a_plan_error():
    r = compose_playbook(steps=[{"kind": "frobnicate", "name": "X"}])
    assert r["ok"] is False
    assert r["code"] == "bad_plan"
    assert any("frobnicate" in e for e in r["errors"])


def test_connector_step_needs_connector_and_operation():
    r = compose_playbook(steps=[{"kind": "connector", "name": "X"}])
    assert r["ok"] is False and r["code"] == "bad_plan"


def test_empty_steps_is_a_clear_error():
    assert compose_playbook(steps=[])["code"] == "no_steps"


def test_registered_tier0_build_only_not_triage():
    from fsr_playbooks.llm import intents, tools
    assert "compose_playbook" in tools.SAFE_TOOLS
    assert tools.TOOL_TIERS["compose_playbook"] == 0
    assert "compose_playbook" in intents.BUILD_ONLY_TOOLS
    build = {t["name"] for t in intents.tools_for_intent("build")}
    triage = {t["name"] for t in intents.tools_for_intent("triage")}
    assert "compose_playbook" in build and "compose_playbook" not in triage


def test_for_each_emits_a_step_modifier_not_a_loop_step_type():
    # The model mis-modeling `for_each` as a step TYPE with nested steps was a
    # live failure (UNKNOWN_STEP_TYPE). In the plan it is a per-step modifier:
    # the looped step keeps its real type, and `item` is wired structurally so
    # the model never types the jinja list path.
    plan = [
        {"kind": "set_variable", "name": "Stage IPs",
         "values": {"ip_list": "{{ vars.input.records[0].iPAddresses }}"}},
        {"kind": "connector", "name": "Check IP Reputation",
         "connector": "virustotal", "operation": "query_ip",
         "inputs": {"ip": "{{ vars.item }}"},
         "for_each": {"item": {"from_step": "Stage IPs", "output": "ip_list"},
                      "parallel": False}},
    ]
    r = compose_playbook(steps=plan, name="Loop VT Over IPs", module="alerts")
    assert r["ok"] is True
    assert r["compile_summary"]["ok"] is True
    y = r["yaml"]
    # for_each is a key on the connector step, and its type is still connector.
    assert "for_each:" in y
    assert "type: connector" in y
    assert "type: for_each" not in y  # never a standalone loop step type
    # the item list was rendered to the one correct vars.steps path.
    assert "{{ vars.steps.Stage_IPs.ip_list }}" in y


def test_for_each_on_a_non_loopable_kind_is_an_honest_plan_error():
    plan = [
        {"kind": "decision", "name": "Branch",
         "conditions": [{"condition": "{{ true }}", "next": ""}], "default": "",
         "for_each": {"item": "{{ vars.x }}"}},
    ]
    r = compose_playbook(steps=plan, name="Bad Loop", module="alerts")
    assert r["ok"] is False
    assert r["code"] == "bad_plan"
    assert any("for_each" in e for e in r["errors"])
