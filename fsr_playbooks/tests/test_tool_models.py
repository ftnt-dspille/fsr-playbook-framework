"""Gate models in llm/tool_models.py must mirror the REAL registered tool
signatures — a stale model silently rejects legitimate calls at dispatch.

Regression source: a live matrix run where get_record's model required
module+record_id(str) while the registered tool accepts iri / module+uuid /
module+record_id; every form the agent tried bounced (3 tool errors in one
turn, turn ended with no deliverable).
"""
import pytest
from pydantic import ValidationError

from fsr_playbooks.llm.tool_models import GetRecordArgs


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
