"""grounding_coverage counts the right references against a known-answer corpus.

A measurement module: the test pins the counting logic (grounded vs ungrounded,
what counts as a payload reference, step-key normalization) with a fake store so
it needs no box and the expected numbers are exact."""
from __future__ import annotations

from tooling.evals.corpus_authoring import grounding_coverage as gc


class _FakeStore:
    """Grounds exactly the ops named; everything else is ungrounded."""

    def __init__(self, grounded: set[tuple[str, str]]):
        self._g = grounded

    def shape_for(self, connector: str, op: str):
        return object() if (connector, op) in self._g else None


# Two connector steps (one grounded op, one not), a non-connector step, and a
# set-variable step that references all three. The space in the step name tests
# key normalization (`Get Rep` -> `Get_Rep`).
_YAML = """\
collection: C
playbooks:
- name: P
  steps:
  - {name: Get Rep, type: connector, connector: virustotal, operation: query_ip}
  - {name: Enrich, type: connector, connector: cyops_utilities, operation: get_macro_list}
  - {name: Decide, type: decision}
  - name: Build
    type: set_variable
    values:
      a: "{{ vars.steps.Get_Rep.data.attributes.country }}"
      b: "{{ vars.steps.Enrich.data | join(', ') }}"
      c: "{{ vars.steps.Decide.result }}"
      d: "{{ vars.steps.Get_Rep.status }}"
"""


def test_counts_grounded_ungrounded_and_ignores_non_connector():
    store = _FakeStore({("virustotal", "query_ip")})  # not cyops get_macro_list
    cov = gc.scan_yaml(_YAML, store)
    # a) Get_Rep.data.attributes.country -> connector op, grounded, payload ref
    assert cov.grounded == 1
    # b) Enrich.data|join -> connector op, ungrounded, payload ref
    assert cov.ungrounded == 1
    assert cov.ungrounded_ops["cyops_utilities:get_macro_list"] == 1
    # c) Decide.result -> non-connector step, ignored
    # d) Get_Rep.status -> envelope field, not a payload shape dependency, ignored
    assert cov.total == 2
    assert cov.playbooks_with_refs == 1


def test_hit_rate_and_merge():
    store = _FakeStore({("virustotal", "query_ip")})
    a = gc.scan_yaml(_YAML, store)
    b = gc.scan_yaml(_YAML, store)
    a.merge(b)
    assert a.grounded == 2 and a.ungrounded == 2
    assert a.hit_rate == 0.5
    assert a.ungrounded_ops["cyops_utilities:get_macro_list"] == 2


def test_key_normalization():
    assert gc._key("Get IP Reputation") == "Get_IP_Reputation"
    assert gc._key("Hunt-Indicator (v2)") == "Hunt_Indicator__v2"


def test_payload_ref_discriminates_envelope_from_data():
    assert gc._is_payload_ref(".data")
    assert gc._is_payload_ref(".data.attributes.country")
    assert gc._is_payload_ref(".foo.bar")  # depth >= 2 deep attr
    assert not gc._is_payload_ref(".status")
    assert not gc._is_payload_ref(".message")
