"""Build-persona verify defaults the safe live-probe ON (S3 lever B2).

`verify_playbook` grounds a connector op's real output envelope by executing
the step — but only for op_safety=='safe' steps (walker gate) and only for
safe categories (run_op refuses others without confirm=True). Since it's a
build-only tool, dispatch() defaults `live_probe=True` so the model needn't
know the flag; an explicit value still wins. Presence of `evidence.live_probes`
is the observable signal the probe path ran.
"""
from fsr_playbooks.llm import tools

_YAML = """
collection: t
visible: true
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Convert Time
        arguments: {module: alerts, button_label: Run}
      - name: Convert Time
        type: connector
        next: Emit
        arguments:
          connector: cyops_utilities
          operation: convert_periodic_time_to_minutes
          config: ''
          params: {periodic_time: 3 hours}
      - name: Emit
        type: create_record
        arguments:
          module: alerts
          resource: {name: t, description: '{{ vars.steps.Convert_Time.data.minutes }}'}
"""


def _evidence(result):
    return result.get("evidence", {}) if isinstance(result, dict) else {}


def test_verify_defaults_live_probe_on():
    r = tools.dispatch("verify_playbook", {"yaml_text": _YAML})
    assert "live_probes" in _evidence(r), \
        "verify_playbook should default live_probe on for the build persona"


def test_explicit_live_probe_false_is_respected():
    r = tools.dispatch("verify_playbook", {"yaml_text": _YAML, "live_probe": False})
    assert "live_probes" not in _evidence(r), \
        "an explicit live_probe=False must win over the default"
