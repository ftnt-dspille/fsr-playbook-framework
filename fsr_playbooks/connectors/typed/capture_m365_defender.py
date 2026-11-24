#!/usr/bin/env python3
"""proto-msftcap: capture live Microsoft 365 Defender connector fixtures.

Loads the soarshelf microsoft-365-defender connector package BY PATH
(stubbing the FortiSOAR connector SDK it imports), acquires a
client-credentials token against the trial tenant, runs each of the 4 ops
(list_incidents, get_incident, update_incident, advanced_hunting) with
representative param sets, and writes one JSON fixture per capture under
``scratch/captures/microsoft-365-defender/`` (``scratch/`` is gitignored --
raw captures are local-only; promote SANITIZED shapes into
``typed/mocks/microsoft-365-defender/`` by hand, never commit a raw capture).

Fixtures follow the m365-trial plan §8.1 discipline: an op that 403s, 404s
or 429s still produces a fixture (the error body IS a valid fixture). On the
current trial tenant the Defender security plane is NOT provisioned yet, so
``403 Account is not provisioned`` is the EXPECTED outcome for most/all ops
until endpoint onboarding lands -- bank those shapes; auth itself is proven
(the Microsoft Threat Protection SP has Incident.ReadWrite.All +
AdvancedHunting.Read.All granted).

Token shape (live-capture-corrected, mirrors the FIXED
``capture_graph_security.py``): ``acquire_token`` returns the RAW access
token with NO ``Bearer `` prefix -- it is preseeded as ``accessToken`` and
the connector's ``validate_token`` adds the prefix itself; a prefixed value
produces a ``Bearer Bearer …`` header. The preseeded ``expiresOn`` is an
epoch FLOAT (``time.time() + 3300``) -- ``convert_ts_epoch`` runs
``ctime()`` on it, which requires a number; a ctime string crashes.

Usage (from the repo root, after exporting the M365 env vars)::

    export M365_TENANT_ID=... M365_CLIENT_ID=... M365_CLIENT_SECRET=...
    .venv/bin/python -m fsr_playbooks.connectors.typed.capture_m365_defender \
        [--allow-mutating] [--set update_incident.id=9] [--auth-error]

``update_incident`` is captured NON-mutatingly by default (a not-found id,
which also pins the connector's 404-returns-a-raw-Response quirk);
``--allow-mutating`` additionally performs one REAL update (a comment on
the first listed incident, or whatever ``--set`` points at).
``--auth-error`` captures the raw AADSTS invalid-client body via a
deliberately-wrong secret.

Env: ``M365_TENANT_ID`` / ``M365_CLIENT_ID`` / ``M365_CLIENT_SECRET``
(required; ``M365_DEFENDER_*`` spellings accepted as fallback),
``M365_DEFENDER_RESOURCE`` (optional; default
https://api.security.microsoft.com), ``FSRPB_DEFENDER_CONNECTOR_SRC``
(optional; connector source dir override).

This script is NOT run by the test suite; the main session runs it when
live creds are available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from fsr_playbooks.connectors.typed.defender_common import (
    load_connector_package,
    parse_connector_error_message,
    stub_fortisoar_connector_sdk,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTDIR = REPO_ROOT / "scratch" / "captures"
DEFAULT_CONNECTOR_SRC = (
    Path.home()
    / "PycharmProjects"
    / "soarshelf"
    / "content"
    / "connectors"
    / "fetch-microsoft-365-defender-incidents-oldest-first"
    / "package"
    / "microsoft-365-defender"
)

DEFENDER_RESOURCE = "https://api.security.microsoft.com"
AUTH_URL = "https://login.microsoftonline.com"
#: the connector's own scope string (microsoft_api_auth.MicrosoftAuth.scope)
DEFENDER_SCOPE = "https://api.security.microsoft.com/.default offline_access"

#: All-zero sentinel incident id: no real incident carries it, so a
#: get/update aimed at one exercises the 404 path (which this connector
#: RETURNS as a raw requests.Response instead of raising).
SENTINEL_ID = "999999"
_CAPTURE_COMMENT = "soarshelf capture"

MUTATING_OPS = {"update_incident"}


def _env(name: str, fallback: str) -> str:
    return os.environ.get(name) or os.environ.get(fallback, "")


def acquire_token(
    tenant_id: str, client_id: str, client_secret: str, verify_ssl: bool = True
) -> str:
    """Client-credentials token -- the same request
    ``acquire_token_with_client_credentials`` makes (scope included), done
    here so the ops run from a pre-seeded config without the connector's
    refresh/write-back path.

    Returns the RAW access token (NO ``Bearer `` prefix): it is stored in
    the config as ``accessToken`` and the connector's ``validate_token``
    adds the prefix itself -- a prefixed value here produces a live-proven
    ``Bearer Bearer …`` header.
    """
    resp = requests.post(
        f"{AUTH_URL}/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": DEFENDER_SCOPE,
        },
        verify=verify_ssl,
        timeout=60,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"token request failed: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    payload: dict[str, Any] = resp.json()
    return str(payload["access_token"])


def build_config(
    token: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    resource: str = DEFENDER_RESOURCE,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "auth_type": "Without a User - Application Permission",
        "resource": resource,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "verify_ssl": verify_ssl,
        "accessToken": token,  # RAW -- validate_token adds "Bearer " itself
        # epoch float -- matches what the connector itself persists
        # (resp['expiresOn'] = ts_now + resp['expires_in']); convert_ts_epoch
        # calls ctime() on it, so it MUST be a number.
        "expiresOn": time.time() + 3300,
        "config_id": "capture",
    }
    return config


def _jsonable(result: Any) -> Any:
    """The ops return parsed JSON, ``True`` (empty body), or -- on the 404
    path -- a raw requests.Response; make all three fixture-shaped."""
    if isinstance(result, (bool, int, float, str)) or result is None:
        return result
    if isinstance(result, (dict, list)):
        return result
    status = getattr(result, "status_code", None)
    if status is not None:
        # the documented 404 quirk: api_request returns the Response itself
        try:
            body: Any = result.json()
        except ValueError:
            body = None
        return {
            "__response_object__": True,
            "status_code": status,
            "body": body,
            "text": getattr(result, "text", "")[:2000],
        }
    return repr(result)


def run_op(
    ops: Any,
    op: str,
    config: dict[str, Any],
    params: dict[str, Any],
    connector_info: dict[str, str],
) -> dict[str, Any]:
    """Run one op in-process and return the fixture body (without the
    connector/op/params envelope)."""
    fn = getattr(ops, op, None)
    if fn is None:
        return {"kind": "not_registered", "message": f"op {op!r} not in operations"}
    try:
        result = fn(config, dict(params), dict(connector_info))
    except Exception as exc:  # ConnectorError and friends ARE error fixtures
        text = str(exc)
        fixture: dict[str, Any] = {"kind": "connector_error", "message": text}
        parsed = parse_connector_error_message(text)
        if parsed is not None:
            fixture["parsed"] = parsed
        else:
            # e.g. the KeyError degradation "ConnectorError('message')" a flat
            # error body produces -- bank it verbatim
            fixture["parsed"] = None
        return fixture
    response = _jsonable(result)
    if isinstance(response, dict) and response.get("__response_object__"):
        # the 404-returns-a-raw-Response quirk: a fixture, not a failure
        return {"kind": "raw_response", "response": response}
    return {"kind": "ok", "response": response}


def _defender_dt(dt: datetime) -> str:
    """The ONLY datetime form ``convert_date_time`` accepts (with .%f)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_env_file(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _coerce_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _write(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _capture(
    ops: Any,
    op: str,
    label: str,
    params: dict[str, Any],
    config: dict[str, Any],
    connector_info: dict[str, str],
    out_dir: Path,
) -> dict[str, Any]:
    name = f"{op}.json" if label == "default" else f"{op}.{label}.json"
    fixture = {
        "connector": connector_info["connector_name"],
        "connector_version": connector_info["connector_version"],
        "op": op,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "params": params,
        **run_op(ops, op, config, params, connector_info),
    }
    path = _write(out_dir, name, fixture)
    status = fixture["kind"]
    if status == "connector_error" and fixture.get("parsed"):
        status = f"connector_error/{fixture['parsed']['status_code']}"
    print(f"  {name}: {status} -> {path}")
    return fixture


def _auth_error_probe(config: dict[str, Any], out_dir: Path) -> None:
    """Token request with a deliberately-wrong secret -> raw AADSTS body."""
    resp = requests.post(
        f"{AUTH_URL}/{config['tenant_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": config["client_id"],
            "client_secret": "deliberately-wrong-do-not-use",
            "scope": DEFENDER_SCOPE,
        },
        verify=config.get("verify_ssl", True),
        timeout=60,
    )
    try:
        body: Any = resp.json()
    except ValueError:
        body = resp.text
    path = _write(
        out_dir,
        "token.error_auth.json",
        {
            "connector": "microsoft-365-defender",
            "op": "token",
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kind": "token_error",
            "status_code": resp.status_code,
            "response": body,
        },
    )
    print(f"  token.error_auth.json: {resp.status_code} -> {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture live Microsoft 365 Defender fixtures into "
        "scratch/captures/microsoft-365-defender/"
    )
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="optional KEY=VALUE file for the M365_* vars",
    )
    parser.add_argument(
        "--connector-src",
        type=Path,
        default=Path(
            os.environ.get("FSRPB_DEFENDER_CONNECTOR_SRC", DEFAULT_CONNECTOR_SRC)
        ),
    )
    parser.add_argument(
        "--allow-mutating",
        action="store_true",
        help="also run update_incident for real (a comment on "
        "the first listed incident, or the --set target)",
    )
    parser.add_argument(
        "--only", action="append", default=[], help="run only this op (repeatable)"
    )
    parser.add_argument("--skip", action="append", default=[])
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="OP.PARAM=VALUE",
        help="override one param (VALUE is JSON-decoded)",
    )
    parser.add_argument(
        "--auth-error",
        action="store_true",
        help="also capture an AADSTS invalid-client body",
    )
    args = parser.parse_args(argv)

    if args.env_file:
        _load_env_file(args.env_file)
    tenant_id = _env("M365_TENANT_ID", "M365_DEFENDER_TENANT_ID")
    client_id = _env("M365_CLIENT_ID", "M365_DEFENDER_CLIENT_ID")
    client_secret = _env("M365_CLIENT_SECRET", "M365_DEFENDER_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        parser.error(
            "set M365_TENANT_ID / M365_CLIENT_ID / M365_CLIENT_SECRET "
            "(or pass --env-file)"
        )

    overrides: dict[str, dict[str, Any]] = {}
    for raw in args.set:
        op_key, _, value = raw.partition("=")
        op, _, param = op_key.partition(".")
        if not op or not param:
            parser.error(f"--set expects OP.PARAM=VALUE, got {raw!r}")
        overrides.setdefault(op, {})[param] = _coerce_value(value)

    stubbed = stub_fortisoar_connector_sdk()
    src = args.connector_src.expanduser()
    pkg = load_connector_package(src, "fsrpb_capture_m365_defender")
    ops = pkg.operations
    info = json.loads((src / "info.json").read_text())
    connector_info = {
        "connector_name": info["name"],
        "connector_version": info["version"],
    }
    resource = os.environ.get("M365_DEFENDER_RESOURCE") or DEFENDER_RESOURCE
    config = build_config(
        acquire_token(tenant_id, client_id, client_secret),
        tenant_id,
        client_id,
        client_secret,
        resource=resource,
    )
    out_dir = args.outdir / connector_info["connector_name"]
    print(
        f"capturing {connector_info['connector_name']} "
        f"v{connector_info['connector_version']} from {src} "
        f"(SDK stubbed: {stubbed})"
    )
    print("config keys: " + ", ".join(sorted(config.keys())))

    only = set(args.only)
    skip = set(args.skip)

    def wanted(op: str) -> bool:
        return (not only or op in only) and op not in skip

    # -- list_incidents ------------------------------------------------------
    week_ago = _defender_dt(
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    )
    primary: dict[str, Any] | None = None
    if wanted("list_incidents"):
        primary = _capture(
            ops,
            "list_incidents",
            "default",
            {"get_all_records": False, "top": 5},
            config,
            connector_info,
            out_dir,
        )
        _capture(
            ops,
            "list_incidents",
            "status_active",
            {"status": ["Active"], "get_all_records": False, "top": 5},
            config,
            connector_info,
            out_dir,
        )
        _capture(
            ops,
            "list_incidents",
            "incremental_pull",
            {"get_all_records": True, "query": f"lastUpdateTime ge {week_ago}"},
            config,
            connector_info,
            out_dir,
        )
        _capture(
            ops,
            "list_incidents",
            "lastupdatetime_param",
            {"lastUpdateTime": week_ago, "get_all_records": False, "top": 5},
            config,
            connector_info,
            out_dir,
        )

    # -- get_incident (real id from the listing when one came back) ----------
    if wanted("get_incident"):
        first: str | None = None
        if primary and primary.get("kind") == "ok":
            value = (primary.get("response") or {}).get("value") or []
            if value:
                first = str(value[0].get("incidentId"))
        _capture(
            ops,
            "get_incident",
            "not_found",
            {"id": SENTINEL_ID},
            config,
            connector_info,
            out_dir,
        )
        if first:
            _capture(
                ops,
                "get_incident",
                "first_listed",
                {"id": first},
                config,
                connector_info,
                out_dir,
            )
        else:
            print(
                "  get_incident.first_listed: SKIPPED -- listing returned "
                "no incidents (a 403-not-provisioned tenant will not)"
            )

    # -- update_incident (non-mutating by default: the sentinel 404 pins the
    # raw-Response quirk; --allow-mutating adds one real comment update) -----
    if wanted("update_incident"):
        _capture(
            ops,
            "update_incident",
            "not_found",
            {"id": SENTINEL_ID, "comment": _CAPTURE_COMMENT},
            config,
            connector_info,
            out_dir,
        )
        if args.allow_mutating:
            target = str(
                overrides.get("update_incident", {}).get("id")
                or (primary or {})
                .get("response", {})
                .get("value", [{}])[0]
                .get("incidentId", SENTINEL_ID)
            )
            params = {"id": target, "comment": _CAPTURE_COMMENT}
            params.update(
                {
                    k: v
                    for k, v in overrides.get("update_incident", {}).items()
                    if k != "id"
                }
            )
            _capture(
                ops,
                "update_incident",
                "comment_update",
                params,
                config,
                connector_info,
                out_dir,
            )
        else:
            print(
                "  update_incident.comment_update: SKIP (mutating; "
                "--allow-mutating to run)"
            )

    # -- advanced_hunting ----------------------------------------------------
    if wanted("advanced_hunting"):
        _capture(
            ops,
            "advanced_hunting",
            "default",
            {"Query": "DeviceInfo | take 5"},
            config,
            connector_info,
            out_dir,
        )
        _capture(
            ops,
            "advanced_hunting",
            "sample_search",
            {"Query": 'search DeviceName: "abc"'},
            config,
            connector_info,
            out_dir,
        )
        _capture(
            ops,
            "advanced_hunting",
            "bad_kql",
            {"Query": "this is not kql !!!"},
            config,
            connector_info,
            out_dir,
        )

    if args.auth_error:
        _auth_error_probe(config, out_dir)

    print(f"done: fixtures under {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
