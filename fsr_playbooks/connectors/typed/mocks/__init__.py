"""Mock fixtures for the soarshelf Microsoft Graph security connectors.

Shaped for the compiler's mock envelope rule (``linter._MOCK_ENVELOPE_STEP_TYPES``):
under ``--mock`` a connector step's ``mock_result`` is returned VERBATIM with NO
``{data, status, message, operation}`` envelope, so a downstream reference reads
``vars.steps.<Step>.<field>`` -- every fixture here is therefore the op's raw
return payload (the Graph JSON body, or the aggregation dict the connector's
thread pool builds), never an envelope. A playbook may still wrap one as
``{"data": <fixture>}`` when it wants ``.data`` references to work in mock runs;
the linter skips its warning when mock_result carries a top-level ``data`` key.

Every fixture is a SYNTHETIC sanitized shape: tenant id
``00000000-0000-0000-0000-000000000000``, ``@contoso.example`` users, RFC 5737
TEST-NET addresses, no real hostnames. Provenance for the whole set:
``source-derived (sanitized synthetic shapes, operations.py v3.1.0 /
v1.0.0), live-capture pending`` -- replace with promoted captures as they
land (``scratch/captures/<connector>/<op>.json`` is the raw-capture spot).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MOCKS_DIR = Path(__file__).resolve().parent

#: op -> fixture path (relative to this directory). ``@V2`` marks a variant
#: fixture for the op's alternate mode; the bare op name is the default mock.
MOCK_FIXTURES: dict[str, dict[str, str]] = {
    "microsoft-graph_dev": {
        "get_risky_users_list": "microsoft_graph_dev/get_risky_users_list.json",
        "get_risky_user_details": "microsoft_graph_dev/get_risky_user_details.json",
        "get_all_security_alerts": "microsoft_graph_dev/get_all_security_alerts.json",
        "get_all_security_alerts@V2": "microsoft_graph_dev/get_all_security_alerts_v2.json",
        "get_security_alert": "microsoft_graph_dev/get_security_alert.json",
        "get_security_alert@V1": "microsoft_graph_dev/get_security_alert_v1.json",
        "update_security_alert": "microsoft_graph_dev/update_security_alert.json",
        "add_comment_on_security_alert": "microsoft_graph_dev/add_comment_on_security_alert.json",
        "get_groups": "microsoft_graph_dev/get_groups.json",
        "get_group_users": "microsoft_graph_dev/get_group_users.json",
        "search_message": "microsoft_graph_dev/search_message.json",
        "del_message": "microsoft_graph_dev/del_message.json",
        "del_message_bulk": "microsoft_graph_dev/del_message_bulk.json",
        "revoke_user_sessions": "microsoft_graph_dev/revoke_user_sessions.json",
        "get_all_named_locations": "microsoft_graph_dev/get_all_named_locations.json",
        "block_new_ips": "microsoft_graph_dev/block_new_ips.json",
        "unblock_new_ips": "microsoft_graph_dev/unblock_new_ips.json",
        "create_ip_range_location": "microsoft_graph_dev/create_ip_range_location.json",
        "get_security_incidents": "microsoft_graph_dev/get_security_incidents.json",
    },
    "microsoft-graph-api-security": {
        "get_security_incidents": "microsoft_graph_api_security/get_security_incidents.json",
        "get_security_alerts": "microsoft_graph_api_security/get_security_alerts.json",
        "get_security_alert": "microsoft_graph_api_security/get_security_alert.json",
        "update_security_incident": "microsoft_graph_api_security/update_security_incident.json",
        "run_advanced_hunting": "microsoft_graph_api_security/run_advanced_hunting.json",
    },
    "microsoft-365-defender": {
        "list_incidents": "microsoft-365-defender/list_incidents.json",
        "get_incident": "microsoft-365-defender/get_incident.json",
        "update_incident": "microsoft-365-defender/update_incident.json",
        "advanced_hunting": "microsoft-365-defender/advanced_hunting.json",
    },
}

#: Shared Graph error envelopes. The same bodies serve both connectors:
#: microsoft-graph_dev embeds them in its ``Fail To request API ...``
#: ConnectorError text; microsoft-graph-api-security raises
#: ``Microsoft Graph Error | Status=... | Code=... | Message=...``.
#: The ``m365def-`` bodies are the microsoft-365-defender connector's own
#: shapes (its ConnectorError text is the third format,
#: ``Response [code:reason Details: message]``); they live under the
#: connector's own directory, not the shared ``errors/``.
ERROR_FIXTURES: dict[str, str] = {
    "graph-401-invalid-token": "errors/graph-401-invalid-token.json",
    "graph-403-forbidden": "errors/graph-403-forbidden.json",
    "graph-404-not-found": "errors/graph-404-not-found.json",
    "graph-429-throttled": "errors/graph-429-throttled.json",
    "aadsts-7000215-invalid-secret": "errors/aadsts-7000215-invalid-secret.json",
    "aadsts-700016-app-not-found": "errors/aadsts-700016-app-not-found.json",
    "m365def-401-unauthorized": "microsoft-365-defender/errors/api_401_unauthorized.json",
    "m365def-403-forbidden": "microsoft-365-defender/errors/api_403_forbidden.json",
    "m365def-403-not-provisioned": "microsoft-365-defender/errors/api_403_not_provisioned.json",
    "m365def-404-incident-not-found": "microsoft-365-defender/errors/api_404_incident_not_found.json",
    "m365def-429-throttled": "microsoft-365-defender/errors/api_429_throttled.json",
    "m365def-400-bad-query": "microsoft-365-defender/errors/api_400_bad_query.json",
    "m365def-aadsts-7000215-invalid-secret": "microsoft-365-defender/errors/token_aadsts_invalid_client.json",
}


def load_mock(connector: str, op: str) -> dict[str, Any]:
    """Load one op's mock fixture as a dict."""
    try:
        rel = MOCK_FIXTURES[connector][op]
    except KeyError:
        raise KeyError(
            f"no mock fixture for {connector}.{op}; known ops: "
            f"{sorted(MOCK_FIXTURES.get(connector, {}))}"
        ) from None
    parsed: dict[str, Any] = json.loads((_MOCKS_DIR / rel).read_text())
    return parsed


def mock_result_json(connector: str, op: str) -> str:
    """The fixture as the exact JSON text to paste into a step's
    ``mock_result: |`` block."""
    return json.dumps(load_mock(connector, op))


def load_error_fixture(key: str) -> dict[str, Any]:
    """Load one shared error envelope as a dict."""
    try:
        rel = ERROR_FIXTURES[key]
    except KeyError:
        raise KeyError(
            f"no error fixture {key!r}; known: {sorted(ERROR_FIXTURES)}"
        ) from None
    parsed: dict[str, Any] = json.loads((_MOCKS_DIR / rel).read_text())
    return parsed


__all__ = [
    "MOCK_FIXTURES",
    "ERROR_FIXTURES",
    "load_mock",
    "mock_result_json",
    "load_error_fixture",
]
