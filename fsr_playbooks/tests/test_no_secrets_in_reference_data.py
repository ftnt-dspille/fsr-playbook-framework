"""The reference DBs and generated docs must carry no harvested credentials.

The DBs are filled by probes reading playbooks off a live appliance, and one of
them stored a real RSA key pair (a `SetAPIKeys` step example), bearer tokens in
HTTP headers and a service-account password in a code snippet. The DBs ship in
the wheel and are tracked on the public mirror, so this runs the same detector
the harvest-time redactor uses over every text cell, the raw bytes (free pages
keep deleted rows), and `data/STEP_TYPES.md`.

Vendor sample defaults (`changeme`, `fortinet`, ...) and prose that merely
mentions a key header are not secrets and stay.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

import fsr_playbooks

_REPO_ROOT = Path(fsr_playbooks.__file__).resolve().parent.parent
_MOD = _REPO_ROOT / "scripts" / "secret_redact.py"

TRACKED_DBS = [
    _REPO_ROOT / "fsr_playbooks" / "_data" / "fsr_reference.db",
    _REPO_ROOT / "tooling" / "tests" / "fixtures" / "tooling_reference.db",
]
TRACKED_DOCS = [_REPO_ROOT / "data" / "STEP_TYPES.md"]

pytestmark = pytest.mark.skipif(
    not _MOD.exists(), reason="scripts/secret_redact.py not present (not a checkout)")


def _load():
    spec = importlib.util.spec_from_file_location("_secret_redact", _MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_secret_redact"] = mod
    spec.loader.exec_module(mod)
    return mod


sr = _load() if _MOD.exists() else None

PEM = ("-----BEGIN RSA PRIVATE KEY-----\n"
       "MIIFAKEFAKEFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfake1234\n"
       "fakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfakeFAKEfake5678\n"
       "-----END RSA PRIVATE KEY-----")


@pytest.mark.parametrize("db", TRACKED_DBS, ids=lambda p: p.name)
def test_committed_reference_db_has_no_secrets(db: Path):
    if not db.exists():
        pytest.skip(f"{db.name} not present in this checkout")
    hits = sr.scan_db(db)
    assert not hits, (
        f"{db.name} holds harvested secrets (table, column, rowid, kind): "
        f"{hits[:8]}\nRun: python scripts/secret_redact.py "
        f"{db.relative_to(_REPO_ROOT)}")
    raw = db.read_bytes().decode("latin-1")
    raw_hits = [n for n, rx in sr._DETECT if rx.search(raw)]
    assert not raw_hits, f"{db.name} raw bytes (free pages) still hold: {raw_hits}"


@pytest.mark.parametrize("doc", TRACKED_DOCS, ids=lambda p: p.name)
def test_generated_docs_have_no_secrets(doc: Path):
    if not doc.exists():
        pytest.skip(f"{doc.name} not present in this checkout")
    hits = sr.find_secrets(doc.read_text(encoding="utf-8"))
    assert not hits, f"{doc.name} holds secrets: {hits}"


# ----------------------------------------------------------- the redactor itself

def test_private_key_redacted_in_real_and_json_escaped_form():
    assert sr.find_secrets(PEM)
    assert not sr.find_secrets(sr.redact_text(PEM))
    esc = PEM.replace("\n", "\\n")
    assert sr.find_secrets(esc)
    out = sr.redact_text(esc)
    assert not sr.find_secrets(out) and "BEGIN RSA PRIVATE KEY" in out


def test_prose_mentioning_the_header_is_not_a_secret():
    doc = "The key should start with '-----BEGIN PRIVATE KEY----- ' and end with '-----END PRIVATE KEY-----'"
    assert not sr.find_secrets(doc)
    assert sr.redact_text(doc) == doc


def test_bearer_tokens_redacted_templates_left():
    assert sr.find_secrets("Authorization: Bearer fakeTokenfakeTokenfakeToken00")
    assert sr.redact_text("Bearer fakeTokenfakeTokenfakeToken00") == "Bearer <redacted-token>"
    for ok in ("Bearer {{vars.token}}", "Bearer <token>", "Bearer <redacted-token>"):
        assert not sr.find_secrets(ok) and sr.redact_text(ok) == ok


def test_secret_named_keys_redacted_vendor_defaults_left():
    doc = {"password": "Sample#Pass9", "adminPassword": "fort!net", "pw2": "x",
           "token": "{{vars.t}}", "api_key": "", "passwd-time": "0000-00-00 00:00:00",
           "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuv"},
           "password2": "changeme"}
    out = sr.redact_obj(doc)
    assert out["password"] == "<redacted-secret>"
    assert out["adminPassword"] == "fort!net"
    assert out["token"] == "{{vars.t}}" and out["password2"] == "changeme"
    assert out["passwd-time"] == "0000-00-00 00:00:00"
    assert out["headers"]["Authorization"] == "Bearer <redacted-token>"
    assert sr.redact_obj(out) == out            # idempotent


def test_session_ids_and_scheme_authorization_headers_redacted():
    doc = {"data": json.dumps({"session": "fakeSessionfakeSession0000", "url": "/sys/status"}),
           "headers": json.dumps({"Authorization": "FortiAnalyzer 00000000-fake-fake-fake-000000000000"}),
           "mode": {"session": "new"}}
    out = sr.redact_obj(doc)
    assert "fakeSessionfake" not in json.dumps(out) and "00000000-fake" not in json.dumps(out)
    assert out["mode"] == {"session": "new"}
    assert sr.find_secrets_in_cell(json.dumps(doc)) and not sr.find_secrets_in_cell(json.dumps(out))


def test_password_literal_in_code_snippet_redacted():
    code = "payload = {\n 'username': 'svc',\n 'password': 'Sup3rSecret!',\n}"
    out = sr.redact_text(code)
    assert "Sup3rSecret" not in out and "'password': '<redacted-secret>'" in out


def test_redact_db_rewrites_cells_and_drops_free_pages(tmp_path):
    p = tmp_path / "t.db"
    db = sqlite3.connect(p)
    db.execute("CREATE TABLE step_examples (name TEXT, snippet_json TEXT)")
    db.execute("INSERT INTO step_examples VALUES ('a', ?)",
               (json.dumps({"arguments": {"private_key": PEM}}),))
    db.execute("INSERT INTO step_examples VALUES ('b', '{\"password\": \"changeme\"}')")
    db.commit(); db.close()
    assert sr.scan_db(p)
    assert sr.redact_db(p, quiet=True) == 1
    assert not sr.scan_db(p)
    assert b"MIIFAKEFAKEF" not in p.read_bytes()
    assert sr.redact_db(p, quiet=True) == 0      # idempotent


# ----------------------------------------- literal credentials under known keys

@pytest.mark.parametrize("db", TRACKED_DBS, ids=lambda p: p.name)
def test_committed_db_raw_bytes_have_no_literal_credentials(db: Path):
    """Literal values under password/session/token keys, including the escaped-quote
    form inside JSON strings and in free pages. Templates and schema words are not hits."""
    if not db.exists():
        pytest.skip(f"{db.name} not present in this checkout")
    raw = db.read_bytes().decode("latin-1")
    hits = [m.group("k") for m in sr.LITERAL_KV_RE.finditer(raw)
            if sr._is_literal_kv_secret(m.group("k"), m.group("v"))]
    assert not hits, f"{db.name} raw bytes hold literal credentials under keys: {sorted(set(hits))}"


LITERAL_CREDENTIAL_CASES = [
    # JSON document: key names the old rules missed
    ('{"adminPassword": "Sample-Only-42!"}', "Sample-Only-42!"),
    ('{"session_id": "fakeSessionValue01"}', "fakeSessionValue01"),
    ('{"SessionID": "Zq7Lp2Xw9Rt4"}', "Zq7Lp2Xw9Rt4"),
    ('{"new_password": "Sample-Only-42!"}', "Sample-Only-42!"),
    ('{"token": "tk_fake_0123456789"}', "tk_fake_0123456789"),
    # the same inside a JSON string (escaped quotes)
    ('{"data": "{\\"session_id\\": \\"fakeSessionValue01\\"}"}', "fakeSessionValue01"),
    # code literals
    ("cfg = {'session_id': 'fakeSessionValue01'}", "fakeSessionValue01"),
    ("admin_pass = 'Sample-Only-42!'", "Sample-Only-42!"),
]


@pytest.mark.parametrize("text,value", LITERAL_CREDENTIAL_CASES)
def test_literal_credentials_under_password_session_token_keys_redacted(text, value):
    assert sr.find_secrets(text), text
    out = sr.redact_text(text)
    assert value not in out, "literal value survived redaction"
    assert not sr.find_secrets(out)


LITERAL_NOT_CREDENTIAL_CASES = [
    '{"completion_tokens": 812, "max_tokens": 4096}',
    '{"tokenStatus": "active", "token_type": "bearer"}',
    '{"password": "{{ vars.pw }}", "session_id": "<session>"}',
    '{"password": "changeme", "token": "{{ vars.t }}", "session": "<session>"}',
    # JSON Schema type declarations are metadata, not credentials
    '{"session_id": {"type": "string"}, "token": "string", "password": "integer"}',
    "{'password': '{{ vault.secret_ref }}'}",
    '{"password_needs_reset": "true", "bypass": "Sample-Only-42"}',
]


@pytest.mark.parametrize("text", LITERAL_NOT_CREDENTIAL_CASES)
def test_templates_counters_placeholders_and_schema_words_left(text):
    assert not sr.find_secrets(text), text
    assert sr.redact_text(text) == text
