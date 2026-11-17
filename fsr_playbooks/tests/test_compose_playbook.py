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


def test_record_action_kind_loops_create_record_over_a_staged_list():
    # for_each_loop shape: stage a list, then create one record per element.
    # A record action is its own FSR step type (create_record), reached via the
    # `record` plan kind + `action`, and it loops with the same for_each modifier.
    plan = [
        {"kind": "set_variable", "name": "Build Alert List",
         "values": {"alerts_to_create": [{"name": "A", "severity": "High"}]}},
        {"kind": "record", "name": "Create Alert Per Item", "action": "create",
         "module": "alerts", "operation": "Create",
         "fields": {"name": "{{ vars.item.name }}",
                    "severity": "{{ vars.item.severity }}"},
         "for_each": {"item": {"from_step": "Build Alert List",
                               "output": "alerts_to_create"}}},
    ]
    r = compose_playbook(steps=plan, name="Create Alerts From Static List",
                         module="alerts")
    assert r["ok"] is True
    assert r["compile_summary"]["ok"] is True
    y = r["yaml"]
    assert "type: create_record" in y
    assert "for_each:" in y
    assert "{{ vars.steps.Build_Alert_List.alerts_to_create }}" in y


def test_record_kind_without_action_is_an_honest_plan_error():
    r = compose_playbook(
        steps=[{"kind": "record", "name": "X", "module": "alerts"}],
        name="Bad Record", module="alerts")
    assert r["ok"] is False
    assert r["code"] == "bad_plan"
    assert any("action" in e for e in r["errors"])


def _one(step):
    return compose_playbook(steps=[step], name="P", module="alerts")


def test_set_variable_vars_alias_is_wired_not_dropped():
    r = _one({"kind": "set_variable", "name": "Stage",
              "vars": {"marker": "hello-marker"}})
    assert r["ok"] is True
    assert "hello-marker" in r["yaml"]


def test_connector_params_alias_and_config_are_read():
    r = _one({"kind": "connector", "name": "Q", "connector": "virustotal",
              "operation": "query_ip", "config": "my-config-marker",
              "params": {"ip": "1.2.3.4"}})
    assert r["ok"] is True
    assert "1.2.3.4" in r["yaml"]
    assert "my-config-marker" in r["yaml"]


def test_unknown_step_key_fails_loudly_with_accepted_keys():
    r = _one({"kind": "set_variable", "name": "S", "variables": {"a": "b"}})
    assert r["ok"] is False and r["code"] == "bad_plan"
    msg = " ".join(r["errors"])
    assert "variables" in msg and "vars" in msg and "values" in msg


def test_both_alias_and_canonical_is_rejected():
    r = _one({"kind": "set_variable", "name": "S", "vars": {"a": "b"},
              "values": {"c": "d"}})
    assert r["ok"] is False


# --- record steps: the live Sonnet turn that burned ~12 compose retries --------
# The model wanted "update the triggering alert". compose's record step had no
# key for the update target, so it tried `record`, `inputs`, `query`, `fields.record`
# in turn; some of those returned ok:true with YAML the compiler then rejected.

_SET_LOOKBACK = {"kind": "set_variable", "name": "Set Lookback",
                 "vars": {"lookback_hours": 24}}


def _rec(**kw):
    return {"kind": "record", "name": "Comment Alert", "action": "update",
            "module": "alerts", **kw}


def test_update_record_targets_the_trigger_record_first_time():
    r = compose_playbook(
        steps=[_SET_LOOKBACK,
               _rec(record={"from_step": "__input__", "output": "@id"},
                    fields={"comments": "seen"})],
        name="Stamp", module="alerts")
    assert r["ok"] is True, r
    assert r["compile_summary"]["ok"] is True
    # `@id` is not a jinja identifier: bracketed, and no `operation: Create`
    # leaks onto an update.
    assert "record: '{{ vars.input.records[0][''@id''] }}'" in r["yaml"]
    assert "operation: Create" not in r["yaml"]


def test_failed_record_shapes_from_the_session_name_the_exact_fix():
    wrong = [
        _rec(query={"field": "id", "value": "1"}, fields={"comments": "x"}),
        _rec(inputs={"record": {"from_step": "__input__", "output": "@id"}},
             fields={"comments": "x"}),
        _rec(fields={"comments": "x",
                     "record": {"from_step": "__input__", "output": "@id"}}),
        _rec(fields={"comments": "x"}),            # no target at all
    ]
    for step in wrong:
        r = compose_playbook(steps=[step], name="P", module="alerts")
        assert r["ok"] is False and r["code"] == "bad_plan", step
        text = " ".join(r["errors"])
        # the corrected example for THIS step kind, with the `record` key
        assert '"action": "update"' in text and '"record":' in text, text
        assert r["message"] == "; ".join(r["errors"])


def test_find_then_update_wires_the_first_match_and_filters_resolve():
    r = compose_playbook(
        steps=[{"kind": "record", "name": "Find This Alert", "action": "find",
                "module": "alerts",
                "query": [{"field": "id", "operator": "eq",
                           "value": {"from_step": "__input__",
                                     "output": "id"}}]},   # list `query` = filters
               _rec(record={"from_step": "Find This Alert", "output": "@id"},
                    fields={"comments": "seen"})],
        name="Stamp", module="alerts")
    assert r["ok"] is True, r
    y = r["yaml"]
    assert "from_step" not in y                       # no raw ref leaked
    assert "{{ vars.input.records[0].id }}" in y
    assert "{{ vars.steps.Find_This_Alert[0][''@id''] }}" in y  # YAML-quoted
    assert "operation: Create" not in y


def test_compile_failure_is_not_reported_as_ok():
    # an unknown connector compiles to YAML the compiler rejects: one honest
    # failure with the text, not ok:true with the verdict in compile_summary
    r = compose_playbook(
        steps=[{"kind": "connector", "name": "X", "connector": "no-such-conn",
                "operation": "nope"}],
        name="P", module="alerts")
    assert r["ok"] is False and r["code"] == "compile_failed"
    assert "no-such-conn" in r["message"] and r["yaml"]


def test_tool_description_is_built_from_the_record_shapes_table():
    from fsr_playbooks.mcp_server import tools_compose as tc
    doc = tc.compose_playbook.__doc__ if callable(tc.compose_playbook) \
        else tc.compose_playbook.fn.__doc__
    doc = doc or getattr(tc.compose_playbook, "description", "")
    for action, spec in tc._RECORD_SHAPES.items():
        assert f"action `{action}`" in doc
        for key in list(spec["required"]) + list(spec["optional"]):
            assert key in doc


# -- the plan's own vocabulary (what a model sends right after plan_playbook) --

def _plan_vocabulary():
    """The same playbook as a model writes it after `plan_playbook`: `type`
    for `kind`, a `start` step, YAML step type names, `purpose` beside it."""
    return [
        {"type": "start", "name": "Start", "module": "alerts",
         "purpose": "Trigger on the alert"},
        {"type": "connector", "name": "Query Ip", "connector": "virustotal",
         "operation": "query_ip", "purpose": "look up the source IP",
         "inputs": {"ip": {"from_step": "__input__", "output": "sourceIp"}}},
        {"type": "set_variable", "name": "Build Note",
         "inputs": {"note": {"from_step": "Query Ip", "output": "reputation"}}},
        {"type": "update_record", "name": "Stamp Alert", "module": "alerts",
         "record": {"from_step": "__input__", "output": "@id"},
         "fields": {"description": {"from_step": "Build Note", "output": "note"}}},
    ]


def _canonical_twin():
    return [
        {"kind": "connector", "name": "Query Ip", "connector": "virustotal",
         "operation": "query_ip",
         "inputs": {"ip": {"from_step": "__input__", "output": "sourceIp"}}},
        {"kind": "set_variable", "name": "Build Note",
         "values": {"note": {"from_step": "Query Ip", "output": "reputation"}}},
        {"kind": "record", "action": "update", "name": "Stamp Alert",
         "module": "alerts",
         "record": {"from_step": "__input__", "output": "@id"},
         "fields": {"description": {"from_step": "Build Note", "output": "note"}}},
    ]


def test_plan_vocabulary_compiles_to_the_same_playbook_as_the_canonical_plan():
    """Each of these spellings was a `bad_plan` and a wasted round. The plan
    means one thing; it must compile to the same YAML however it is spelled."""
    spoken = compose_playbook(steps=_plan_vocabulary(), name="P")
    canon = compose_playbook(steps=_canonical_twin(), name="P", module="alerts")
    assert canon["ok"] is True, canon
    assert spoken["ok"] is True, spoken.get("message")
    assert spoken["yaml"] == canon["yaml"]


def test_absorbed_start_step_is_reported_not_silent():
    r = compose_playbook(steps=_plan_vocabulary(), name="P")
    assert "manual action on alerts" in r["start"]
    # The canonical plan had no start step, so there is nothing to report.
    assert "start" not in compose_playbook(steps=_canonical_twin(), name="P",
                                           module="alerts")


def test_explicit_module_wins_over_the_start_steps_module():
    plan = _plan_vocabulary()
    plan[0]["module"] = "incidents"
    r = compose_playbook(steps=plan, name="P", module="alerts")
    assert "manual action on alerts" in r["start"]


def test_kind_spelled_as_a_yaml_step_type_is_read_as_the_record_action():
    plan = [{"kind": "find_record", "name": "Find", "module": "alerts",
             "filters": [{"field": "status", "operator": "eq", "value": "Open"}]}]
    r = compose_playbook(steps=plan, name="P", module="alerts")
    assert r["ok"] is True, r.get("message")
    assert "find_record" in r["yaml"]


def test_a_plan_of_only_a_start_step_says_what_is_missing():
    r = compose_playbook(steps=[{"type": "start", "module": "alerts"}])
    assert r["ok"] is False and r["code"] == "no_steps"
    assert "only a start step" in r["message"]


def test_an_unknown_type_is_still_rejected_with_the_kinds():
    r = compose_playbook(steps=[{"type": "teleport", "name": "X"}])
    assert r["ok"] is False and r["code"] == "bad_plan"
    assert "unknown kind 'teleport'" in r["message"] and "connector" in r["message"]


# -- the trigger: a start step in the plan picks how the playbook is started --

import pytest  # noqa: E402
import yaml as _yaml  # noqa: E402


def _start_of(r):
    steps = _yaml.safe_load(r["yaml"])["playbooks"][0]["steps"]
    return steps[0]


@pytest.mark.parametrize("word,says", [
    ("start_on_create", "runs when a record in alerts is created"),
    ("start_on_update", "runs when a record in alerts is updated"),
    ("start_on_delete", "runs when a record in alerts is deleted"),
])
def test_a_record_event_start_step_sets_the_trigger(word, says):
    """"Run when an alert is created" was a bad_plan: the model recomposed
    without the trigger and hand-edited the YAML to put it back."""
    plan = [{"type": word, "module": "alerts"}] + _canonical_twin()
    r = compose_playbook(steps=plan, name="P")
    assert r["ok"] is True, r.get("message")
    assert r["compile_summary"]["ok"] is True, r["compile_summary"]
    start = _start_of(r)
    assert (start["type"], start["module"]) == (word, "alerts")
    assert start["next"] == "Query Ip"
    assert r["start"] == says


def test_a_plain_start_step_keeps_the_manual_trigger():
    r = compose_playbook(steps=_plan_vocabulary(), name="P")
    assert _start_of(r)["type"] == "start"


def test_a_record_event_trigger_without_a_module_is_refused():
    plan = [{"type": "start_on_create"}] + _canonical_twin()
    r = compose_playbook(steps=plan, name="P")
    assert r["ok"] is False and r["code"] == "bad_plan"
    assert "needs the module it watches" in r["message"]


# -- `next` on a plan step ------------------------------------------------

def _with_next(plan, nexts):
    return [{**s, **({"next": n} if n is not ... else {})}
            for s, n in zip(plan, nexts)]


def test_next_naming_the_following_step_is_the_order_already_given():
    """YAML steps carry `next`, so a model writes it in the plan. It was an
    unknown-key bad_plan on every step."""
    canon = compose_playbook(steps=_canonical_twin(), name="P", module="alerts")
    for nexts in (("Build Note", "Stamp Alert", ...),      # exact names
                  ("build_note", "stamp alert", None),      # spelled loosely, last = None
                  ("Build Note", "Stamp Alert", "End")):    # a `next` on the last step
        r = compose_playbook(steps=_with_next(_canonical_twin(), nexts),
                             name="P", module="alerts")
        assert r["ok"] is True, (nexts, r.get("message"))
        assert r["yaml"] == canon["yaml"], nexts


def test_next_pointing_elsewhere_is_still_refused():
    """A jump is a branch; dropping it would silently build a different flow."""
    plan = _with_next(_canonical_twin(), ("Stamp Alert", ..., ...))
    r = compose_playbook(steps=plan, name="P", module="alerts")
    assert r["ok"] is False and r["code"] == "bad_plan"
    assert "unknown key(s) ['next']" in r["message"]


# --- decision branches that end the playbook -------------------------------
# The compiler chains steps in plan order, so a decision's "otherwise" fell
# through to the next step: "only when Critical" built a playbook that ran
# either way. A model that tried to say "otherwise stop" with an `end` step
# was refused, and without one the branch target matched nothing.

_OPEN = [{"field": "status", "operator": "eq", "value": "Open"}]
_WHEN = "{{ vars.input.records[0].severity.itemValue == 'Critical' }}"


def _gate(conditions, **extra):
    return {"kind": "decision", "name": "Is Critical",
            "conditions": conditions, **extra}


def _gated_plan(decision, *tail):
    return [decision,
            {"kind": "record", "action": "find", "name": "Find Alerts",
             "module": "alerts", "filters": _OPEN},
            {"kind": "set_variable", "name": "Note", "values": {"m": "x"}},
            *tail]


def _steps_of(r):
    steps = _yaml.safe_load(r["yaml"])["playbooks"][0]["steps"]
    return {s["name"]: s for s in steps}


_YES = {"display": "Yes", "when": _WHEN, "next": "Find Alerts"}


@pytest.mark.parametrize("decision, tail", [
    (_gate([_YES]), ()),                                   # no otherwise given
    (_gate([_YES], default="End"), ()),                    # named, no end step
    (_gate([_YES], default="Done"),
     ({"type": "end", "name": "Done"},)),                  # an end step
    (_gate([_YES], default="Stop Here"),
     ({"kind": "stop", "name": "Stop Here"},)),
    (_gate([_YES, {"display": "No", "next": "End"}]), ()),  # else as a branch
    (_gate([_YES, {"display": "No"}]), ()),
])
def test_otherwise_ends_the_playbook_instead_of_running_the_next_step(
        decision, tail):
    r = compose_playbook(steps=_gated_plan(decision, *tail), name="P",
                         module="incidents")
    assert r["ok"], r.get("message")
    steps = _steps_of(r)
    dec = steps["Is Critical"]
    end = [s for s in steps.values() if s["type"] == "end"]
    assert len(end) == 1
    assert dec["default"] == end[0]["name"]
    assert "next" not in dec, "a fall-through next is the else branch"
    assert [c["next"] for c in dec["conditions"]] == ["Find Alerts"]
    assert r["branches"] == {"Is Critical": {
        "Yes": "Find Alerts", "otherwise": "ends the playbook"}}


def test_an_otherwise_that_names_a_real_step_is_kept():
    r = compose_playbook(steps=_gated_plan(_gate([_YES], default="Note")),
                         name="P", module="incidents")
    assert r["ok"], r.get("message")
    steps = _steps_of(r)
    assert steps["Is Critical"]["default"] == "Note"
    assert not [s for s in steps.values() if s["type"] == "end"]
    assert r["branches"]["Is Critical"]["otherwise"] == "Note"


def test_a_step_can_end_its_branch_so_the_else_path_does_not_run_after_it():
    plan = [_gate([_YES], default="Note"),
            {"kind": "record", "action": "find", "name": "Find Alerts",
             "module": "alerts", "filters": _OPEN, "next": "End"},
            {"kind": "set_variable", "name": "Note", "values": {"m": "x"}}]
    r = compose_playbook(steps=plan, name="P", module="incidents")
    assert r["ok"], r.get("message")
    steps = _steps_of(r)
    assert steps[steps["Find Alerts"]["next"]]["type"] == "end"
    assert "next" not in steps["Note"]


def test_a_step_really_named_end_is_a_step_not_an_ending():
    plan = [_gate([_YES], default="End"),
            {"kind": "record", "action": "find", "name": "Find Alerts",
             "module": "alerts", "filters": _OPEN},
            {"kind": "set_variable", "name": "End", "values": {"m": "x"}}]
    r = compose_playbook(steps=plan, name="P", module="incidents")
    assert r["ok"], r.get("message")
    steps = _steps_of(r)
    assert steps["Is Critical"]["default"] == "End"
    assert steps["End"]["type"] == "set_variable"


def test_a_plan_without_a_decision_gets_no_end_step_or_branches():
    r = compose_playbook(steps=_canonical_twin(), name="P", module="alerts")
    assert r["ok"] and "branches" not in r
    assert not [s for s in _steps_of(r).values() if s["type"] == "end"]


def test_a_decision_with_invented_keys_is_shown_the_shape():
    r = compose_playbook(steps=_gated_plan(
        {"kind": "decision", "name": "Is Critical", "condition": _WHEN,
         "next_if_true": "Find Alerts", "next_if_false": "End"}),
        name="P", module="incidents")
    assert r["ok"] is False and r["code"] == "bad_plan"
    assert '"conditions": [{"display"' in r["message"]


def test_the_description_states_the_decision_shape():
    from fsr_playbooks.mcp_server import tools_compose as tc
    assert "{display, when, next}" in tc._COMPOSE_DOC


# --- what the in-app model is actually sent --------------------------------
# The description is cut to its first paragraphs, so the step shapes written
# in the docstring never reached the model: it was sent `steps: array of
# object`. These read the registry entry the agent loop advertises, not the
# docstring.

def _sent():
    import json as _json

    from fsr_playbooks.llm.tools import REGISTRY
    spec = REGISTRY["compose_playbook"]
    return spec, _json.dumps(spec.input_schema)


def test_the_model_is_sent_every_kind_and_every_accepted_key():
    from fsr_playbooks.mcp_server import tools_compose as tc
    spec, sent = _sent()
    steps = spec.input_schema["properties"]["steps"]
    props = steps["items"]["properties"]
    for kind in list(tc._KIND_TO_SKILL) + ["record"]:
        assert kind in props["kind"]["description"]
    accepted = set().union(*tc._STEP_KEYS.values()) | tc._COMMON_STEP_KEYS
    # `params` and `vars` are tolerated aliases, not the one advertised way.
    missing = accepted - {"params", "vars"} - set(props)
    assert not missing, f"accepted by the validator, never advertised: {missing}"
    for action, shape in tc._RECORD_SHAPES.items():
        for key in shape["required"]:
            assert f"{key} (required)" in steps["description"]
        assert action in props["action"]["enum"]


def test_the_model_is_sent_the_decision_branch_shape_and_the_ref_form():
    spec, sent = _sent()
    cond = (spec.input_schema["properties"]["steps"]["items"]["properties"]
            ["conditions"]["items"]["properties"])
    assert set(cond) == {"display", "when", "next"}
    assert "from_step" in sent and "__input__" in sent
    assert "start_on_update" in sent


def test_plans_the_tool_accepts_are_not_refused_by_the_argument_gate():
    """The schema is enforced before the tool runs. It must describe the
    shape without refusing the plan-vocabulary spellings the tool reads."""
    from fsr_playbooks.llm.tools import dispatch
    plans = [
        _canonical_twin(),
        _plan_vocabulary(),
        _gated_plan(_gate([_YES, {"display": "No"}])),
        _gated_plan(_gate([_YES], default="Done"),
                    {"type": "end", "name": "Done"}),
    ]
    for plan in plans:
        r = dispatch("compose_playbook",
                     {"steps": plan, "name": "P", "module": "alerts"})
        assert isinstance(r, dict) and r.get("ok"), (plan, r)


# --- manual_input form fields ----------------------------------------------
# Found by replaying real stored compose calls: the tool advertised `fields`
# for a manual_input step, and the compiler rejected every plan that used it.

def _ask(**extra):
    return [{"kind": "manual_input", "name": "Ask", "message": "Why?", **extra},
            {"kind": "set_variable", "name": "Note", "values": {"m": "x"}}]


def test_manual_input_form_fields_reach_the_playbook():
    fields = [{"name": "reason", "type": "text", "label": "Reason"}]
    r = compose_playbook(steps=_ask(options=["Go"], fields=fields),
                         name="P", module="alerts")
    assert r["ok"], r.get("message")
    assert _steps_of(r)["Ask"]["inputs"] == fields


def test_a_manual_input_plan_with_form_fields_passes_the_argument_gate():
    from fsr_playbooks.llm.tools import dispatch
    r = dispatch("compose_playbook", {
        "steps": _ask(fields=[{"name": "reason", "type": "text",
                               "label": "Reason"}]),
        "name": "P", "module": "alerts"})
    assert isinstance(r, dict) and r.get("ok"), r
