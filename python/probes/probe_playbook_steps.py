"""probe_playbook_steps — index every step from every FSR playbook JSON
export we can find on disk, plus (optionally) the live FSR appliance.

Why: `step_examples` only carries 3 sampled snippets per step type. When
we tighten linting/validation around manual_input, decision, and other
branch-fan-out steps, we need to *mine* real-world argument shapes —
which means querying every step that's ever been exported. That's what
this probe builds.

Sources walked:
  - Miscellaneous/fortisoar/SPs/playbooks/**/*.json   (SP bundles)
  - FSRPlaybookYaml/store/incoming/*.json             (manual drops)

Live FSR ingestion is left as a follow-up — see TODO I12. The schema
already accommodates it via `source='live_fsr'`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import _env
from .common import REPO_ROOT, probe_session, record_verification, wipe_probe_tables

PROBE_NAME = "probe_playbook_steps"

SP_PLAYBOOKS_DIR = (
    Path.home() / "PycharmProjects" / "Miscellaneous"
    / "fortisoar" / "SPs" / "playbooks"
)
INCOMING_DIR = REPO_ROOT / "store" / "incoming"


def _load_step_type_index(conn: sqlite3.Connection) -> dict[str, str]:
    """Map step_types.uuid → step_types.name. Built once per run."""
    cur = conn.execute("SELECT uuid, name FROM step_types WHERE uuid IS NOT NULL")
    return {row["uuid"]: row["name"] for row in cur.fetchall()}


def _extract_uuid_from_iri(iri: object) -> str | None:
    """Resolve a stepType reference to its UUID.

    SP exports give us `stepType: "/api/3/workflow_step_types/<uuid>"`.
    Live FSR with `$relationships=true` expands it into a full dict
    `{"@id": "/api/3/workflow_step_types/<uuid>", "uuid": "<uuid>", ...}`.
    Handle both.
    """
    if isinstance(iri, dict):
        u = iri.get("uuid")
        if isinstance(u, str) and len(u) == 36:
            return u
        iri = iri.get("@id")
    if not isinstance(iri, str) or not iri:
        return None
    tail = iri.rstrip("/").rsplit("/", 1)[-1]
    return tail if len(tail) == 36 and tail.count("-") == 4 else None


def _iter_playbook_files(sources: list[tuple[str, Path]]) -> Iterator[tuple[str, Path]]:
    """Yield (source_label, path) for every plausible playbook JSON file."""
    skip_names = {"globalVariables.json", "tags.json", "info.json", "data.json"}
    for label, root in sources:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".json":
            if root.name not in skip_names:
                yield label, root
            continue
        for p in root.rglob("*.json"):
            if p.name in skip_names:
                continue
            yield label, p


def _iter_steps_in_doc(doc: object) -> Iterator[dict]:
    """Walk arbitrary FSR JSON exports and yield every WorkflowStep dict."""
    if isinstance(doc, list):
        for item in doc:
            yield from _iter_steps_in_doc(item)
    elif isinstance(doc, dict):
        if doc.get("@type") == "WorkflowStep":
            yield doc
        for v in doc.values():
            if isinstance(v, (list, dict)):
                yield from _iter_steps_in_doc(v)


def _iter_playbooks_in_doc(doc: object) -> Iterator[dict]:
    """Yield every playbook (Workflow) dict — needed to attach
    playbook_name/uuid/collection to each step rather than just the file."""
    if isinstance(doc, list):
        for item in doc:
            yield from _iter_playbooks_in_doc(item)
    elif isinstance(doc, dict):
        # Top-level Workflow export: dict with name, uuid, steps[].
        if "steps" in doc and isinstance(doc.get("steps"), list) and (
            doc.get("@type") == "Workflow" or "uuid" in doc
        ):
            yield doc
        for v in doc.values():
            if isinstance(v, (list, dict)):
                yield from _iter_playbooks_in_doc(v)


def _ingest_file(
    conn: sqlite3.Connection,
    source: str,
    path: Path,
    step_type_by_uuid: dict[str, str],
    now: str,
) -> int:
    try:
        doc = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return 0
    inserted = 0
    seen_pbs = list(_iter_playbooks_in_doc(doc))
    if not seen_pbs:
        # Some files have steps directly under the root without the Workflow
        # wrapper — treat the whole doc as one synthetic playbook.
        seen_pbs = [doc] if isinstance(doc, dict) and "steps" in doc else []
    for pb in seen_pbs:
        pb_name = pb.get("name")
        pb_uuid = pb.get("uuid")
        collection = None
        coll = pb.get("collection")
        if isinstance(coll, dict):
            collection = coll.get("name")
        elif isinstance(coll, str):
            collection = coll
        for step in pb.get("steps", []) or []:
            if not isinstance(step, dict) or step.get("@type") != "WorkflowStep":
                continue
            step_type_uuid = _extract_uuid_from_iri(step.get("stepType"))
            step_type_name = step_type_by_uuid.get(step_type_uuid) if step_type_uuid else None
            args = step.get("arguments")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO playbook_steps "
                    "(source, source_path, collection, playbook_name, playbook_uuid, "
                    " step_uuid, step_name, step_type_uuid, step_type_name, "
                    " arguments_json, ingested_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        source,
                        str(path),
                        collection,
                        pb_name,
                        pb_uuid,
                        step.get("uuid"),
                        step.get("name"),
                        step_type_uuid,
                        step_type_name,
                        json.dumps(args, sort_keys=True) if args is not None else "{}",
                        now,
                    ),
                )
                inserted += conn.total_changes and 1 or 0
            except sqlite3.IntegrityError:
                pass
    return inserted


def _ingest_live(conn: sqlite3.Connection,
                 step_type_by_uuid: dict[str, str],
                 now: str) -> tuple[int, int]:
    """Page /api/3/workflows?$relationships=true and write every step.

    Returns (workflows, steps_inserted). Records a verification row on the
    `GET /api/3/workflows` endpoint when at least one page comes back.
    """
    client = _env.get_client()
    if client is None:
        return 0, 0
    base_url = _env.get_config().base_url
    page = 1
    limit = 200
    workflows = steps = 0
    total = None
    while page <= 50:  # 10k workflow ceiling, matches probe_playbooks
        try:
            r = client.get(
                "/api/3/workflows",
                params={"$relationships": "true",
                        "$limit": limit, "$page": page},
            )
        except Exception as e:  # noqa: BLE001
            print(f"[probe_playbook_steps] live page {page} failed: {e!r}",
                  file=sys.stderr)
            break
        members = r.get("hydra:member") if isinstance(r, dict) else []
        if total is None and isinstance(r, dict):
            total = r.get("hydra:totalItems")
        if not members:
            break
        for wf in members:
            if not isinstance(wf, dict):
                continue
            workflows += 1
            wf_steps = wf.get("steps") if isinstance(wf.get("steps"), list) else []
            coll = wf.get("collection")
            collection = coll if isinstance(coll, str) else (
                coll.get("name") if isinstance(coll, dict) else None
            )
            for step in wf_steps:
                if not isinstance(step, dict):
                    continue
                step_type_uuid = _extract_uuid_from_iri(step.get("stepType"))
                step_type_name = step_type_by_uuid.get(step_type_uuid) if step_type_uuid else None
                args = step.get("arguments")
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO playbook_steps "
                        "(source, source_path, collection, playbook_name, "
                        " playbook_uuid, step_uuid, step_name, step_type_uuid, "
                        " step_type_name, arguments_json, ingested_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            "live_fsr", base_url, collection,
                            wf.get("name"), wf.get("uuid"),
                            step.get("uuid"), step.get("name"),
                            step_type_uuid, step_type_name,
                            json.dumps(args, sort_keys=True) if args is not None else "{}",
                            now,
                        ),
                    )
                    steps += 1
                except sqlite3.IntegrityError:
                    pass
        if total is not None and workflows >= total:
            break
        if len(members) < limit:
            break
        page += 1
    if workflows:
        record_verification(
            conn, kind="api_endpoint",
            key="GET /api/3/workflows (step_detail)",
            method="live_api_get", status="tested_pass",
            notes=f"workflows={workflows} steps={steps}",
        )
    return workflows, steps


def run(*, live: bool = False) -> dict:
    """Re-ingest every known playbook export.

    Idempotent: wipes the `playbook_steps` table first, then re-walks the
    on-disk sources. When `live=True` and FSR creds are configured, also
    pages /api/3/workflows and writes rows with source='live_fsr'.
    """
    sources = [("sp_export", SP_PLAYBOOKS_DIR), ("incoming", INCOMING_DIR)]
    src_paths = [p for _, p in sources if p.exists()]
    with probe_session(PROBE_NAME, src_paths) as conn:
        wipe_probe_tables(conn, PROBE_NAME)
        st_idx = _load_step_type_index(conn)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        files = 0
        for label, path in _iter_playbook_files(sources):
            files += 1
            _ingest_file(conn, label, path, st_idx, now)
        live_workflows = live_steps = 0
        if live:
            live_workflows, live_steps = _ingest_live(conn, st_idx, now)
        cur = conn.execute("SELECT COUNT(*) AS n FROM playbook_steps")
        total = cur.fetchone()["n"]
        cur = conn.execute(
            "SELECT step_type_name, COUNT(*) AS n FROM playbook_steps "
            "GROUP BY step_type_name ORDER BY n DESC"
        )
        per_type = {row["step_type_name"]: row["n"] for row in cur.fetchall()}
    return {
        "files": files,
        "rows": total,
        "live_workflows": live_workflows,
        "live_steps": live_steps,
        "per_step_type": per_type,
    }


def main() -> int:
    live = "--live" in sys.argv[1:] or os.environ.get("FSRPB_PROBE_LIVE") == "1"
    result = run(live=live)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
