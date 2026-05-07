from backend.llm.tools import REGISTRY, anthropic_tools, dispatch


def test_registry_nonempty():
    assert len(REGISTRY) >= 10
    assert "find_connector" in REGISTRY
    assert "validate_yaml" in REGISTRY


def test_anthropic_schema_shape():
    schemas = anthropic_tools()
    for s in schemas:
        assert set(s) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
        assert isinstance(s["input_schema"]["properties"], dict)
        assert isinstance(s["input_schema"]["required"], list)


def test_dispatch_find_connector():
    out = dispatch("find_connector", {"q": "jira", "limit": 3})
    assert isinstance(out, dict)
    assert isinstance(out["matches"], list)
    assert len(out["matches"]) <= 3


def test_dispatch_unknown_tool_returns_error():
    out = dispatch("does_not_exist", {})
    assert isinstance(out, dict) and "error" in out


def test_dispatch_bad_args_returns_error():
    out = dispatch("find_connector", {"unexpected_kw": 1})
    assert isinstance(out, dict) and "error" in out


def test_validate_yaml_tool_via_dispatch():
    res = dispatch("validate_yaml", {"yaml_text": "x: 1"})
    assert isinstance(res, dict)
    assert "ok" in res
