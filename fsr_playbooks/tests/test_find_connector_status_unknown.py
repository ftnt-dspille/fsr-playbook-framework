"""find(kind="operation") must not say configured:false when the configured
lookup returned nothing.

A run saw `connector_status: {configured: false}` for a connector that
list_configured_connectors had just listed Available. `_configured_rows` returns
[] when the lookup fails or the cache is cold, and the listing fails open on that;
the status claimed a verdict instead of saying nothing.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fsr_playbooks.mcp_server import tools_execution as te
from fsr_playbooks.mcp_server import tools_find as tf


def _status(rows, name="servicenow"):
    cfg = MagicMock()
    cfg.is_live.return_value = True
    with patch("probes._env.get_config", return_value=cfg), \
         patch("probes._env.get_client", return_value=MagicMock()), \
         patch.object(te, "_configured_rows", return_value=rows), \
         patch.object(te, "_cached_health", return_value={"status": "Available"}):
        return tf._connector_status(name)


def test_empty_lookup_is_unknown_not_unconfigured():
    assert _status([]) is None


def test_listed_connector_is_configured():
    assert _status([{"name": "servicenow", "version": "1.0"}]) == {
        "configured": True, "health": "Available"}


def test_absent_connector_among_others_is_unconfigured():
    assert _status([{"name": "virustotal"}]) == {"configured": False}
