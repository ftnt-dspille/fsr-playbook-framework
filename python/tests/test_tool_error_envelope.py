"""Structured `{ok, code, message, suggestions}` contract for the
LLM-facing MCP tools.

Item 7 of the success ladder: `compile_yaml`, `validate_yaml`, and
`run_op` must return machine-readable error codes + repair hints
instead of prose so any LLM (Claude / GPT-4o-mini / a local model)
can recover deterministically from a tool failure.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import mcp_server  # noqa: E402
from agent import load_system_prompt  # noqa: E402


# --- system prompt ---------------------------------------------------------

def test_system_prompt_loads_from_md():
    text = load_system_prompt()
    assert "FortiSOAR" in text
    assert "validate_yaml" in text
    # Documents the new error contract so the LLM knows to read `code`
    # and `suggestions` rather than regex-parsing the prose message.
    assert "code" in text and "suggestions" in text


def test_web_backend_system_prompt_uses_loader():
    # Importing through the web backend path should yield the SAME text
    # as loading directly — single source of truth.
    from backend.system_prompt import SYSTEM_PROMPT
    assert SYSTEM_PROMPT == load_system_prompt()


# --- compile_yaml / validate_yaml -----------------------------------------

from pathlib import Path

# Use a known-good shipped example so the success-path test stays
# decoupled from compiler schema tweaks.
GOOD_YAML = (Path(__file__).resolve().parents[2] / "examples"
             / "hello_connector.yaml").read_text()

BAD_YAML = """
collection: Envelope Test
playbooks:
  - name: pb
    trigger: { type: manual }
    steps:
      - type: connector
        name: Bad Step
        connector: this_connector_does_not_exist_xyz
        operation: ghost_op
"""


def _check_error_envelope(out: dict) -> None:
    """The contract: every failure returns ok=false, str code, str
    message, and a `suggestions` list (possibly empty)."""
    assert out["ok"] is False
    assert isinstance(out["code"], str) and out["code"]
    assert isinstance(out["message"], str) and out["message"]
    assert isinstance(out["suggestions"], list)


def test_validate_yaml_success():
    out = mcp_server.validate_yaml(GOOD_YAML)
    assert out["ok"] is True


def test_validate_yaml_envelope_on_failure():
    out = mcp_server.validate_yaml(BAD_YAML)
    _check_error_envelope(out)
    assert out["code"] == "validation_failed"
    assert out["errors"]
    # Per-error item: code + path + message + suggestions array.
    e0 = out["errors"][0]
    assert "code" in e0 and "message" in e0
    assert isinstance(e0.get("suggestions"), list)
    # Backward-compat: legacy singular `suggestion` still present.
    assert "suggestion" in e0


def test_compile_yaml_envelope_on_failure():
    out = mcp_server.compile_yaml(BAD_YAML)
    _check_error_envelope(out)
    assert out["code"] == "compile_failed"


# --- run_op ---------------------------------------------------------------

def test_run_op_no_live_fsr_envelope(monkeypatch):
    # Force the live-config check to report unconfigured.
    import probes._env as env

    class _Cfg:
        def is_live(self):
            return False

    monkeypatch.setattr(env, "get_config", lambda: _Cfg())
    out = mcp_server.run_op("any_connector", "any_op")
    _check_error_envelope(out)
    assert out["code"] == "no_live_fsr"
    assert any("FSR_BASE_URL" in s for s in out["suggestions"])


def test_run_op_unknown_connector_envelope(monkeypatch):
    import probes._env as env

    class _Cfg:
        def is_live(self):
            return True

    monkeypatch.setattr(env, "get_config", lambda: _Cfg())
    monkeypatch.setattr(env, "get_client", lambda: object())
    out = mcp_server.run_op("__definitely_not_a_real_connector__", "noop")
    _check_error_envelope(out)
    assert out["code"] == "unknown_connector"
