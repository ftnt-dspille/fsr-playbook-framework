"""Unified playbook + draft store.

Supersedes the per-mode pickers (examples/ disk reads in Design,
localStorage drafts in CLI). Both Studio modes pull from this single
endpoint set so the same playbook follows the user across the toggle.

Storage layout:
- `examples/*.yaml` on disk → read-only "example" kind.
- SQLite-backed drafts in `store/drafts.db`:
    drafts(name PK, yaml, created_ts, updated_ts)
    draft_revisions(id PK, draft_name FK, yaml, reason, is_auto, created_ts)

Save semantics: every PUT inserts a revision; `is_auto=1` for system-
fired snapshots (mode switch, picker change, deploy), `is_auto=0` for
deliberate user saves. The revision list is the linear history users
browse in the Revisions drawer.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples"
# Separate DB so user-data (drafts) lives apart from the curated
# `fsr_reference.db` reference store. Easier to back up / wipe / sync.
# DRAFTS_DB_PATH override lets the e2e fixture point at a tempdir so
# CI runs don't share state with a developer's live drafts.db.
DRAFTS_DB = Path(os.environ.get("DRAFTS_DB_PATH") or REPO_ROOT / "store" / "drafts.db")

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])


# --------------------------------------------------------------------- DB

def _db() -> sqlite3.Connection:
    DRAFTS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DRAFTS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS drafts (
          name TEXT PRIMARY KEY,
          yaml TEXT NOT NULL,
          created_ts TEXT NOT NULL,
          updated_ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS draft_revisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          draft_name TEXT NOT NULL,
          yaml TEXT NOT NULL,
          reason TEXT,
          is_auto INTEGER NOT NULL DEFAULT 0,
          created_ts TEXT NOT NULL,
          FOREIGN KEY (draft_name) REFERENCES drafts(name) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_revisions_draft
          ON draft_revisions(draft_name, id DESC);
        -- Pruning predicate scans (draft, is_auto, age); this index
        -- keeps the per-save prune cheap as a draft's auto-history grows.
        CREATE INDEX IF NOT EXISTS idx_revisions_prune
          ON draft_revisions(draft_name, is_auto, created_ts);
        """
    )


# Tiered retention for AUTO revisions. Manual saves (is_auto=0) are
# never pruned — those are checkpoints the user explicitly committed
# to. Same shape Google Docs uses ("aggregate older changes").
#
# Each tier covers an age range and keeps the newest auto-revision per
# bucket within that range. Bucket sizes are in seconds.
#
# Tier 5 (older than the last tier's upper bound) drops everything,
# encoded as `bucket_seconds = None`.
_PRUNE_TIERS: tuple[tuple[int, int, int | None], ...] = (
    # (age_low_seconds, age_high_seconds, bucket_seconds)
    (60,           60 * 60,             60),          # 1min–1hr: 1min buckets
    (60 * 60,      24 * 60 * 60,        10 * 60),     # 1hr–1d:  10min buckets
    (24 * 60 * 60, 7 * 24 * 60 * 60,    60 * 60),     # 1d–1w:   1hr buckets
    (7 * 24 * 60 * 60,  30 * 24 * 60 * 60, 24 * 60 * 60),  # 1w–1mo: 1day buckets
    (30 * 24 * 60 * 60, 10 ** 12,       None),        # older: drop
)


def _prune_auto_revisions(conn: sqlite3.Connection, draft_name: str) -> int:
    """Apply tiered retention to this draft's auto-revisions. Called
    inside the same transaction as the INSERT so prune+insert are
    atomic — a crash between them can't leave the table mid-pruned.

    Returns the number of rows deleted (useful for tests + telemetry).

    Uses `strftime('%s', created_ts)` to convert the ISO timestamp into
    Unix-epoch seconds; integer-divide by `bucket_seconds` to get the
    bucket id. Keeping `MAX(id)` per bucket means the most recent edit
    within that minute/hour/day wins.
    """
    deleted = 0
    for age_low, age_high, bucket in _PRUNE_TIERS:
        if bucket is None:
            cur = conn.execute(
                """
                DELETE FROM draft_revisions
                WHERE draft_name = ?
                  AND is_auto = 1
                  AND (strftime('%s','now') - strftime('%s', created_ts)) >= ?
                """,
                (draft_name, age_low),
            )
            deleted += cur.rowcount or 0
            continue
        cur = conn.execute(
            """
            DELETE FROM draft_revisions
            WHERE draft_name = ?
              AND is_auto = 1
              AND (strftime('%s','now') - strftime('%s', created_ts)) >= ?
              AND (strftime('%s','now') - strftime('%s', created_ts)) <  ?
              AND id NOT IN (
                SELECT MAX(id) FROM draft_revisions
                WHERE draft_name = ?
                  AND is_auto = 1
                  AND (strftime('%s','now') - strftime('%s', created_ts)) >= ?
                  AND (strftime('%s','now') - strftime('%s', created_ts)) <  ?
                GROUP BY CAST(strftime('%s', created_ts) AS INTEGER) / ?
              )
            """,
            (draft_name, age_low, age_high,
             draft_name, age_low, age_high, bucket),
        )
        deleted += cur.rowcount or 0
    return deleted


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_name(name: str) -> str:
    """Accept user-supplied draft names but reject anything that could
    travel back as a path segment misinterpretation. Drafts are keyed in
    SQLite, not the filesystem — but the name shows up in URLs so keep
    it ASCII-printable, no slashes, modest length."""
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "draft name required")
    if "/" in name or "\\" in name:
        raise HTTPException(400, "draft name must not contain path separators")
    if len(name) > 200:
        raise HTTPException(400, "draft name too long (max 200 chars)")
    return name


def _safe_example(rel_path: str) -> Path:
    candidate = (EXAMPLES_DIR / rel_path).resolve()
    if not str(candidate).startswith(str(EXAMPLES_DIR.resolve())):
        raise HTTPException(400, "path escapes examples/ root")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(404, f"no such example: {rel_path}")
    return candidate


# --------------------------------------------------------------------- list


@router.get("")
@router.get("/")
def list_playbooks() -> dict[str, Any]:
    """One combined list of examples (read-only) + drafts (editable).

    Each entry: `{kind, name, updated_ts?, size}`. Frontend renders a
    single picker keyed by `f"{kind}:{name}"` so collisions can't happen.
    """
    items: list[dict[str, Any]] = []

    if EXAMPLES_DIR.exists():
        for p in sorted(EXAMPLES_DIR.glob("*.yaml")):
            if p.name.endswith(".test.yaml"):
                continue
            items.append({
                "kind": "example",
                "name": p.name,
                "size": p.stat().st_size,
                "updated_ts": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            })

    with _db() as conn:
        rows = conn.execute(
            "SELECT name, length(yaml) AS size, updated_ts "
            "FROM drafts ORDER BY updated_ts DESC"
        ).fetchall()
        for r in rows:
            items.append({
                "kind": "draft",
                "name": r["name"],
                "size": r["size"],
                "updated_ts": r["updated_ts"],
            })

    return {"count": len(items), "items": items}


# --------------------------------------------------------------------- examples


@router.get("/example/{name:path}")
def get_example(name: str) -> dict[str, Any]:
    p = _safe_example(name)
    return {"kind": "example", "name": name, "yaml": p.read_text()}


# --------------------------------------------------------------------- drafts


class DraftSave(BaseModel):
    yaml: str
    reason: str | None = None
    auto: bool = Field(default=False)


class CloneExample(BaseModel):
    example: str
    draft: str


@router.get("/draft/{name}")
def get_draft(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    with _db() as conn:
        row = conn.execute(
            "SELECT name, yaml, created_ts, updated_ts FROM drafts WHERE name=?",
            (name,),
        ).fetchone()
    if not row:
        raise HTTPException(404, f"no such draft: {name}")
    return {
        "kind": "draft",
        "name": row["name"],
        "yaml": row["yaml"],
        "created_ts": row["created_ts"],
        "updated_ts": row["updated_ts"],
    }


@router.post("/draft/from-example")
def clone_example(payload: CloneExample) -> dict[str, Any]:
    """Promote a curated example into a user-editable draft.

    Examples on disk stay untouched; the new draft starts with the
    example's full YAML and an initial revision noting its provenance.
    Refuses if the target draft name already exists so the user can't
    silently overwrite an in-progress draft.
    """
    src = _safe_example(payload.example)
    name = _validate_name(payload.draft)
    yaml_text = src.read_text()
    now = _now()
    with _db() as conn:
        if conn.execute(
            "SELECT 1 FROM drafts WHERE name=?", (name,)
        ).fetchone():
            raise HTTPException(409, f"draft already exists: {name}")
        conn.execute(
            "INSERT INTO drafts(name, yaml, created_ts, updated_ts) "
            "VALUES (?,?,?,?)",
            (name, yaml_text, now, now),
        )
        cur = conn.execute(
            "INSERT INTO draft_revisions"
            "(draft_name, yaml, reason, is_auto, created_ts) "
            "VALUES (?,?,?,?,?)",
            (name, yaml_text, f"cloned from example: {payload.example}", 0, now),
        )
        rev_id = cur.lastrowid
        conn.commit()
    return {
        "ok": True,
        "kind": "draft",
        "name": name,
        "created_ts": now,
        "updated_ts": now,
        "revision_id": rev_id,
        "from_example": payload.example,
    }


@router.put("/draft/{name}")
def put_draft(name: str, payload: DraftSave) -> dict[str, Any]:
    """Create-or-update the draft head; always inserts a revision row.

    `auto=true` flags the revision as a system snapshot (mode switch,
    picker change, deploy) so the Revisions UI can fade them visually
    or bucket them under "Auto-snapshots" while named saves stay loud.
    """
    name = _validate_name(name)
    now = _now()
    with _db() as conn:
        existing = conn.execute(
            "SELECT created_ts FROM drafts WHERE name=?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE drafts SET yaml=?, updated_ts=? WHERE name=?",
                (payload.yaml, now, name),
            )
            created_ts = existing["created_ts"]
        else:
            conn.execute(
                "INSERT INTO drafts(name, yaml, created_ts, updated_ts) "
                "VALUES (?,?,?,?)",
                (name, payload.yaml, now, now),
            )
            created_ts = now
        cursor = conn.execute(
            "INSERT INTO draft_revisions"
            "(draft_name, yaml, reason, is_auto, created_ts) "
            "VALUES (?,?,?,?,?)",
            (name, payload.yaml, payload.reason, 1 if payload.auto else 0, now),
        )
        rev_id = cursor.lastrowid
        # Prune older auto-revisions in the same txn — keeps the table
        # bounded without a background job, and a crash mid-save can't
        # leave it half-pruned. Manual saves are never touched.
        _prune_auto_revisions(conn, name)
        conn.commit()
    return {
        "ok": True,
        "kind": "draft",
        "name": name,
        "created_ts": created_ts,
        "updated_ts": now,
        "revision_id": rev_id,
    }


@router.delete("/draft/{name}")
def delete_draft(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    with _db() as conn:
        cur = conn.execute("DELETE FROM drafts WHERE name=?", (name,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"no such draft: {name}")
    return {"ok": True, "name": name}


@router.get("/draft/{name}/revisions")
def list_revisions(name: str, limit: int = 200) -> dict[str, Any]:
    """Linear history, newest first. `limit` caps the response so a
    rapid-fire auto-snapshot stream doesn't return megabytes."""
    name = _validate_name(name)
    with _db() as conn:
        if not conn.execute(
            "SELECT 1 FROM drafts WHERE name=?", (name,)
        ).fetchone():
            raise HTTPException(404, f"no such draft: {name}")
        rows = conn.execute(
            "SELECT id, reason, is_auto, created_ts, length(yaml) AS size "
            "FROM draft_revisions WHERE draft_name=? "
            "ORDER BY id DESC LIMIT ?",
            (name, max(1, min(limit, 1000))),
        ).fetchall()
    return {
        "name": name,
        "count": len(rows),
        "revisions": [
            {
                "id": r["id"],
                "reason": r["reason"],
                "is_auto": bool(r["is_auto"]),
                "created_ts": r["created_ts"],
                "size": r["size"],
            }
            for r in rows
        ],
    }


@router.get("/draft/{name}/revisions/{rev_id}")
def get_revision(name: str, rev_id: int) -> dict[str, Any]:
    name = _validate_name(name)
    with _db() as conn:
        row = conn.execute(
            "SELECT id, yaml, reason, is_auto, created_ts "
            "FROM draft_revisions WHERE draft_name=? AND id=?",
            (name, rev_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, f"no such revision: {name}#{rev_id}")
    return {
        "name": name,
        "id": row["id"],
        "yaml": row["yaml"],
        "reason": row["reason"],
        "is_auto": bool(row["is_auto"]),
        "created_ts": row["created_ts"],
    }
