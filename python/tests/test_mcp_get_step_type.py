"""mcp_server.get_step_type — short-name mapping, friendly_form
coverage, and slim-vs-verbose payload caps.

Token cost was the driver: a single naïve `get_step_type('manual_input')`
used to return ~5 KB and `code_snippet` returned 18 KB (one corpus
example contained a giant inline Python blob). Slim mode drops both
to ~1–2 KB by omitting raw corpus examples in favor of the curated
`friendly_form` block.
"""
from __future__ import annotations

import json

import pytest

# `mcp_server` imports `mcp.server.fastmcp.FastMCP` at module load.
# Skip this whole file gracefully on environments without the mcp
# package installed — the get_step_type behavior it tests is exercised
# indirectly by the chat / resolver tests.
pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import fsr_core.mcp_server as mcp_server  # noqa: E402


# Every short type listed in resolver.SHORT_TYPE_TO_FSR — this is the
# contract the `friendly_form` coverage promises.
SHORT_TYPES = [
    "start", "start_on_create", "start_on_update",
    "set_variable", "decision", "connector", "stop", "end",
    "find_record", "create_record", "insert_record", "update_record",
    "delay", "manual_input", "code_snippet", "workflow_reference",
    "approval",
]


def _size(obj) -> int:
    return len(json.dumps(obj, default=str))


# ---- short-name mapping ------------------------------------------

def test_short_name_resolves_to_canonical():
    r = mcp_server.get_step_type("manual_input")
    assert r["name"] == "ManualInput"


def test_canonical_name_still_resolves():
    """Existing callers using the canonical name must keep working."""
    r = mcp_server.get_step_type("ManualInput")
    assert r["name"] == "ManualInput"


def test_all_short_types_resolve():
    """Every short type the resolver knows about should resolve via
    get_step_type — otherwise the AI's tool call dead-ends."""
    for n in SHORT_TYPES:
        r = mcp_server.get_step_type(n)
        assert "error" not in r, f"{n} → {r.get('error')}"
        assert r.get("name"), f"{n} returned no canonical name"


# ---- friendly_form coverage --------------------------------------

def test_every_short_type_carries_markdown_or_examples():
    """Slim mode returns a `markdown` skeleton for types with a
    friendly_form; the rest fall back to corpus examples. Either way,
    the response must give the agent something to author against."""
    for n in SHORT_TYPES:
        r = mcp_server.get_step_type(n)
        assert "markdown" in r or "examples" in r, (
            f"{n}: no markdown and no examples — nothing to author against"
        )


def test_markdown_carries_yaml_skeleton():
    """The slim markdown response must include a fenced YAML skeleton
    the agent can copy. Without it, the model has to reconstruct shape
    from prose."""
    r = mcp_server.get_step_type("manual_input")
    md = r["markdown"]
    assert "```yaml" in md
    assert "type: manual_input" in md


def test_manual_input_markdown_warns_about_traps():
    """`pitfalls` section lists the wrong-shape mistakes the resolver
    hard-rejects. Keep them aligned."""
    r = mcp_server.get_step_type("manual_input")
    md = r["markdown"]
    assert "textarea" in md
    assert "label" in md
    assert "message" in md


# ---- slim vs verbose payload size --------------------------------

def test_default_response_is_slim():
    """manual_input slim is well under the old 5 KB and nowhere near
    the 18 KB code_snippet hit."""
    r = mcp_server.get_step_type("manual_input")
    assert _size(r) < 2800, f"manual_input slim is {_size(r)} chars"


def test_code_snippet_default_avoids_18k_blob():
    r = mcp_server.get_step_type("code_snippet")
    assert _size(r) < 1500, (
        f"code_snippet slim is {_size(r)} chars — corpus blob leaking "
        f"through?"
    )


def test_default_omits_raw_corpus_examples_when_friendly_form_present():
    r = mcp_server.get_step_type("manual_input")
    # Slim path drops the corpus examples entirely — the markdown
    # skeleton has the only example the LLM needs.
    assert "examples" not in r
    assert "markdown" in r


def test_verbose_returns_full_corpus():
    """verbose=True is the escape hatch for cases the friendly form
    doesn't cover; it must include the raw corpus examples."""
    r = mcp_server.get_step_type("manual_input", verbose=True)
    assert "examples" in r
    assert isinstance(r["examples"], list)
    assert _size(r) > _size(mcp_server.get_step_type("manual_input"))


def test_step_type_without_friendly_form_still_returns_examples():
    """Step types that aren't in _FRIENDLY_FORMS (like ManualDecision,
    ApprovalManualInput) should still get a corpus example so the AI
    has something to anchor on."""
    r = mcp_server.get_step_type("ManualTask")
    assert "examples" in r
