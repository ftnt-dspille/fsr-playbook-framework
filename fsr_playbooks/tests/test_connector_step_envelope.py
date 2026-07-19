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


def test_bare_field_path_is_flagged_toward_the_envelope():
    """`vars.steps.<name>.<field>` (no `.data`) is the broken path the model
    used — the validator must warn so the author is steered to `.data.<field>`."""
    warns = _warns(_errs(_nested("{{ vars.steps.Convert.minutes }}")))
    assert any("minutes" in (e.message or "") and "output keys" in (e.message or "")
               for e in warns), \
        "bare .minutes path should warn (envelope top keys are data/status/message/operation)"
