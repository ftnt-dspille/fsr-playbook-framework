"""probe_modules -- populate modules / module_fields from a live FSR.

Live source:
  GET /api/3/staging_model_metadatas?$limit=...&$orderby=type&$relationships=true
      → every module + its `attributes[]` inline (the `$relationships=true`
        flag is the magic param; without it `attributes` is null).
  GET /api/3/picklist_names?$limit=...&$relationships=true
      → picklists with their items inlined, used to resolve picklist @id refs
        on attribute defaults.

The live read and the writes live in `fsr_playbooks.warmup` (shipped), so
`fsrpb warmup` and this probe share one ingest. This module keeps the
probe-only parts: the opt-in conditional refetch and the local fallback.

Trust ladder:
  module existence:    tested_pass via live_api_get
  field declaration:   seen via live_api_get (declared on the box, not exercised)
  picklist values:     tested_pass via live_api_get (we read them directly)

Local fallback:
  fortisoar/schema.json (snapshot) -- written as `seen` only.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

from fsr_playbooks import warmup

# TAGS_URL and _tag_rows are re-exported: the tooling tests import them from here.
from fsr_playbooks.warmup import (  # noqa: F401
    METADATA_URL,
    PICKLISTS_URL,
    TAGS_URL,
    _tag_rows,
)

from . import _env
from .common import (
    SCHEMA_JSON_PATH,
    conditional_refetch,
    probe_session,
    wipe_probe_tables,
)

PROBE_NAME = "probe_modules"


# ----------------------- live -----------------------

def _live(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, 0, ["env not configured"]

    # Tier-2 conditional refetch (opt-in via FSR_CONDITIONAL_REFETCH), keyed on
    # the picklists collection. A fresh/unchanged picklists response skips the
    # whole re-derive; a refreshed 200 wipes and re-derives everything. The
    # picklists ETag and warm time are recorded by conditional_refetch itself,
    # so warm_modules is handed the body and skips its own picklists GET.
    conditional = _env.is_conditional_enabled()
    picklists_body = None
    if conditional:
        outcome, payload = conditional_refetch(
            client, url=PICKLISTS_URL, conn=conn, collection="picklists",
        )
        if outcome in ("fresh", "unchanged"):
            print(f"[{PROBE_NAME}] conditional_refetch: {outcome} "
                  f"(catalog current; skipped rewrite)")
            return 0, 0, []
        if outcome == "error":
            return 0, 0, [str(payload)]
        wipe_probe_tables(conn, PROBE_NAME)
        picklists_body = payload

    try:
        n_mod, n_fld, errors, etags = warmup.warm_modules(
            conn, client, picklists_body=picklists_body,
        )
    except warmup.WarmupFatal as e:
        return 0, 0, [str(e)]

    cfg = _env.get_config()
    warmup.stamp_provenance(
        conn, client, instance_label=cfg.instance_label, base_url=cfg.base_url,
    )
    warmup.record_warm_markers(conn, etags)
    conn.commit()
    return n_mod, n_fld, errors


# ----------------------- local fallback -----------------------

def _local(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    if not SCHEMA_JSON_PATH.exists():
        return 0, 0, [f"missing {SCHEMA_JSON_PATH}"]
    try:
        d = json.loads(SCHEMA_JSON_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        return 0, 0, [f"{SCHEMA_JSON_PATH}: {e!r}"]
    n_modules, n_fields = warmup.write_modules(
        conn, d.get("hydra:member") or [], {},
        method="schema_json", module_status="seen",
    )
    return n_modules, n_fields, []


# ----------------------- entry -----------------------

def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    sources: list[Path] = []
    if cfg.is_live():
        sources.append(Path(cfg.base_url + METADATA_URL))

    with probe_session(PROBE_NAME, sources) as conn:
        # Idempotent migration for already-built DBs that predate the
        # picklists table / module_fields.picklist_name column.
        warmup.apply_migrations(conn)
        # Default (always-re-pull) path wipes before _live rewrites. When
        # FSR_CONDITIONAL_REFETCH is on, _live owns the wipe (only on a refreshed
        # 200) so a fresh/unchanged outcome leaves existing rows intact.
        if not _env.is_conditional_enabled():
            wipe_probe_tables(conn, PROBE_NAME)

        n_mod = n_fld = 0
        live_errs: list[str] = []
        if cfg.is_live():
            n_mod, n_fld, live_errs = _live(conn)

        local_errs: list[str] = []
        if (not cfg.is_live()) or n_mod == 0:
            n_mod, n_fld, local_errs = _local(conn)
            sources.append(SCHEMA_JSON_PATH)

        notes = json.dumps({
            "modules": n_mod, "fields": n_fld,
            "errors": (live_errs + local_errs)[:30],
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] modules={n_mod}  fields={n_fld}  "
              f"errors={len(live_errs)+len(local_errs)}")
        for e in (live_errs + local_errs)[:10]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
