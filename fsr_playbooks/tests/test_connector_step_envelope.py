"""Connector-step authoring gaps the S3 build-persona eval caught on the box.

The build model, asked to author a connector-action playbook (call a connector
op, map its output onward into a record), failed 3/3 on 206 for two independent
reasons — both fixed here:

  * **params dropped.** It emitted `connector:`/`operation:`/`params:` at the
    step top level (siblings of `type:`) instead of under `arguments:`. The
    compiler already hoisted `connector`/`operation` but NOT `params`, so the op
    compiled with no inputs → a hard `missing_field` on the required param.
    (parser.py: `_STEP_KEYS_BY_TYPE['connector']` + the hoist loop.)

  * **`.data` envelope missing.** It referenced the op output as
    `vars.steps.<step>.<field>`, but a connector result is an ENVELOPE —
    `{data: <op output>, status, message, operation}` — so the field lives at
    `vars.steps.<step>.data.<field>`. The validator's `_step_output_top_keys`
    returned the op's `output_schema` keys as the *top-level* keys, which flagged
    the CORRECT `.data.<field>` path and blessed the broken bare one.
    (validator.py.)

Live-verified envelope: `convert_periodic_time_to_minutes("3 hours")` returns
`{"data": {"minutes": 180}, "status": "Success", "message": "", "operation": null}`
as the step's `vars.steps.<name>` value.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

DB = default_db_path()


def _errs(yaml_text: str):
    return compile_yaml(yaml_text, DB).errors


def _hard(errs):
    return [e for e in errs if getattr(e, "severity", "error") == "error"]


def _warns(errs):
    return [e for e in errs if getattr(e, "severity", "error") == "warning"]


_ALL_TOP_LEVEL = """
collection: t
visible: true
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Convert
        arguments: {module: alerts, button_label: Run}
      - name: Convert
        type: connector
        connector: cyops_utilities
        operation: convert_periodic_time_to_minutes
        params: {periodic_time: 3 hours}
        next: Emit
      - name: Emit
        type: create_record
        arguments:
          module: alerts
          resource: {name: t, description: '{{ vars.steps.Convert.data.minutes }}'}
"""


def _nested(desc_ref: str) -> str:
    return f"""
collection: t
visible: true
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Convert
        arguments: {{module: alerts, button_label: Run}}
      - name: Convert
        type: connector
        next: Emit
        arguments:
          connector: cyops_utilities
          operation: convert_periodic_time_to_minutes
          config: ''
          params: {{periodic_time: 3 hours}}
      - name: Emit
        type: create_record
        arguments:
          module: alerts
          resource: {{name: t, description: '{desc_ref}'}}
"""


def test_top_level_params_are_hoisted_not_dropped():
    """The all-top-level shape the box model emits must compile — `params` is
    hoisted into `arguments:` like `connector`/`operation`, so the required
    param is present and no `missing_field` error fires."""
    errs = _errs(_ALL_TOP_LEVEL)
    hard = _hard(errs)
    assert not hard, f"expected no hard errors, got {[(e.code, e.message) for e in hard]}"
    # And the fix is a warn-and-teach, not silent — a hoist warning mentions params.
    assert any("params" in (e.message or "") and "hoisted" in (e.message or "").lower()
               for e in _warns(errs)), \
        "expected a warn-and-hoist message teaching to nest params under arguments"


def test_correct_data_path_is_not_flagged():
    """`vars.steps.<name>.data.<field>` is the real runtime path — it must NOT
    draw an 'output keys' warning (the bug flagged exactly this correct path)."""
    warns = _warns(_errs(_nested("{{ vars.steps.Convert.data.minutes }}")))
    offenders = [e.message for e in warns
                 if "Convert" in (e.message or "") and "output keys" in (e.message or "")]
    assert not offenders, f"correct .data path wrongly flagged: {offenders}"


def test_bare_field_path_is_auto_fixed_to_the_envelope():
    """`vars.steps.<name>.<field>` (no `.data`) is the broken path the model
    used. Lever A now REWRITES it to `.data.<field>` (warn-and-fix) rather than
    only warning — so the author is not merely steered, the pushed playbook is
    correct. Assert the fix notice is emitted (and no stale 'output keys' warn,
    since the ref is corrected before validate() runs)."""
    warns = _warns(_errs(_nested("{{ vars.steps.Convert.minutes }}")))
    assert any("rewrote" in (e.message or "") and "data.minutes" in (e.message or "")
               for e in warns), "bare .minutes path should be auto-fixed to .data.minutes"
    assert not any("output keys" in (e.message or "") for e in warns), \
        "no stale 'output keys' warning once the ref is rewritten"


# ── Lever A: compile-time output-path auto-correct ──────────────────────────
# The grounding fix alone moved the S3 eval only 0→1/3 — the box model still
# wrote `.result` / `.outputs.result` / bare `.<field>`. This deterministic
# compile-time repair rewrites them to `.data.<field>` when unambiguous, so the
# pushed playbook works regardless of which output-path spelling the model
# emitted (and even when it skips verify_playbook entirely).
import json as _json


def _emit(ref: str) -> str:
    y = f"""
collection: t
visible: true
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Convert Time
        arguments: {{module: alerts, button_label: Run}}
      - name: Convert Time
        type: connector
        next: Emit
        arguments:
          connector: cyops_utilities
          operation: convert_periodic_time_to_minutes
          config: ''
          params: {{periodic_time: 3 hours}}
      - name: Emit
        type: create_record
        arguments:
          module: alerts
          resource: {{name: t, description: '{ref}'}}
"""
    res = compile_yaml(y, DB)
    assert res.fsr_json is not None, [ (e.severity, e.message) for e in res.errors ]
    return _json.dumps(res.fsr_json)


def test_bare_field_ref_is_rewritten_to_data_path():
    blob = _emit("{{ vars.steps.Convert_Time.minutes }}")
    assert "vars.steps.Convert_Time.data.minutes" in blob
    assert "Convert_Time.minutes" not in blob.replace("Convert_Time.data.minutes", "")


def test_result_alias_collapses_to_single_data_field():
    # `.result` on a single-output op is unambiguous → `.data.minutes`.
    blob = _emit("{{ vars.steps.Convert_Time.result }}")
    assert "vars.steps.Convert_Time.data.minutes" in blob
    assert "Convert_Time.result" not in blob


def test_outputs_result_alias_collapses_too():
    blob = _emit("{{ vars.steps.Convert_Time.outputs.result }}")
    assert "vars.steps.Convert_Time.data.minutes" in blob
    assert "Convert_Time.outputs" not in blob


def test_correct_data_path_is_left_untouched():
    blob = _emit("{{ vars.steps.Convert_Time.data.minutes }}")
    assert blob.count("Convert_Time.data.minutes") == 1  # not double-wrapped


def test_envelope_status_key_is_left_untouched():
    blob = _emit("{{ vars.steps.Convert_Time.status }}")
    assert "vars.steps.Convert_Time.status" in blob
    assert "data.status" not in blob
