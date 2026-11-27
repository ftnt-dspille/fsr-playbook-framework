"""Offline typing + mock-fixture gate for the microsoft-365-defender connector.

Pins the typed models in ``fsr_playbooks/connectors/typed/microsoft_365_defender.py``
against the sanitized fixtures in ``typed/mocks/microsoft-365-defender/``:

* every op fixture validates through its per-op output model AND round-trips
  exactly (``model_dump(by_alias=True, exclude_unset=True) == fixture`` --
  the same contract the graph-security suite pins);
* every error fixture validates through the AADSTS / Defender error models,
  in both nested and flat body shapes;
* the documented wire quirks (int-or-str incident ids, null collections,
  empty-body ``True`` on update, blank-string platform params, the
  microseconds-only datetime format, the stale ``@odata.nextLink``, the
  epoch-float ``expiresOn``) behave as documented;
* the ``ConnectorError`` message formats match the connector's own string
  formatting exactly -- that string is what a playbook sees on a failed step.

Provenance: source-derived (operations.py), live-capture pending -- the
shapes pinned here come from info.json ``output_schema`` + the connector's
own code. The ``live``-marked suite in ``tooling/tests/test_m365_defender_live.py``
re-validates the same models against the real tenant when ``M365_*`` creds
are in the environment (deselected everywhere by default).

No network, no reference DB: green on a bare checkout.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
from fsr_playbooks.connectors.typed.graph_common import TokenResponseErrorText
from fsr_playbooks.connectors.typed.mocks import (
    ERROR_FIXTURES,
    MOCK_FIXTURES,
    load_error_fixture,
    load_mock,
)

_DEFENDER_OPS = (
    "list_incidents",
    "get_incident",
    "update_incident",
    "advanced_hunting",
    "list_machines",
    "get_machine",
    "isolate_machine",
    "unisolate_machine",
    "run_av_scan",
    "collect_investigation_package",
    "restrict_app_execution",
    "unrestrict_app_execution",
    "get_machine_action",
)

_ERROR_KEYS = sorted(k for k in ERROR_FIXTURES if k.startswith("m365def-"))


# --- registry completeness ----------------------------------------------------


def test_every_registered_op_has_a_fixture_and_a_model() -> None:
    mocked = set(MOCK_FIXTURES["microsoft-365-defender"])
    assert mocked == set(_DEFENDER_OPS)
    assert set(m.OPERATION_MODELS) == set(_DEFENDER_OPS)
    assert set(m.OP_PARAM_MODELS) == set(_DEFENDER_OPS)


def test_every_defender_error_fixture_is_registered() -> None:
    on_disk = sorted(p.name for p in (_mock_dir() / "errors").glob("*.json"))
    assert len(_ERROR_KEYS) == len(on_disk), (_ERROR_KEYS, on_disk)


def _mock_dir() -> Path:
    return Path(m.__file__).resolve().parent / "mocks" / "microsoft-365-defender"


# --- every fixture validates through its model -------------------------------


_MACHINE_ACTION_OPS = (
    "isolate_machine",
    "unisolate_machine",
    "run_av_scan",
    "collect_investigation_package",
    "restrict_app_execution",
    "unrestrict_app_execution",
    "get_machine_action",
)


@pytest.mark.parametrize("op", _DEFENDER_OPS)
def test_every_op_fixture_validates_through_its_model(op: str) -> None:
    body = load_mock("microsoft-365-defender", op)
    if op == "update_incident":
        parsed = TypeAdapter(m.UpdateIncidentResponse).validate_python(body)
        assert parsed.status == "Resolved"
        return
    model = m.OPERATION_MODELS[op]
    parsed = model.model_validate(body)
    if op == "list_incidents":
        assert parsed.value
        assert parsed.value[0].incidentId == "9"
    elif op == "get_incident":
        assert parsed.incidentId == "9"
    elif op == "list_machines":
        assert parsed.value and len(parsed.value[0].id) == 40
    elif op == "get_machine":
        assert len(parsed.id) == 40 and parsed.onboardingStatus == "Onboarded"
    elif op in _MACHINE_ACTION_OPS:
        assert parsed.id and parsed.status in m.MACHINE_ACTION_TERMINAL_STATUSES + ("Pending", "InProgress")
    else:
        assert parsed.Schema[0].Name == "Timestamp"
        assert parsed.Results[0]["EventCount"] == 3
        assert parsed.Stats is not None


@pytest.mark.parametrize("op", _DEFENDER_OPS)
def test_every_op_fixture_round_trips_exactly(op: str) -> None:
    """``model_dump(by_alias=True, exclude_unset=True)`` must reproduce the
    fixture byte-for-byte (as a dict) -- the promoted mock_result and the
    typed layer produce the SAME shape downstream."""
    body = load_mock("microsoft-365-defender", op)
    if op == "update_incident":
        parsed = TypeAdapter(m.UpdateIncidentResponse).validate_python(body)
        assert parsed.model_dump(by_alias=True, exclude_unset=True) == body
        return
    model = m.OPERATION_MODELS[op]
    parsed = model.model_validate(body)
    assert parsed.model_dump(by_alias=True, exclude_unset=True) == body


def test_update_fixture_full_incident_shape_also_validates() -> None:
    """The PATCH may return the FULL incident; the union model keeps its keys.
    Extra keys ride through RAW (extra="allow" does not normalize them) -- the
    int incidentId is preserved as the wire sent it."""
    incident = load_mock("microsoft-365-defender", "list_incidents")["value"][0]
    parsed = TypeAdapter(m.UpdateIncidentResponse).validate_python(incident)
    assert parsed.status == "Active"
    assert parsed.incidentId == "9"


@pytest.mark.parametrize("key", _ERROR_KEYS)
def test_every_error_fixture_validates(key: str) -> None:
    body = load_error_fixture(key)
    parsed = DefenderAPIError.model_validate(body)
    assert parsed.error_text()


def test_op_fixtures_are_raw_payloads_without_the_mock_envelope() -> None:
    """Connector steps with ``mock_result`` return it VERBATIM under --mock
    (see the compiler linter's ``_MOCK_ENVELOPE_STEP_TYPES``); a top-level
    ``data`` key would flip the linter's reading of ``.data`` references.
    These fixtures are the raw op payloads, so none of them may carry one."""
    for op in _DEFENDER_OPS:
        body = load_mock("microsoft-365-defender", op)
        assert isinstance(body, dict)
        assert "data" not in body, op


# --- output quirks -----------------------------------------------------------


def test_incident_ids_normalize_to_str_and_refuse_bools() -> None:
    assert m.Incident(incidentId=9).incidentId == "9"
    assert m.Incident(incidentId="9").incidentId == "9"
    assert m.Incident(incidentId=9, redirectIncidentId="").redirectIncidentId is None
    with pytest.raises(ValidationError):
        m.Incident(incidentId=True)


def test_null_collections_become_empty_lists() -> None:
    incident = m.Incident.model_validate(
        {
            "incidentId": 1,
            "tags": None,
            "comments": None,
            "alerts": None,
        }
    )
    assert incident.tags == [] and incident.comments == [] and incident.alerts == []
    alert = m.IncidentAlert.model_validate(
        {
            "alertId": "a",
            "mitreTechniques": None,
            "devices": None,
            "entities": None,
        }
    )
    assert alert.mitreTechniques == [] and alert.devices == [] and alert.entities == []


def test_update_incident_empty_body_maps_to_true() -> None:
    """api_request returns ``True`` for an empty body -- the quirk the union
    model exists for."""
    adapter = TypeAdapter(m.UpdateIncidentResponse)
    assert adapter.validate_python(True) is True


def test_list_response_keeps_a_stale_next_link() -> None:
    """fetch_all_records merges every page but leaves the FIRST page's
    @odata.nextLink in the merged body -- following it re-fetches page 2."""
    body = load_mock("microsoft-365-defender", "list_incidents")
    body["@odata.nextLink"] = (
        "https://api.security.microsoft.com/api/incidents?$skip=100"
    )
    parsed = m.IncidentListResponse.model_validate(body)
    assert parsed.odata_next_link.endswith("$skip=100")


def test_advanced_hunting_cells_are_not_lossily_coerced() -> None:
    parsed = m.AdvancedHuntingResponse.model_validate(
        {
            "Schema": [],
            "Results": [
                {
                    "Name": "123",
                    "Count": 123,
                    "Flag": True,
                    "Real": 1.5,
                    "Dyn": {"k": [1, 2]},
                }
            ],
        }
    )
    row = parsed.Results[0]
    assert row["Name"] == "123"  # a numeric-looking string stays a string
    assert row["Count"] == 123 and row["Flag"] is True and row["Real"] == 1.5
    assert row["Dyn"] == {"k": [1, 2]}


# --- param models ------------------------------------------------------------


def test_blank_string_platform_params_normalize_to_none() -> None:
    """The platform hands unset TEXT params as "" (the connector's own sample
    playbook passes ``top: ""``)."""
    params = m.ListIncidentsParams.model_validate(
        {
            "top": "",
            "skip": "",
            "status": "",
            "assignedTo": "",
            "query": "",
        }
    )
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
        "Active",
        "Resolved",
    ]


def test_determination_requires_its_classification() -> None:
    with pytest.raises(ValidationError):
        m.UpdateIncidentParams(id="9", determination="Phishing")
    with pytest.raises(ValidationError):
        m.UpdateIncidentParams(
            id="9", classification="FalsePositive", determination="Phishing"
        )
    ok = m.UpdateIncidentParams(
        id="9", classification="TruePositive", determination="Phishing"
    )
    assert ok.determination == "Phishing"


def test_sample_playbook_param_shapes_validate() -> None:
    """Resolved forms of the connector's own sample-playbook param sets
    (playbooks.json): the bounded listing and the csv-tags update."""
    bounded = m.ListIncidentsParams.model_validate(
        {
            "top": 3,
            "skip": "",
            "query": "",
            "status": "Active",
            "assignedTo": "",
            "createdTime": "",
            "lastUpdateTime": "",
            "get_all_records": "",
        }
    )
    assert bounded.top == 3 and bounded.get_all_records is False
    update = m.UpdateIncidentParams.model_validate(
        {
            "id": "9",
            "status": "Resolved",
            "classification": "FalsePositive",
            "determination": "Not malicious",
            "tags": "triaged, nightly-noise",
            "comment": "Closed after review",
        }
    )
    assert update.tags == "triaged, nightly-noise"


def test_empty_required_params_are_refused_with_the_wire_reason() -> None:
    with pytest.raises(ValidationError):
        m.GetIncidentParams(id="")  # would GET the collection url
    with pytest.raises(ValidationError):
        m.AdvancedHuntingParams(Query="")  # would POST {} and 400


# --- config model ------------------------------------------------------------


def test_config_resource_is_normalized_like_microsoft_auth() -> None:
    def mk(resource: str) -> str:
        return m.DefenderConnectorConfig(
            tenant_id="t", client_id="c", client_secret="s", resource=resource
        ).resource

    assert mk("api.security.microsoft.com") == "https://api.security.microsoft.com"
    assert (
        mk("http://api.security.microsoft.com") == "https://api.security.microsoft.com"
    )
    assert (
        mk("https://api.security.microsoft.com/")
        == "https://api.security.microsoft.com"
    )


def test_config_expires_on_is_an_epoch_float() -> None:
    """Live-capture-corrected: the connector stores ``time() + expires_in`` --
    a NUMBER (``convert_ts_epoch`` runs ``ctime()`` on it, which requires a
    number; a ctime string crashes the op). Numeric strings are tolerated
    (``convert_ts_epoch`` floats them itself)."""
    base = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
    assert (
        m.DefenderConnectorConfig(expiresOn=1764000000.5, **base).expiresOn
        == 1764000000.5
    )
    assert (
        m.DefenderConnectorConfig(expiresOn=1764000000, **base).expiresOn
        == 1764000000.0
    )
    assert (
        m.DefenderConnectorConfig(expiresOn="1764000000", **base).expiresOn
        == 1764000000.0
    )
    with pytest.raises(ValidationError):
        m.DefenderConnectorConfig(expiresOn="Mon Nov 24 10:00:00 2026", **base)
    with pytest.raises(ValidationError):
        m.DefenderConnectorConfig(expiresOn=True, **base)


def test_delegated_auth_requires_the_authorization_code() -> None:
    with pytest.raises(ValidationError):
        m.DefenderConnectorConfig(
            auth_type="On behalf of User - Delegated Permission",
            tenant_id="t",
            client_id="c",
            client_secret="s",
        )
    ok = m.DefenderConnectorConfig(
        auth_type="On behalf of User - Delegated Permission",
        tenant_id="t",
        client_id="c",
        client_secret="s",
        code="0.AXo",
    )
    assert ok.code == "0.AXo"


# --- error envelope + ConnectorError wrapping --------------------------------


def test_error_models_match_both_wire_shapes() -> None:
    """The nested OData envelope AND the flat ``{"error": "<text>"}`` body
    both validate; ``error_text()`` normalizes them."""
    nested = DefenderAPIError.model_validate(
        load_error_fixture("m365def-403-forbidden")
    )
    assert nested.error_text().startswith("The application lacks")
    flat = DefenderAPIError.model_validate({"error": "Account is not provisioned."})
    assert flat.error_text() == "Account is not provisioned."


def test_the_not_provisioned_403_is_the_expected_trial_tenant_shape() -> None:
    body = load_error_fixture("m365def-403-not-provisioned")
    parsed = DefenderAPIError.model_validate(body)
    assert "provisioned" in parsed.error_text()
    text = connector_error_message(403, "Forbidden", parsed.error_text())
    parsed_text = parse_connector_error_message(text)
    assert parsed_text is not None
    assert parsed_text["status_code"] == 403
    assert "provisioned" in str(parsed_text["details"])


def test_connector_error_message_matches_the_connector_format_exactly() -> None:
    assert (
        connector_error_message(
            401, "Unauthorized", "Access token is empty or expired."
        )
        == "Response [401:Unauthorized Details: Access token is empty or expired.]"
    )
    # an error body without a message formats EMPTY, exactly as the connector does
    assert (
        connector_error_message(500, "Server Error", None)
        == "Response [500:Server Error Details: ]"
    )


def test_connector_error_message_round_trips_through_the_parser() -> None:
    body = load_error_fixture("m365def-403-forbidden")
    err = DefenderAPIError.model_validate(body)
    text = connector_error_message(403, "Forbidden", err.error_text())
    parsed = parse_connector_error_message(text)
    assert parsed == {
        "status_code": 403,
        "reason": "Forbidden",
        "details": err.error_text(),
    }
    assert parse_connector_error_message("The request timed out") is None
    # the KeyError degradation a flat error body produces is NOT this format
    assert parse_connector_error_message("'message'") is None


def test_token_error_message_matches_the_auth_module_format_exactly() -> None:
    body = load_error_fixture("aadsts-7000215-invalid-secret")
    err = AADSTSError.model_validate(body)
    text = token_error_connector_message(400, "Bad Request", err.error_description)
    assert text == (
        f"Response 400: Bad Request \n Error Message: {err.error_description}"
    )
    parsed = TokenResponseErrorText.parse(text)
    assert parsed is not None
    assert parsed.status == 400 and parsed.reason == "Bad Request"
    assert parsed.error_message == err.error_description


def test_aadsts_code_is_extractable_without_error_codes() -> None:
    body = load_error_fixture("aadsts-7000215-invalid-secret")
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
        m.Incident.model_validate(load_error_fixture("m365def-404-incident-not-found"))


# --- the connector imports by path, offline ----------------------------------

_LIVE_ENV_VARS = ("M365_TENANT_ID", "M365_CLIENT_ID", "M365_CLIENT_SECRET")
_DEFAULT_SRC = (
    "~/PycharmProjects/soarshelf/content/connectors/"
    "fetch-microsoft-365-defender-incidents-oldest-first/package/microsoft-365-defender"
)


def _connector_src() -> Path:
    return Path(
        os.environ.get("FSRPB_DEFENDER_CONNECTOR_SRC", _DEFAULT_SRC)
    ).expanduser()


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
            "advanced_hunting",
            "get_incident",
            "list_incidents",
            "update_incident",
        ]
        from fsrpb_offline_m365_defender import constant, microsoft_api_auth

        assert constant.INCIDENT == "/api/incidents/"
        assert constant.ADVANCE_HUNTING == "/api/advancedhunting/run"
        auth = microsoft_api_auth.MicrosoftAuth(
            {
                "client_id": "x",
                "client_secret": "y",
                "verify_ssl": True,
                "resource": "http://api.security.microsoft.com",
                "tenant_id": "t",
                "auth_type": "Without a User - Application Permission",
            }
        )
        # the resource/scope the module docstring cites, pinned from the source
        assert (
            auth.scope == "https://api.security.microsoft.com/.default offline_access"
        )
        assert auth.host == "https://api.security.microsoft.com"
    finally:
        if stubbed:
            _uninstall_connector_modules("fsrpb_offline_m365_defender")


def _uninstall_connector_modules(prefix: str) -> None:
    for name in [
        n for n in list(sys.modules) if n == prefix or n.startswith(prefix + ".")
    ]:
        del sys.modules[name]
    for name in (
        "connectors.core.utils",
        "connectors.core.connector",
        "connectors.core",
        "connectors",
    ):
        sys.modules.pop(name, None)


def test_capture_script_param_helpers_round_trip() -> None:
    """The capture script's helpers: the sentinel not-found id, the epoch
    expiresOn in build_config, and the RAW (no-Bearer) token contract."""
    from fsr_playbooks.connectors.typed import capture_m365_defender as cap

    assert cap.SENTINEL_ID
    config = cap.build_config("raw-token-value", "tenant", "client", "secret")
    assert isinstance(config["expiresOn"], float)
    assert config["accessToken"] == "raw-token-value"
    assert not config["accessToken"].startswith("Bearer ")
    m.DefenderConnectorConfig.model_validate(config)
    assert cap._jsonable(True) is True
    assert cap._coerce_value("5") == 5
    assert cap._coerce_value("abc") == "abc"


def test_live_env_fallback_spelling() -> None:
    assert (
        _connector_src()
        == Path(
            os.environ.get("FSRPB_DEFENDER_CONNECTOR_SRC", _DEFAULT_SRC)
        ).expanduser()
    )
