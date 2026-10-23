"""get_record(full=True) must never dump the raw ~100KB hydrated body into
context (the token-waste finding). full=True now returns a
cleaned (null/empty + SLA/boilerplate stripped), hard size-capped body with
`coerced_full=true` -- not the verbatim record.
"""
from __future__ import annotations

import json


def test_clean_full_record_drops_noise_and_boilerplate():
    from fsr_playbooks.mcp_server.tools_triage import _clean_full_record
    rec = {
        "@id": "/api/3/incidents/u1",
        "name": "smithDesktop defense-evasion",
        "sourceIp": "10.1.1.5",
        "severity": "Critical",
        "description": None,            # null → dropped
        "owners": ["a", "b"],            # hydra/audit noise → dropped
        "impactAssessments": "x" * 500,  # boilerplate prose → dropped
        "slaCompletionDate": "2026-01-01",   # *SLA* plumbing → dropped
        "responseProcedure": "long...",  # boilerplate → dropped
        "escalation_rules": {"k": "v"},  # boilerplate → dropped
        "emptyList": [],                 # empty → dropped
    }
    out = _clean_full_record(rec)
    assert out["@id"] == "/api/3/incidents/u1"
    assert out["name"].startswith("smithDesktop")
    assert out["sourceIp"] == "10.1.1.5"
    assert out["severity"] == "Critical"
    for gone in ("description", "owners", "impactAssessments",
                 "slaCompletionDate", "responseProcedure",
                 "escalation_rules", "emptyList"):
        assert gone not in out


def test_cap_json_truncates_oversized_body():
    from fsr_playbooks.mcp_server.tools_triage import _REC_FULL_MAX_BYTES, _cap_json
    small, truncated = _cap_json({"a": 1})
    assert truncated is False and small == {"a": 1}

    big = {"blob": "y" * (_REC_FULL_MAX_BYTES * 2)}
    capped, truncated = _cap_json(big)
    assert truncated is True
    assert capped["_truncated"] is True
    assert capped["_original_bytes"] > _REC_FULL_MAX_BYTES
    # The marker itself is bounded (head + tail ~= max_bytes, plus small keys).
    assert len(json.dumps(capped)) < _REC_FULL_MAX_BYTES + 512


class _FakeResp:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeSession:
    def __init__(self, data):
        self._data = data

    def get(self, url, verify=None):
        return _FakeResp(self._data)


class _FakeClient:
    base_url = "https://fsr.example"
    verify_ssl = False

    def __init__(self, data):
        self.session = _FakeSession(data)


def test_get_record_full_returns_cleaned_capped_body(monkeypatch):
    from fsr_playbooks.mcp_server import _shared
    from fsr_playbooks.mcp_server.tools_triage import get_record

    raw = {
        "@id": "/api/3/incidents/u1",
        "name": "smithDesktop",
        "sourceIp": "10.1.1.5",
        "impactAssessments": "boilerplate " * 2000,  # ~24KB of prose
        "slaDueDate": "2026-01-01",
        "nullField": None,
    }
    monkeypatch.setattr(_shared, "_live_client", lambda: _FakeClient(raw))

    out = get_record(iri="/api/3/incidents/u1", relationships=False, full=True)
    assert out["ok"] is True
    assert out["coerced_full"] is True
    assert "summarized" not in out
    rec = out["record"]
    # Either the cleaned body (no boilerplate/null) or a truncation marker --
    # in both cases the 24KB impact wall is gone.
    body = json.dumps(rec)
    assert "impactAssessments" not in body
    assert "nullField" not in body
    assert len(body) < 8192 + 512


def test_get_record_default_still_pruned(monkeypatch):
    from fsr_playbooks.mcp_server import _shared
    from fsr_playbooks.mcp_server.tools_triage import get_record

    raw = {"@id": "/api/3/incidents/u1", "name": "x", "sourceIp": "10.0.0.1"}
    monkeypatch.setattr(_shared, "_live_client", lambda: _FakeClient(raw))
    out = get_record(iri="/api/3/incidents/u1", relationships=False)
    assert out["summarized"] is True
    assert "coerced_full" not in out


# --- reading a long field whole -------------------------------------------------
# Live (a ZTPF automation action): the record carries ~100KB of example vars, so
# even full=True fell back to the record view, which cut every template to 600
# characters and stripped an HTML template's tags. The model refused one edit
# for it and rewrote a whole template from its first 600 characters in another.

_TEMPLATE = "{%- set ints = data.dvmdb_ints | default([]) -%}\n" + "{{ d.name }}\n" * 400
_HTML = "<style>.iface { color: #ddd }</style><table><tr><td>{{ x }}</td></tr></table>"
_ACTION = {"@id": "/api/3/ztpf_automation_actions/a1", "name": "Interfaces",
           "outputTemplateJSON": _TEMPLATE, "outputTemplateHTML": _HTML,
           "description": "short", "exampleJinjaVars": {"data": {"blob": "z" * 120000}}}


def _get(monkeypatch, **kw):
    from fsr_playbooks.mcp_server import _shared
    from fsr_playbooks.mcp_server.tools_triage import get_record
    monkeypatch.setattr(_shared, "_live_client", lambda: _FakeClient(dict(_ACTION)))
    return get_record(iri="/api/3/ztpf_automation_actions/a1", relationships=False, **kw)


def test_the_record_view_names_the_fields_it_shortened(monkeypatch):
    for kw in ({}, {"full": True}):
        out = _get(monkeypatch, **kw)
        assert out["summarized"] is True, kw
        assert out["clipped_fields"] == ["outputTemplateJSON", "outputTemplateHTML"], kw
        assert "fields=" in out["clipped_note"]


def test_fields_come_back_whole_and_verbatim(monkeypatch):
    # Case as the model wrote it live; the record spells it outputTemplateJSON.
    out = _get(monkeypatch, fields=["outputTemplateJson", "outputTemplateHTML"])
    assert out["fields"] == {"outputTemplateJSON": _TEMPLATE, "outputTemplateHTML": _HTML}
    assert "clipped_fields" not in out, "nothing it returned whole is reported as cut"
    assert "unknown_fields" not in out


def test_an_unknown_field_names_the_closest(monkeypatch):
    out = _get(monkeypatch, fields=["outputTemplate"])
    assert out["fields"] == {}
    assert "outputTemplateJSON" in out["unknown_fields"]["outputTemplate"]
