"""OpenAI provider must accept Anthropic-shaped tools (the connector
advertises that shape for triage) and emit the OpenAI function envelope —
regression for the live 400 'Missing required parameter: tools[0].type'."""
from fsr_playbooks.llm.openai_provider import _normalize_tools


def test_converts_anthropic_shape():
    out = _normalize_tools([
        {"name": "get_record", "description": "fetch",
         "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}}},
    ])
    assert out == [{
        "type": "function",
        "function": {"name": "get_record", "description": "fetch",
                     "parameters": {"type": "object",
                                    "properties": {"id": {"type": "string"}}}},
    }]


def test_passes_through_openai_shape():
    t = {"type": "function", "function": {"name": "x", "description": "",
                                          "parameters": {"type": "object", "properties": {}}}}
    assert _normalize_tools([t]) == [t]


def test_drops_nameless_and_nondict():
    assert _normalize_tools([{"description": "no name"}, "junk", 5]) == []


def test_defaults_empty_parameters():
    out = _normalize_tools([{"name": "ping"}])
    assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}
