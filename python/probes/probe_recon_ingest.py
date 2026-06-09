"""Ingest a fsr_recon.sh tarball into the reference store.

Usage:
    python -m probes.probe_recon_ingest <path-to-extracted-recon-dir>

Reads:
  A1_routes_full.txt           — Symfony route table
  D1_function_map_live.json    — workflow.eval.FUNCTION_MAP dump
  scripts/internal/workflow_urls.log    — Django workflow service url patterns (if present)

Writes:
  api_endpoints                — one row per route discovered
  step_handlers                — augmented with module/qualname from live FUNCTION_MAP
  verifications                — `recon_route_dump` rows for each new endpoint

Idempotent: re-running on the same tarball updates existing rows in place.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

from probes.common import DB_PATH


SYMFONY_ROUTE_RE = re.compile(
    r'^\s*(?P<name>\S+)\s+(?P<methods>[A-Z|]+)\s+\S+\s+\S+\s+(?P<path>/\S+)\s*$'
)


def parse_symfony_routes(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = SYMFONY_ROUTE_RE.match(line)
        if not m:
            continue
        for method in m.group("methods").split("|"):
            out.append({
                "name": m.group("name"),
                "method": method,
                "path": m.group("path"),
            })
    return out


DJANGO_LOG_RE = re.compile(
    r'^(?P<methods>[A-Z,?]+)\s+(?P<path>\S+)\s+(?P<view>\S+)\s*$'
)


def parse_django_urls(text: str) -> list[dict]:
    out = []
    for raw in text.splitlines():
        m = DJANGO_LOG_RE.match(raw.strip())
        if not m:
            continue
        path = m.group("path")
        # Django logs come in as `wf/api/^foo/$` regex form — keep as-is for traceability
        for method in m.group("methods").split(","):
            if method == "?":
                continue
            out.append({
                "method": method,
                "path": "/" + path.lstrip("/"),
                "view": m.group("view"),
            })
    return out


def upsert_endpoint(conn: sqlite3.Connection, *, path: str, method: str,
                    service: str, summary: str) -> None:
    conn.execute(
        """INSERT INTO api_endpoints(path_pattern, http_method, service, source, summary, response_kind)
           VALUES (?,?,?,?,?, 'json')
           ON CONFLICT(path_pattern, http_method) DO UPDATE SET
               service=excluded.service,
               source=excluded.source,
               summary=COALESCE(api_endpoints.summary, excluded.summary)""",
        (path, method, service, "recon_route_dump", summary),
    )


def upsert_function_map(conn: sqlite3.Connection, fmap: dict[str, str]) -> int:
    n = 0
    for key, qualname in fmap.items():
        if not isinstance(qualname, str):
            continue
        mod, _, qn = qualname.rpartition(".")
        cur = conn.execute(
            """UPDATE step_handlers
               SET module = COALESCE(module, ?), qualname = COALESCE(qualname, ?)
               WHERE function_name = ?""",
            (mod, qn, key),
        )
        if cur.rowcount:
            n += cur.rowcount
    return n


def ingest(recon_dir: Path) -> dict:
    summary = {"symfony_routes": 0, "django_routes": 0, "function_map": 0}
    conn = sqlite3.connect(DB_PATH)
    try:
        a1 = recon_dir / "A1_routes_full.txt"
        if a1.exists():
            for r in parse_symfony_routes(a1.read_text()):
                upsert_endpoint(
                    conn, path=r["path"], method=r["method"],
                    service="api",
                    summary=f"Symfony route {r['name']}",
                )
                summary["symfony_routes"] += 1

        d1 = recon_dir / "D1_function_map_live.json"
        if d1.exists() and d1.stat().st_size > 0:
            try:
                fmap = json.loads(d1.read_text())
                if isinstance(fmap, dict) and "error" not in fmap:
                    summary["function_map"] = upsert_function_map(conn, fmap)
            except json.JSONDecodeError:
                pass

        # Django urls (optional — comes from older scripts/internal/dump_workflow_urls.py output)
        for p in [recon_dir / "G2_workflow_urlconfs.txt",
                  Path("scripts/internal/workflow_urls.log")]:
            if p.exists():
                for r in parse_django_urls(p.read_text()):
                    upsert_endpoint(
                        conn, path=r["path"], method=r["method"],
                        service="wf",
                        summary=f"Django view {r['view']}",
                    )
                    summary["django_routes"] += 1
                break

        conn.commit()
    finally:
        conn.close()
    return summary


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    p = Path(sys.argv[1]).resolve()
    if not p.is_dir():
        print(f"not a directory: {p}", file=sys.stderr)
        return 1
    s = ingest(p)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
