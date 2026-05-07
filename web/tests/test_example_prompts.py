"""GET /api/ref/example-prompts surfaces the eval-task corpus to the
chat UI's prompt picker. Adding/removing a JSON file under
`python/evals/tasks/` must show up here without code changes."""
from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)


def test_returns_at_least_the_three_seed_tasks():
    r = client.get("/api/ref/example-prompts")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = {p["name"] for p in body}
    # The original three tasks plus the Phase-3A expansion (15 total)
    # — assert the seed three are always present so the picker keeps
    # working even if someone reorders / renumbers files.
    for must_have in ("hello_connector", "decision_branch",
                      "alert_action_var_chain"):
        assert must_have in names


def test_each_entry_has_required_fields():
    r = client.get("/api/ref/example-prompts")
    for p in r.json():
        assert "name" in p
        assert "prompt" in p and isinstance(p["prompt"], str) and p["prompt"]
        assert "notes" in p
        assert "has_gold" in p and isinstance(p["has_gold"], bool)


def test_has_gold_flag_matches_gold_pointer():
    """`has_gold: true` ⇔ task JSON has a gold_yaml_path field."""
    import json
    from pathlib import Path

    tasks_dir = (Path(__file__).resolve().parents[2]
                 / "python" / "evals" / "tasks")
    on_disk = {}
    for p in tasks_dir.glob("*.json"):
        data = json.loads(p.read_text())
        on_disk[data["name"]] = bool(data.get("gold_yaml_path"))

    r = client.get("/api/ref/example-prompts")
    for entry in r.json():
        assert entry["has_gold"] == on_disk[entry["name"]], entry["name"]
