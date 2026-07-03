"""Gate models in llm/tool_models.py must mirror the REAL registered tool
signatures — a stale model silently rejects legitimate calls at dispatch.

Regression source: a live matrix run where get_record's model required
module+record_id(str) while the registered tool accepts iri / module+uuid /
module+record_id; every form the agent tried bounced (3 tool errors in one
turn, turn ended with no deliverable). The same drift class later hit the
emit_action_card / emit_choice_card models (required `title`, a field neither
registered tool accepts).
"""
import inspect

import pytest
from pydantic import ValidationError

from fsr_playbooks.llm.tool_models import (
    EmitActionCardArgs,
    EmitChoiceCardArgs,
    GetRecordArgs,
)
from fsr_playbooks.mcp_server import tools_emit


def test_iri_only_is_valid():
    GetRecordArgs(iri="/api/3/alerts/e035f3f3-4ff3-4036-a625-bc66d48846e5")


def test_module_plus_uuid_is_valid():
    GetRecordArgs(module="alerts", uuid="e035f3f3-4ff3-4036-a625-bc66d48846e5")


def test_module_plus_int_record_id_coerces():
    # The live agent passed record_id as a bare integer; the gate must
    # coerce, not bounce.
    args = GetRecordArgs(module="alerts", record_id=30369)
    assert args.record_id == "30369"


def test_no_identifier_rejected_with_example():
    with pytest.raises(ValidationError) as exc:
        GetRecordArgs(relationships=True)
    assert "get_record(iri=" in str(exc.value)


def test_module_alone_rejected():
    with pytest.raises(ValidationError):
        GetRecordArgs(module="alerts")


def test_real_signature_kwargs_all_accepted():
    # Full real signature: get_record(iri, module, uuid, relationships,
    # full, record_id) — the model must not reject any real param.
    GetRecordArgs(iri="/api/3/alerts/x", module="alerts", uuid="x",
                  relationships=False, full=True, record_id="1")


# --- emit_action_card ------------------------------------------------------
# The live agent staged a containment card with the REAL tool's args
# (id, connector, operation, summary, args) and the old gate bounced it with
# "title: Field required" — title is not a param the tool accepts. The gate
# must accept exactly the registered signature.


def test_emit_action_card_accepts_real_signature():
    # The exact shape a grounded containment card uses: the agent fills
    # args from find_containment_actions' params, editable_fields from the
    # params it wants the analyst to tweak.
    EmitActionCardArgs(
        id="block_c2_ip",
        connector="fortigate-firewall",
        operation="block_ip_new",
        summary="Block C2 IP 51.15.43.205 on FortiGate",
        args={"ip": "51.15.43.205", "ip_type": "IPv4"},
        editable_fields=["ip"],
    )


def test_emit_action_card_rejects_missing_required():
    with pytest.raises(ValidationError) as exc:
        EmitActionCardArgs(
            id="block_c2_ip", connector="fortigate-firewall",
            operation="block_ip_new", summary="Block C2 IP",
        )  # missing args + editable_fields
    msg = str(exc.value)
    assert "args" in msg and "editable_fields" in msg
    # The drift symptom must NOT recur: the gate must not demand `title`.
    assert "title" not in msg


# --- emit_choice_card ------------------------------------------------------


def test_emit_choice_card_accepts_real_signature():
    EmitChoiceCardArgs(
        id="branch",
        prompt="Contain now or build a playbook?",
        options=[{"label": "Contain", "value": "contain"},
                 {"label": "Build", "value": "build"}],
    )


def test_emit_choice_card_rejects_missing_required():
    with pytest.raises(ValidationError) as exc:
        EmitChoiceCardArgs(id="branch")  # missing prompt + options
    msg = str(exc.value)
    assert "prompt" in msg and "options" in msg
    assert "title" not in msg


# --- signature-sync guard --------------------------------------------------
# The guard that was MISSING when GetRecordArgs, then the emit_* card models,
# drifted from their registered signatures. Introspects each registered tool
# the gate covers (that lives in tools_emit) and asserts the gate declares
# every real required param — so a stale gate can't silently bounce a
# legitimate call again. Extend REAL_FNS as more gated tools are pinned down.


REAL_FNS = {
    "emit_action_card": tools_emit.emit_action_card,
    "emit_choice_card": tools_emit.emit_choice_card,
}


@pytest.mark.parametrize("tool_name", sorted(REAL_FNS))
def test_gate_model_covers_all_real_required_params(tool_name):
    from fsr_playbooks.llm import tool_models as tm

    fn = REAL_FNS[tool_name]
    model = tm.TOOL_MODELS[tool_name]
    sig = inspect.signature(fn)
    real_required = {
        p for p, v in sig.parameters.items()
        if v.default is inspect.Parameter.empty
        and v.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                       inspect.Parameter.KEYWORD_ONLY)
    }
    declared = set(model.model_fields)
    missing = real_required - declared
    assert not missing, (
        f"{tool_name}: gate {model.__name__} is missing required real params "
        f"{sorted(missing)}; declared={sorted(declared)}"
    )

