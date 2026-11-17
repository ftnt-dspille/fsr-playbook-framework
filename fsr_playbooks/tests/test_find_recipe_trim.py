"""find(kind='recipe') returns full YAML for the best matches only."""
from fsr_playbooks.mcp_server import tools_find


def test_only_the_top_recipes_carry_their_yaml(monkeypatch):
    import fsr_playbooks.mcp_server as srv
    rows = [{"name": f"r{i}", "kind": "example", "when_to_use": "w",
             "yaml_template": "x" * 5000} for i in range(10)]
    monkeypatch.setattr(srv, "find_recipe",
                        lambda q, limit=3: {"ok": True, "count": 10,
                                            "recipes": [dict(r) for r in rows]})
    out = tools_find.find("recipe", "block an ip")
    shown = [r for r in out["recipes"] if "yaml_template" in r]
    assert [r["name"] for r in shown] == ["r0", "r1"]
    assert all(r["when_to_use"] for r in out["recipes"])
    assert "find(kind='recipe', query=<its name>, limit=1)" in out["note"]


def test_a_single_named_recipe_keeps_its_yaml(monkeypatch):
    import fsr_playbooks.mcp_server as srv
    monkeypatch.setattr(srv, "find_recipe", lambda q, limit=3: {
        "ok": True, "count": 1,
        "recipes": [{"name": "r0", "yaml_template": "steps: []"}]})
    out = tools_find.find("recipe", "r0", limit=1)
    assert out["recipes"][0]["yaml_template"] == "steps: []"
    assert "note" not in out
