"""Offline typing + mock-fixture gate for the microsoft-365-defender connector.

Pins the typed models in ``fsr_playbooks/connectors/typed/microsoft_365_defender.py``
against the sanitized fixtures in ``typed/mocks/microsoft-365-defender/``:

* every op fixture validates through its per-op output model;
* every error fixture validates through the AADSTS / Defender error models;
* the documented wire quirks (int incident ids, null collections, empty-body
  ``True`` on update, blank-string platform params, the microseconds-only
  datetime format, the stale ``@odata.nextLink``) behave as documented;
* the ``ConnectorError`` message formats match the connector's own string
  formatting exactly -- that string is what a playbook sees on a failed step.

Provenance: source-derived (operations.py), live-capture pending -- the
shapes pinned here come from info.json ``output_schema`` + the connector's own
code. The ``live``-marked block at the bottom re-validates the same models
against the real tenant when ``M365_DEFENDER_*`` creds are in the environment
(and self-skips everywhere else, offline gate included).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from fsr_playbooks.connectors.typed import microsoft_365_defender as m
from fsr_playbooks.connectors.typed.defender_common import (
    AADSTSError,
    DefenderAPIError,
    connector_error_message,
    parse_connector_error_message,
    token_error_connector_message,
)

_TYPED_DIR = Path(__file__).resolve().parents[1] / "connectors" / "typed"
_MOCKS = _TYPED_DIR / "mocks" / "microsoft-365-defender"

_ERRORS = [
    "token_aadsts_invalid_client.json",
    "api_401_unauthorized.json",
    "api_403_forbidden.json",
    "api_404_incident_not_found.json",
    "api_429_throttled.json",
    "api_400_bad_query.json",
]


def _load(name: str) -> dict[str, Any]:
    return json.loads((_MOCKS / name).read_text())


# --- every fixture validates through its model -------------------------------


@pytest.mark.parametrize(
    "fixture_name", ["list_incidents.json", "get_incident.json",
                     "update_incident.json", "advanced_hunting.json"],
)
def test_every_op_fixture_validates_through_its_model(fixture_name: str) -> None:
    body = _load(fixture_name)
    op = fixture_name.removesuffix(".json")
    if op == "update_incident":
        parsed = TypeAdapter(m.UpdateIncidentResponse).validate_python(body)
        assert parsed.status == "Resolved"
        return
    if op == "list_incidents":
        parsed = m.IncidentListResponse.model_validate(body)
        assert parsed.value
        assert parsed.value[0].incidentId == "9"  # int on the fixture wire
        return
    if op == "get_incident":
        parsed = m.GetIncidentResponse.model_validate(body)
        assert parsed.incidentId == "9"
        return
    parsed = m.AdvancedHuntingResponse.model_validate(body)
    assert parsed.Schema[0].Name == "Timestamp"
    assert parsed.Results[0]["EventCount"] == 3
    assert parsed.Stats is not None


def test_update_fixture_full_incident_shape_also_validates() -> None:
    """The PATCH may return the FULL incident; the union model keeps its keys.
    Extra keys ride through RAW (extra="allow" does not normalize them) -- the
    int incidentId is preserved as the wire sent it."""
    incident = _load("list_incidents.json")["value"][0]
    parsed = TypeAdapter(m.UpdateIncidentResponse).validate_python(incident)
    assert parsed.status == "Active"
    assert parsed.incidentId == 9 


@pytest.mark.parametrize("fixture_name", _ERRORS)
def test_every_error_fixture_validates(fixture_name: str) -> None:
    body = _load(f"errors/{fixture_name}")
    if fixture_name.startswith("token_"):
        parsed = AADSTSError.model_validate(body)
        assert parsed.aadsts_code() == 7000215
    else:
        parsed = DefenderAPIError.model_validate(body)
        assert parsed.error.message


def test_op_fixtures_are_raw_payloads_without_the_mock_envelope() -> None:
    """Connector steps with ``mock_result`` return it VERBATIM under --mock
    (see the compiler linter's ``_MOCK_ENVELOPE_STEP_TYPES``); a top-level
    ``data`` key would flip the linter's reading of ``.data`` references.
    These fixtures are the raw op payloads, so none of them may carry one."""
    for name in ("list_incidents.json", "get_incident.json",
                 "update_incident.json", "advanced_hunting.json"):
        body = _load(name)
        assert isinstance(body, dict)
        assert "data" not in body, name


# --- output quirks -----------------------------------------------------------


def test_incident_ids_normalize_to_str_and_refuse_bools() -> None:
    assert m.Incident(incidentId=9).incidentId == "9"
    assert m.Incident(incidentId="9").incidentId == "9"
    assert m.Incident(incidentId=9, redirectIncidentId="").redirectIncidentId is None
    with pytest.raises(ValidationError):
        m.Incident(incidentId=True)


def test_null_collections_become_empty_lists() -> None:
    incident = m.Incident.model_validate({
        "incidentId": 1, "tags": None, "comments": None, "alerts": None,
    })
    assert incident.tags == [] and incident.comments == [] and incident.alerts == []
    alert = m.IncidentAlert.model_validate({
        "alertId": "a", "mitreTechniques": None, "devices": None, "entities": None,
    })
    assert alert.mitreTechniques == [] and alert.devices == [] and alert.entities == []


def test_update_incident_empty_body_maps_to_true() -> None:
    """api_request returns ``True`` for an empty body -- the quirk the union
    model exists for."""
    adapter = TypeAdapter(m.UpdateIncidentResponse)
    assert adapter.validate_python(True) is True


def test_list_response_keeps_a_stale_next_link() -> None:
    """fetch_all_records merges every page but leaves the FIRST page's
    @odata.nextLink in the merged body -- following it re-fetches page 2."""
    body = _load("list_incidents.json")
    body["@odata.nextLink"] = "https://api.security.microsoft.com/api/incidents?$skip=100"
    parsed = m.IncidentListResponse.model_validate(body)
    assert parsed.odata_next_link.endswith("$skip=100")


def test_advanced_hunting_cells_are_not_lossily_coerced() -> None:
    parsed = m.AdvancedHuntingResponse.model_validate({
        "Schema": [], "Results": [{"Name": "123", "Count": 123, "Flag": True,
                                   "Real": 1.5, "Dyn": {"k": [1, 2]}}],
    })
    row = parsed.Results[0]
    assert row["Name"] == "123"  # a numeric-looking string stays a string
    assert row["Count"] == 123 and row["Flag"] is True and row["Real"] == 1.5
    assert row["Dyn"] == {"k": [1, 2]}


# --- param models ------------------------------------------------------------


def test_blank_string_platform_params_normalize_to_none() -> None:
    """The platform hands unset TEXT params as "" (the connector's own sample
    playbook passes ``top: ""``)."""
    params = m.ListIncidentsParams.model_validate({
        "top": "", "skip": "", "status": "", "assignedTo": "", "query": "",
    })
    assert params.top is None and params.status is None and params.query is None


def test_blank_get_all_records_means_false() -> None:
    """``get_all_records: ""`` is the UNCHECKED checkbox -- NOT the default."""
    assert m.ListIncidentsParams(get_all_records="").get_all_records is False
    assert m.ListIncidentsParams().get_all_records is True


def test_defender_datetimes_require_fractional_seconds() -> None:
    ok = m.ListIncidentsParams(lastUpdateTime="2026-11-01T00:00:00.000Z")
    assert ok.lastUpdateTime == "2026-11-01T00:00:00.000Z"
    with pytest.raises(ValidationError):
        m.ListIncidentsParams(lastUpdateTime="2026-11-01T00:00:00Z")


def test_unknown_status_is_refused_not_sent_as_none() -> None:
    """The connector would send the literal OData ``status eq 'None'`` for an
    unknown value (STATUS.get -> None); the model refuses it instead."""
    with pytest.raises(ValidationError):
        m.ListIncidentsParams(status="ResolvedX")
    assert m.ListIncidentsParams(status=["Active", "Resolved"]).status == [
        "Active", "Resolved",
    ]


def test_determination_requires_its_classification() -> None:
    with pytest.raises(ValidationError):
        m.UpdateIncidentParams(id="9", determination="Phishing")
    with pytest.raises(ValidationError):
        m.UpdateIncidentParams(id="9", classification="FalsePositive",
                               determination="Phishing")
    ok = m.UpdateIncidentParams(id="9", classification="TruePositive",
                                determination="Phishing")
    assert ok.determination == "Phishing"


def test_sample_playbook_param_shapes_validate() -> None:
    """Resolved forms of the connector's own sample-playbook param sets
    (playbooks.json): the bounded listing and the csv-tags update."""
    bounded = m.ListIncidentsParams.model_validate({
        "top": 3, "skip": "", "query": "", "status": "Active",
        "assignedTo": "", "createdTime": "", "lastUpdateTime": "",
        "get_all_records": "",
    })
    assert bounded.top == 3 and bounded.get_all_records is False
    update = m.UpdateIncidentParams.model_validate({
        "id": "9", "status": "Resolved", "classification": "FalsePositive",
        "determination": "Not malicious", "tags": "triaged, nightly-noise",
        "comment": "Closed after review",
    })
    assert update.tags == "triaged, nightly-noise"


def test_empty_required_params_are_refused_with_the_wire_reason() -> None:
    with pytest.raises(ValidationError):
        m.GetIncidentParams(id="")  # would GET the collection url
    with pytest.raises(ValidationError):
        m.AdvancedHuntingParams(Query="")  # would POST {} and 400


# --- config model ------------------------------------------------------------


def test_config_resource_is_normalized_like_microsoft_auth() -> None:
    mk = lambda resource: m.DefenderConnectorConfig(  # noqa: E731
        tenant_id="t", client_id="c", client_secret="s", resource=resource
    ).resource
    assert mk("api.security.microsoft.com") == "https://api.security.microsoft.com"
    assert mk("http://api.security.microsoft.com") == "https://api.security.microsoft.com"
    assert mk("https://api.security.microsoft.com/") == "https://api.security.microsoft.com"


def test_config_expires_on_is_a_ctime_string_not_an_epoch() -> None:
    cfg = m.DefenderConnectorConfig.model_validate({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "expiresOn": "Mon Nov 24 10:00:00 2026",
    })
    assert cfg.expiresOn == "Mon Nov 24 10:00:00 2026"
    with pytest.raises(ValidationError):
        m.DefenderConnectorConfig.model_validate({
            "tenant_id": "t", "client_id": "c", "client_secret": "s",
            "expiresOn": "1764000000",
        })


def test_delegated_auth_requires_the_authorization_code() -> None:
    with pytest.raises(ValidationError):
        m.DefenderConnectorConfig(
            auth_type="On behalf of User - Delegated Permission",
            tenant_id="t", client_id="c", client_secret="s",
        )
    ok = m.DefenderConnectorConfig(
        auth_type="On behalf of User - Delegated Permission",
        tenant_id="t", client_id="c", client_secret="s", code="0.AXo",
    )
    assert ok.code == "0.AXo"


# --- error envelope + ConnectorError wrapping --------------------------------


def test_connector_error_message_matches_the_connector_format_exactly() -> None:
    assert connector_error_message(
        401, "Unauthorized", "Access token is empty or expired."
    ) == "Response [401:Unauthorized Details: Access token is empty or expired.]"
    # an error body without a message formats EMPTY, exactly as the connector does
    assert connector_error_message(500, "Server Error", None) == \
        "Response [500:Server Error Details: ]"


def test_connector_error_message_round_trips_through_the_parser() -> None:
    body = _load("errors/api_403_forbidden.json")
    err = DefenderAPIError.model_validate(body)
    text = connector_error_message(403, "Forbidden", err.error.message)
    parsed = parse_connector_error_message(text)
    assert parsed == {
        "status_code": 403, "reason": "Forbidden", "details": err.error.message,
    }
    assert parse_connector_error_message("The request timed out") is None


def test_token_error_message_matches_the_auth_module_format_exactly() -> None:
    body = _load("errors/token_aadsts_invalid_client.json")
    err = AADSTSError.model_validate(body)
    assert token_error_connector_message(400, "Bad Request", err.error_description) == (
        f"Response 400: Bad Request \n Error Message: {err.error_description}"
    )


def test_aadsts_code_is_extractable_without_error_codes() -> None:
    body = _load("errors/token_aadsts_invalid_client.json")
    codes_only = AADSTSError.model_validate(body)
    description_only = AADSTSError.model_validate(
        {k: v for k, v in body.items() if k != "error_codes"}
    )
    assert codes_only.aadsts_code() == 7000215
    assert description_only.aadsts_code() == 7000215


def test_a_404_error_body_is_not_an_incident() -> None:
    """The error envelope and the incident shape stay distinct -- a NotFound
    body must not slide through the incident model."""
    with pytest.raises(ValidationError):
        m.Incident.model_validate(_load("errors/api_404_incident_not_found.json"))


def _connector_src() -> Path:
    return Path(os.environ.get("FSRPB_DEFENDER_CONNECTOR_SRC", _DEFAULT_SRC)).expanduser()


def test_connector_package_imports_by_path_offline() -> None:
    """The loader + SDK stub the capture script and live tests rely on,
    proven offline against the real connector source (skipped when the
    checkout is absent). Read-only: nothing under the connector repo is
    touched, and no network call happens (an auth object is only constructed)."""
    src = _connector_src()
    if not (src / "operations.py").is_file():
        pytest.skip(f"connector source not present: {src}")
    from fsr_playbooks.connectors.typed.defender_common import (
        load_connector_package,
        stub_fortisoar_connector_sdk,
    )

    stubbed = stub_fortisoar_connector_sdk()
    try:
        pkg = load_connector_package(src, "fsrpb_offline_m365_defender")
        assert sorted(pkg.operations.operations.keys()) == [
            "advanced_hunting", "get_incident", "list_incidents", "update_incident",
        ]
        from fsrpb_offline_m365_defender import constant, microsoft_api_auth

        assert constant.INCIDENT == "/api/incidents/"
        assert constant.ADVANCE_HUNTING == "/api/advancedhunting/run"
        auth = microsoft_api_auth.MicrosoftAuth({
            "client_id": "x", "client_secret": "y", "verify_ssl": True,
            "resource": "http://api.security.microsoft.com", "tenant_id": "t",
            "auth_type": "Without a User - Application Permission",
        })
        # the resource/scope the module docstring cites, pinned from the source
        assert auth.scope == "https://api.security.microsoft.com/.default offline_access"
        assert auth.host == "https://api.security.microsoft.com"
    finally:
        if stubbed:
            _uninstall_connector_modules("fsrpb_offline_m365_defender")


# --- live (self-skipping) ----------------------------------------------------

_LIVE_ENV_VARS = (
    "M365_DEFENDER_TENANT_ID", "M365_DEFENDER_CLIENT_ID", "M365_DEFENDER_CLIENT_SECRET",
)
_DEFAULT_SRC = (
    "~/PycharmProjects/soarshelf/content/connectors/"
    "fetch-microsoft-365-defender-incidents-oldest-first/package/microsoft-365-defender"
)


def _live_skip_reason() -> str:
    if not all(os.environ.get(v) for v in _LIVE_ENV_VARS):
        return "M365_DEFENDER_* creds not set"
    src = _connector_src()
    if not (src / "operations.py").is_file():
        return f"connector source not present: {src}"
    return ""


_LIVE_SKIP = _live_skip_reason()


def _load_live_connector() -> Any:
    """Import the connector package BY PATH, in-process, SDK stubbed."""
    from fsr_playbooks.connectors.typed.defender_common import (
        load_connector_package,
        stub_fortisoar_connector_sdk,
    )

    stubbed = stub_fortisoar_connector_sdk()
    pkg = load_connector_package(_connector_src(), "fsrpb_live_m365_defender")
    return pkg, stubbed


def _uninstall_connector_modules(prefix: str) -> None:
    for name in [n for n in list(sys.modules) if n == prefix or n.startswith(prefix + ".")]:
        del sys.modules[name]
    for name in ("connectors.core.utils", "connectors.core.connector",
                 "connectors.core", "connectors"):
        sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def live_connector() -> Any:
    """The imported connector ops plus a minted-token config."""
    pkg, stubbed = _load_live_connector()
    ops = pkg.operations
    info = json.loads((_connector_src() / "info.json").read_text())
    connector_info = {
        "connector_name": info["name"], "connector_version": info["version"],
    }
    config: dict[str, Any] = {
        "auth_type": "Without a User - Application Permission",
        "resource": os.environ.get("M365_DEFENDER_RESOURCE")
        or "https://api.security.microsoft.com",
        "tenant_id": os.environ["M365_DEFENDER_TENANT_ID"],
        "client_id": os.environ["M365_DEFENDER_CLIENT_ID"],
        "client_secret": os.environ["M365_DEFENDER_CLIENT_SECRET"],
        "verify_ssl": True,
    }
    ops.check(config, dict(connector_info))
    yield ops, config, connector_info
    if stubbed:  # keep the suite's module namespace clean under random order
        _uninstall_connector_modules("fsrpb_live_m365_defender")


@pytest.mark.live
@pytest.mark.skipif(bool(_LIVE_SKIP), reason=_LIVE_SKIP)
class TestLiveM365Defender:
    """Same models, real tenant. Non-mutating: no update is performed."""

    def test_list_incidents_validates(self, live_connector: Any) -> None:
        ops, config, connector_info = live_connector
        result = ops.list_incidents(config, {"get_all_records": False, "top": 5},
                                    dict(connector_info))
        parsed = m.IncidentListResponse.model_validate(result)
        for incident in parsed.value:
            assert incident.incidentId
            assert incident.status in ("Active", "Resolved", "InProgress", "Redirected")

    def test_get_incident_validates(self, live_connector: Any) -> None:
        ops, config, connector_info = live_connector
        listing = ops.list_incidents(config, {"get_all_records": False, "top": 1},
                                     dict(connector_info))
        value = listing.get("value") or []
        if not value:
            pytest.skip("tenant has no incidents to fetch")
        incident_id = str(value[0]["incidentId"])
        result = ops.get_incident(config, {"id": incident_id}, dict(connector_info))
        parsed = m.GetIncidentResponse.model_validate(result)
        assert parsed.incidentId == incident_id

    def test_get_incident_404_returns_a_raw_response_not_an_error(self, live_connector: Any) -> None:
        """Pins the connector's most dangerous quirk against the live wire:
        a 404 comes back as a requests.Response object, NOT a ConnectorError
        and NOT an incident body."""
        ops, config, connector_info = live_connector
        result = ops.get_incident(config, {"id": "999999"}, dict(connector_info))
        assert hasattr(result, "status_code")
        assert result.status_code == 404

    def test_update_incident_404_is_also_a_raw_response(self, live_connector: Any) -> None:
        ops, config, connector_info = live_connector
        result = ops.update_incident(config, {"id": "999999", "comment": "x"},
                                     dict(connector_info))
        assert hasattr(result, "status_code")
        assert result.status_code == 404

    def test_advanced_hunting_validates(self, live_connector: Any) -> None:
        ops, config, connector_info = live_connector
        result = ops.advanced_hunting(config, {"Query": "DeviceInfo | take 5"},
                                      dict(connector_info))
        parsed = m.AdvancedHuntingResponse.model_validate(result)
        assert len(parsed.Schema) > 0
        for row in parsed.Results:
            assert set(row.keys()) == {c.Name for c in parsed.Schema}

    def test_bad_kql_is_a_400_envelope(self, live_connector: Any) -> None:
        ops, config, connector_info = live_connector
        with pytest.raises(Exception) as excinfo:
            ops.advanced_hunting(config, {"Query": "this is not kql !!!"},
                                 dict(connector_info))
        parsed = parse_connector_error_message(str(excinfo.value))
        assert parsed is not None and parsed["status_code"] == 400
