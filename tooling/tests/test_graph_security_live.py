"""LIVE tests: run the soarshelf Graph security connectors against the
M365 trial tenant and assert each response validates through the typed
models.

Requires ``M365_TENANT_ID`` / ``M365_CLIENT_ID`` / ``M365_CLIENT_SECRET``
(application permissions on Graph), the soarshelf checkout at
``SOARSHELF_HOME`` (default ``~/PycharmProjects/soarshelf``), and
``-m live`` (deselected by default everywhere). Only READ-ONLY ops run
here; the mutating ops live behind ``--allow-mutating`` in
``fsr_playbooks.connectors.typed.capture_graph_security`` and are never
touched by tests.

An op that 403s (riskyUsers on a P1 tenant, advanced hunting without
Defender XDR) is not a failure: the assertion is that the failure text
parses as a Graph error (the same shape the capture script banks).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fsr_playbooks.connectors.typed.capture_graph_security import (
    CONNECTOR_SOURCES,
    PARAM_SETS,
    _install_sdk_stubs,
    acquire_token,
    build_config,
    load_connector_package,
    run_op,
)
from fsr_playbooks.connectors.typed.graph_common import (
    extract_error_body,
    parse_graph_connector_error,
)

pytestmark = pytest.mark.live

_TENANT = os.environ.get("M365_TENANT_ID", "")
_CLIENT_ID = os.environ.get("M365_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("M365_CLIENT_SECRET", "")
_SOARSHELF = Path(os.environ.get("SOARSHELF_HOME",
                                 Path.home() / "PycharmProjects" / "soarshelf"))

if not (_TENANT and _CLIENT_ID and _CLIENT_SECRET):
    pytest.skip(
        "live M365 Graph capture needs M365_TENANT_ID / M365_CLIENT_ID / "
        "M365_CLIENT_SECRET", allow_module_level=True)
if not (_SOARSHELF / "content" / "connectors").exists():
    pytest.skip(
        f"soarshelf checkout not found at {_SOARSHELF} (set SOARSHELF_HOME)",
        allow_module_level=True)

_install_sdk_stubs()

_LOADED: dict[str, tuple[object, dict]] = {}
for _connector, _source in CONNECTOR_SOURCES.items():
    _LOADED[_connector] = load_connector_package(_source, _SOARSHELF)

#: ops whose 403/404 is the EXPECTED outcome on a Business Premium tenant
_MAY_ERROR = {"get_risky_users_list", "get_risky_user_details",
              "run_advanced_hunting", "get_security_alert",
              "get_group_users"}


@pytest.fixture(scope="module")
def live_config():
    token = acquire_token(_TENANT, _CLIENT_ID, _CLIENT_SECRET)
    return {connector: build_config(connector, token, _TENANT, _CLIENT_ID,
                                    _CLIENT_SECRET, _LOADED[connector][1])
            for connector in CONNECTOR_SOURCES}


def _live_params(connector: str, op: str) -> dict:
    param_set = PARAM_SETS[connector][op][0]
    assert not param_set.mutating, f"{op} must stay read-only in live tests"
    return dict(param_set.params)


def _assert_live_result(connector: str, op: str, fixture: dict) -> None:
    kind = fixture["kind"]
    if kind == "ok":
        from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
            OPERATION_MODELS as SEC_OPS,
        )
        from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
            OPERATION_MODELS as DEV_OPS,
        )
        model = (DEV_OPS if connector == "microsoft-graph_dev" else SEC_OPS)[op]
        model.model_validate(fixture["response"])
        return
    assert kind == "connector_error", fixture
    text = fixture["message"]
    parsed = parse_graph_connector_error(text)
    if parsed is not None:
        assert parsed.status in (403, 404, 401, 429), text
        return
    if op not in _MAY_ERROR:
        # read ops on a healthy tenant should succeed; a raw non-Graph
        # failure here is a real bug (or an expired token) -- fail loudly
        pytest.fail(f"{connector}.{op} failed with an unrecognized error: "
                    f"{text[:300]}")
    assert extract_error_body(text) is not None, (
        f"{connector}.{op}: error carried no JSON body: {text[:300]}")


@pytest.mark.parametrize("connector", sorted(CONNECTOR_SOURCES))
def test_read_ops_validate_through_models(live_config, connector: str) -> None:
    """Every read-only op validates through its model, or fails with a
    parseable Graph error."""
    source = CONNECTOR_SOURCES[connector]
    pkg, _info = _LOADED[connector]
    for op in sorted(PARAM_SETS[connector]):
        if PARAM_SETS[connector][op][0].mutating:
            continue
        fixture = run_op(connector, source, pkg, _info, live_config[connector],
                         op, _live_params(connector, op))
        _assert_live_result(connector, op, fixture)


def test_preseeded_config_carries_both_tenant_field_names(live_config) -> None:
    dev_config = live_config["microsoft-graph_dev"]
    sec_config = live_config["microsoft-graph-api-security"]
    assert dev_config["tenant"] == _TENANT and "tenant_id" not in dev_config
    assert sec_config["tenant_id"] == _TENANT and "tenant" not in sec_config
    # RAW token: validate_token adds the "Bearer " prefix itself; a prefixed
    # value here becomes a live-proven "Bearer Bearer …" header (Graph
    # InvalidAuthenticationToken).
    assert dev_config["accessToken"].startswith("eyJ")
    assert not dev_config["accessToken"].startswith("Bearer ")
    assert sec_config["accessToken"].startswith("eyJ")
