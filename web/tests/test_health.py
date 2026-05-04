from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["compiler"]["ok"] is True
    assert "fsr" in body
    assert "llm" in body
