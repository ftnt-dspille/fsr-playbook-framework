"""A connector step's output is an envelope; reading a field off it directly
renders empty. That is certain, so it blocks.

Live (analyst sim): a reputation gate read
`vars.steps.Check_IP_Reputation.attributes.last_analysis_stats.malicious |
default(0)`. VirusTotal's report sits under `data`, so the condition was always
0, the block never ran -- and the gate only warned, so ready_to_push said yes.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.mcp_server._shared import DB_PATH

_PB = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, module: alerts, next: Lookup}
      - name: Lookup
        type: connector
        connector: virustotal
        operation: query_ip
        params: {ip: 1.2.3.4}
        __MOCK__
        next: Note
      - name: Note
        type: set_variable
        vars:
          hits: "{{ vars.steps.Lookup.__PATH__ }}"
"""


def _codes(path: str, mock: str = "") -> list[tuple[str, str]]:
    res = compile_yaml(_PB.replace("__PATH__", path).replace("__MOCK__", mock), DB_PATH)
    return [(e.severity, e.message) for e in list(res.errors) + list(res.warnings)
            if "output keys" in e.message]


def test_a_field_read_past_the_envelope_blocks():
    # The decision-condition form the sim produced; the op's output shape is
    # unknown, so the compiler's own .data rewrite cannot repair it.
    found = _codes("verdict_stats.malicious")
    assert found and found[0][0] == "error", found
    assert "vars.steps.Lookup.data" in found[0][1]


def test_the_data_path_is_clean():
    assert _codes("data.attributes.last_analysis_stats.malicious") == []


def test_a_mocked_step_whose_mock_has_the_key_only_warns():
    # Two shipped demo playbooks read mock output this way; useMockOutput
    # returns mock_result verbatim. Both the mapping and the JSON-string form.
    for mock in ('mock_result: {verdict_stats: {x: 1}}',
                 'mock_result: \'{"verdict_stats": {"x": 1}}\''):
        found = _codes("verdict_stats.x", mock)
        assert found and found[0][0] == "warning", (mock, found)
