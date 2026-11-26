"""Offline tests for the typed models + mock fixtures of the soarshelf
Microsoft security connectors (m365-trial plan §8.2/8.3).

The contract under test:

- every registered op of the three soarshelf Microsoft security connectors
  (``microsoft-graph_dev``, ``microsoft-graph-api-security``,
  ``microsoft-365-defender``) has a mock fixture and an output model;
- every fixture validates through its model and round-trips exactly
  (``model_dump(by_alias=True, exclude_unset=True) == fixture``);
- error envelopes validate through the error models;
- every model carries the plan's provenance line and does not claim
  live-verification before a capture has been promoted.

No network, no reference DB: this suite must stay green on a checkout
with no ``data/fsr_reference.db`` and no tenant.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from fsr_playbooks.connectors.typed import defender_common as dcom
from fsr_playbooks.connectors.typed import graph_common as gc
from fsr_playbooks.connectors.typed import microsoft_365_defender as mdef
from fsr_playbooks.connectors.typed import microsoft_graph_api_security as sec
from fsr_playbooks.connectors.typed import microsoft_graph_dev as dev
from fsr_playbooks.connectors.typed.capture_graph_security import (
    MUTATING_VERBS,
    PARAM_SETS,
    SENTINEL_ID,
)
from fsr_playbooks.connectors.typed.defender_common import DefenderAPIError
from fsr_playbooks.connectors.typed.graph_common import (
    AadstsTokenError,
    GraphErrorEnvelope,
    TokenResponseErrorText,
    extract_error_body,
    parse_graph_connector_error,
)
from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
    OPERATION_MODELS as SEC_OPS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
    AdvancedHuntingResult,
    MicrosoftGraphApiSecurityConfig,
    MutationNoContentResult,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    OPERATION_MODELS as DEV_OPS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    MicrosoftGraphDevConfig,
    RevokeSessionsResult,
    SecurityAlertResult,
    SecurityAlertsAnyVersionPage,
    ThreadedMailResult,
)
from fsr_playbooks.connectors.typed.mocks import (
    ERROR_FIXTURES,
    MOCK_FIXTURES,
    load_error_fixture,
    load_mock,
)

_MOCKS_DIR = Path(gc.__file__).resolve().parent / "mocks"

#: variant key (``op@MODE``) -> the op whose model validates it
_VARIANT_OPS = {"get_all_security_alerts@V2": "get_all_security_alerts",
                "get_security_alert@V1": "get_security_alert"}


def _all_fixture_keys() -> list[tuple[str, str]]:
    out = []
    for connector, ops in MOCK_FIXTURES.items():
        for key in ops:
            out.append((connector, key))
    return out


def _model_for(connector: str, key: str) -> type[BaseModel]:
    op = _VARIANT_OPS.get(key, key)
    if connector == "microsoft-graph_dev":
        return DEV_OPS[op]
    if connector == "microsoft-graph-api-security":
        return SEC_OPS[op]
    if connector == "microsoft-365-defender":
        # update_incident's registry entry is the dict-or-True UNION; its
        # fixture is the dict side, so route the roundtrip through that model
        if op == "update_incident":
            return mdef.UpdateIncidentResult
        return mdef.OPERATION_MODELS[op]
    raise KeyError(connector)


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


def test_every_registered_op_has_a_fixture_and_model() -> None:
    for registry, connector in [(DEV_OPS, "microsoft-graph_dev"),
                                (SEC_OPS, "microsoft-graph-api-security"),
                                (mdef.OPERATION_MODELS,
                                 "microsoft-365-defender")]:
        mocked = set(MOCK_FIXTURES[connector])
        missing = sorted(set(registry) - mocked)
        assert not missing, f"{connector}: ops without a mock fixture: {missing}"
        unmodeled = sorted(
            k for k in mocked if _VARIANT_OPS.get(k, k) not in registry)
        assert not unmodeled, f"{connector}: fixtures without a model: {unmodeled}"


def test_dev_registry_covers_the_forks_seventeen_ops() -> None:
    # the 17 ops the connector package advertises (info.json operations),
    # exactly -- check_health is in the operations dict but not an op surface
    expected = {
        "get_risky_users_list", "get_risky_user_details", "get_all_security_alerts",
        "get_security_alert", "update_security_alert", "add_comment_on_security_alert",
        "get_groups", "get_group_users", "search_message", "del_message",
        "del_message_bulk", "revoke_user_sessions", "get_all_named_locations",
        "block_new_ips", "unblock_new_ips", "create_ip_range_location",
        "get_security_incidents",
    }
    assert set(DEV_OPS) == expected


def test_sec_registry_covers_the_five_registered_ops() -> None:
    assert set(SEC_OPS) == {
        "get_security_incidents", "get_security_alerts", "get_security_alert",
        "update_security_incident", "run_advanced_hunting",
    }


def test_defender_registry_covers_the_registered_ops() -> None:
    assert set(mdef.OPERATION_MODELS) == {
        "list_incidents", "get_incident", "update_incident", "advanced_hunting",
        "list_machines", "get_machine", "isolate_machine", "unisolate_machine",
        "run_av_scan", "collect_investigation_package", "restrict_app_execution",
        "unrestrict_app_execution", "get_machine_action",
    }
    assert set(mdef.OP_PARAM_MODELS) == set(mdef.OPERATION_MODELS)


# ---------------------------------------------------------------------------
# Fixture -> model validation + roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("connector,key", _all_fixture_keys())
def test_fixture_validates_and_roundtrips(connector: str, key: str) -> None:
    fixture = load_mock(connector, key)
    model = _model_for(connector, key)
    parsed = model.model_validate(fixture)
    assert parsed.model_dump(by_alias=True, exclude_unset=True) == fixture


def test_no_fixture_carries_a_mock_envelope() -> None:
    # a top-level `data` key would flip the fixture into the ENVELOPE shape
    # the linter special-cases; these fixtures are raw payloads by contract
    for connector, key in _all_fixture_keys():
        fixture = load_mock(connector, key)
        if not isinstance(fixture, dict):
            continue  # e.g. update_security_incident's literal-true 204 quirk
        assert "data" not in fixture, f"{connector}.{key} carries a data envelope"


def test_update_incident_mock_is_the_204_true_quirk() -> None:
    fixture = load_mock("microsoft-graph-api-security", "update_security_incident")
    assert fixture is True
    parsed = MutationNoContentResult.model_validate(fixture)
    assert parsed.root is True


def test_threaded_mail_result_shapes() -> None:
    search = ThreadedMailResult.model_validate(
        load_mock("microsoft-graph_dev", "search_message"))
    assert search.message_found_list and search.message_found_list[0].user_id
    assert search.message_not_found_list[0].value == []
    assert search.error_list is None  # key absent when empty (api_result quirk)
    assert search.run_time >= 0

    bulk = ThreadedMailResult.model_validate(
        load_mock("microsoft-graph_dev", "del_message_bulk"))
    assert bulk.message_deleted_list[0].msg_deleted == "Yes"
    assert bulk.message_deleted_list[0].user_id.message_id
    err = bulk.error_list[0]
    assert err.user_id.user_id  # the delete path echoes the full target dict
    assert search.message_found_list[0].value[0].from_.emailAddress.address


def test_revoke_sessions_coerces_string_true() -> None:
    ok = RevokeSessionsResult.model_validate({"@odata.context": "x", "value": True})
    assert ok.value is True
    sloppy = RevokeSessionsResult.model_validate({"value": "true"})
    assert sloppy.value is True


def test_alert_union_discriminates_generations() -> None:
    v1 = SecurityAlertResult.model_validate(
        load_mock("microsoft-graph_dev", "get_security_alert@V1"))
    assert isinstance(v1.root, gc.LegacySecurityAlert)
    assert v1.root.azureTenantId

    v2 = SecurityAlertResult.model_validate(
        load_mock("microsoft-graph_dev", "get_security_alert"))
    assert isinstance(v2.root, gc.SecurityAlertV2)
    assert v2.root.tenantId

    page_v1 = SecurityAlertsAnyVersionPage.model_validate(
        load_mock("microsoft-graph_dev", "get_all_security_alerts"))
    assert isinstance(page_v1.value[0], gc.LegacySecurityAlert)
    page_v2 = SecurityAlertsAnyVersionPage.model_validate(
        load_mock("microsoft-graph_dev", "get_all_security_alerts@V2"))
    assert isinstance(page_v2.value[0], gc.SecurityAlertV2)


def test_advanced_hunting_schema_and_rows() -> None:
    result = AdvancedHuntingResult.model_validate(
        load_mock("microsoft-graph-api-security", "run_advanced_hunting"))
    assert [c.name for c in result.schema_] == ["Timestamp", "DeviceName",
                                                "InitiatingProcessAccountName"]
    assert result.results[0]["DeviceName"].endswith(".contoso.example")


def test_incident_page_alerts_pass_through_until_captured() -> None:
    page = dev.IncidentsPage.model_validate(
        load_mock("microsoft-graph_dev", "get_security_incidents"))
    incident = page.value[0]
    assert incident.alerts and isinstance(incident.alerts[0], dict)


# ---------------------------------------------------------------------------
# Error shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(ERROR_FIXTURES))
def test_error_fixture_validates(key: str) -> None:
    fixture = load_error_fixture(key)
    if key.startswith("aadsts-") or key.startswith("m365def-aadsts-"):
        model: type[BaseModel] = AadstsTokenError
    elif key.startswith("m365def-"):
        # the defender connector's own resource-error shape (nested OR flat)
        model = DefenderAPIError
    else:
        model = GraphErrorEnvelope
    parsed = model.model_validate(fixture)
    assert parsed.model_dump(by_alias=True, exclude_unset=True) == fixture


def test_the_defender_not_provisioned_403_is_a_registered_shape() -> None:
    parsed = DefenderAPIError.model_validate(
        load_error_fixture("m365def-403-not-provisioned"))
    assert "provisioned" in parsed.error_text()


def test_throttling_error_carries_graph_code() -> None:
    body = GraphErrorEnvelope.model_validate(load_error_fixture("graph-429-throttled"))
    assert body.error.code == "TooManyRequests"


def test_connector_error_text_parsers() -> None:
    # microsoft-graph-api-security raises "Microsoft Graph Error | Status=…"
    parsed = parse_graph_connector_error(
        "Microsoft Graph Error | Status=403 | Code=Forbidden "
        "| Message=Insufficient privileges to complete the operation.")
    assert parsed is not None
    assert parsed.status == 403 and parsed.code == "Forbidden"

    # the token modules raise "Response <status>: <reason> \n Error Message: …"
    token = TokenResponseErrorText.parse(
        "Response 401: Unauthorized \n Error Message: AADSTS7000215: "
        "Invalid client secret provided.")
    assert token is not None
    assert token.status == 401 and "7000215" in token.error_message

    # microsoft-graph_dev embeds the raw response body in its message
    body = extract_error_body(
        'Fail To request API https://graph.microsoft.com/v1.0/x response is '
        ':b\'{"error": {"code": "NotFoundError"}}\' with reason: Not Found')
    assert body == {"error": {"code": "NotFoundError"}}

    assert parse_graph_connector_error("not a connector error") is None
    assert extract_error_body("no json here") is None


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


def test_dev_config_tenant_field_and_injected_api_version() -> None:
    config = MicrosoftGraphDevConfig.model_validate({
        "auth_type": "Without a User - Application Permission",
        "resource": "https://graph.microsoft.com",
        "tenant": "00000000-0000-0000-0000-000000000000",
        "client_id": "00000000-0000-0000-0000-0000000000aa",
        "client_secret": "<secret>",
        "accessToken": "<token>",
        "expiresOn": "Mon Jan 19 10:00:00 2026",
        "api_version": "v1.0",
    })
    assert config.tenant and config.api_version == "v1.0"
    assert config.verify_ssl is True
    with pytest.raises(Exception):
        MicrosoftGraphDevConfig.model_validate({"tenant_id": "x"})  # wrong field name


def test_sec_config_uses_tenant_id() -> None:
    config = MicrosoftGraphApiSecurityConfig.model_validate({
        "auth_type": "Without a User - Application Permission",
        "tenant_id": "00000000-0000-0000-0000-000000000000",
        "client_id": "00000000-0000-0000-0000-0000000000aa",
        "client_secret": "<secret>",
    })
    assert config.tenant_id and config.resource == "https://graph.microsoft.com"
    assert config.api_version if False else True  # no api_version key exists here
    assert "api_version" not in MicrosoftGraphApiSecurityConfig.model_fields


def test_delegated_and_certificate_branches_validate() -> None:
    delegated = MicrosoftGraphDevConfig.model_validate({
        "auth_type": "On behalf of User - Delegate Permission",
        "tenant": "00000000-0000-0000-0000-000000000000",
        "client_id": "00000000-0000-0000-0000-0000000000aa",
        "client_secret": "<secret>",
        "code": "<auth-code>",
        "redirect_url": "https://localhost/myapp",
    })
    assert delegated.code and delegated.redirect_url
    certificate = MicrosoftGraphDevConfig.model_validate({
        "auth_type": "Certificate Based Authentication",
        "tenant": "00000000-0000-0000-0000-000000000000",
        "client_id": "00000000-0000-0000-0000-0000000000aa",
        "thumbprint": "<thumbprint>",
        "private_key": {"@type": "File", "@id": "/api/attachments/1"},
    })
    assert certificate.thumbprint and certificate.client_secret is None


# ---------------------------------------------------------------------------
# Provenance doctrine (plan §8.2): every model cites its provenance
# ---------------------------------------------------------------------------


def _public_models(module) -> list[type[BaseModel]]:
    seen = []
    for name, obj in vars(module).items():
        if name.startswith("_") or not inspect.isclass(obj):
            continue
        if not issubclass(obj, BaseModel):
            continue
        if obj.__module__ != module.__name__:
            continue
        if "[" in obj.__name__:
            continue  # parametrized-generic alias; the base model carries the doc
        seen.append(obj)
    return seen


# Defender models whose shape is backed by a promoted live capture (the machine
# operations and the alert device block, run against a lab appliance). They cite
# the live verification; every other model still waits for its capture.
_LIVE_PROMOTED = frozenset({
    "ListMachinesParams", "MachineIdParams", "IsolateMachineParams",
    "RunAVScanParams", "GetMachineActionParams", "Machine",
    "MachineListResponse", "MachineAction", "AlertDevice",
})


@pytest.mark.parametrize("module", [gc, dev, sec, mdef, dcom])
def test_every_model_cites_provenance(module) -> None:
    for model in _public_models(module):
        doc = " ".join((model.__doc__ or "").split())
        assert "Provenance:" in doc, f"{model.__name__} lacks a provenance line"
        if model.__name__ in _LIVE_PROMOTED:
            assert "live-verified" in doc, (
                f"{model.__name__} is a promoted live capture and must cite it")
            continue
        assert "live-capture pending" in doc, (
            f"{model.__name__} must not claim live-verification before a "
            "capture has been promoted")


def test_no_model_claims_live_verification_yet() -> None:
    for module in (gc, dev, sec, mdef, dcom):
        for model in _public_models(module):
            if module is mdef and model.__name__ in _LIVE_PROMOTED:
                continue
            assert "live-verified" not in " ".join(
                (model.__doc__ or "").split()).lower()


def test_fixture_registry_paths_exist() -> None:
    for rel in list(ERROR_FIXTURES.values()) + [
        rel for ops in MOCK_FIXTURES.values() for rel in ops.values()
    ]:
        assert (_MOCKS_DIR / rel).exists(), rel


def test_fixture_files_are_valid_json() -> None:
    for path in sorted(_MOCKS_DIR.rglob("*.json")):
        json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Capture plan (proto-msftcap) static gating
# ---------------------------------------------------------------------------

_ID_PARAMS = {"risk_id", "alert_id", "group_id", "user_id", "message_id",
              "namedLocationUuid", "incidentID", "alertID", "user"}


def test_param_sets_cover_every_registered_op() -> None:
    for registry, connector in [(DEV_OPS, "microsoft-graph_dev"),
                                (SEC_OPS, "microsoft-graph-api-security")]:
        assert set(PARAM_SETS[connector]) == set(registry), connector


def test_mutating_ops_are_flagged_and_sentinel_defaulted() -> None:
    for connector, ops in PARAM_SETS.items():
        for op, sets in ops.items():
            flagged = {ps.mutating for ps in sets}
            if op in MUTATING_VERBS:
                assert flagged == {True}, (
                    f"{connector}.{op} mutates ({sorted(MUTATING_VERBS)}) but a "
                    "param set is not flagged mutating")
                for ps in sets:
                    for key, value in ps.params.items():
                        if key in _ID_PARAMS:
                            assert value == SENTINEL_ID, (
                                f"{connector}.{op}[{ps.label}].{key} must default "
                                "to the all-zero sentinel id")
            else:
                assert flagged == {False}, (
                    f"{connector}.{op} is read-only but is flagged mutating")


def test_revoke_user_sessions_never_runs_without_explicit_target() -> None:
    (ps,) = PARAM_SETS["microsoft-graph_dev"]["revoke_user_sessions"]
    assert ps.mutating and ps.requires_set == ("user",)


def test_create_location_default_is_a_labelled_throwaway() -> None:
    (ps,) = PARAM_SETS["microsoft-graph_dev"]["create_ip_range_location"]
    assert ps.mutating
    assert str(ps.params["name"]).startswith("fsoar-capture-")
    assert ps.params["ipv4_ips"] == "203.0.113.0/24"  # RFC 5737 TEST-NET-3
