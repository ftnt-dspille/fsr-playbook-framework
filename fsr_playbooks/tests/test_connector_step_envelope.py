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
import re

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


# --------------------------------------------------------------------------
# Missing `vars.` prefix — the third broken form, and the one that was SILENT.
#
# `{{ steps.Convert_Time.result }}` was observed in a live S3 run. FSR exposes
# step output only under `vars`, so a bare `steps.` renders EMPTY at runtime —
# the same silent-blank failure as a dropped `.data`.
#
# It was invisible to every existing check because the whole reference lint
# anchors on `\bvars\.steps\.` (validator.py), so the one error that consists of
# NOT matching the anchor slipped past the machinery built to catch it. Verified
# on the pre-fix code: this form produced zero errors and zero warnings.
# --------------------------------------------------------------------------


def test_bare_steps_prefix_is_repaired():
    blob = _emit("{{ steps.Convert_Time.result }}")
    # Repaired all the way: prefix AND envelope, in one compile.
    assert "vars.steps.Convert_Time.data.minutes" in blob
    assert not re.search(r"(?<![\w.])steps\.", blob), "a bare `steps.` leaked"


def test_bare_steps_prefix_with_bare_field_is_repaired():
    blob = _emit("{{ steps.Convert_Time.minutes }}")
    assert "vars.steps.Convert_Time.data.minutes" in blob
    assert not re.search(r"(?<![\w.])steps\.", blob)


def test_bare_steps_prefix_warns():
    warns = _warns(_errs(_nested("{{ steps.Convert.result }}")))
    assert any("`steps.Convert`" in str(w.message) and "vars.steps" in str(w.message)
               for w in warns), [str(w.message) for w in warns]


def test_bare_steps_prefix_for_unknown_step_is_left_alone():
    """Only a REAL connector step is repaired. An unresolvable name is left for
    the reference lint's hard error — silently inventing a `vars.` prefix for a
    step that does not exist would turn a caught error into a runtime blank."""
    blob = _emit("{{ steps.Unknown_Step.result }}")
    assert "vars.steps.Unknown_Step" not in blob


def test_vars_steps_is_not_double_prefixed():
    """The lookbehind must keep the prefix pass off already-correct refs."""
    blob = _emit("{{ vars.steps.Convert_Time.data.minutes }}")
    assert "vars.vars.steps" not in blob
    assert blob.count("Convert_Time.data.minutes") == 1
