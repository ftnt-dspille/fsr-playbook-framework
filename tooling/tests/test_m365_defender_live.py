"""LIVE tests: run the soarshelf microsoft-365-defender connector against
the M365 trial tenant and assert each response validates through the typed
models.

Requires ``M365_TENANT_ID`` / ``M365_CLIENT_ID`` / ``M365_CLIENT_SECRET``
(application permissions on the Defender security plane), the soarshelf
checkout at ``SOARSHELF_HOME`` (default ``~/PycharmProjects/soarshelf``),
and ``-m live`` (deselected by default everywhere). Only NON-MUTATING ops
run here: update_incident is exercised only against a not-found id, which
pins the connector's 404-returns-a-raw-Response quirk without touching
tenant state. Real mutations live behind ``--allow-mutating`` in
``fsr_playbooks.connectors.typed.capture_m365_defender``.

An op that 401/403/404/429s is not a failure: the assertion is that the
failure text parses as this connector's error shape (the same shape the
capture script banks). On the current trial tenant the Defender security
plane is NOT provisioned yet, so ``403 Account is not provisioned`` is the
EXPECTED outcome for most/all ops until endpoint onboarding lands -- auth
itself is proven (the Microsoft Threat Protection SP holds
Incident.ReadWrite.All + AdvancedHunting.Read.All).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from fsr_playbooks.connectors.typed import microsoft_365_defender as m
from fsr_playbooks.connectors.typed.capture_m365_defender import (
    SENTINEL_ID,
    acquire_token,
    build_config,
)
from fsr_playbooks.connectors.typed.defender_common import (
    load_connector_package,
    parse_connector_error_message,
    stub_fortisoar_connector_sdk,
)

pytestmark = pytest.mark.live

_TENANT = os.environ.get("M365_TENANT_ID")
if not _TENANT:
    _TENANT = os.environ.get("M365_DEFENDER_TENANT_ID", "")
_CLIENT_ID = os.environ.get("M365_CLIENT_ID") or os.environ.get(
    "M365_DEFENDER_CLIENT_ID", ""
)
_CLIENT_SECRET = os.environ.get("M365_CLIENT_SECRET") or os.environ.get(
    "M365_DEFENDER_CLIENT_SECRET", ""
)
_SOARSHELF = Path(
    os.environ.get("SOARSHELF_HOME", Path.home() / "PycharmProjects" / "soarshelf")
)
_SRC = Path(
    os.environ.get(
        "FSRPB_DEFENDER_CONNECTOR_SRC",
        str(
            _SOARSHELF
            / "content"
            / "connectors"
            / "fetch-microsoft-365-defender-incidents-oldest-first"
            / "package"
            / "microsoft-365-defender"
        ),
    )
)

if not (_TENANT and _CLIENT_ID and _CLIENT_SECRET):
    pytest.skip(
        "live M365 Defender capture needs M365_TENANT_ID / M365_CLIENT_ID / "
        "M365_CLIENT_SECRET (or the M365_DEFENDER_* spellings)",
        allow_module_level=True,
    )
if not (_SRC / "operations.py").is_file():
    pytest.skip(
        f"connector source not found at {_SRC} (set FSRPB_DEFENDER_CONNECTOR_SRC)",
        allow_module_level=True,
    )

stub_fortisoar_connector_sdk()
_PKG = load_connector_package(_SRC, "fsrpb_live_m365_defender")

#: statuses a failed op may legally report on the trial tenant
_ACCEPTED_ERROR_STATUS = (401, 403, 404, 429)


@pytest.fixture(scope="module")
def live() -> tuple[Any, dict[str, Any], dict[str, str]]:
    """(operations module, preseeded config, connector_info).

    The config carries the RAW access token (``validate_token`` adds the
    ``Bearer `` prefix itself) and an epoch-float ``expiresOn`` -- the two
    shapes the live captures corrected.
    """
    token = acquire_token(_TENANT, _CLIENT_ID, _CLIENT_SECRET)
    config = build_config(token, _TENANT, _CLIENT_ID, _CLIENT_SECRET)
    import json

    info = json.loads((_SRC / "info.json").read_text())
    connector_info = {
        "connector_name": info["name"],
        "connector_version": info["version"],
    }
    return _PKG.operations, config, connector_info


def _assert_live_result(op: str, fixture: dict[str, Any]) -> Any:
    """Success validates through the model; a failure must parse as one of
    the accepted error statuses (403 not-provisioned included)."""
    kind = fixture["kind"]
    if kind == "raw_response":
        # the connector's 404 quirk: the op RETURNS the Response object
        assert fixture["status_code"] in (404, 403), fixture
        return None
    if kind == "ok":
        model = m.OPERATION_MODELS[op]
        return model.model_validate(fixture["response"])
    assert kind == "connector_error", fixture
    parsed = parse_connector_error_message(fixture["message"])
    if parsed is not None:
        assert parsed["status_code"] in _ACCEPTED_ERROR_STATUS, fixture
        assert parsed["details"], fixture
        return parsed
    pytest.fail(f"error text did not parse: {fixture['message'][:300]}")


def _run_live(
    ops: Any,
    config: dict[str, Any],
    connector_info: dict[str, str],
    op: str,
    params: dict[str, Any],
) -> None:
    """Run one op and funnel the outcome through :func:`_assert_live_result`."""
    fn = getattr(ops, op)
    try:
        response = fn(config, dict(params), dict(connector_info))
    except Exception as exc:  # ConnectorError and friends ARE valid outcomes
        _assert_live_result(op, {"kind": "connector_error", "message": str(exc)})
        return
    status = getattr(response, "status_code", None)
    if status is not None:
        # the documented 404 quirk: api_request returns the Response itself
        _assert_live_result(op, {"kind": "raw_response", "status_code": status})
        return
    _assert_live_result(op, {"kind": "ok", "response": response})


class TestLiveM365Defender:
    def test_config_and_token_shapes(self, live) -> None:
        """The two live-capture corrections, pinned against the real flow:
        the preseeded token is RAW and ``expiresOn`` is an epoch float the
        config model accepts."""
        _ops, config, _info = live
        assert config["accessToken"].startswith("eyJ")
        assert not config["accessToken"].startswith("Bearer ")
        assert isinstance(config["expiresOn"], float)
        m.DefenderConnectorConfig.model_validate(config)

    def test_list_incidents_validates_or_errors_cleanly(self, live) -> None:
        ops, config, info = live
        _run_live(
            ops, config, info, "list_incidents", {"get_all_records": False, "top": 5}
        )
        _run_live(
            ops,
            config,
            info,
            "list_incidents",
            {"status": ["Active"], "get_all_records": False, "top": 5},
        )

    def test_get_incident_from_the_listing(self, live) -> None:
        ops, config, info = live
        listing = ops.list_incidents(
            config, {"get_all_records": False, "top": 5}, dict(info)
        )
        status = getattr(listing, "status_code", None)
        if status is not None:
            pytest.skip(f"listing did not return incidents (HTTP {status})")
        value = (listing or {}).get("value") or []
        if not value:
            pytest.skip("tenant has no incidents to fetch")
        incident_id = str(value[0]["incidentId"])
        _run_live(ops, config, info, "get_incident", {"id": incident_id})

    def test_get_incident_not_found_is_a_raw_response_or_clean_error(
        self, live
    ) -> None:
        """The 404 quirk, pinned live: a bad id RETURNS a raw Response (not a
        ConnectorError, not an incident body) on a provisioned tenant; on a
        not-provisioned one the 403 raises instead. Both are accepted."""
        ops, config, info = live
        _run_live(ops, config, info, "get_incident", {"id": SENTINEL_ID})

    def test_update_incident_not_found_never_mutates(self, live) -> None:
        ops, config, info = live
        _run_live(
            ops,
            config,
            info,
            "update_incident",
            {"id": SENTINEL_ID, "comment": "soarshelf live test"},
        )

    def test_advanced_hunting_validates_or_errors_cleanly(self, live) -> None:
        ops, config, info = live
        _run_live(
            ops, config, info, "advanced_hunting", {"Query": "DeviceInfo | take 5"}
        )

    def test_bad_kql_parses_as_a_documented_error(self, live) -> None:
        ops, config, info = live
        try:
            getattr(ops, "advanced_hunting")(
                config, {"Query": "this is not kql !!!"}, dict(info)
            )
        except Exception as exc:
            parsed = parse_connector_error_message(str(exc))
            assert parsed is not None, str(exc)[:300]
            assert parsed["status_code"] in _ACCEPTED_ERROR_STATUS
        else:
            pytest.fail("a garbage KQL query unexpectedly succeeded")
