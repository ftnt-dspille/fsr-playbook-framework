#!/usr/bin/env python3
"""Live capture driver for the microsoft-365-defender connector ops.

Enumerates the connector's 4 operations (list_incidents, get_incident,
update_incident, advanced_hunting) with representative parameter sets, runs
them against the live Microsoft 365 Defender tenant, and writes one JSON
fixture per capture into ``scratch/captures/microsoft-365-defender/``
(``scratch/`` is gitignored -- raw captures stay local; promote SANITIZED
shapes into ``mocks/microsoft-365-defender/`` by hand).

The connector package is imported BY PATH (it is a dash-named FortiSOAR
connector source, not an installed module); the FortiSOAR connector SDK is
stubbed in-process when absent, so this runs on any machine with
``requests``. Credentials come ONLY from the environment:

    M365_DEFENDER_TENANT_ID      directory (tenant) id
    M365_DEFENDER_CLIENT_ID      application (client) id
    M365_DEFENDER_CLIENT_SECRET  application secret
    M365_DEFENDER_RESOURCE       optional; default https://api.security.microsoft.com

Representative parameter sets are cited from the connector's own sample
playbook (``playbooks/playbooks.json``) and the reference store's
``operation_params`` (connector ``microsoft-365-defender``).

Error bodies are valid fixtures too: a syntactically-bad KQL query (400), a
not-found incident id (404 -- which this connector RETURNS as a raw
``requests.Response`` instead of raising: recorded as status/reason/body), and
optionally (``--auth-error``) a token request with a deliberately-wrong secret
(AADSTS envelope, raw body + the ConnectorError message the connector raises).

``update_incident`` is CAPTURED NON-MUTATINGLY by default (a not-found id).
``--write`` additionally performs one REAL update (a comment on the first
listed incident) -- run it only against a tenant where that is acceptable.

Usage (run from the fsr-playbook-framework repo root):

    .venv/bin/python -m fsr_playbooks.connectors.typed.capture_m365_defender \
        [--connector-src PATH] [--out DIR] [--incident-id ID] [--write] [--auth-error]

Default connector source:
``~/PycharmProjects/soarshelf/content/connectors/fetch-microsoft-365-defender-incidents-oldest-first/package/microsoft-365-defender``
(override with ``FSRPB_DEFENDER_CONNECTOR_SRC`` or ``--connector-src``).

This script is NOT run by the test suite; it exists so the main session can
produce captures in one command when live creds are available.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .defender_common import load_connector_package, stub_fortisoar_connector_sdk

DEFAULT_CONNECTOR_SRC = (
    "~/PycharmProjects/soarshelf/content/connectors/"
    "fetch-microsoft-365-defender-incidents-oldest-first/package/microsoft-365-defender"
)
DEFAULT_OUT = Path("scratch/captures/microsoft-365-defender")

_NOT_FOUND_ID = "999999"
_BAD_KQL = "this is not kql !!!"
_CAPTURE_COMMENT = "soarshelf capture"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _defender_dt(dt: datetime) -> str:
    """The ONLY datetime form ``convert_date_time`` accepts (with .%f)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _env_creds() -> dict[str, Any] | None:
    tenant = os.environ.get("M365_DEFENDER_TENANT_ID")
    client = os.environ.get("M365_DEFENDER_CLIENT_ID")
    secret = os.environ.get("M365_DEFENDER_CLIENT_SECRET")
    if not (tenant and client and secret):
        return None
    config: dict[str, Any] = {
        "auth_type": "Without a User - Application Permission",
        "resource": os.environ.get("M365_DEFENDER_RESOURCE")
        or "https://api.security.microsoft.com",
        "tenant_id": tenant,
        "client_id": client,
        "client_secret": secret,
        "verify_ssl": True,
    }
    return config


def _record_response(result: Any) -> dict[str, Any]:
    """Shape whatever the op returned into a JSON-recordable mapping.

    The op returns parsed JSON for 2xx bodies, ``True`` for an empty body,
    and a raw ``requests.Response`` for a 404 (the connector's documented
    quirk) -- the last one is recorded as status/reason/body.
    """
    if hasattr(result, "status_code"):  # raw requests.Response (404 quirk)
        return {
            "raw_response": True,
            "status_code": result.status_code,
            "reason": result.reason,
            "body": result.text[:4000],
        }
    return {"raw_response": False, "body": result}


def _write(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _capture(
    ops: Any, op_name: str, params: dict[str, Any], config: dict[str, Any],
    connector_info: dict[str, str], out_dir: Path, variant: str = "",
) -> dict[str, Any] | None:
    label = "{}{}.json".format(op_name, ("." + variant) if variant else "")
    try:
        result = getattr(ops, op_name)(config, dict(params), dict(connector_info))
        recorded = _record_response(result)
    except Exception as err:  # ConnectorError and friends ARE error fixtures
        recorded = {"raised": type(err).__name__, "message": str(err)}
        ok = False
    else:
        ok = not recorded.get("raw_response")
    path = _write(out_dir, label, {
        "connector": connector_info["connector_name"],
        "version": connector_info["connector_version"],
        "op": op_name,
        "params": params,
        "captured_at_utc": _utcnow().isoformat(timespec="seconds") + "Z",
        "response": recorded,
    })
    status = "captured" if ok else ("ERROR (fixture)" if "raised" not in recorded
                                    else "RAISED (fixture)")
    print(f"  {label}: {status} -> {path}")
    return recorded if ok else None


def _error_probe(
    ops: Any, op_name: str, params: dict[str, Any], config: dict[str, Any],
    connector_info: dict[str, str], out_dir: Path, tag: str,
) -> None:
    """Run an op expected to FAIL and record the error shape."""
    try:
        result = getattr(ops, op_name)(config, dict(params), dict(connector_info))
        recorded = _record_response(result)
        kind = "raw_response" if recorded.get("raw_response") else "unexpected_success"
    except Exception as err:
        recorded = {"raised": type(err).__name__, "message": str(err)}
        kind = "raised"
    path = _write(out_dir, f"{op_name}.error_{tag}.json", {
        "connector": connector_info["connector_name"],
        "version": connector_info["connector_version"],
        "op": op_name,
        "params": params,
        "captured_at_utc": _utcnow().isoformat(timespec="seconds") + "Z",
        "error_kind": kind,
        "response": recorded,
    })
    print(f"  {op_name}.error_{tag}.json: {kind} -> {path}")


def _auth_error_probe(config: dict[str, Any], connector_info: dict[str, str],
                      out_dir: Path) -> None:
    """Token request with a deliberately-wrong secret -> raw AADSTS body."""
    import requests

    token_url = "https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(
        config["tenant_id"]
    )
    data = {
        "grant_type": "client_credentials",
        "client_id": config["client_id"],
        "client_secret": "deliberately-wrong-do-not-use",
        "scope": "https://api.security.microsoft.com/.default offline_access",
    }
    resp = requests.post(token_url, data=data, verify=config.get("verify_ssl", True))
    try:
        body: Any = resp.json()
    except ValueError:
        body = resp.text
    path = _write(out_dir, "token.error_auth.json", {
        "connector": connector_info["connector_name"],
        "version": connector_info["connector_version"],
        "op": "token",
        "captured_at_utc": _utcnow().isoformat(timespec="seconds") + "Z",
        "status_code": resp.status_code,
        "response": {"raw_response": False, "body": body},
    })
    print(f"  token.error_auth.json: {resp.status_code} -> {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--connector-src", default=os.environ.get("FSRPB_DEFENDER_CONNECTOR_SRC")
        or DEFAULT_CONNECTOR_SRC,
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--incident-id", help="use this incident id instead of the first listed")
    parser.add_argument("--write", action="store_true",
                        help="also perform ONE real update_incident (comment)")
    parser.add_argument("--no-error-probes", action="store_true")
    parser.add_argument("--auth-error", action="store_true",
                        help="also capture an AADSTS invalid-client body")
    args = parser.parse_args(argv)

    config = _env_creds()
    if config is None:
        print("M365_DEFENDER_TENANT_ID / _CLIENT_ID / _CLIENT_SECRET are not set "
              "-- nothing captured (the test suite never runs this).", file=sys.stderr)
        return 2

    stubbed = stub_fortisoar_connector_sdk()
    src = Path(args.connector_src).expanduser()
    pkg = load_connector_package(src, "fsrpb_capture_m365_defender")
    ops = pkg.operations
    info_path = src / "info.json"
    info = json.loads(info_path.read_text())
    connector_info = {
        "connector_name": info["name"],
        "connector_version": info["version"],
    }
    out_dir = Path(args.out)
    print("capturing {} v{} from {} (SDK stubbed: {})".format(
        connector_info["connector_name"], connector_info["connector_version"],
        src, stubbed,
    ))
    print(f"config keys used: {sorted(config.keys())}")

    # mint + cache the token exactly like the connector's health check does
    check = getattr(ops, "check")
    try:
        check(config, dict(connector_info))
    except Exception as err:
        print(f"token mint FAILED: {type(err).__name__}: {err}",
              file=sys.stderr)
        print("(if the creds are right but the tenant rejects the grant, capture "
              "the body with --auth-error)", file=sys.stderr)
        return 1
    print("token minted (accessToken present: {})".format(bool(config.get("accessToken"))))

    failures: list[str] = []

    # -- list_incidents ------------------------------------------------------
    week_ago = _defender_dt(_utcnow() - timedelta(days=7))
    primary = _capture(ops, "list_incidents", {
        "get_all_records": False, "top": 5,
    }, config, connector_info, out_dir)
    if primary is None:
        failures.append("list_incidents")
    _capture(ops, "list_incidents", {
        "status": ["Active"], "get_all_records": False, "top": 5,
    }, config, connector_info, out_dir, variant="status_active")
    _capture(ops, "list_incidents", {
        "get_all_records": True, "query": f"lastUpdateTime ge {week_ago}",
    }, config, connector_info, out_dir, variant="incremental_pull")
    _capture(ops, "list_incidents", {
        "lastUpdateTime": week_ago, "get_all_records": False, "top": 5,
    }, config, connector_info, out_dir, variant="lastupdatetime_param")

    # -- get_incident (id from the listing) ----------------------------------
    first = None
    if primary and isinstance(primary.get("body"), dict):
        value = primary["body"].get("value") or []
        if value:
            first = str(value[0].get("incidentId"))
    incident_id = args.incident_id or first
    if incident_id:
        if _capture(ops, "get_incident", {"id": incident_id},
                    config, connector_info, out_dir) is None:
            failures.append("get_incident")
    else:
        failures.append("get_incident (no incident id available)")
        print("  get_incident: SKIPPED -- listing returned no incidents")

    # -- update_incident (non-mutating by default) ---------------------------
    if args.write and incident_id:
        if _capture(ops, "update_incident", {
            "id": incident_id, "comment": _CAPTURE_COMMENT,
        }, config, connector_info, out_dir) is None:
            failures.append("update_incident")
    else:
        if not args.write:
            print("  update_incident: capture is non-mutating by default "
                  "(--write performs one real comment update)")

    # -- advanced_hunting ----------------------------------------------------
    if _capture(ops, "advanced_hunting", {
        "Query": "DeviceInfo | take 5",
    }, config, connector_info, out_dir) is None:
        failures.append("advanced_hunting")
    _capture(ops, "advanced_hunting", {
        "Query": 'search DeviceName: "abc"',
    }, config, connector_info, out_dir, variant="sample_search")

    # -- error bodies (valid fixtures too) ------------------------------------
    if not args.no_error_probes:
        _error_probe(ops, "get_incident", {"id": _NOT_FOUND_ID},
                     config, connector_info, out_dir, "not_found")
        _error_probe(ops, "update_incident", {"id": _NOT_FOUND_ID},
                     config, connector_info, out_dir, "not_found")
        _error_probe(ops, "advanced_hunting", {"Query": _BAD_KQL},
                     config, connector_info, out_dir, "bad_kql")
    if args.auth_error:
        _auth_error_probe(config, connector_info, out_dir)

    print(f"done. fixtures in {out_dir.resolve()}")
    if failures:
        print("FAILED primary captures: {}".format(", ".join(failures)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
