"""Smoke: the capture loader runs the REAL soarshelf connector packages
in-process, off-box (SDK stubs in place, no network).

Skipped unless a soarshelf checkout exists (``SOARSHELF_HOME`` or
``~/PycharmProjects/soarshelf``); CI has no soarshelf and stays green.
This is the offline half of the live suite: it proves the loader, the SDK
stubs and the operations-dict wiring before any tenant is touched.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fsr_playbooks.connectors.typed.capture_graph_security import (
    CONNECTOR_SOURCES,
    PARAM_SETS,
    _install_sdk_stubs,
    load_connector_package,
)
from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
    OPERATION_MODELS as SEC_OPS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    OPERATION_MODELS as DEV_OPS,
)

_SOARSHELF = Path(os.environ.get("SOARSHELF_HOME",
                                 Path.home() / "PycharmProjects" / "soarshelf"))

pytestmark = pytest.mark.skipif(
    not (_SOARSHELF / "content" / "connectors").exists(),
    reason=f"soarshelf checkout not found at {_SOARSHELF} (set SOARSHELF_HOME)")

_install_sdk_stubs()

_LOADED = {name: load_connector_package(src, _SOARSHELF)
           for name, src in CONNECTOR_SOURCES.items()}


def test_dev_package_loads_with_all_seventeen_ops() -> None:
    pkg, info = _LOADED["microsoft-graph_dev"]
    assert info["version"] == "3.1.0"
    ops = set(pkg.operations.operations)
    assert ops - {"check_health"} == set(DEV_OPS)
    assert set(PARAM_SETS["microsoft-graph_dev"]) == set(DEV_OPS)


def test_sec_package_loads_with_all_five_ops() -> None:
    pkg, info = _LOADED["microsoft-graph-api-security"]
    assert info["version"] == "1.0.0"
    assert set(pkg.operations.operations) == set(SEC_OPS)
    assert set(PARAM_SETS["microsoft-graph-api-security"]) == set(SEC_OPS)


def test_update_security_alert_exists_but_is_not_registered() -> None:
    # the fork carries an update_security_alert FUNCTION that its operations
    # dict does not register -- it is not an op surface, so neither the
    # registry nor the capture plan may include it
    pkg, _ = _LOADED["microsoft-graph-api-security"]
    assert hasattr(pkg.operations, "update_security_alert")
    assert "update_security_alert" not in pkg.operations.operations
    assert "update_security_alert" not in SEC_OPS


def test_stubs_absorb_the_connector_sdk() -> None:
    import connectors.core.connector as stub
    import integrations.crudhub as crudhub
    import msal

    logger = stub.get_logger("x")
    logger.info("no-op")
    with pytest.raises(NotImplementedError):
        crudhub.make_request("/x", "GET")
    with pytest.raises(NotImplementedError):
        msal.ConfidentialClientApplication("id")
