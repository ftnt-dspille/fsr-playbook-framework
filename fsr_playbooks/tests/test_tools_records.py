"""create_record / update_record: the host write gate + transport shaping.

No box -- a fake `_shared._live_client()` + captured requests. The invariants:
  - No host write policy => `write_not_permitted` (no client call made).
  - Policy present but module out of scope => `write_not_permitted`.
  - Policy permits => POST/PUT to `/api/3/<module>[/<uuid>]`, result shaped.
  - Registration: both tools land in REGISTRY at tier 3 and in TRIAGE_ONLY_TOOLS.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm.tool_result import tool_err
from fsr_playbooks.mcp_server import _shared, tools_records


def _scope_gate(scope):
    """A host write policy permitting exactly ``scope`` (and naming it)."""
    def gate(module):
        if module in scope:
            return None
        return tool_err("write_not_permitted",
                        f"writes to {module!r} are outside the scope {scope}")
    return gate


@pytest.fixture
def _gate(monkeypatch):
    def install(scope):
        monkeypatch.setattr(_shared, "_RECORD_WRITE_GATE",
                            None if scope is None else _scope_gate(scope))
    return install


@pytest.fixture
def writer(_gate):
    """A host policy that may write ztpf_templates."""
    _gate(["ztpf_templates"])


@pytest.fixture
def no_policy(_gate):
    """No host write policy at all."""
    _gate(None)


class _Resp:
    def __init__(self, status=201, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self):
        return self._payload


class _Client:
    base_url = ""


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    """Each test's fake box declares its own fields; a schema another test
    cached must not leak in (every write now reads the module's fields)."""
    tools_records._ATTR_CACHE.clear()
    yield
    tools_records._ATTR_CACHE.clear()


def _patch_client(monkeypatch, capture, resp=None):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client())

    def fake_request(method, client, url, **kwargs):
        capture.append((method, url, kwargs))
        return resp if resp is not None else _Resp(
            201, {"@id": f"{url}/uuid-1", "uuid": "uuid-1", "id": 7})

    monkeypatch.setattr(_shared, "live_request_with_reauth", fake_request)


# --- gate: no policy -------------------------------------------------------

def test_create_no_policy_refused(no_policy, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "x"})
    assert out["ok"] is False and out["code"] == "write_not_permitted"
    assert cap == []  # never reached the client


def test_create_module_not_in_may_write_refused(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    out = tools_records.create_record("alerts", {"name": "x"})
    assert out["ok"] is False and out["code"] == "write_not_permitted"
    assert "alerts" in out["message"]
    assert cap == []


def test_a_gate_that_raises_refuses(monkeypatch):
    """An unreadable policy must not read as permission."""
    def boom(module):
        raise RuntimeError("policy store down")
    monkeypatch.setattr(_shared, "_RECORD_WRITE_GATE", boom)
    cap = []
    _patch_client(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "x"})
    assert out["code"] == "write_not_permitted" and cap == []


# --- happy path -------------------------------------------------------------

def test_create_permitted(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "cfg-gen"})
    assert out["ok"] is True
    assert out["action"] == "create"
    assert out["uuid"] == "uuid-1"
    assert out["iri"].endswith("/uuid-1")
    [(method, url, kwargs)] = [c for c in cap if c[0] != "get"]  # after the schema read
    assert method == "post"
    assert url == "/api/3/ztpf_templates"
    assert kwargs["json"] == {"name": "cfg-gen"}


def test_update_permitted(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap, resp=_Resp(200, {"@id": "/api/3/ztpf_templates/u",
                                                     "uuid": "u", "id": 3}))
    out = tools_records.update_record("ztpf_templates", "u", {"name": "new"})
    assert out["ok"] is True and out["action"] == "update"
    [(method, url, kwargs)] = [c for c in cap if c[0] != "get"]  # after the schema read
    assert method == "put"
    assert url == "/api/3/ztpf_templates/u"


@pytest.mark.parametrize("verb", ["create", "update"])
def test_a_link_sent_as_an_object_is_written_as_its_iri(writer, monkeypatch, verb):
    """Models copy the read tools' `{iri, uuid, label}` shape into a write; the
    box needs the IRI string, or the record lands unlinked."""
    cap = []
    _patch_client(monkeypatch, cap)
    fields = {"name": "s",
              "ztpfAutomationProfiles": {"iri": "/api/3/ztpf_automation_profiles/p"},
              "ztpfAutomationActions": {"@id": "/api/3/ztpf_automation_actions/a",
                                        "name": "Get System Status"},
              "recordTags": ["/api/3/tags/t", {"iri": "/api/3/tags/u"}],
              "stepARGS": {"input": {"firmware": "7.6.8"}}}
    if verb == "create":
        tools_records.create_record("ztpf_templates", fields)
    else:
        tools_records.update_record("ztpf_templates", "u", fields)
    sent = next(c for c in cap if c[0] in ("post", "put"))[2]["json"]
    assert sent["ztpfAutomationProfiles"] == "/api/3/ztpf_automation_profiles/p"
    assert sent["ztpfAutomationActions"] == "/api/3/ztpf_automation_actions/a"
    assert sent["recordTags"] == ["/api/3/tags/t", "/api/3/tags/u"]
    # A dict that is data, not a link, is left alone.
    assert sent["stepARGS"] == {"input": {"firmware": "7.6.8"}}


# --- input validation -------------------------------------------------------

def test_create_missing_fields(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    assert tools_records.create_record("ztpf_templates", {})["code"] == "missing_fields"
    assert tools_records.create_record("", {"a": 1})["code"] == "missing_module"
    assert cap == []


def test_update_missing_uuid(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    assert tools_records.update_record("ztpf_templates", "", {"a": 1})["code"] == "missing_uuid"
    assert cap == []


# --- transport / http errors ------------------------------------------------

def test_create_http_error_surfaced(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap, resp=_Resp(400, {"message": "bad field"}))
    out = tools_records.create_record("ztpf_templates", {"name": "x"})
    assert out["ok"] is False and out["code"] == "http_400"
    assert "bad field" in out["message"]


def test_create_no_client(writer, monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: None)
    out = tools_records.create_record("ztpf_templates", {"name": "x"})
    assert out["code"] == "no_fsr_configured"


# --- registration -----------------------------------------------------------

def test_registered_tier3_and_triage_only():
    from fsr_playbooks.llm.intents import TRIAGE_ONLY_TOOLS
    from fsr_playbooks.llm.tools import _PRECARD_VALIDATORS, REGISTRY, TOOL_TIERS
    for n in ("create_record", "update_record"):
        assert n in REGISTRY
        assert REGISTRY[n].tier == 3
        assert TOOL_TIERS[n] == 3
        assert n in TRIAGE_ONLY_TOOLS
        assert _PRECARD_VALIDATORS[n] is tools_records.precard_validate


# --------------------------------------------------------------------------
# Backlog 1.1: the refusal must come BEFORE the approval card, not after it.
#
# The write gate runs in the tool body, and a tier-3 body only runs once the
# analyst has approved. So an out-of-scope write used to produce:
#
#   propose -> full approval card -> analyst reviews fields -> APPROVE
#           -> body runs -> write_not_permitted
#
# The system knew at proposal time that it would refuse. These tests pin the
# ORDERING, which is the entire defect -- the body's refusal was never in doubt.
# --------------------------------------------------------------------------
def test_precard_refuses_a_module_outside_the_scope(writer):
    out = tools_records.precard_validate(
        {"module": "ztpf_devices", "fields": {"name": "x"}})
    assert out is not None
    assert out["code"] == "write_not_permitted"
    assert "ztpf_templates" in out["message"], \
        "the refusal must NAME the scope, or the analyst cannot act on it"


def test_precard_lets_an_in_scope_write_through_to_the_card(writer):
    assert tools_records.precard_validate(
        {"module": "ztpf_templates", "fields": {"name": "x"}}) is None


def test_precard_refuses_when_no_policy_is_set(no_policy):
    out = tools_records.precard_validate({"module": "ztpf_templates"})
    assert out is not None and out["code"] == "write_not_permitted"


def test_precard_defers_a_missing_module_to_the_tool_body(writer):
    """Fail-open on an arg the body already validates: a pre-card validator that
    invented its own arg errors would report them in the card's place, where the
    model's self-correction path is worse."""
    assert tools_records.precard_validate({}) is None
    assert tools_records.precard_validate({"module": ""}) is None


def test_precard_is_the_same_gate_not_a_second_copy(writer):
    """Two spellings of "who may write where" would drift, and the drift would
    only show at the exact moment a write is refused after approval."""
    for module in ("ztpf_templates", "ztpf_devices", "alerts"):
        assert (tools_records.precard_validate({"module": module})
                == _shared.record_write_gate(module))


def test_dispatch_refuses_out_of_scope_before_building_a_card(writer, monkeypatch):
    """End-to-end through the real dispatch: the analyst must never see a card
    for a write the system already knows it will refuse."""
    from fsr_playbooks.llm import tools as fw

    out = fw.dispatch("create_record",
                      {"module": "ztpf_devices", "fields": {"name": "x"}},
                      session_id="s-precard")
    assert not out.get("pending_approval"), \
        "carded a write the write policy forbids"
    assert out.get("code") == "write_not_permitted"

    # The inverse, so the test above cannot pass by refusing everything.
    ok = fw.dispatch("create_record",
                     {"module": "ztpf_templates", "fields": {"name": "x"}},
                     session_id="s-precard")
    assert ok.get("pending_approval"), \
        "an in-scope write must still reach the analyst as a card"


# --- picklist fields: a refused label resolves on the box -------------------
# Live, a template create sent `outputType: "Text"` and the box refused it: the
# field takes the picklist item's IRI. The refusal names the picklist, so the
# write looks the label up there and retries once per refused field.

_REFUSAL = ('{"type": "UnexpectedValueException", "message": "FSR_CH_0000001 : '
            'The \\"outputType\\" field is required to have a value from the '
            '\\"ztpfOutputType\\" picklist. However, the provided value does not"}')
_TEXT_IRI = "/api/3/picklists/d859d6fd-cef6-431a-b4f6-fbcd90c9a654"


def _box(monkeypatch, cap):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client())

    def fake_request(method, client, url, **kwargs):
        cap.append((method, url, kwargs))
        if method == "get" and "/api/3/picklist_names" in url:
            assert "name=ztpfOutputType" in url
            return _Resp(200, {"hydra:member": [{"picklists": [
                {"itemValue": "Text", "@id": _TEXT_IRI},
                {"itemValue": "JSON", "@id": "/api/3/picklists/json"}]}]})
        body = (kwargs.get("json") or {})
        if str(body.get("outputType", "")).startswith("/api/3/picklists/"):
            return _Resp(201, {"@id": f"{url}/uuid-1", "uuid": "uuid-1", "id": 7})
        r = _Resp(400, {"message": "refused"})
        r.text = _REFUSAL
        return r

    monkeypatch.setattr(_shared, "live_request_with_reauth", fake_request)


def test_a_refused_picklist_label_is_resolved_and_the_write_retried(writer, monkeypatch):
    cap = []
    _box(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "x", "outputType": "text"})
    assert out["ok"] is True and out["resolved_picklists"] == {"outputType": "Text"}
    posts = [c for c in cap if c[0] == "post"]
    assert len(posts) == 2 and posts[-1][2]["json"]["outputType"] == _TEXT_IRI


def test_the_read_shape_of_a_picklist_is_accepted_too(writer, monkeypatch):
    cap = []
    _box(monkeypatch, cap)
    out = tools_records.update_record("ztpf_templates", "u1",
                                      {"outputType": {"itemValue": "JSON"}})
    assert out["ok"] is True
    assert [c for c in cap if c[0] == "put"][-1][2]["json"]["outputType"] == "/api/3/picklists/json"


def test_a_value_not_on_the_picklist_names_the_real_choices(writer, monkeypatch):
    cap = []
    _box(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "x", "outputType": "Script"})
    assert out["ok"] is False and out["code"] == "bad_picklist_value"
    assert out["valid_values"] == ["Text", "JSON"] and "Text, JSON" in out["message"]
    assert len([c for c in cap if c[0] == "post"]) == 1


# --- a list or object sent to a text field --------------------------------
# Live: a template create sent inputParameters: [] and the box saved the word
# "Array". The field is a string whose records hold newline-separated names.
def _typed_box(monkeypatch, cap):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client())
    tools_records._ATTR_CACHE.clear()

    def fake_request(method, client, url, **kwargs):
        cap.append((method, url, kwargs))
        if "/api/3/model_metadatas" in url:
            return _Resp(200, {"hydra:member": [{"attributes": [
                {"name": "name", "type": "string"},
                {"name": "inputParameters", "type": "string"},
                {"name": "script", "type": "string"},
                {"name": "ztpfMetadataSources", "type": "ztpf_metadata_sources"}]}]})
        if method == "get":
            return _Resp(200, {"hydra:member": [{"inputParameters": "Array"},
                                                {"inputParameters": "lo_name\ndescription"}]})
        return _Resp(201, {"@id": f"{url}/uuid-1", "uuid": "uuid-1"})

    monkeypatch.setattr(_shared, "live_request_with_reauth", fake_request)


def test_a_list_for_a_text_field_is_refused_before_the_card(writer, monkeypatch):
    cap = []
    _typed_box(monkeypatch, cap)
    out = tools_records.precard_validate(
        {"module": "ztpf_templates", "fields": {"name": "t", "inputParameters": []}})
    assert out["ok"] is False and out["code"] == "not_text"
    assert out["field"] == "inputParameters"
    assert out["examples"] == ["lo_name\ndescription"], "a stored 'Array' is not an example"


def test_the_write_itself_refuses_too_and_sends_nothing(writer, monkeypatch):
    cap = []
    _typed_box(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {"name": "t", "inputParameters": ["lo_name"]})
    assert out["code"] == "not_text"
    assert not [c for c in cap if c[0] == "post"]


def test_links_and_text_pass(writer, monkeypatch):
    cap = []
    _typed_box(monkeypatch, cap)
    out = tools_records.create_record("ztpf_templates", {
        "name": "t", "inputParameters": "lo_name", "script": "x",
        "ztpfMetadataSources": ["/api/3/ztpf_metadata_sources/a"]})
    assert out["ok"] is True


def test_an_unknown_field_type_fails_open(writer, monkeypatch):
    cap = []
    _typed_box(monkeypatch, cap)
    assert tools_records._structured_into_text(_Client(), "ztpf_templates", {"data": {"a": 1}}) is None


# --- a picklist label the field's picklist does not have -------------------
# Live: an unattended close staged closureReason "Benign" on an alert. The
# card was approved, the box refused the label, and the alert stayed open.

@pytest.fixture
def alert_writer(_gate):
    _gate(["alerts"])


_CLOSURE = ["False Positive", "Escalated to Case", "Invalid", "Resolved"]


def _picklist_box(monkeypatch, cap, items=_CLOSURE):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client())
    tools_records._ATTR_CACHE.clear()

    def fake_request(method, client, url, **kwargs):
        cap.append((method, url, kwargs))
        if "/api/3/model_metadatas" in url:
            return _Resp(200, {"hydra:member": [{"attributes": [
                {"name": "closureReason", "type": "picklists", "dataSource": {
                    "model": "picklists", "query": {"filters": [
                        {"field": "listName__name", "operator": "eq",
                         "value": "AlertClosureReason"}]}}},
                {"name": "closureNotes", "type": "html"},
                {"name": "status", "type": "picklists"},
                {"name": "outputTemplateJSON", "type": "text"}]}]})
        if "/api/3/picklist_names" in url:
            assert "name=AlertClosureReason" in url
            return _Resp(200, {"hydra:member": [{"picklists": [
                {"itemValue": v, "@id": f"/api/3/picklists/{i}"}
                for i, v in enumerate(items)]}]})
        return _Resp(200, {"@id": url, "uuid": "u1"})

    monkeypatch.setattr(_shared, "live_request_with_reauth", fake_request)


def _close(reason):
    return {"module": "alerts",
            "fields": {"status": "/api/3/picklists/closed", "closureReason": reason,
                       "closureNotes": "Authorized scanner."}}


def test_a_label_the_picklist_lacks_is_refused_before_the_card(alert_writer, monkeypatch):
    for label in ("Benign", "Benign test activity", {"itemValue": "Benign"}):
        cap = []
        _picklist_box(monkeypatch, cap)
        out = tools_records.precard_validate(_close(label))
        assert out and out["ok"] is False and out["code"] == "bad_picklist_value", label
        assert out["field"] == "closureReason" and out["valid_values"] == _CLOSURE
        assert "False Positive, Escalated to Case, Invalid, Resolved" in out["message"]
        assert not [c for c in cap if c[0] in ("put", "post")]


def test_a_label_the_picklist_has_passes(alert_writer, monkeypatch):
    for label in ("False Positive", "false positive", {"itemValue": "Resolved"},
                  "/api/3/picklists/0", None, ""):
        _picklist_box(monkeypatch, [])
        assert tools_records.precard_validate(_close(label)) is None, label


def test_an_unreadable_picklist_fails_open(alert_writer, monkeypatch):
    _picklist_box(monkeypatch, [], items=[])
    assert tools_records.precard_validate(_close("Benign")) is None


# --- a field the module does not have ------------------------------------------
# Live: `outputTemplateJson` for `outputTemplateJSON`. The platform ignored the
# key and answered 200; the card was approved twice and nothing was saved.

def test_a_field_the_module_lacks_is_refused_before_the_card(alert_writer, monkeypatch):
    cap = []
    _picklist_box(monkeypatch, cap)
    out = tools_records.precard_validate(
        {"module": "alerts", "fields": {"outputTemplateJson": "[]"}})
    assert out and out["ok"] is False and out["code"] == "unknown_field"
    assert out["fields"] == ["outputTemplateJson"]
    assert out["suggestions"]["outputTemplateJson"] == ["outputTemplateJSON"]
    assert "'outputTemplateJSON'" in out["message"]
    assert not [c for c in cap if c[0] in ("put", "post")]


def test_the_write_itself_refuses_it_too(alert_writer, monkeypatch):
    """A grant or a resumed approval reaches the body without the pre-card check."""
    cap = []
    _picklist_box(monkeypatch, cap)
    out = tools_records.update_record(module="alerts", uuid="u1",
                                      fields={"outputTemplateJson": "[]"})
    assert out["ok"] is False and out["code"] == "unknown_field"
    assert not [c for c in cap if c[0] == "put"]


def test_declared_and_system_fields_pass(alert_writer, monkeypatch):
    _picklist_box(monkeypatch, [])
    assert tools_records.precard_validate({"module": "alerts", "fields": {
        "outputTemplateJSON": "[]", "recordTags": ["/api/3/tags/x"],
        "@type": "Alert"}}) is None


def test_unreadable_module_fields_fail_open(alert_writer, monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client())
    tools_records._ATTR_CACHE.clear()
    monkeypatch.setattr(_shared, "live_request_with_reauth",
                        lambda *a, **k: _Resp(500, {}))
    assert tools_records._unknown_fields(_Client(), "alerts", {"anything": 1}) is None


# --- identifiers are path segments --------------------------------------------
# module and uuid are interpolated into /api/3/<module>/<uuid>; a '/', '?' or
# '..' must be refused before the gate or the transport, whatever the policy.

@pytest.mark.parametrize("module", ["ztpf_templates/../alerts", "alerts?$limit=1",
                                    "ztpf_templates/x", "a b"])
def test_a_module_that_is_not_an_identifier_is_refused(_gate, monkeypatch, module):
    _gate([module])  # even a policy that permits the raw string
    cap = []
    _patch_client(monkeypatch, cap)
    assert tools_records.create_record(module, {"name": "x"})["code"] == "bad_module"
    assert tools_records.precard_validate({"module": module})["code"] == "bad_module"
    assert cap == []


def test_a_uuid_that_is_not_an_identifier_is_refused(writer, monkeypatch):
    cap = []
    _patch_client(monkeypatch, cap)
    for uuid in ("u/../../alerts/v", "u?x=1"):
        out = tools_records.update_record("ztpf_templates", uuid, {"name": "x"})
        assert out["code"] == "bad_uuid"
        assert tools_records.precard_validate(
            {"module": "ztpf_templates", "uuid": uuid})["code"] == "bad_uuid"
    assert cap == []
