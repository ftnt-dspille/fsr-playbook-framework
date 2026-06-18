"""probe_api_endpoints — populate api_endpoints / api_endpoint_params.

Live source (preferred):
    GET /api/3/  — Hydra root. API Platform returns a hydra:Collection whose
    members enumerate every exposed `/api/3/{plural}` collection (and member
    URI templates for the per-record routes). Every entry becomes a row with
    method=live_api_get, status=tested_pass.

Local seed (always run for non-Hydra routes):
    Parse the "Endpoint inventory" table in
    soar-reporting-dashboard-cl/docs/FORTISOAR_API.md for `/api/gateway/*`,
    `/api/integration/*`, `/api/wf/*`, etc. Stamps method=fortisoar_api_md,
    status=seen.

Both runs share `_upsert_endpoint`, so re-runs are idempotent. Param
verifications land per row in `verifications(kind='api_endpoint_param')`.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import _env
from .common import (
    probe_session,
    record_verification,
    wipe_probe_tables,
)

PROBE_NAME = "probe_api_endpoints"

FORTISOAR_API_MD = (
    Path.home()
    / "PycharmProjects"
    / "soar-reporting-dashboard-cl"
    / "docs"
    / "FORTISOAR_API.md"
)

# Methods we'll seed for any Hydra-discovered collection. API Platform
# generally exposes these unless an entity overrides; we mark them all `seen`
# from the Hydra discovery, but only the GET we actually performed becomes
# tested_pass via record_verification.
HYDRA_METHODS_COLLECTION = ("GET", "POST")
HYDRA_METHODS_MEMBER = ("GET", "PUT", "PATCH", "DELETE")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _upsert_endpoint(
    conn: sqlite3.Connection,
    *,
    path_pattern: str,
    http_method: str,
    service: str,
    source: str,
    summary: str | None = None,
    controller: str | None = None,
    response_kind: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO api_endpoints
            (path_pattern, http_method, service, controller, summary,
             response_kind, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path_pattern, http_method) DO UPDATE SET
            service       = COALESCE(excluded.service, service),
            controller    = COALESCE(excluded.controller, controller),
            summary       = COALESCE(excluded.summary, summary),
            response_kind = COALESCE(excluded.response_kind, response_kind),
            source        = excluded.source
        RETURNING id
        """,
        (path_pattern, http_method, service, controller, summary, response_kind, source),
    )
    return cur.fetchone()[0]


def _verif_key(method: str, path_pattern: str) -> str:
    return f"{method} {path_pattern}"


# ---------------- Live: Hydra root ----------------

def _live_hydra(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Hit /api/3/ Hydra root, populate endpoints. Returns (count, errors)."""
    client = _env.get_client()
    if client is None:
        return 0, ["env not configured for live access"]
    errors: list[str] = []
    count = 0
    try:
        # pyfsr's client.get() prepends base_url.
        root = client.get("/api/3/")
    except Exception as e:  # noqa: BLE001 — capture for the audit row
        return 0, [f"GET /api/3/ failed: {e!r}"]

    # API Platform Hydra root is a hydra:Documentation-ish object; the simplest
    # signal of "this collection exists" is that the root response itself maps
    # collection slugs to URIs. Different FSR versions return slightly
    # different shapes — handle the two we've seen, fall back to scanning for
    # "@id" strings starting with "/api/3/".
    seen_collections: set[str] = set()
    if isinstance(root, dict):
        for key, val in root.items():
            if isinstance(val, str) and val.startswith("/api/3/") and "{" not in val:
                seen_collections.add(val.rstrip("/"))
        # Some shapes nest under 'hydra:supportedClass' / 'collections'.
        for nested_key in ("hydra:supportedClass", "collections", "hydra:member"):
            nested = root.get(nested_key)
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        uri = item.get("@id") or item.get("hydra:title")
                        if isinstance(uri, str) and uri.startswith("/api/3/"):
                            seen_collections.add(uri.rstrip("/"))

    for coll_path in sorted(seen_collections):
        for m in HYDRA_METHODS_COLLECTION:
            _upsert_endpoint(
                conn,
                path_pattern=coll_path,
                http_method=m,
                service="php",
                source="hydra_root",
                response_kind="hydra_collection" if m == "GET" else None,
            )
            count += 1
            # Hydra discovery proves the endpoint EXISTS, not that it responds
            # for our creds/RBAC. Everything stays `seen` until a real probe
            # exercises it. Only the root `/api/3/` (handled below) is
            # tested_pass because we actually hit it.
            record_verification(
                conn,
                kind="api_endpoint",
                key=_verif_key(m, coll_path),
                method="hydra_root",
                status="seen",
            )
        # Member route (single record by uuid)
        member_path = f"{coll_path}/{{uuid}}"
        for m in HYDRA_METHODS_MEMBER:
            _upsert_endpoint(
                conn,
                path_pattern=member_path,
                http_method=m,
                service="php",
                source="hydra_root",
                response_kind="hydra_member" if m == "GET" else None,
            )
            count += 1
            record_verification(
                conn,
                kind="api_endpoint",
                key=_verif_key(m, member_path),
                method="hydra_root",
                status="seen",
            )

    # Stash the raw root payload as a request example on '/api/3/' itself for
    # debugging / future re-parsers.
    root_id = _upsert_endpoint(
        conn,
        path_pattern="/api/3/",
        http_method="GET",
        service="php",
        source="hydra_root",
        summary="Hydra root — enumerates exposed /api/3/{plural} collections.",
        response_kind="hydra_collection",
    )
    conn.execute(
        "INSERT INTO api_endpoint_examples (endpoint_id, direction, status_code, payload, notes) "
        "VALUES (?, 'response', 200, ?, ?)",
        (root_id, json.dumps(root)[:50_000], "captured by probe_api_endpoints"),
    )
    record_verification(
        conn,
        kind="api_endpoint",
        key="GET /api/3/",
        method="live_api_get",
        status="tested_pass",
    )
    return count, errors


# ---------------- Local: parse FORTISOAR_API.md ----------------

# Match table rows like:  | `/api/3/connectors` | GET, POST | description |
_TABLE_ROW = re.compile(
    r"^\|\s*`(?P<path>/api/[^`]+)`\s*\|\s*(?P<methods>[A-Z, ]+)\s*\|(?P<rest>[^|]*)\|"
)
# Match prose mentions like "POST /api/gateway/audit/activities"
_PROSE_LINE = re.compile(
    r"\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<path>/api/[^\s`,]+)"
)


def _service_for(path: str) -> str:
    if path.startswith("/api/gateway/"):
        return "java_gateway"
    if path.startswith("/api/integration/"):
        return "integration"
    if path.startswith("/api/wf/"):
        return "wf"
    if path.startswith("/api/rule/"):
        return "rule"
    if path.startswith("/api/auth/"):
        return "auth"
    if path.startswith("/api/saml/"):
        return "saml"
    if path.startswith("/api/postman/"):
        return "postman"
    return "php"  # /api/3/*, /api/query/*, /api/triggers/*, etc.


def _seed_from_md(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    if not FORTISOAR_API_MD.exists():
        return 0, [f"missing {FORTISOAR_API_MD}"]
    text = FORTISOAR_API_MD.read_text()
    count = 0
    seen_pairs: set[tuple[str, str]] = set()

    for line in text.splitlines():
        m = _TABLE_ROW.match(line)
        if m:
            path = m["path"].strip().rstrip("/")
            methods = [x.strip() for x in m["methods"].split(",") if x.strip()]
            summary = m["rest"].strip().strip("|").strip() or None
            for method in methods:
                if (method, path) in seen_pairs:
                    continue
                seen_pairs.add((method, path))
                _upsert_endpoint(
                    conn,
                    path_pattern=path,
                    http_method=method,
                    service=_service_for(path),
                    source="fortisoar_api_md",
                    summary=summary,
                )
                record_verification(
                    conn,
                    kind="api_endpoint",
                    key=_verif_key(method, path),
                    method="fortisoar_api_md",
                    status="seen",
                )
                count += 1
            continue
        for pm in _PROSE_LINE.finditer(line):
            method, path = pm["method"], pm["path"].rstrip(".,)/")
            if (method, path) in seen_pairs:
                continue
            seen_pairs.add((method, path))
            _upsert_endpoint(
                conn,
                path_pattern=path,
                http_method=method,
                service=_service_for(path),
                source="fortisoar_api_md",
                summary=None,
            )
            record_verification(
                conn,
                kind="api_endpoint",
                key=_verif_key(method, path),
                method="fortisoar_api_md",
                status="seen",
            )
            count += 1
    return count, []


# ---------------- Entry point ----------------

def main() -> int:
    sources = [FORTISOAR_API_MD]
    cfg = _env.get_config()
    if cfg.is_live():
        sources.append(Path(cfg.base_url + "/api/3/"))

    with probe_session(PROBE_NAME, sources) as conn:
        wipe_probe_tables(conn, PROBE_NAME)
        # Also wipe our verification rows for these kinds — re-derive from scratch.
        conn.execute(
            "DELETE FROM verifications WHERE kind IN ('api_endpoint', 'api_endpoint_param')"
        )
        live_count, live_errs = _live_hydra(conn)
        md_count, md_errs = _seed_from_md(conn)

        notes = json.dumps({
            "live_count": live_count,
            "md_count": md_count,
            "errors": live_errs + md_errs,
            "instance_label": cfg.instance_label,
        })
        # _probe_runs row is written by probe_session; we tack notes on after.
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] live={live_count}  md={md_count}  errors={len(live_errs)+len(md_errs)}")
        for e in live_errs + md_errs:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
