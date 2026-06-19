"""probe_playbooks — populates step_types, step_examples, playbooks_seen, recipes.

Merged from the planned probe_step_types + probe_playbook_patterns since
they share the workflow_steps fetch.

Live sources:
  GET /api/3/workflow_step_types/?$limit=...        — step type catalog
  GET /api/3/workflow_steps?$relationships=true     — every step instance
                                                       w/ stepType expanded
                                                       (≈7k rows on this box)
  GET /api/3/workflows?$relationships=true&$limit=  — full playbook inventory
                                                       w/ steps[] inline

Trust ladder:
  step_types existence: tested_pass via live_api_get
  step_examples: tested_pass (we read a real instance)
  playbooks_seen: tested_pass (we read the workflow record)
  recipes: tested_pass for the count, seen for the (yet-empty) yaml_template

What we DON'T do here (deferred to v2 / dashboard work):
  - Yaml templates per recipe — needs structural mining of step graphs
  - Per-trigger drill into arguments.resources (`$exists=alerts` style filters)
    to bin recipes by module. Trivial to add via dot-notation filters once we
    decide the recipe taxonomy.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import _env
from .common import (
    probe_session,
    record_verification,
)

PROBE_NAME = "probe_playbooks"

STEP_TYPES_URL = "/api/3/workflow_step_types/"
WORKFLOW_STEPS_URL = "/api/3/workflow_steps"
WORKFLOWS_URL = "/api/3/workflows"

EXAMPLES_PER_TYPE = 3   # cap step_examples per step_type to keep DB lean


def _scalarize(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


# ---------------- step types ----------------

def _load_step_types(conn: sqlite3.Connection, client) -> int:
    r = client.get(STEP_TYPES_URL, params={"$limit": 1000})
    members = r.get("hydra:member", [])
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/workflow_step_types/",
        method="live_api_get", status="tested_pass",
        notes=f"totalItems={r.get('hydra:totalItems')}",
    )
    n = 0
    for st in members:
        if not isinstance(st, dict):
            continue
        name = st.get("name")
        uuid = st.get("uuid") or (st.get("@id") or "").rsplit("/", 1)[-1]
        if not name or not uuid:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO step_types
               (uuid, name, label, category, description, args_schema_json,
                occurrences, common_pitfalls)
               VALUES (?, ?, ?, ?, ?, ?, 0, NULL)""",
            (
                uuid, name,
                _scalarize(st.get("displayName") or name),
                # `parent` is a full nested step-type record when expanded;
                # surface just its name to keep the column scalar.
                _scalarize(
                    (st.get("parent") or {}).get("name") if isinstance(st.get("parent"), dict)
                    else (st.get("parent") or st.get("category"))
                ),
                _scalarize(st.get("description")),
                _scalarize(st.get("arguments")),
            ),
        )
        record_verification(
            conn, kind="step_type", key=name,
            method="live_api_get", status="tested_pass",
            notes=f"deprecated={st.get('deprecated')} visible={st.get('visible')}",
        )
        n += 1
    return n


# ---------------- step examples + occurrences ----------------

def _mine_steps(conn: sqlite3.Connection, client) -> tuple[int, dict[str, int]]:
    """Stream every workflow_step, count by stepType, sample examples."""
    counts: dict[str, int] = defaultdict(int)
    examples: dict[str, int] = defaultdict(int)
    page = 1
    limit = 200
    items = 0
    total = None

    while page <= 200:  # 200 * 200 = 40k step ceiling
        try:
            r = client.get(
                WORKFLOW_STEPS_URL,
                params={"$relationships": "true", "$limit": limit, "$page": page},
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"workflow_steps p{page}: {e!r}") from e
        members = r.get("hydra:member", [])
        if total is None:
            total = r.get("hydra:totalItems")
        if not members:
            break
        for s in members:
            st = s.get("stepType")
            type_name = st.get("name") if isinstance(st, dict) else None
            if not type_name:
                continue
            counts[type_name] += 1
            items += 1
            if examples[type_name] < EXAMPLES_PER_TYPE:
                # store the args; that's the part agents care about
                conn.execute(
                    "INSERT INTO step_examples (step_type_name, from_playbook, snippet_json) "
                    "VALUES (?, ?, ?)",
                    (
                        type_name,
                        # We don't have the workflow id on a step record without
                        # another join; record the step uuid for traceability.
                        f"step:{s.get('uuid')}",
                        json.dumps({"name": s.get("name"), "arguments": s.get("arguments")}),
                    ),
                )
                examples[type_name] += 1
        if total is not None and items >= total:
            break
        if len(members) < limit:
            break
        page += 1

    # Push counts back into step_types.occurrences.
    for name, c in counts.items():
        conn.execute("UPDATE step_types SET occurrences = ? WHERE name = ?", (c, name))

    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/workflow_steps",
        method="live_api_get", status="tested_pass",
        notes=f"items={items} totalItems={total} unique_types={len(counts)}",
    )
    return items, counts


# ---------------- playbooks + recipes ----------------

def _load_playbooks(
    conn: sqlite3.Connection, client, type_counts: dict[str, int],
) -> tuple[int, int]:
    """Inventory all workflows; bin by trigger step type into recipes."""
    page = 1
    limit = 200
    pb_count = 0
    total = None
    trigger_counts: dict[str, int] = defaultdict(int)
    # Map of triggerStep IRI -> stepType.name; built lazily on demand.

    while page <= 50:  # 50*200 = 10k playbook ceiling
        try:
            r = client.get(
                WORKFLOWS_URL,
                params={"$relationships": "true", "$limit": limit, "$page": page},
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"workflows p{page}: {e!r}") from e
        members = r.get("hydra:member", [])
        if total is None:
            total = r.get("hydra:totalItems")
        if not members:
            break

        for wf in members:
            uuid = wf.get("uuid")
            name = wf.get("name") or ""
            steps = wf.get("steps") if isinstance(wf.get("steps"), list) else []
            collection = wf.get("collection") or ""
            if not uuid:
                continue

            # Walk steps to find connectors used (any step where arguments has
            # a 'connector' key). Cheap heuristic; refine later.
            connectors_used: set[str] = set()
            for s in steps:
                if not isinstance(s, dict):
                    continue
                args = s.get("arguments") if isinstance(s.get("arguments"), dict) else {}
                if isinstance(args, dict) and isinstance(args.get("connector"), str):
                    connectors_used.add(args["connector"])

            conn.execute(
                """INSERT OR REPLACE INTO playbooks_seen
                   (collection, workflow, file, step_count, uses_connectors_csv)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    str(collection), name, uuid,
                    len(steps),
                    ",".join(sorted(connectors_used)) if connectors_used else None,
                ),
            )
            record_verification(
                conn, kind="workflow", key=uuid,
                method="live_api_get", status="tested_pass",
            )
            pb_count += 1

            # triggerStep is an IRI string. To get its stepType we'd N+1 by
            # default; instead, count IRIs and resolve once at the end via a
            # single follow-up query per distinct trigger.
            ts = wf.get("triggerStep")
            if isinstance(ts, str) and ts:
                trigger_counts[ts] += 1

        if total is not None and pb_count >= total:
            break
        if len(members) < limit:
            break
        page += 1

    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/workflows",
        method="live_api_get", status="tested_pass",
        notes=f"items={pb_count} totalItems={total}",
    )

    # Resolve each distinct trigger IRI → stepType.name. Some are duplicates
    # across many playbooks, so this is much cheaper than per-playbook.
    distinct_trigger_steps = list(trigger_counts.keys())
    type_per_trigger: dict[str, str] = {}
    for iri in distinct_trigger_steps:
        path = iri if iri.startswith("/") else "/" + iri
        try:
            ts_rec = client.get(path)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(ts_rec, dict):
            st = ts_rec.get("stepType")
            if isinstance(st, str):
                # Need one more hop to get the name.
                try:
                    st_rec = client.get(st if st.startswith("/") else "/" + st)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(st_rec, dict) and st_rec.get("name"):
                    type_per_trigger[iri] = st_rec["name"]
            elif isinstance(st, dict) and st.get("name"):
                type_per_trigger[iri] = st["name"]

    # Aggregate playbook count per trigger type and write a recipe row.
    playbooks_per_type: dict[str, int] = defaultdict(int)
    for iri, n in trigger_counts.items():
        type_name = type_per_trigger.get(iri)
        if type_name:
            playbooks_per_type[type_name] += n

    n_recipes = 0
    for type_name, n in sorted(playbooks_per_type.items(), key=lambda x: -x[1]):
        conn.execute(
            """INSERT OR REPLACE INTO recipes
               (name, kind, when_to_use, yaml_template, source_playbook)
               VALUES (?, ?, ?, ?, ?)""",
            (
                f"trigger:{type_name}",
                "trigger_pattern",
                f"{n} playbook(s) on this instance trigger via stepType={type_name}",
                "",  # yaml_template TBD in v2
                str(n),
            ),
        )
        record_verification(
            conn, kind="recipe", key=f"trigger:{type_name}",
            method="live_api_get", status="tested_pass",
            notes=f"playbook_count={n}",
        )
        n_recipes += 1
    return pb_count, n_recipes


# ---------------- entry ----------------

def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    if not cfg.is_live():
        print(f"[{PROBE_NAME}] env not configured; skipping live probe")
        return 0
    sources = [Path(cfg.base_url + STEP_TYPES_URL)]

    with probe_session(PROBE_NAME, sources) as conn:
        # Wipe owned tables manually since this probe owns 4 of them.
        for t in ("step_types", "step_examples", "playbooks_seen", "recipes"):
            conn.execute(f"DELETE FROM {t}")
        conn.execute(
            "DELETE FROM verifications "
            "WHERE kind IN ('step_type','workflow','recipe') "
            "  AND method = 'live_api_get'"
        )

        client = _env.get_client()
        n_types = _load_step_types(conn, client)
        n_steps, type_counts = _mine_steps(conn, client)
        n_pb, n_recipes = _load_playbooks(conn, client, type_counts)

        notes = json.dumps({
            "step_types": n_types, "steps_mined": n_steps,
            "playbooks": n_pb, "recipes": n_recipes,
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] step_types={n_types}  steps={n_steps}  "
              f"playbooks={n_pb}  recipes={n_recipes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
