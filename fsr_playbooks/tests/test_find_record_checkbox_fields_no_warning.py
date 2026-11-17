"""A find_record step must not warn about `checkboxFields` -- the compiler wrote it.

The find_record normalizer calls ``a.setdefault("checkboxFields", False)`` on
every find_record step, because the editor deletes ``__selectFields`` when that
flag is absent. ``arg_validator`` then walked the same arguments against the
``find_data(module, query, partial=True, **kw)`` signature and warned that
``checkboxFields`` was an unknown argument.

So every find_record step in every playbook carried a warning about a key no
author had written, and which the compiler could not have omitted. Across the
demo suite that was 8 of 14 playbooks. A diagnostic that fires on correct,
compiler-generated output trains the reader to skim the warning list, which is
where the real ones (a Fetch step with no ``mock_result``) also live.
"""
from __future__ import annotations

from pathlib import Path

from fsr_playbooks.compiler import compile_yaml

DB = Path(__file__).resolve().parents[2] / "tooling" / "tests" / "fixtures" / "tooling_reference.db"

_YAML = """
collection: X
visible: true
playbooks:
  - name: T
    is_active: true
    steps:
      - name: trigger
        type: start
        next: S1
      - name: S1
        type: find_record
        module: alerts
        select: [name, severity]
        filters:
          - field: name
            operator: eq
            value: hello
"""


def _compile():
    res = compile_yaml(_YAML, DB)
    assert res.ok, [e.message for e in res.errors if e.severity == "error"]
    return res


def test_checkbox_fields_draws_no_unknown_param_warning():
    res = _compile()
    offenders = [
        e for e in res.errors
        if str(getattr(e.code, "value", e.code)).endswith("unknown_param")
        and "checkboxFields" in e.message
    ]
    assert offenders == [], [e.message for e in offenders]


def test_checkbox_fields_is_still_emitted_on_the_wire():
    # The allowlist must silence the warning WITHOUT changing what compiles --
    # if this key stops being emitted, the editor drops the projection.
    step = next(
        s for s in _compile().fsr_json["data"][0]["workflows"][0]["steps"]
        if s["name"] == "S1"
    )
    assert step["arguments"]["checkboxFields"] is True


def test_a_genuinely_unknown_kwarg_on_find_data_still_warns():
    # The allowlist is per-key, not a blanket amnesty for the handler.
    res = compile_yaml(_YAML.replace("        select: [name, severity]",
                                     "        select: [name, severity]\n        nonsenseArg: 1"), DB)
    assert any(
        str(getattr(e.code, "value", e.code)).endswith("unknown_param")
        and "nonsenseArg" in e.message
        for e in res.errors
    ), [e.message for e in res.errors]
