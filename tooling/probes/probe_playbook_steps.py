"""probe_playbook_steps -- index every step from every FSR playbook JSON
export we can find on disk, plus (optionally) the live FSR appliance.

Why: `step_examples` only carries 3 sampled snippets per step type. When
we tighten linting/validation around manual_input, decision, and other
branch-fan-out steps, we need to *mine* real-world argument shapes --
which means querying every step that's ever been exported. That's what
this probe builds.

Sources walked:
  - Miscellaneous/fortisoar/SPs/playbooks/**/*.json   (SP bundles)
  - fsr-playbook-framework/store/incoming/*.json             (manual drops)

Live FSR ingestion is left as a follow-up -- see TODO I12. The schema
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
from .common import REPO_ROOT, probe_session, record_verification

PROBE_NAME = "probe_playbook_steps"

SP_PLAYBOOKS_DIR = (
    Path.home() / "PycharmProjects" / "Miscellaneous"
    / "fortisoar" / "SPs" / "playbooks"
)
INCOMING_DIR = REPO_ROOT / "data" / "incoming"

# Solution packs pulled off an appliance by `tooling/harvest_solution_packs.py`.
# Pack playbooks are the good material: measured across the machine, Use Case
# collections average 10.6 steps and SP collections 6.5, against 2.6 for the
# vendor connector samples this probe filters out.
HARVESTED_PACKS_DIR = REPO_ROOT / "data" / "solution_packs"

# Additional on-disk corpora. These are personal archives that accumulate
# playbook exports; they are opt-in via --wide because walking them is slow
# (OneDrive is network-backed) and they carry a long tail of duplicates.
WIDE_DIRS: list[tuple[str, Path]] = [
    ("downloads", Path.home() / "Downloads"),
    ("onedrive", Path.home() / "Library" / "CloudStorage"
     / "OneDrive-FortinetCorpMain"),
]


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
    # `_catalog.json` is the Content Hub pack metadata written by
    # harvest_solution_packs -- dependencies and connectors, no playbooks.
    skip_names = {"globalVariables.json", "tags.json", "info.json", "data.json",
                  "_catalog.json"}
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


def _iter_playbooks_in_doc(doc: object,
                           collection_name: str | None = None) -> Iterator[tuple[dict, str | None]]:
    """Yield ``(playbook, collection_name)`` for every Workflow dict.

    The collection *name* is threaded down from the enclosing collection when
    the export has one. A playbook's own ``collection`` field is only an IRI
    (``/api/3/workflow_collections/<uuid>``), which is useless for judging
    whether it is a vendor connector sample -- and that judgement is what the
    stub filter below depends on.
    """
    if isinstance(doc, list):
        for item in doc:
            yield from _iter_playbooks_in_doc(item, collection_name)
    elif isinstance(doc, dict):
        # A collection wrapper: remember its name for the playbooks beneath it.
        name = doc.get("name")
        if isinstance(name, str) and (
            doc.get("@type") == "WorkflowCollection"
            or isinstance(doc.get("workflows"), list)
            or isinstance(doc.get("playbooks"), list)
        ):
            collection_name = name
        # Top-level Workflow export: dict with name, uuid, steps[].
        if "steps" in doc and isinstance(doc.get("steps"), list) and (
            doc.get("@type") == "Workflow" or "uuid" in doc
        ):
            yield doc, collection_name
        for v in doc.values():
            if isinstance(v, (list, dict)):
                yield from _iter_playbooks_in_doc(v, collection_name)


# Step types that merely start a playbook. A "sample stub" is a playbook that
# has one of these plus at most one real step.
_TRIGGER_STEP_NAMES = {
    "Trigger", "FASTrigger", "ManualStart", "OnCreate", "OnUpdate",
    "APIEndpoint", "IngestBulkFeed", "Start",
}


def is_sample_stub(pb: dict, collection_name: str | None,
                   step_type_by_uuid: dict[str, str]) -> bool:
    """True for vendor connector-sample playbooks that teach us nothing.

    Connector packs ship a ``Sample - <Connector> - <version>`` collection whose
    playbooks are a start step plus a single bare operation call and nothing
    else. Measured across 49,431 playbooks on disk: 23,472 live in ``Sample - *``
    collections, average 2.6 steps, and **89% have 3 steps or fewer**.

    Ingesting them is actively harmful, not merely wasteful -- they would
    outnumber real playbooks 2:1 and skew every argument-shape and
    connector-frequency rollup built on this table toward
    "one connector call, no context".

    The test is deliberately two-part: the collection name *and* the shape.
    Name alone would drop a genuinely rich playbook someone left in a Sample
    collection; shape alone would drop legitimately short utility playbooks.
    """
    if not collection_name or not collection_name.startswith("Sample - "):
        return False
    steps = [s for s in (pb.get("steps") or [])
             if isinstance(s, dict) and s.get("@type") == "WorkflowStep"]
    if len(steps) > 3:
        return False
    non_trigger = 0
    for s in steps:
        uuid = _extract_uuid_from_iri(s.get("stepType"))
        name = step_type_by_uuid.get(uuid) if uuid else None
        if name not in _TRIGGER_STEP_NAMES:
            non_trigger += 1
    return non_trigger <= 1


def _ingest_file(
    conn: sqlite3.Connection,
    source: str,
    path: Path,
    step_type_by_uuid: dict[str, str],
    now: str,
    include_samples: bool = False,
) -> tuple[int, int]:
    """Returns ``(steps_inserted, sample_stubs_skipped)``."""
    try:
        doc = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return 0, 0
    inserted = 0
    skipped = 0
    # Solution-pack bundles store one Workflow per file with no collection
    # wrapper, so the containing directory is the only carrier of the
    # collection name (`.../playbooks/<Collection Name>/<Playbook>.json`).
    # Without this fall-back every pack playbook lands with an opaque IRI and
    # the sample-stub filter -- which keys off the collection name -- can never
    # fire.
    dir_collection = path.parent.name or None
    if dir_collection in {"playbooks", "incoming", "solution_packs"}:
        dir_collection = None

    seen_pbs = [(pb, coll or dir_collection)
                for pb, coll in _iter_playbooks_in_doc(doc)]
    if not seen_pbs:
        # Some files have steps directly under the root without the Workflow
        # wrapper -- treat the whole doc as one synthetic playbook.
        seen_pbs = [(doc, dir_collection)] if isinstance(doc, dict) and "steps" in doc else []
    for pb, coll_name in seen_pbs:
        if not include_samples and is_sample_stub(pb, coll_name, step_type_by_uuid):
            skipped += 1
            continue
        pb_name = pb.get("name")
        pb_uuid = pb.get("uuid")
        # Prefer the human collection name threaded down from the enclosing
        # collection; a playbook's own `collection` field is usually just an
        # IRI, which nothing downstream can read.
        collection = coll_name
        if not collection:
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
    return inserted, skipped


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


def _ingest_pack_catalog(conn: sqlite3.Connection, now: str) -> dict[str, int]:
    """Load the Content Hub pack record written by ``harvest_solution_packs``.

    Fully owned by this probe, so a straight wipe-and-reload is safe here (the
    scoped wipe below exists for `playbook_steps`, which mixes sources this run
    cannot regenerate; these three tables have exactly one source).

    Silently a no-op when the sidecar is absent -- a corpus built before the
    harvest ran should still ingest playbooks.
    """
    sidecar = HARVESTED_PACKS_DIR / "_catalog.json"
    if not sidecar.exists():
        return {"packs": 0, "connectors": 0, "deps": 0}
    try:
        catalog = json.loads(sidecar.read_text())
    except (json.JSONDecodeError, OSError):
        return {"packs": 0, "connectors": 0, "deps": 0}

    conn.execute("DELETE FROM solution_pack_connectors")
    conn.execute("DELETE FROM solution_pack_deps")
    conn.execute("DELETE FROM solution_packs")
    packs = conns = deps = 0
    for name, rec in catalog.items():
        version = rec.get("version")
        # `category` arrives as a list in the Content Hub record ("Threat
        # Intel", "Compliance", ...). Flattened to a comma-joined string so it
        # stays greppable with LIKE rather than needing a fourth table.
        cat = rec.get("category")
        if isinstance(cat, list):
            cat = ", ".join(str(x) for x in cat) or None
        conn.execute(
            "INSERT INTO solution_packs (name, label, version, category, dir_name,"
            " min_fsr, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, rec.get("label"), version, cat,
             f"{name}-{version}" if version else name,
             rec.get("fsrMinCompatibility"), now),
        )
        packs += 1
        for c in rec.get("connectors") or []:
            api = c.get("apiName")
            if not api:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO solution_pack_connectors (pack_name,"
                " connector, label) VALUES (?, ?, ?)", (name, api, c.get("name")))
            conns += 1
        for d in rec.get("dependencies") or []:
            dep = d.get("name")
            if not dep:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO solution_pack_deps (pack_name, depends_on,"
                " dep_label, dep_version) VALUES (?, ?, ?, ?)",
                (name, dep, d.get("label"), d.get("version")))
            deps += 1
    return {"packs": packs, "connectors": conns, "deps": deps}


def run(*, live: bool = False, wide: bool = False,
        include_samples: bool = False) -> dict:
    """Re-ingest every known playbook export.

    Idempotent: wipes the `playbook_steps` table first, then re-walks the
    on-disk sources. When `live=True` and FSR creds are configured, also
    pages /api/3/workflows and writes rows with source='live_fsr'.

    `wide=True` additionally walks the personal archives in WIDE_DIRS.
    `include_samples=True` disables the connector-sample-stub filter -- off by
    default because those stubs outnumber real playbooks 2:1 and would skew
    every rollup built on this table.
    """
    sources = [
        ("sp_export", SP_PLAYBOOKS_DIR),
        ("sp_harvest", HARVESTED_PACKS_DIR),
        ("incoming", INCOMING_DIR),
    ]
    if wide:
        sources += WIDE_DIRS
    src_paths = [p for _, p in sources if p.exists()]
    with probe_session(PROBE_NAME, src_paths) as conn:
        # Scoped wipe, NOT wipe_probe_tables(). A blanket DELETE destroys rows
        # this run cannot regenerate: `live_fsr` rows only come back with
        # --live, and on-disk sources that have since shrunk take their history
        # with them. (Learned the hard way -- a plain re-ingest once cut this
        # table from 7,442 rows to 685, discarding 7,122 live-sourced rows.)
        # Deleting only the labels being re-ingested keeps the run idempotent
        # for its own sources while leaving every other source intact.
        labels = [label for label, _ in sources]
        if live:
            labels.append("live_fsr")
        conn.executemany(
            "DELETE FROM playbook_steps WHERE source = ?",
            [(lbl,) for lbl in labels],
        )
        st_idx = _load_step_type_index(conn)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pack_catalog = _ingest_pack_catalog(conn, now)
        files = 0
        stubs_skipped = 0
        for label, path in _iter_playbook_files(sources):
            files += 1
            _, skipped = _ingest_file(conn, label, path, st_idx, now,
                                      include_samples=include_samples)
            stubs_skipped += skipped
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
        # Reported, never silent: a filter that quietly drops half the corpus
        # is indistinguishable from a parser that failed to read it.
        "sample_stubs_skipped": stubs_skipped,
        "live_workflows": live_workflows,
        "live_steps": live_steps,
        "pack_catalog": pack_catalog,
        "per_step_type": per_type,
    }


def main() -> int:
    argv = sys.argv[1:]
    live = "--live" in argv or os.environ.get("FSRPB_PROBE_LIVE") == "1"
    result = run(live=live,
                 wide="--wide" in argv,
                 include_samples="--include-samples" in argv)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
