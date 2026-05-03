"""probe_playbook_constraints — discover FSR's workflow_collection import endpoint.

Strategy: compile our `examples/hello_connector.yaml` to a minimal FSR
JSON, then POST it to a series of candidate endpoints until one accepts
it. Whichever returns 2xx is the truth; everything else gets recorded
as `tested_fail` so we never re-try them blindly.

Why this lives as a probe rather than an e2e test: it's a one-shot
discovery, gated on `FSR_ALLOW_E2E=true` so we don't accidentally write
to the appliance during routine `fsrpb refresh`. After it's run once
and the canonical endpoint is recorded, future imports use that path
directly via pyfsr.

Cleanup: any collection successfully created here is DELETEd at the
end. If cleanup fails (network blip, etc.) the collection name is
suffixed with `__fsrpb_probe__` so it's recognizable in the UI.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

from . import _env
from .common import (
    REPO_ROOT,
    probe_session,
    record_verification,
)

PROBE_NAME = "probe_playbook_constraints"

# (path, payload_shape) — "envelope" sends the export-style outer wrapper,
# "entity" sends the unwrapped collection (what API Platform CRUD expects).
CANDIDATE_PATHS: list[tuple[str, str]] = [
    ("/api/3/workflow_collections", "entity"),       # API Platform standard create
    ("/api/3/import_jobs", "envelope"),              # counterpart to /api/3/export_jobs/
    ("/api/3/import_jobs/", "envelope"),             # trailing-slash variant
    ("/api/3/workflow_collections", "envelope"),     # already failed once but kept for record
]


def _compile_test_collection() -> dict:
    sys.path.insert(0, str(REPO_ROOT / "python"))
    from compiler import compile_yaml  # type: ignore

    yaml_text = (REPO_ROOT / "examples" / "hello_connector.yaml").read_text()
    # Suffix the collection name so we can identify and clean it up.
    yaml_text = yaml_text.replace(
        "collection: Compiler Demo",
        "collection: Compiler Demo __fsrpb_probe__",
    )
    result = compile_yaml(yaml_text, REPO_ROOT / "store" / "fsr_reference.db")
    if not result.ok:
        raise RuntimeError(f"compile failed: {[e.to_dict() for e in result.errors]}")
    return result.fsr_json


def _try_post(client, path: str, payload: dict) -> tuple[int, str]:
    """Try one candidate endpoint. Returns (status, body_summary)."""
    try:
        body = client.post(path, payload)
        return (200, json.dumps(body)[:500] if body else "(empty body)")
    except Exception as e:  # noqa: BLE001
        # pyfsr raises on non-2xx; pull the status if attached.
        status = getattr(getattr(e, "response", None), "status_code", 0)
        text = ""
        resp = getattr(e, "response", None)
        if resp is not None:
            text = (resp.text or "")[:500]
        if not status:
            return (-1, f"{type(e).__name__}: {e}"[:500])
        return (status, text)


def _delete_collection(client, uuid: str) -> None:
    try:
        client.delete(f"/api/3/workflow_collections/{uuid}")
    except Exception as e:  # noqa: BLE001
        print(f"[{PROBE_NAME}] cleanup DELETE failed for {uuid}: {e}", file=sys.stderr)


def main() -> int:
    warnings.filterwarnings("ignore")
    if os.environ.get("FSR_ALLOW_E2E", "").lower() not in ("1", "true", "yes"):
        print(f"[{PROBE_NAME}] FSR_ALLOW_E2E not set; skipping (set =true to run)")
        return 0

    cfg = _env.get_config()
    if not cfg.is_live():
        print(f"[{PROBE_NAME}] env not configured; skipping")
        return 0

    envelope_payload = _compile_test_collection()
    coll = envelope_payload["data"][0]
    coll_uuid = coll["uuid"]
    coll_name = coll["name"]

    client = _env.get_client()
    sources = [Path(cfg.base_url + CANDIDATE_PATHS[0][0])]

    winner_path: str | None = None
    winner_shape: str | None = None
    winner_uuid: str | None = None

    with probe_session(PROBE_NAME, sources) as conn:
        for path, shape in CANDIDATE_PATHS:
            payload = envelope_payload if shape == "envelope" else coll
            status, body = _try_post(client, path, payload)
            print(f"[{PROBE_NAME}] POST {path} ({shape}) -> {status}",
                  file=sys.stderr)
            if status and 200 <= status < 300:
                winner_path = path
                winner_shape = shape
                try:
                    parsed = json.loads(body)
                    winner_uuid = parsed.get("uuid") or coll_uuid
                except Exception:
                    winner_uuid = coll_uuid
                record_verification(
                    conn, kind="api_endpoint",
                    key=f"POST {path} ({shape})",
                    method="live_api_post", status="tested_pass",
                    notes=f"workflow_collection import path; sent uuid={coll_uuid}",
                )
                break
            else:
                record_verification(
                    conn, kind="api_endpoint",
                    key=f"POST {path} ({shape})",
                    method="live_api_post", status="tested_fail",
                    notes=f"http={status} body={body[:300]}",
                )

        # Re-import to test UUID-collision behavior (only if we found a path).
        collision_status: int | None = None
        put_status: int | None = None
        if winner_path:
            collision_payload = envelope_payload if winner_shape == "envelope" else coll
            collision_status, _ = _try_post(client, winner_path, collision_payload)
            print(
                f"[{PROBE_NAME}] re-POST same payload -> {collision_status} "
                f"(collision behavior)",
                file=sys.stderr,
            )
            record_verification(
                conn, kind="api_endpoint",
                key=f"POST {winner_path} (collision)",
                method="live_api_post",
                status="tested_pass" if collision_status and 200 <= collision_status < 500 else "tested_fail",
                notes=f"second-import http={collision_status}",
            )

            # Try PUT for upsert/update via API Platform's item endpoint.
            put_path = f"{winner_path}/{coll_uuid}"
            try:
                client.put(put_path, coll)
                put_status = 200
            except Exception as e:  # noqa: BLE001
                resp = getattr(e, "response", None)
                put_status = getattr(resp, "status_code", -1)
                put_body = (resp.text if resp is not None else "")[:300]
            else:
                put_body = "ok"
            print(f"[{PROBE_NAME}] PUT {put_path} -> {put_status}", file=sys.stderr)
            record_verification(
                conn, kind="api_endpoint", key=f"PUT {put_path}",
                method="live_api_put",
                status="tested_pass" if put_status and 200 <= put_status < 300 else "tested_fail",
                notes=f"http={put_status} body={put_body}" if put_status != 200 else "ok",
            )

        # Cleanup
        if winner_uuid and winner_path:
            _delete_collection(client, winner_uuid)

        notes = json.dumps({
            "winner_path": winner_path,
            "collision_status": collision_status,
            "candidates_tried": len(CANDIDATE_PATHS),
            "test_collection_name": coll_name,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        if winner_path:
            print(f"[{PROBE_NAME}] import endpoint: POST {winner_path}")
        else:
            print(f"[{PROBE_NAME}] no candidate path accepted the payload — "
                  f"see verifications for failure details")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
