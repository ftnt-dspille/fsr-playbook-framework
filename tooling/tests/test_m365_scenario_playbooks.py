"""Offline gates for ``scenarios/*/playbooks`` (the M365 scenario set).

Three layers, all offline (the fixture reference DB, no connector configured,
no live FSR):

1. **compile** -- every scenario ``playbooks.yaml`` compiles with zero
   error-severity findings and only unknown-connector-class warnings (the
   fixture DB ships no Microsoft connectors, so ``unknown_connector`` is the
   expected warning there, not a defect).
2. **run** -- every scenario steps through end-to-end in the offline
   simulator: both manual-approval branches plus each scenario's no-op and
   degraded branches, asserting which response steps ran, which did not, and
   the terminal ``outcome`` variable.
3. **mock fidelity** -- every connector step carries a ``mock_result`` in the
   production ``{data, status, message, operation}`` envelope, and every
   payload validates through the typed op models
   (``fsr_playbooks.connectors.typed``) -- proving the hand-adapted mock
   payloads stayed on-model.

The committed ``playbooks.json`` artefacts are also pinned: a fresh compile of
the YAML must reproduce them byte-for-byte modulo ``lastModifyDate`` (which
``build.py`` pins to the YAML's mtime), so a stale artefact fails the gate.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

pytest.importorskip(
    "mcp",
    reason="mcp package not installed (pip install mcp)",
)

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402
import fsr_playbooks.mcp_server._shared  # noqa: E402,F401
from fsr_playbooks.compiler import compile_yaml  # noqa: E402
from fsr_playbooks.connectors.typed.microsoft_365_defender import (  # noqa: E402
    OPERATION_MODELS as DEFENDER_OPS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (  # noqa: E402
    OPERATION_MODELS as DEV_OPS,
)

REPO = Path(__file__).resolve().parents[2]
SCENARIOS = REPO / "scenarios"

#: The fixture DB has no Microsoft connectors, so these are the only warnings
#: a clean compile may carry.
LAX_CODES = {"unknown_connector", "unknown_operation", "unknown_param"}

#: scenario dir -> (collection yaml path, compiled artefact path)
_SCENARIO_FILES = {
    "microsoft-graph_dev": ("playbooks/playbooks.yaml", "playbooks/playbooks.json"),
    "microsoft-365-defender": ("playbooks/playbooks.yaml", "playbooks/playbooks.json"),
}

_TYPED_OPS = {
    "microsoft-graph_dev": DEV_OPS,
    "microsoft-365-defender": DEFENDER_OPS,
}


@pytest.fixture(autouse=True)
def _no_live_fsr(monkeypatch):
    """Force the stepper offline: mock_result is the only connector output."""
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)


def _scenario_yaml(connector: str) -> Path:
    return SCENARIOS / connector / _SCENARIO_FILES[connector][0]


def _scenario_json(connector: str) -> Path:
    return SCENARIOS / connector / _SCENARIO_FILES[connector][1]


def _code_of(error) -> str:
    """Normalize a CompileError's code to its plain name."""
    code = error.code
    value = getattr(code, "value", None)
    if isinstance(value, str):
        return value
    return str(getattr(code, "name", code)).lower()


def _trace_by_id(result: dict) -> dict[str, dict]:
    return {record["step_id"]: record for record in result["trace"]}


def _terminal_outputs(result: dict) -> list[dict]:
    """Every step output that carries an ``outcome`` (the terminal set_variable)."""
    return [r["output"] for r in result["trace"]
            if isinstance(r.get("output"), dict) and "outcome" in r["output"]]


# ---- 1. compile --------------------------------------------------------


@pytest.mark.parametrize("connector", sorted(_SCENARIO_FILES))
def test_scenario_yaml_compiles_clean(connector: str, db_path):
    """Zero error-severity findings; only unknown-connector-class warnings."""
    res = compile_yaml(_scenario_yaml(connector).read_text(), db_path,
                       lax_codes=LAX_CODES)
    errors = [e for e in res.errors if getattr(e, "severity", "") == "error"]
    assert res.ok and not errors, [e.to_dict() for e in res.errors]
    unexpected = [(_code_of(e), e.message) for e in res.errors
                  if _code_of(e) not in LAX_CODES]
    assert not unexpected, unexpected


@pytest.mark.parametrize("connector", sorted(_SCENARIO_FILES))
def test_compiled_json_matches_yaml(connector: str, db_path):
    """The committed playbooks.json is not stale vs its playbooks.yaml.

    Compares modulo the fields the compiler derives from the environment
    rather than the document:

    - ``lastModifyDate`` -- build.py pins it to the YAML's mtime, which
      necessarily differs between the build machine and this run.
    - ``config`` -- re-derived per appliance from the ``connector_configs``
      catalog; ``""`` is the documented "use the default configuration"
      sentinel (compiler/prewrite.py), and shipped artefacts carry ``""``.
    - the connector-step display envelope (``name``/``operationTitle``/
      ``version``/``step_variables``/``pickFromTenant``) -- stamped from
      catalog rows only when the catalog knows the connector
      (compiler/resolver/connector_args.py); a build on a warmed catalog
      carries it, one on a cold catalog does not. The scenario YAMLs author
      none of these keys on connector steps, so anything present is
      re-derived.
    """
    res = compile_yaml(_scenario_yaml(connector).read_text(), db_path,
                       lax_codes=LAX_CODES)

    _STAMPED = {"version", "name", "operationTitle", "step_variables",
                "pickFromTenant"}

    def _normalize(doc):
        doc = copy.deepcopy(doc)

        def _walk(n):
            if isinstance(n, dict):
                n.pop("lastModifyDate", None)
                if "connector" in n and "operation" in n:
                    # Connector-step arguments: strip the catalog-stamped
                    # envelope, collapse the per-appliance config id.
                    for key in _STAMPED:
                        n.pop(key, None)
                    if isinstance(n.get("config"), str):
                        n["config"] = "<config>"
                for v in n.values():
                    _walk(v)
            elif isinstance(n, list):
                for v in n:
                    _walk(v)

        _walk(doc)
        return json.dumps(doc, indent=2) + "\n"

    fresh = _normalize(res.fsr_json)
    committed = _normalize(json.loads(_scenario_json(connector).read_text()))
    assert fresh == committed, (
        f"{_scenario_json(connector)} is stale: rebuild it with its build.py"
    )


# ---- 2. run ------------------------------------------------------------


_MANUAL_BRANCH = {
    "graph": "Approval",
    "defender": "Approval",
}

_BRANCH_CASES = [
    # Scenario A - compromised-user response (microsoft-graph_dev).
    {
        "id": "A-approve-blocks",
        "yaml": "microsoft-graph_dev",
        "playbook": "Respond to Compromised User Report",
        "manual": {"Approval": "approve"},
        "present": ["Revoke Sessions", "Find Named Location", "Block IPs",
                    "Close Out Blocked"],
        "absent": ["Close Out Rejected"],
        "outcome": "contained",
        "terminal_extra": {"blocked_ip": "198.51.100.7"},
    },
    {
        "id": "A-approve-no-named-location",
        "yaml": "microsoft-graph_dev",
        "playbook": "Respond to Compromised User Report",
        "manual": {"Approval": "approve"},
        "branches": {"Named Location Found":
                     "Named location missing or not an IP location"},
        "present": ["Revoke Sessions", "Close Out No Block"],
        "absent": ["Block IPs"],
        "outcome": "contained_no_block",
    },
    {
        "id": "A-reject",
        "yaml": "microsoft-graph_dev",
        "playbook": "Respond to Compromised User Report",
        "manual": {"Approval": "reject"},
        "present": ["Close Out Rejected"],
        "absent": ["Revoke Sessions", "Block IPs"],
        "outcome": "not_approved",
    },
    {
        "id": "A-nothing-actionable",
        "yaml": "microsoft-graph_dev",
        "playbook": "Respond to Compromised User Report",
        "branches": {"Risky Users Found": "Nothing actionable"},
        "present": [],
        "absent": ["Revoke Sessions", "Block IPs"],
        "outcome": "no_action_taken",
    },
    # Scenario B - Defender incident triage (microsoft-365-defender).
    {
        "id": "B-approve-responds",
        "yaml": "microsoft-365-defender",
        "playbook": "Triage Defender Incident to Response",
        "manual": {"Approval": "approve"},
        "present": ["Get Incident", "Device Hunt", "Create SOAR Alert",
                    "Update Incident", "Block IPs", "Revoke Sessions"],
        "absent": ["Reject Comment"],
        "outcome": "responded",
        "terminal_extra": {"incident_id": "9"},
    },
    {
        "id": "B-reject-holds",
        "yaml": "microsoft-365-defender",
        "playbook": "Triage Defender Incident to Response",
        "manual": {"Approval": "reject"},
        "present": ["Reject Comment"],
        "absent": ["Update Incident", "Block IPs", "Revoke Sessions"],
        "outcome": "held",
    },
    {
        "id": "B-nothing-to-triage",
        "yaml": "microsoft-365-defender",
        "playbook": "Triage Defender Incident to Response",
        "branches": {"Incidents Found": "Nothing to triage"},
        "present": [],
        "absent": ["Get Incident", "Update Incident"],
        "outcome": "nothing_to_triage",
    },
    # Scenario C - phishing mail purge (microsoft-graph_dev). The purge mock
    # carries one 404 in Error_List (the fixture's already-gone copy), so the
    # default approve run lands on the PARTIAL branch; the clean branch is
    # pinned explicitly.
    # Scenario D - Defender endpoint response (microsoft-365-defender). The
    # analyst gate is a plain manual_input; each option is one containment.
    {
        "id": "D-isolate-responds",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "manual": {"Analyst Gate": "isolate"},
        "present": ["Get Incident", "Pick Device", "Get Machine", "Isolate Device",
                    "Note Isolation", "Settle Action", "Poll Action", "Action Result",
                    "Record Response", "Responded"],
        "absent": ["Run AV Scan", "Collect Package", "Record No Action",
                   "Close Not Onboarded", "Close No Device"],
        "outcome": "responded",
        "terminal_extra": {"action_name": "isolate", "final_status": "Succeeded"},
    },
    {
        "id": "D-av-scan-responds",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "manual": {"Analyst Gate": "av scan"},
        "present": ["Run AV Scan", "Note AV Scan", "Settle Action", "Poll Action",
                    "Record Response", "Responded"],
        "absent": ["Isolate Device", "Collect Package", "Record No Action"],
        "outcome": "responded",
        "terminal_extra": {"action_name": "av_scan"},
    },
    {
        "id": "D-collect-responds",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "manual": {"Analyst Gate": "collect package"},
        "present": ["Collect Package", "Note Package", "Settle Action", "Poll Action",
                    "Record Response", "Responded"],
        "absent": ["Isolate Device", "Run AV Scan", "Record No Action"],
        "outcome": "responded",
        "terminal_extra": {"action_name": "collect_package"},
    },
    {
        "id": "D-no-action-records",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "manual": {"Analyst Gate": "no action"},
        "present": ["Record No Action", "Close No Action"],
        "absent": ["Isolate Device", "Run AV Scan", "Collect Package", "Poll Action",
                   "Record Response"],
        "outcome": "no_action",
    },
    {
        "id": "D-not-onboarded",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "branches": {"Onboarded": "Not onboarded or record unreadable"},
        "present": ["Close Not Onboarded"],
        "absent": ["Analyst Gate", "Isolate Device", "Run AV Scan", "Collect Package"],
        "outcome": "not_onboarded",
    },
    {
        "id": "D-no-device",
        "yaml": "microsoft-365-defender",
        "playbook": "Respond to Defender Endpoint Incident",
        "branches": {"Device Found": "No device in the evidence"},
        "present": ["Close No Device"],
        "absent": ["Get Machine", "Analyst Gate"],
        "outcome": "no_device",
    },
    {
        "id": "C-approve-partial",
        "yaml": "microsoft-graph_dev",
        "playbook": "Purge Reported Phishing Mail",
        "manual": {"Approval": "approve"},
        "present": ["Build Delete Targets", "Purge Mail", "Close Out Partial"],
        "absent": ["Reject Comment", "Close Out Purged"],
        "outcome": "purged_with_errors",
        "terminal_extra": {"deleted_count": 1, "error_count": 1},
    },
    {
        "id": "C-approve-clean",
        "yaml": "microsoft-graph_dev",
        "playbook": "Purge Reported Phishing Mail",
        "manual": {"Approval": "approve"},
        "branches": {"Purge Checked": "All deletions succeeded"},
        "present": ["Purge Mail", "Close Out Purged"],
        "absent": ["Close Out Partial"],
        "outcome": "purged",
    },
    {
        "id": "C-reject",
        "yaml": "microsoft-graph_dev",
        "playbook": "Purge Reported Phishing Mail",
        "manual": {"Approval": "reject"},
        "present": ["Reject Comment"],
        "absent": ["Purge Mail"],
        "outcome": "not_approved",
    },
    {
        "id": "C-no-mail",
        "yaml": "microsoft-graph_dev",
        "playbook": "Purge Reported Phishing Mail",
        "branches": {"Messages Found": "No matched mail"},
        "present": [],
        "absent": ["Purge Mail", "Reject Comment"],
        "outcome": "no_mail_found",
    },
]


@pytest.mark.parametrize("case", _BRANCH_CASES, ids=lambda c: c["id"])
def test_scenario_branches_run_end_to_end(case: dict):
    """Each approval / no-op / degraded branch routes to its terminal outcome."""
    yaml_text = _scenario_yaml(case["yaml"]).read_text()
    result = mcp_server.step_through_playbook(
        yaml_text=yaml_text,
        playbook=case["playbook"],
        manual_choices=case.get("manual"),
        branch_choices=case.get("branches"),
        execute_safe_ops=False,
    )
    assert result["ok"], result.get("first_error")
    by_id = _trace_by_id(result)

    ran = list(by_id)
    for name in case["present"]:
        assert name in by_id, f"expected {name!r} to run; trace ran {ran}"
    for name in case["absent"]:
        assert name not in by_id, f"{name!r} must not run on this branch"

    terminals = _terminal_outputs(result)
    matching = [t for t in terminals if t["outcome"] == case["outcome"]]
    assert matching, (
        f"no terminal reached outcome {case['outcome']!r}; "
        f"terminals: {[t['outcome'] for t in terminals]}"
    )
    for key, want in case.get("terminal_extra", {}).items():
        assert matching[0].get(key) == want, (
            f"terminal {key} = {matching[0].get(key)!r}, want {want!r}"
        )


# ---- 3. mock fidelity --------------------------------------------------


@pytest.mark.parametrize("connector", sorted(_SCENARIO_FILES))
def test_every_connector_step_carries_mock_envelope(connector: str):
    """Connector/create_record steps mock in the production envelope; snippet
    mocks carry ``code_output``; decision/manual/set_variable steps carry none."""
    doc = yaml.safe_load(_scenario_yaml(connector).read_text())
    for pb in doc["playbooks"]:
        for step in pb["steps"]:
            mock = step.get("mock_result")
            if step["type"] in ("connector", "create_record"):
                assert mock is not None, (
                    f"{pb['name']} step {step['name']!r}: connector steps must "
                    f"carry a mock_result (the mock run has no connector)"
                )
                for key in ("data", "status", "message", "operation"):
                    assert key in mock, (
                        f"{pb['name']} step {step['name']!r}: mock_result lacks "
                        f"{key!r} (the envelope downstream .data refs rely on)"
                    )
            elif step["type"] == "code_snippet":
                assert mock is not None, (
                    f"{pb['name']} step {step['name']!r}: snippet steps must "
                    f"carry a mock_result so the offline run sees code_output"
                )
                assert "code_output" in mock.get("data", {}), (
                    f"{pb['name']} step {step['name']!r}: snippet mock must "
                    f"carry data.code_output (the production wrapper shape)"
                )
            else:
                assert mock is None, (
                    f"{pb['name']} step {step['name']!r}: {step['type']} steps "
                    f"take no mock_result"
                )


@pytest.mark.parametrize("connector", sorted(_SCENARIO_FILES))
def test_mock_payloads_validate_against_typed_models(connector: str):
    """Every embedded mock payload parses through its op's typed output model.

    The payloads are hand-adapted fixture copies (branch coherence tweaks);
    this is the check that the adaptations stayed on-model.
    """
    models_by_connector = _TYPED_OPS
    doc = yaml.safe_load(_scenario_yaml(connector).read_text())
    from pydantic import TypeAdapter

    checked = 0
    for pb in doc["playbooks"]:
        for step in pb["steps"]:
            if step["type"] != "connector":
                continue
            step_models = models_by_connector[step["connector"]]
            mock = step["mock_result"]
            op = mock["operation"]
            assert op in step_models, (
                f"{pb['name']} step {step['name']!r}: {op} has no typed model"
            )
            TypeAdapter(step_models[op]).validate_python(mock["data"])
            checked += 1
    assert checked >= 7  # graph_dev: 12; defender-native: 4


def test_scenario_b_cross_connector_steps_use_real_ops():
    """Scenario B's Graph-side steps name real microsoft-graph_dev ops.

    The flagship playbook runs two connectors; this pins that its Graph steps
    route to ops the graph_dev typed module actually ships.
    """
    doc = yaml.safe_load(_scenario_yaml("microsoft-365-defender").read_text())
    graph_ops = set(DEV_OPS)
    seen = []
    for step in doc["playbooks"][0]["steps"]:
        if step["type"] == "connector" and step.get("connector") == "microsoft-graph_dev":
            op = step["operation"]
            assert op in graph_ops, f"{step['name']!r}: {op} is not a graph_dev op"
            seen.append(op)
    assert set(seen) == {"block_new_ips", "revoke_user_sessions",
                         "add_comment_on_security_alert"}


def test_scenario_d_failed_machine_action_reaches_action_failed():
    """A machine action Defender finishes as Failed must not report success.

    The offline run cannot choose a poll result, so the poll's mock status is
    rewritten to Failed in a copy of the scenario YAML before stepping through.
    """
    doc = yaml.safe_load(_scenario_yaml("microsoft-365-defender").read_text())
    pb = next(p for p in doc["playbooks"] if p["name"] == "Respond to Defender Endpoint Incident")
    poll = next(st for st in pb["steps"] if st["name"] == "Poll Action")
    poll["mock_result"]["data"]["status"] = "Failed"
    result = mcp_server.step_through_playbook(
        yaml_text=yaml.safe_dump(doc, sort_keys=False),
        playbook="Respond to Defender Endpoint Incident",
        manual_choices={"Analyst Gate": "av scan"},
        execute_safe_ops=False,
    )
    assert result["ok"], result.get("first_error")
    outcomes = [t["outcome"] for t in _terminal_outputs(result)]
    assert outcomes == ["action_failed"], outcomes
