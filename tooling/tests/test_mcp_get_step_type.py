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

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402


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


# ---- regression: parallel name lists drift --------------------------------

def test_manual_input_kinds_match_validator():
    """Regression test for parallel-name-list drift bug.

    The teaching copy (friendly_form.inputs_shape) and the enforcing copy
    (compiler/typed_args/steps/manual_input.py via PicklistMixin._INPUT_FIELD_KINDS)
    must stay in sync. This test ensures that the kinds named in get_step_type's
    response are EXACTLY the ones the validator enforces, so a model authoring
    a step with a missing-or-new kind fails with the same enum the discovery
    tool taught.
    """
    import re
    from fsr_playbooks.compiler.resolver.picklists import PicklistMixin

    # Get the taught list from the discovery tool
    r = mcp_server.get_step_type("manual_input")
    markdown = r.get("markdown", "")
    assert markdown, "manual_input should return markdown in slim response"

    # Extract the kinds from the taught text. The format is:
    # "kind is one of: kind1, kind2, kind3, ... ."
    kinds_match = re.search(r"kind is one of: ([^.]+)\.", markdown)
    assert kinds_match, (
        f"Could not find 'kind is one of:' pattern in markdown; "
        f"taught text: {markdown[:500]!r}"
    )
    taught_kinds = set(k.strip() for k in kinds_match.group(1).split(","))

    # Get the enforced set from the validator
    enforced_kinds = set(PicklistMixin._INPUT_FIELD_KINDS.keys())

    # They must be identical
    assert taught_kinds == enforced_kinds, (
        f"manual_input inputs_shape teaches a different kind set than the "
        f"validator enforces:\n"
        f"  Taught: {sorted(taught_kinds)}\n"
        f"  Enforced: {sorted(enforced_kinds)}\n"
        f"  Missing from taught: {sorted(enforced_kinds - taught_kinds)}\n"
        f"  Extra in taught: {sorted(taught_kinds - enforced_kinds)}\n"
    )


def test_manual_input_option_key_taught_is_the_authoring_key():
    """`display:` is the SURFACE key; `option:` is the WIRE key.

    `parser.py` rewrites `display` → `option` on the way in (same rewrite it
    does for decision `display`/`when`), so BOTH spellings route correctly and
    emit byte-identical FSR JSON. This test exists because that equivalence is
    invisible from the resolver — `normalizers.py` reads only `o.get("option")`,
    which reads like `display` is unsupported and invites someone to "fix" the
    docs by teaching the wire key.

    Teaching `option:` here would be a real regression: `decision` steps teach
    `display:`, so the two branch-bearing step types would disagree on the name
    of the same concept — exactly the parallel-list drift this suite guards.
    Assert the taught key, and prove the synonym is genuinely accepted rather
    than trusting either doc string.
    """
    from fsr_playbooks._db import default_db_path
    from fsr_playbooks.compiler import compile_yaml as _compile

    r = mcp_server.get_step_type("manual_input")
    markdown = r.get("markdown", "")
    assert "{display, next, primary?}" in markdown, (
        "manual_input must teach the surface key `display:` for parity with "
        f"decision steps; got: {markdown[:400]!r}"
    )

    pb = """collection: C
playbooks:
- name: PB
  trigger_step_id: start
  steps:
  - type: start
    name: Start
    module: alerts
    next: Ask
  - type: manual_input
    name: Ask
    arguments:
      title: T
      inputs:
      - {name: f, kind: text, label: F}
    options:
    - {KEY: Approve, primary: true, next: Done}
    - {KEY: Reject, next: Other}
  - type: connector
    name: Done
    arguments: {connector: cyops_utilities, operation: no_op, params: {}}
  - type: connector
    name: Other
    arguments: {connector: cyops_utilities, operation: no_op, params: {}}
"""

    def _routes(key: str):
        res = _compile(pb.replace("KEY", key), default_db_path())
        assert res.ok, f"{key}: {[e.message for e in res.errors]}"
        wf = res.fsr_json["data"][0]["workflows"][0]
        names = {s["uuid"]: s.get("name") for s in wf.get("steps") or []}
        return sorted(
            (str(rt.get("label")),
             names.get(str(rt.get("sourceStep", "")).rsplit("/", 1)[-1]),
             names.get(str(rt.get("targetStep", "")).rsplit("/", 1)[-1]))
            for rt in wf.get("routes") or []
        )

    by_display, by_option = _routes("display"), _routes("option")
    assert by_display == by_option, (
        "display/option are documented as synonyms but route differently:\n"
        f"  display: {by_display}\n  option:  {by_option}"
    )
    # Both buttons must actually reach their targets — a dropped `next:` would
    # leave a prompt whose buttons go nowhere, which still compiles clean.
    assert ("Approve", "Ask", "Done") in by_display
    assert ("Reject", "Ask", "Other") in by_display
