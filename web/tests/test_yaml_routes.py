from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)


GOOD = """\
collection: Hello
playbooks:
  - name: Hello
    steps:
      - id: trigger
        type: start
        next: stop
      - id: stop
        type: stop
"""


def test_validate_good():
    r = client.post("/api/yaml/validate", json={"text": GOOD})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # warnings allowed; no errors
    assert all(m["severity"] != "error" for m in body["markers"])


def test_validate_yaml_syntax_error_has_line_col():
    bad = "collection: Hi\n  bad: : :\n"
    r = client.post("/api/yaml/validate", json={"text": bad})
    body = r.json()
    assert body["ok"] is False
    assert body["markers"]
    m = body["markers"][0]
    assert m["code"] == "parse_error"
    assert m["line"] >= 1
    assert m["col"] >= 1


def test_validate_missing_fields():
    r = client.post("/api/yaml/validate", json={"text": "foo: bar\n"})
    body = r.json()
    assert body["ok"] is False
    codes = {m["code"] for m in body["markers"]}
    assert "missing_field" in codes


def test_compile_good():
    r = client.post("/api/yaml/compile", json={"text": GOOD})
    body = r.json()
    assert body["ok"] is True
    assert body["fsr_json"] is not None
    assert "name" in body["fsr_json"] or "uuid" in str(body["fsr_json"])


def test_compile_bad():
    r = client.post("/api/yaml/compile", json={"text": "not valid yaml: : :"})
    body = r.json()
    assert body["ok"] is False
    assert body["fsr_json"] is None
