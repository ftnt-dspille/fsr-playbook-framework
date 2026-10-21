"""connector_configs.list_configurations returns EVERY configuration of a
connector, not just the first API page (tracker #159).

The integration API paginates (default 30 per page), so a connector with more
configurations than that must still come back whole. The fake client below
mimics the connector row that /api/integration/connectors/ returns, with the
embedded configuration[] array; it stays offline.
"""
from __future__ import annotations

import pytest

import connector_configs


class _Resp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict:
        return self._payload


class _Session:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, verify=None):
        self.calls.append((url, dict(params or {})))
        return _Resp(self._payload)


class _Client:
    def __init__(self, payload: dict) -> None:
        self.session = _Session(payload)
        self.base_url = "https://fsr.example.com"
        self.verify_ssl = False


def _row(connector: str, n_configs: int) -> dict:
    return {
        "name": connector,
        "configuration": [
            {"config_id": f"cfg-{i:03d}", "name": f"cfg-{i:03d}",
             "default": i == 0}
            for i in range(n_configs)
        ],
    }


@pytest.fixture
def fake_client(monkeypatch, tmp_path):
    # Keep the resolution cache out of the repo's data/ directory.
    monkeypatch.setattr(connector_configs, "CACHE_PATH", tmp_path / "cfg_map.json")
    monkeypatch.setattr(connector_configs, "_cache", None)

    def install(payload: dict) -> _Client:
        client = _Client(payload)
        monkeypatch.setattr(connector_configs, "_live_client", lambda: client)
        return client

    return install


def test_connector_with_more_than_one_page_of_configs_is_returned_whole(fake_client):
    # 45 configurations: past the 30-per-page default the API uses.
    client = fake_client({"data": [_row("fortinet_siem", 45)]})

    configs = connector_configs.list_configurations("fortinet_siem")

    assert len(configs) == 45
    assert [c["config_id"] for c in configs] == [f"cfg-{i:03d}" for i in range(45)]
    assert configs[0]["default"] is True
    assert all(c["default"] is False for c in configs[1:])


def test_last_configuration_past_page_one_is_resolvable(fake_client):
    fake_client({"data": [_row("fortinet_siem", 45)]})
    cid = connector_configs.resolve_config_id("fortinet_siem", "cfg-044")
    assert cid == "cfg-044"


def test_request_asks_for_the_connector_by_name_with_a_large_page(fake_client):
    client = fake_client({"data": [_row("fortinet_siem", 45)]})

    connector_configs.list_configurations("fortinet_siem")

    (url, params), = client.session.calls
    assert url == "https://fsr.example.com/api/integration/connectors/"
    assert params["name"] == "fortinet_siem"
    assert params["page_size"] >= 1000


def test_other_connectors_rows_are_ignored(fake_client):
    fake_client({"data": [_row("other", 40), _row("fortinet_siem", 35)]})
    configs = connector_configs.list_configurations("fortinet_siem")
    assert len(configs) == 35
