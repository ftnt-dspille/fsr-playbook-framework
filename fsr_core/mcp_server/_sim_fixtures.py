"""Canned fixtures for :mod:`fsr_core.mcp_server._sim_client`.

Kept separate from the client transport so the data is easy to read, extend,
and assert against in tests. Everything here is fabricated demo data —
plausible shapes, obviously-synthetic values.

The (connector, operation) registry below is the "lot of tools and functions
we simulate": each entry returns a result whose *shape* matches what the real
connector op returns, so the agent's downstream reasoning, the enrichment
summarizer, and the widget cards all behave as they would live.

Add a new op by dropping another entry in :data:`_EXECUTE`. Unknown pairs
fall back to :func:`_generic`, so a hunt never dead-ends in sim mode.
"""
from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Configured-connector roster (connector_details / list_configured_connectors)
# ---------------------------------------------------------------------------
# name -> version. All reported healthy + "Completed" in sim mode so the
# preflight gate passes and the agent has a fully-wired instance to work with.
_ROSTER: dict[str, str] = {
    "fortinet-fortisiem": "5.4.2",
    "splunk": "2.0.2",
    "elasticsearch": "4.0.0",
    "virustotal": "4.0.0",
    "shodan": "2.0.0",
    "abuseipdb": "1.0.0",
    "fortinet-fortiguard-threat-intelligence": "1.2.0",
    "fortigate-firewall": "2.1.0",
    "cyops_utilities": "3.0.0",
    "mitre-attack": "2.0.0",
}


def connector_rows() -> list[dict[str, Any]]:
    """The ``data`` list returned by /api/integration/connector_details/."""
    rows = []
    for name, version in _ROSTER.items():
        rows.append({
            "name": name,
            "version": version,
            "status": "Completed",
            "configs": [{"name": "simulation", "config_id": f"sim-{name}"}],
        })
    return rows


def connector_from_healthcheck_path(path: str) -> str:
    """Extract the connector name from a healthcheck URL.

    /api/integration/connectors/healthcheck/<connector>/<version>/?config=…
    """
    core = path.split("?", 1)[0]
    parts = [p for p in core.split("/") if p]
    if "healthcheck" in parts:
        i = parts.index("healthcheck")
        if i + 1 < len(parts):
            return parts[i + 1]
    return ""


def healthcheck(_name: str) -> dict[str, Any]:
    return {"status": "available", "message": "simulated — connector reachable"}


# ---------------------------------------------------------------------------
# Per-(connector, operation) execute fixtures
# ---------------------------------------------------------------------------
# Demo entities the SIEM fixtures are wired around.
_C2_IP = "185.220.101.47"
_HOST = "WIN-HR-04"
_HOST_IP = "10.10.20.55"
_USER = "j.harmon"


def _siem_ip_context(params: dict) -> Any:
    ip = params.get("value") or params.get("ip") or _C2_IP
    return {
        "ipAddress": ip,
        "hostName": _HOST if ip == _HOST_IP else "(external)",
        "deviceType": "Workstation" if ip == _HOST_IP else "Unknown/External",
        "location": {"country": "DE", "city": "Frankfurt"} if ip == _C2_IP
                    else {"country": "US", "city": "Austin"},
        "firstSeen": "2026-05-29T06:14:02Z",
        "lastSeen": "2026-05-29T09:51:44Z",
        "knownMalicious": ip == _C2_IP,
        "tags": ["tor-exit", "c2-suspected"] if ip == _C2_IP else [],
    }


def _siem_host_context(params: dict) -> Any:
    host = params.get("value") or params.get("hostname") or _HOST
    return {
        "hostName": host,
        "ipAddress": _HOST_IP,
        "deviceType": "Workstation",
        "os": "Windows 11 23H2",
        "owner": _USER,
        "department": "Human Resources",
        "lastLogon": {"user": _USER, "time": "2026-05-29T06:02:11Z"},
        "openIncidents": 1,
        "criticality": "medium",
    }


def _siem_user_context(params: dict) -> Any:
    user = params.get("value") or params.get("user") or _USER
    return {
        "user": user,
        "displayName": "Jordan Harmon",
        "department": "Human Resources",
        "managedHosts": [_HOST],
        "recentLogons": [
            {"host": _HOST, "ip": _HOST_IP, "time": "2026-05-29T06:02:11Z",
             "result": "success"},
            {"host": _HOST, "ip": _HOST_IP, "time": "2026-05-28T17:48:33Z",
             "result": "success"},
        ],
        "riskScore": 62,
        "mfaEnabled": True,
    }


def _siem_search_events(params: dict) -> Any:
    """A short, ordered event sequence linking the host to the C2 IP."""
    return [
        {"phRecvTime": "2026-05-29T09:12:05Z", "eventType": "Traffic",
         "eventName": "Outbound Connection", "srcIpAddr": _HOST_IP,
         "destIpAddr": _C2_IP, "destPort": 443, "user": _USER,
         "action": "ALLOW", "bytesOut": 18422},
        {"phRecvTime": "2026-05-29T09:21:39Z", "eventType": "Traffic",
         "eventName": "Outbound Connection", "srcIpAddr": _HOST_IP,
         "destIpAddr": _C2_IP, "destPort": 443, "user": _USER,
         "action": "ALLOW", "bytesOut": 20144},
        {"phRecvTime": "2026-05-29T09:44:12Z", "eventType": "Traffic",
         "eventName": "Outbound Connection (Beacon)", "srcIpAddr": _HOST_IP,
         "destIpAddr": _C2_IP, "destPort": 443, "user": _USER,
         "action": "ALLOW", "bytesOut": 19877},
    ]


def _siem_incidents(_params: dict) -> Any:
    return [
        {"incidentId": "INC-2026-04821", "title": "Suspected C2 beaconing",
         "severity": "High", "status": "Active", "host": _HOST,
         "indicator": _C2_IP, "created": "2026-05-29T09:50:00Z"},
    ]


def _vt_query_ip(params: dict) -> Any:
    ip = params.get("ip") or params.get("value") or _C2_IP
    return {
        "id": ip,
        "type": "ip_address",
        "attributes": {
            "last_analysis_stats": {"malicious": 14, "suspicious": 2,
                                    "harmless": 52, "undetected": 18},
            "reputation": -41,
            "total_votes": {"harmless": 1, "malicious": 27},
            "tags": ["tor", "malicious-activity"],
            "country": "DE",
            "as_owner": "ForPrivacyNET",
            "asn": 60729,
            "network": "185.220.101.0/24",
            "last_analysis_date": 1748509200,
        },
    }


def _shodan_host(params: dict) -> Any:
    ip = params.get("ip") or params.get("value") or _C2_IP
    return {
        "ip_str": ip,
        "org": "ForPrivacyNET",
        "isp": "ForPrivacyNET",
        "asn": "AS60729",
        "country_name": "Germany",
        "country_code": "DE",
        "city": "Frankfurt",
        "hostnames": [],
        "ports": [22, 443, 9001, 9030],
        "tags": ["tor"],
        "os": None,
        "last_update": "2026-05-27T22:10:03Z",
        "vulns": [],
    }


def _abuseipdb(params: dict) -> Any:
    ip = params.get("ipAddress") or params.get("ip") or params.get("value") or _C2_IP
    return {
        "data": {
            "ipAddress": ip,
            "abuseConfidenceScore": 100,
            "countryCode": "DE",
            "totalReports": 1843,
            "numDistinctUsers": 412,
            "isTor": True,
            "isWhitelisted": False,
            "usageType": "Data Center/Web Hosting/Transit",
            "domain": "for-privacy.net",
            "isp": "ForPrivacyNET",
            "lastReportedAt": "2026-05-29T07:33:00Z",
        }
    }


def _firewall_block_ip(params: dict) -> Any:
    ip = (params.get("ip") or params.get("ip_address")
          or params.get("value") or _C2_IP)
    return {
        "status": "success",
        "message": f"Address object created and added to deny policy for {ip}",
        "policyId": "deny-c2-egress",
        "addressObject": f"BLOCK_{ip}",
        "blockedIp": ip,
    }


_EXECUTE: dict[tuple[str, str], Callable[[dict], Any]] = {
    ("fortinet-fortisiem", "get_ip_context"): _siem_ip_context,
    ("fortinet-fortisiem", "get_host_context"): _siem_host_context,
    ("fortinet-fortisiem", "get_user_context"): _siem_user_context,
    ("fortinet-fortisiem", "search_events"): _siem_search_events,
    ("fortinet-fortisiem", "get_incidents"): _siem_incidents,
    ("virustotal", "query_ip"): _vt_query_ip,
    ("shodan", "host_information"): _shodan_host,
    ("shodan", "query_ip"): _shodan_host,
    ("abuseipdb", "check_ip"): _abuseipdb,
    ("fortigate-firewall", "block_ip_new"): _firewall_block_ip,
    ("fortigate-firewall", "block_ip"): _firewall_block_ip,
}


def _generic(connector: str, op: str, params: dict) -> Any:
    return {"ok": True, "simulated": True, "connector": connector,
            "operation": op, "params": params,
            "note": "no specific sim fixture; generic ok envelope"}


def execute(connector: Any, op: Any, params: dict) -> Any:
    fn = _EXECUTE.get((connector, op))
    if fn is not None:
        return fn(params or {})
    return _generic(connector, op, params or {})
