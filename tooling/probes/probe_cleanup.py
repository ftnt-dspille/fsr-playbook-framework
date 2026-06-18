"""probe_cleanup — find and delete leftover collections from `fsrpb` test runs.

Targets collections whose names match patterns we control (so we don't risk
deleting real user content):
  - *__fsrpb_probe__*  — left by `probe_playbook_constraints`
  - Compiler Demo*     — left by direct `fsrpb push` smoke tests
  - <custom>           — pass --pattern to add more

Gated on `FSR_ALLOW_E2E=true` so accidental imports don't trigger deletion.

Two-pass cleanup:
  1. Match by name via `GET /api/3/workflow_collections?name=<exact>`. If exact
     filter doesn't pull in wildcards, we list all + filter client-side.
  2. DELETE each match by uuid via `/api/3/workflow_collections/{uuid}`.

Records every delete attempt in `verifications` (kind=`api_endpoint`,
method=`live_api_delete`) so we never re-try a known-failing path blindly.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
import warnings
from pathlib import Path

from . import _env
from .common import probe_session, record_verification

PROBE_NAME = "probe_cleanup"

DEFAULT_PATTERNS = (
    "*__fsrpb_probe__*",
    "Compiler Demo*",
    "Compiler Examples*",
)


def _list_matching(client, patterns: tuple[str, ...]) -> list[dict]:
    """Page through workflow_collections client-side, filter by glob.

    The exact `?name=` filter only matches whole strings, so for wildcard
    patterns (the common case here) we have to list and match locally.
    The collection list is small enough (~120) that one fetch suffices.
    """
    listing = client.get("/api/3/workflow_collections", params={"$limit": 500})
    members = listing.get("hydra:member", []) if isinstance(listing, dict) else []
    return [
        m for m in members
        if any(fnmatch.fnmatch(m.get("name") or "", p) for p in patterns)
    ]


def main() -> int:
    warnings.filterwarnings("ignore")
    if os.environ.get("FSR_ALLOW_E2E", "").lower() not in ("1", "true", "yes"):
        print(f"[{PROBE_NAME}] FSR_ALLOW_E2E not set; skipping (set =true to run)")
        return 0

    cfg = _env.get_config()
    if not cfg.is_live():
        print(f"[{PROBE_NAME}] env not configured; skipping")
        return 0

    extra_patterns = tuple(
        p for p in os.environ.get("FSRPB_CLEANUP_PATTERNS", "").split(",") if p
    )
    patterns = DEFAULT_PATTERNS + extra_patterns

    client = _env.get_client()
    sources = [Path(cfg.base_url + "/api/3/workflow_collections")]
    deleted = 0
    failed = 0

    with probe_session(PROBE_NAME, sources) as conn:
        matches = _list_matching(client, patterns)
        if not matches:
            print(f"[{PROBE_NAME}] no matches for patterns {patterns}")
            return 0

        for m in matches:
            uuid = m.get("uuid")
            name = m.get("name", "?")
            print(f"[{PROBE_NAME}] DELETE {name!r}  ({uuid})", file=sys.stderr)
            try:
                client.delete(f"/api/3/workflow_collections/{uuid}")
                deleted += 1
                record_verification(
                    conn, kind="api_endpoint",
                    key=f"DELETE /api/3/workflow_collections/{uuid}",
                    method="live_api_delete", status="tested_pass",
                    notes=f"cleanup of {name!r}",
                )
            except Exception as e:  # noqa: BLE001
                failed += 1
                resp = getattr(e, "response", None)
                http_status = getattr(resp, "status_code", -1)
                body = (resp.text if resp is not None else str(e))[:300]
                print(f"  failed: HTTP {http_status} {body}", file=sys.stderr)
                record_verification(
                    conn, kind="api_endpoint",
                    key=f"DELETE /api/3/workflow_collections/{uuid}",
                    method="live_api_delete", status="tested_fail",
                    notes=f"http={http_status} body={body[:200]}",
                )

        notes = json.dumps({
            "patterns": list(patterns),
            "matched": len(matches),
            "deleted": deleted,
            "failed": failed,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] deleted={deleted} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
