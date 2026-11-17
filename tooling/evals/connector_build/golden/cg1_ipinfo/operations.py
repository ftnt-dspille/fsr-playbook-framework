"""Operation handlers for the cg1-ipinfo golden eval connector.

Static-clean against the connector toolkit's own gates: a dispatch dict, two
handlers that take (config, params) and read their required params, a
module-level check_health, and no cyops import antipattern.
"""
from connectors.core.connector import ConnectorError, get_logger

logger = get_logger("cg1-ipinfo")


def _request(config, path, query):
    import requests

    base = str(config.get("base_url", "")).rstrip("/")
    resp = requests.get(
        f"{base}/{path}",
        params=query,
        headers={"Authorization": f"Bearer {config.get('api_key', '')}"},
        timeout=30,
        verify=config.get("verify", True),
    )
    if resp.status_code != 200:
        raise ConnectorError(f"cg1-ipinfo {path} failed: HTTP {resp.status_code}")
    return resp.json()


def lookup_ip(config, params):
    ip = params.get("ip")
    return _request(config, "ip", {"addr": ip})


def lookup_asn(config, params):
    asn = params.get("asn")
    return _request(config, "asn", {"asn": asn})


def check_health(config):
    _request(config, "health", {})
    return True


operations = {
    "lookup_ip": lookup_ip,
    "lookup_asn": lookup_asn,
}
