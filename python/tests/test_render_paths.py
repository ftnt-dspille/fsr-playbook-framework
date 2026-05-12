"""compiler.render_paths — vars.X extractor for the render-path
validator (RENDER_PATH_VALIDATOR_PLAN.md Phase 2).

Tests pin the deepest-chain pruning, location reporting, container
walks, and resilience to malformed templates so the analyzer can rely
on these guarantees in Phase 3.
"""
from __future__ import annotations

import textwrap

from compiler.render_paths import (
    ConsumedPath,
    consumed_paths_dict,
    extract_consumed_paths,
)


def _paths(value, location="arguments"):
    return [(c.path, c.source_step_id, c.location)
            for c in extract_consumed_paths(value, location)]


def test_simple_steps_ref():
    out = _paths("{{ vars.steps.fetch_alert.data.id }}")
    assert out == [
        ("vars.steps.fetch_alert.data.id", "fetch_alert", "arguments"),
    ]


def test_input_ref_has_no_source_step():
    out = _paths("{{ vars.input.params.alert_id }}")
    assert out == [("vars.input.params.alert_id", "", "arguments")]


def test_item_ref_inside_for_each_body():
    out = _paths("{{ vars.item.id }}")
    assert out[0][0] == "vars.item.id"
    assert out[0][1] == ""  # not a steps ref


def test_deepest_chain_only():
    """Walking the AST hits Getattr at every depth — we want only the
    deepest reference per template."""
    out = _paths("{{ vars.steps.a.b.c }}")
    assert len(out) == 1
    assert out[0][0] == "vars.steps.a.b.c"


def test_multiple_distinct_refs_in_one_template():
    tpl = "{{ vars.steps.a.x }} - {{ vars.steps.b.y }}"
    out = _paths(tpl)
    assert {o[0] for o in out} == {
        "vars.steps.a.x", "vars.steps.b.y",
    }


def test_subscript_string_index():
    out = _paths("{{ vars.steps['fetch'].data['id'] }}")
    paths = [o[0] for o in out]
    # subscript lookup with constant string args should still resolve
    assert "vars.steps.fetch.data.id" in paths


def test_subscript_runtime_index_is_skipped():
    """`vars.steps[some_var]` is unresolvable statically — extractor
    drops the chain rather than emit a partial path."""
    out = _paths("{{ vars.steps[vars.input.k].id }}")
    # The outer chain can't resolve, but the inner vars.input.k can.
    paths = [o[0] for o in out]
    assert "vars.input.k" in paths


def test_filter_pipes_dont_break_extraction():
    out = _paths("{{ vars.steps.x.y | upper | default('-') }}")
    assert ("vars.steps.x.y", "x", "arguments") in out


def test_conditional_block():
    tpl = textwrap.dedent("""\
        {% if vars.steps.gate.data.allow %}
          {{ vars.steps.fetch.data.id }}
        {% endif %}""")
    out = _paths(tpl)
    paths = {o[0] for o in out}
    assert "vars.steps.gate.data.allow" in paths
    assert "vars.steps.fetch.data.id" in paths


def test_nested_dict_walk_records_location():
    args = {
        "params": {
            "url": "https://x/{{ vars.steps.a.id }}",
            "headers": {
                "X-Token": "{{ vars.input.params.token }}",
            },
        },
        "list_field": [
            "{{ vars.steps.b.value }}",
            "literal",
        ],
    }
    out = _paths(args)
    by_path = {o[0]: o for o in out}
    assert by_path["vars.steps.a.id"][2] == "arguments.params.url"
    assert by_path["vars.input.params.token"][2] == \
        "arguments.params.headers.X-Token"
    assert by_path["vars.steps.b.value"][2] == "arguments.list_field[0]"


def test_no_template_returns_empty():
    assert _paths("just a literal") == []
    assert _paths(123) == []
    assert _paths(None) == []


def test_malformed_template_does_not_raise():
    # Unclosed `{{` — extractor must swallow and return [].
    assert _paths("{{ vars.steps.x.y") == []


def test_extract_picklist_refs_simple():
    from compiler.render_paths import extract_picklist_refs
    out = extract_picklist_refs(
        "{{ 'AlertStatus' | picklist('Open') }}"
    )
    assert out == [{"picklist": "AlertStatus", "value": "Open",
                    "location": "arguments"}]


def test_extract_picklist_refs_nested_with_locations():
    from compiler.render_paths import extract_picklist_refs
    args = {
        "fields": {
            "status":   "{{ 'AlertStatus' | picklist('Open') }}",
            "severity": "{{ 'Severity' | picklist('Critical') }}",
        },
    }
    out = extract_picklist_refs(args)
    by_pl = {x["picklist"]: x for x in out}
    assert by_pl["AlertStatus"]["location"] == "arguments.fields.status"
    assert by_pl["Severity"]["value"] == "Critical"


def test_extract_picklist_refs_skips_literals_without_filter():
    from compiler.render_paths import extract_picklist_refs
    assert extract_picklist_refs("just text") == []
    assert extract_picklist_refs("{{ vars.steps.x.y }}") == []


def test_consumed_paths_dict_shape():
    out = consumed_paths_dict({"x": "{{ vars.steps.a.b }}"})
    assert out == [{
        "path": "vars.steps.a.b",
        "segments": ["steps", "a", "b"],
        "root": "steps",
        "source_step_id": "a",
        "location": "arguments.x",
    }]


def test_consumed_path_dataclass_is_hashable():
    cp = ConsumedPath(
        path="vars.steps.a.b", segments=("steps", "a", "b"),
        root="steps", source_step_id="a", location="arguments.x",
    )
    assert hash(cp) == hash(cp)  # frozen dataclass


# ---- Integration: the trace records get consumed_paths attached -------

import pytest  # noqa: E402

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed",
)
import mcp_server  # noqa: E402


def test_consumed_paths_attached_to_trace(monkeypatch):
    monkeypatch.setattr(mcp_server, "_live_client", lambda: None)
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: fetch
              - id: fetch
                type: connector
                name: Fetch
                arguments:
                  connector: jira
                  operation: get_ticket_details
                  mock_result:
                    data: {id: 9, summary: ok}
                next: emit
              - id: emit
                type: set_variable
                name: Emit
                arguments:
                  arg_list:
                    - name: ticket_id
                      value: "{{ vars.steps.Fetch.data.id }}"
                    - name: alert
                      value: "{{ vars.input.params.alert_id }}"
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    r = mcp_server.step_through_playbook(yaml)
    by = {rec["step_id"]: rec for rec in r["trace"]}
    emit_paths = {p["path"] for p in by["emit"]["consumed_paths"]}
    assert "vars.steps.Fetch.data.id" in emit_paths
    assert "vars.input.params.alert_id" in emit_paths
