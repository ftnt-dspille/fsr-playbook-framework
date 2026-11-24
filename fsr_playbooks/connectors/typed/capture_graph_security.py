"""proto-msftcap: capture live Microsoft Graph security connector fixtures.

Loads the two soarshelf connector packages BY PATH (stubbing the FortiSOAR
connector SDK they import), acquires a client-credentials token against the
trial tenant, runs each op with a representative param set, and writes one
JSON fixture per op under ``scratch/captures/<connector>/<op>.json``
(``scratch/`` is gitignored -- raw captures are local-only; promote
SANITIZED shapes into ``typed/mocks/`` by hand afterwards, never commit a
raw capture).

Fixtures are the m365-trial plan §8.1 capture discipline: an op that 403s
or 404s still produces a fixture (the error body IS a valid fixture), so a
permission-limited tenant still banks shapes.

Usage (from the repo root, after exporting the M365 env vars)::

    export M365_TENANT_ID=... M365_CLIENT_ID=... M365_CLIENT_SECRET=...
    uv run python -m fsr_playbooks.connectors.typed.capture_graph_security

Mutating ops (PATCH/POST/DELETE/create) are SKIPPED unless
``--allow-mutating``; their default params use all-zero sentinel ids so a
gated run captures 404 error shapes without touching tenant state, and
``--set op.param=value`` overrides any single param (e.g. a real alert id
from a prior read capture). ``revoke_user_sessions`` additionally requires
an explicit ``--set revoke_user_sessions.user=<user-id>``: it is the one
op that can lock a real administrator out.

Env: ``M365_TENANT_ID``, ``M365_CLIENT_ID``, ``M365_CLIENT_SECRET`` (all
required), ``M365_TEST_USER_UPN`` (optional; default mailbox for
``search_message``), ``SOARSHELF_HOME`` (optional; defaults to
``~/PycharmProjects/soarshelf``).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from fsr_playbooks.connectors.typed.graph_common import (
    extract_error_body,
    parse_graph_connector_error,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTDIR = REPO_ROOT / "scratch" / "captures"
DEFAULT_SOARSHELF = Path.home() / "PycharmProjects" / "soarshelf"

GRAPH_RESOURCE = "https://graph.microsoft.com"
AUTH_URL = "https://login.microsoftonline.com"

MUTATING_VERBS = {"update_security_alert", "add_comment_on_security_alert",
                  "del_message", "del_message_bulk", "revoke_user_sessions",
                  "create_ip_range_location", "block_new_ips", "unblock_new_ips",
                  "update_security_incident"}

#: All-zero sentinel id: no real directory object carries it, so a
#: mutating op aimed at one 404s instead of changing tenant state.
SENTINEL_ID = "00000000-0000-0000-0000-000000000000"


@dataclass
class ConnectorSource:
    """Where a connector package lives inside the soarshelf checkout, and
    how its ops are called."""
    subdir: str
    python_pkg: str
    #: "config_params" (microsoft-graph_dev) or "config_params_info"
    #: (microsoft-graph-api-security takes connector_info as a 3rd arg).
    call_shape: str


CONNECTOR_SOURCES: dict[str, ConnectorSource] = {
    "microsoft-graph_dev": ConnectorSource(
        subdir="content/connectors/get-microsoft-graph-security-incidents-with-reworked-auth/package/microsoft-graph_dev",
        python_pkg="msgraph_dev_capture",
        call_shape="config_params",
    ),
    "microsoft-graph-api-security": ConnectorSource(
        subdir="content/connectors/manage-graph-security-incidents-and-alerts/package/microsoft-graph-api-security",
        python_pkg="msgraph_api_sec_capture",
        call_shape="config_params_info",
    ),
}


@dataclass
class ParamSet:
    label: str
    params: dict[str, Any]
    mutating: bool = False
    #: op params that MUST be overridden via --set before the op may run
    requires_set: tuple[str, ...] = ()

    def filename(self, op: str) -> str:
        if self.label == "default":
            return f"{op}.json"
        return f"{op}__{self.label}.json"


#: Representative param sets per connector+op, derived from each op's
#: info.json parameters and operations.py param reads. Provenance:
#: source-derived (info.json parameters v3.1.0 / v1.0.0), live-capture pending.
PARAM_SETS: dict[str, dict[str, list[ParamSet]]] = {
    "microsoft-graph_dev": {
        "get_risky_users_list": [ParamSet("default", {})],
        "get_risky_user_details": [ParamSet("default", {"risk_id": SENTINEL_ID})],
        "get_all_security_alerts": [
            ParamSet("default", {"api_version": "V2", "top": 5}),
            ParamSet("v1", {"api_version": "V1", "top": 5}),
        ],
        "get_security_alert": [
            ParamSet("default", {"alert_id": SENTINEL_ID, "api_version": "V2"}),
            ParamSet("v1", {"alert_id": SENTINEL_ID, "api_version": "V1"}),
        ],
        "update_security_alert": [
            ParamSet("default", {"alert_id": SENTINEL_ID, "api_version": "V2",
                                 "status": "Resolved", "classification": "True Positive"},
                     mutating=True),
        ],
        "add_comment_on_security_alert": [
            ParamSet("default", {"alert_id": SENTINEL_ID, "comment": "fsoar capture probe"},
                     mutating=True),
        ],
        "get_groups": [ParamSet("default", {})],
        "get_group_users": [ParamSet("default", {"group_id": SENTINEL_ID})],
        "search_message": [ParamSet("default", {
            "subject": "Quarterly compliance training reminder",
            "user_list": [os.environ.get("M365_TEST_USER_UPN", "alice@contoso.example")],
            "size": 5,
        })],
        "del_message": [
            ParamSet("default", {"user_id": SENTINEL_ID, "message_id": SENTINEL_ID},
                     mutating=True),
        ],
        "del_message_bulk": [
            ParamSet("default", {"user_list": [{"user_id": SENTINEL_ID,
                                                "message_id": SENTINEL_ID}]},
                     mutating=True),
        ],
        "revoke_user_sessions": [
            ParamSet("default", {"user": SENTINEL_ID}, mutating=True,
                     requires_set=("user",)),
        ],
        "get_all_named_locations": [ParamSet("default", {"size": 10})],
        "block_new_ips": [
            ParamSet("default", {"namedLocationUuid": SENTINEL_ID,
                                 "ipv4_ips": "203.0.113.0/24"},
                     mutating=True),
        ],
        "unblock_new_ips": [
            ParamSet("default", {"namedLocationUuid": SENTINEL_ID,
                                 "ipv4_ips": "203.0.113.0/24"},
                     mutating=True),
        ],
        "create_ip_range_location": [
            ParamSet("default", {"name": "fsoar-capture-throwaway",
                                 "is_trusted": False,
                                 "ipv4_ips": "203.0.113.0/24"},
                     mutating=True),
        ],
        "get_security_incidents": [ParamSet("default", {"top": 5, "fetchAlerts": True})],
    },
    "microsoft-graph-api-security": {
        "get_security_incidents": [ParamSet("default", {"top": 5})],
        "get_security_alerts": [ParamSet("default", {"top": 5})],
        "get_security_alert": [ParamSet("default", {"alertID": SENTINEL_ID})],
        "update_security_incident": [
            ParamSet("default", {"incidentID": SENTINEL_ID, "status": "Resolved"},
                     mutating=True),
        ],
        "run_advanced_hunting": [ParamSet("default", {
            "query": "DeviceInfo | take 5",
            "timespan": "Last 30 Days",
        })],
    },
}


# ---------------------------------------------------------------------------
# Connector-SDK stubs: the packages import the FortiSOAR connector runtime
# (connectors.core..., integrations.crudhub, msal) which only exists on a
# SOAR box. Stub them minimally so the ops run in-process off-box.
# ---------------------------------------------------------------------------


def _install_sdk_stubs() -> None:
    import logging

    def _get_logger(name: str) -> logging.Logger:
        return logging.getLogger(f"fsoar-capture.{name}")

    class _ConnectorError(Exception):
        pass

    def _make_request_unavailable(*a: Any, **k: Any) -> None:
        raise NotImplementedError("crudhub.make_request is unavailable off-box")

    class _MsalStub:
        def __init__(self, *a: Any, **k: Any) -> None:
            raise NotImplementedError("certificate auth is stubbed in capture mode")

    connectors = types.ModuleType("connectors")
    core = types.ModuleType("connectors.core")
    core_connector = types.ModuleType("connectors.core.connector")
    core_utils = types.ModuleType("connectors.core.utils")
    crudhub = types.ModuleType("integrations.crudhub")
    integrations = types.ModuleType("integrations")
    msal = types.ModuleType("msal")

    setattr(core_connector, "get_logger", _get_logger)
    setattr(core_connector, "ConnectorError", _ConnectorError)
    setattr(core_utils, "update_connnector_config", lambda *a, **k: None)
    setattr(core, "connector", core_connector)
    setattr(core, "utils", core_utils)
    setattr(crudhub, "make_request", _make_request_unavailable)
    setattr(integrations, "crudhub", crudhub)
    setattr(msal, "ConfidentialClientApplication", _MsalStub)
    for name, mod in [("connectors", connectors), ("connectors.core", core),
                      ("connectors.core.connector", core_connector),
                      ("connectors.core.utils", core_utils),
                      ("integrations", integrations),
                      ("integrations.crudhub", crudhub),
                      ("msal", msal)]:
        sys.modules.setdefault(name, mod)


def load_connector_package(source: ConnectorSource, soarshelf_home: Path):
    """Import a connector package (no __init__.py in the shipped dir) with
    relative imports intact."""
    pkg_dir = soarshelf_home / source.subdir
    if not (pkg_dir / "operations.py").exists():
        raise FileNotFoundError(f"connector package not found: {pkg_dir}")
    pkg = types.ModuleType(source.python_pkg)
    pkg.__path__ = [str(pkg_dir)]
    sys.modules[source.python_pkg] = pkg
    for mod_name in ("constants", "constant", "microsoft_api_auth", "utils",
                     "operations"):
        mod_file = pkg_dir / f"{mod_name}.py"
        if not mod_file.exists():
            continue
        spec = importlib.util.spec_from_file_location(
            f"{source.python_pkg}.{mod_name}", mod_file)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        setattr(pkg, mod_name, module)
    info = json.loads((pkg_dir / "info.json").read_text())
    return pkg, info


# ---------------------------------------------------------------------------
# Token + config
# ---------------------------------------------------------------------------


def acquire_token(tenant_id: str, client_id: str, client_secret: str,
                  verify_ssl: bool = True) -> str:
    """Client-credentials token -- the same request
    ``acquire_token_with_client_credentials`` makes, done here so the ops
    can run from a pre-seeded config without the msal/refresh path.

    Returns the RAW access token (no ``Bearer `` prefix): it is stored in the
    config as ``accessToken`` and the connector's ``validate_token`` adds the
    prefix itself -- a prefixed value here produces a live-proven
    ``Bearer Bearer …`` header (Graph: InvalidAuthenticationToken, "The token
    could not be read").
    """
    resp = requests.post(
        f"{AUTH_URL}/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": f"{GRAPH_RESOURCE}/.default",
        },
        verify=verify_ssl,
        timeout=60,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"token request failed: HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["access_token"]


def build_config(connector: str, token: str, tenant_id: str, client_id: str,
                 client_secret: str, info: dict) -> dict[str, Any]:
    config: dict[str, Any] = {
        "auth_type": "Without a User - Application Permission",
        "resource": GRAPH_RESOURCE,
        "client_id": client_id,
        "client_secret": client_secret,
        "verify_ssl": True,
        "accessToken": token,
        # epoch float -- matches what the connector itself persists
        # (resp['expiresOn'] = ts_now + resp['expires_in']); convert_ts_epoch
        # calls ctime(ts) on it, so it MUST be a number, and its string
        # fallback branch wants '%Y-%m-%d %H:%M:%S.%f', not a ctime string.
        "expiresOn": time.time() + 3300,
        "config_id": "capture",
        "connector_info": {
            "connector_name": info.get("name", connector),
            "connector_version": info.get("version", "0"),
        },
    }
    if connector == "microsoft-graph_dev":
        config["tenant"] = tenant_id
        config["api_version"] = "v1.0"
    else:
        config["tenant_id"] = tenant_id
    return config


def _coerce_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# Capture core
# ---------------------------------------------------------------------------


def run_op(connector: str, source: ConnectorSource, pkg, info: dict,
           config: dict, op: str, params: dict) -> dict:
    """Run one op in-process and return the fixture body (without the
    connector/op/params envelope)."""
    fn = getattr(pkg.operations, "operations", {}).get(op)
    if fn is None:
        return {"kind": "not_registered", "message": f"op {op!r} not in operations dict"}
    try:
        if source.call_shape == "config_params":
            result = fn(config, params)
        else:
            result = fn(config, params, config["connector_info"])
        return {"kind": "ok", "response": _jsonable(result)}
    except Exception as exc:  # ConnectorError and anything else
        text = str(exc)
        fixture: dict[str, Any] = {"kind": "connector_error", "message": text}
        parsed = parse_graph_connector_error(text)
        if parsed is not None:
            fixture["parsed"] = {
                "status": parsed.status,
                "code": parsed.code,
                "message": parsed.message,
            }
            body = extract_error_body(parsed.message)
        else:
            body = extract_error_body(text)
        if body is not None:
            fixture["extracted_body"] = body
        return fixture


def _jsonable(result: Any) -> Any:
    """The ops return parsed JSON, True, or (on the api-security 404 path)
    a raw requests.Response -- make all three fixture-shaped."""
    if isinstance(result, (bool, int, float, str)) or result is None:
        return result
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return result
    status = getattr(result, "status_code", None)
    if status is not None:
        # the documented 404 quirk: api_request returns the Response itself
        try:
            body = result.json()
        except ValueError:
            body = None
        return {"__response_object__": True, "status_code": status,
                "body": body, "text": getattr(result, "text", "")[:2000]}
    return repr(result)


def capture_connector(connector: str, source: ConnectorSource, soarshelf_home: Path,
                      outdir: Path, token: str, tenant_id: str, client_id: str,
                      client_secret: str, allow_mutating: bool, overrides: dict,
                      only: set[str], skip: set[str]) -> list[Path]:
    pkg, info = load_connector_package(source, soarshelf_home)
    config = build_config(connector, token, tenant_id, client_id, client_secret, info)
    out_dir = outdir / connector
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for op, sets in PARAM_SETS[connector].items():
        if only and op not in only:
            continue
        if op in skip:
            continue
        for ps in sets:
            if ps.mutating and not allow_mutating:
                print(f"  SKIP {op}[{ps.label}] (mutating; --allow-mutating to run)")
                continue
            params = dict(ps.params)
            for key, val in overrides.get(op, {}).items():
                params[key] = val
            missing = [p for p in ps.requires_set if p not in overrides.get(op, {})]
            if missing:
                print(f"  SKIP {op}[{ps.label}] (requires --set {op}."
                      f"{missing[0]}=<real value>)")
                continue
            fixture = {
                "connector": connector,
                "connector_version": info.get("version"),
                "op": op,
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "params": params,
                **run_op(connector, source, pkg, info, config, op, params),
            }
            path = out_dir / ps.filename(op)
            path.write_text(json.dumps(fixture, indent=2) + "\n")
            written.append(path)
            print(f"  wrote {path.relative_to(outdir)} "
                  f"[{fixture['kind']}{'/' + str(fixture.get('parsed', {}).get('status', '')) if fixture.get('parsed') else ''}]")
    return written


def _load_env_file(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture live Graph security fixtures into scratch/captures/")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--env-file", type=Path, default=None,
                        help="optional KEY=VALUE file for the M365_* vars")
    parser.add_argument("--soarshelf-home", type=Path,
                        default=Path(os.environ.get("SOARSHELF_HOME", DEFAULT_SOARSHELF)))
    parser.add_argument("--allow-mutating", action="store_true",
                        help="also run PATCH/POST/DELETE ops (defaults use "
                             "all-zero sentinel ids; override with --set)")
    parser.add_argument("--only", action="append", default=[],
                        help="run only this op (repeatable)")
    parser.add_argument("--skip", action="append", default=[])
    parser.add_argument("--set", action="append", default=[],
                        metavar="OP.PARAM=VALUE",
                        help="override one param (VALUE is JSON-decoded)")
    args = parser.parse_args(argv)

    if args.env_file:
        _load_env_file(args.env_file)
    tenant_id = os.environ.get("M365_TENANT_ID", "")
    client_id = os.environ.get("M365_CLIENT_ID", "")
    client_secret = os.environ.get("M365_CLIENT_SECRET", "")
    if not (tenant_id and client_id and client_secret):
        parser.error("set M365_TENANT_ID / M365_CLIENT_ID / M365_CLIENT_SECRET "
                     "(or pass --env-file)")

    overrides: dict[str, dict[str, Any]] = {}
    for raw in args.set:
        op_key, _, value = raw.partition("=")
        op, _, param = op_key.partition(".")
        if not op or not param:
            parser.error(f"--set expects OP.PARAM=VALUE, got {raw!r}")
        overrides.setdefault(op, {})[param] = _coerce_value(value)

    _install_sdk_stubs()
    token = acquire_token(tenant_id, client_id, client_secret)
    print(f"token acquired for tenant {tenant_id[:8]}...")

    all_written: list[Path] = []
    for connector, source in CONNECTOR_SOURCES.items():
        print(f"== {connector}")
        all_written += capture_connector(
            connector, source, args.soarshelf_home, args.outdir,
            token, tenant_id, client_id, client_secret,
            allow_mutating=args.allow_mutating, overrides=overrides,
            only=set(args.only), skip=set(args.skip))
    print(f"done: {len(all_written)} fixtures under {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
