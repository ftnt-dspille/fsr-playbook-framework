"""Typed-args model for the post-write record-trigger step types
(`start_on_create` / `start_on_update` / `start_on_delete` — FSR handlers
``cybersponse.post_create`` / ``post_update`` / ``post_delete``) — registry
contract, the friendly module->resource/resources transform (single + list
forms, empty-default-to-[alerts, incidents] + warning, per-item catalog
resolve), the when->fieldbasedtrigger expansion, and the new scalar
validation (`module` wrong-typed -> clean BAD_VALUE).

These steps emit to fixed-field trigger wire, so the byte-identical contract
is pinned by the corpus round-trip + wire-shape suites; here we pin the typed
layer directly. `expand_post_create_update` takes the resolver's
`resolve_module_name` as a callback — here a passthrough identity (no catalog)
or a recorder (to assert per-item invocation)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    PostCreateUpdateArgs,
    expand_post_create_update,
    is_modeled,
)


def _ident(raw, _path, _errs):
    """Stand-in for resolver.resolve_module_name (passthrough, no catalog)."""
    return raw


def _expand(args, step_type="start_on_create", errs=None, resolve=None):
    return expand_post_create_update(
        args, step_type, "p.steps[0]", errs if errs is not None else [],
        resolve or _ident,
    )


def test_registry_models_all_three_trigger_types():
    for t in ("start_on_create", "start_on_update", "start_on_delete"):
        assert STEP_ARG_MODELS.get(t) is PostCreateUpdateArgs
        assert is_modeled(t) is True


def test_single_module_to_resource_and_resources():
    out = _expand({"module": "alerts"}, "start_on_create")
    assert out["resource"] == "alerts"
    assert out["resources"] == ["alerts"]
    assert "module" not in out


def test_modules_list_form():
    out = _expand({"modules": ["alerts", "incidents"]}, "start_on_update")
    assert out["resource"] == "alerts"
    assert out["resources"] == ["alerts", "incidents"]
    assert "modules" not in out


def test_no_module_defaults_to_alerts_incidents_with_warning():
    errs: list[CompileError] = []
    out = _expand({}, "start_on_create", errs)
    assert out["resources"] == ["alerts", "incidents"]
    assert out["resource"] == "alerts"
    assert any(
        e.code is ErrorCode.MISSING_FIELD and e.severity == "warning"
        and e.path.endswith("arguments.module")
        for e in errs
    )


def test_resolve_module_called_per_item():
    seen: list[str] = []

    def record(raw, _path, _errs):
        seen.append(raw)
        return raw

    _expand({"modules": ["alerts", "incidents", "indicators"]},
            "start_on_create", resolve=record)
    assert seen == ["alerts", "incidents", "indicators"]


def test_when_compiles_to_fieldbasedtrigger():
    out = _expand(
        {
            "module": "alerts",
            "when": {
                "logic": "AND",
                "filters": [{"field": "name", "op": "like",
                             "value": "%fsrpb_e2e%"}],
            },
        },
        "start_on_create",
    )
    fbt = out["fieldbasedtrigger"]
    assert fbt["logic"] == "AND"
    assert fbt["filters"][0]["field"] == "name"
    assert "when" not in out


def test_no_when_gets_empty_fieldbasedtrigger_default():
    out = _expand({"module": "alerts"}, "start_on_create")
    assert out["fieldbasedtrigger"] == {
        "sort": [], "limit": 30, "logic": "AND", "filters": [],
    }


def test_setdefaults_are_filled():
    out = _expand({"module": "alerts"}, "start_on_create")
    assert out["step_variables"] == {
        "input": {"records": ["{{vars.input.records[0]}}"]}}
    assert out["triggerOnSource"] is True
    assert out["triggerOnReplicate"] is False
    assert out["__triggerLimit"] is True


def test_already_set_fieldbasedtrigger_not_clobbered():
    preset = {"logic": "OR", "filters": []}
    out = _expand(
        {"module": "alerts", "fieldbasedtrigger": preset}, "start_on_create",
    )
    assert out["fieldbasedtrigger"] is preset


def test_already_set_step_variables_not_clobbered():
    sv = {"input": {"records": ["{{vars.input.records}}"]}}
    out = _expand(
        {"module": "alerts", "step_variables": sv}, "start_on_create",
    )
    assert out["step_variables"] is sv


def test_non_string_module_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": [1, 2]}, "start_on_create", errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.module")
        for e in errs
    )


def test_non_dict_returns_none():
    assert expand_post_create_update(
        "nope", "start_on_create", "p", [], _ident) is None


def test_end_to_end_compile_start_on_create(db_path):
    text = """
collection: T
playbooks:
  - name: P
    is_active: true
    steps:
      - name: On Alert Create
        type: start_on_create
        next: Stamp marker
        arguments:
          module: alerts
          when:
            logic: AND
            filters:
              - {field: name, op: like, value: "%marker%"}
      - name: Stamp marker
        type: update_record
        arguments:
          collection: "{{ vars.input.records[0]['@id'] }}"
          module: alerts
          resource:
            description: "marker"
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
