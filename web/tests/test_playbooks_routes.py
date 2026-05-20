"""Coverage for the unified /api/playbooks surface.

Backs Phase A of the Studio playbook unification: a single picker
listing examples + drafts, draft head + revisions endpoints with
auto-snapshot vs named-save distinction.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.routes import playbooks as pb_routes


@pytest.fixture(autouse=True)
def _isolate_drafts_db(tmp_path, monkeypatch):
    """Every test gets a fresh drafts.db so list/save state doesn't
    bleed between cases. The route reads `pb_routes.DRAFTS_DB` lazily
    inside `_db()`, so monkeypatching the module-level constant is
    enough."""
    db = tmp_path / "drafts.db"
    monkeypatch.setattr(pb_routes, "DRAFTS_DB", db)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_list_combines_examples_and_drafts(client):
    # Seed a draft so we have at least one of each kind.
    client.put(
        "/api/playbooks/draft/scratchpad",
        json={"yaml": "playbooks: []\n", "reason": "first save"},
    )
    r = client.get("/api/playbooks")
    assert r.status_code == 200
    body = r.json()
    kinds = {it["kind"] for it in body["items"]}
    assert "draft" in kinds
    # examples/ exists in the repo so the example kind should show too.
    assert "example" in kinds
    # The draft we just saved is in the list.
    drafts = [it for it in body["items"] if it["kind"] == "draft"]
    assert any(d["name"] == "scratchpad" for d in drafts)


def test_put_draft_creates_then_updates_with_revision_history(client):
    # Initial save — manual.
    r1 = client.put(
        "/api/playbooks/draft/incident_v1",
        json={"yaml": "step: 1\n", "reason": "initial draft", "auto": False},
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["ok"] is True
    rev1 = body1["revision_id"]

    # Auto-snapshot — different reason, is_auto flagged.
    r2 = client.put(
        "/api/playbooks/draft/incident_v1",
        json={"yaml": "step: 2\n", "reason": "mode-switch", "auto": True},
    )
    assert r2.status_code == 200
    rev2 = r2.json()["revision_id"]
    assert rev2 != rev1

    # Manual save again.
    r3 = client.put(
        "/api/playbooks/draft/incident_v1",
        json={"yaml": "step: 3\n", "reason": "save"},
    )
    rev3 = r3.json()["revision_id"]

    # Head should be step: 3.
    head = client.get("/api/playbooks/draft/incident_v1").json()
    assert head["yaml"] == "step: 3\n"

    # Revisions list, newest first, with auto flags preserved.
    revs = client.get("/api/playbooks/draft/incident_v1/revisions").json()
    assert revs["count"] == 3
    ids = [r["id"] for r in revs["revisions"]]
    assert ids == [rev3, rev2, rev1]
    auto_flags = {r["id"]: r["is_auto"] for r in revs["revisions"]}
    assert auto_flags[rev2] is True
    assert auto_flags[rev1] is False
    assert auto_flags[rev3] is False

    # Specific revision returns the original yaml.
    body = client.get(f"/api/playbooks/draft/incident_v1/revisions/{rev1}").json()
    assert body["yaml"] == "step: 1\n"
    assert body["reason"] == "initial draft"


def test_get_draft_404_when_missing(client):
    r = client.get("/api/playbooks/draft/never_made")
    assert r.status_code == 404


def test_delete_draft_cascades_revisions(client):
    client.put(
        "/api/playbooks/draft/throwaway",
        json={"yaml": "x: 1\n"},
    )
    client.put(
        "/api/playbooks/draft/throwaway",
        json={"yaml": "x: 2\n"},
    )
    r = client.delete("/api/playbooks/draft/throwaway")
    assert r.status_code == 200

    # Both head + revisions gone.
    assert client.get("/api/playbooks/draft/throwaway").status_code == 404
    assert client.get(
        "/api/playbooks/draft/throwaway/revisions"
    ).status_code == 404


def test_invalid_draft_names_rejected(client):
    # Length limit — names over 200 chars are user error, reject early.
    long_name = "x" * 201
    bad = client.put(
        f"/api/playbooks/draft/{long_name}",
        json={"yaml": "y: 1\n"},
    )
    assert bad.status_code == 400


def test_clone_example_creates_draft_and_preserves_source(client):
    listing = client.get("/api/playbooks").json()
    examples = [it for it in listing["items"] if it["kind"] == "example"]
    if not examples:
        pytest.skip("no example fixtures in this checkout")
    src_name = examples[0]["name"]

    src_yaml = client.get(f"/api/playbooks/example/{src_name}").json()["yaml"]
    r = client.post(
        "/api/playbooks/draft/from-example",
        json={"example": src_name, "draft": "my_clone"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["from_example"] == src_name

    # Draft has the example's YAML as its head revision.
    draft = client.get("/api/playbooks/draft/my_clone").json()
    assert draft["yaml"] == src_yaml

    # Initial revision documents provenance.
    revs = client.get("/api/playbooks/draft/my_clone/revisions").json()
    assert revs["count"] == 1
    assert "cloned from example" in revs["revisions"][0]["reason"]

    # Source example is still intact.
    src_after = client.get(f"/api/playbooks/example/{src_name}").json()
    assert src_after["yaml"] == src_yaml


def test_clone_example_refuses_to_overwrite_existing_draft(client):
    listing = client.get("/api/playbooks").json()
    examples = [it for it in listing["items"] if it["kind"] == "example"]
    if not examples:
        pytest.skip("no example fixtures in this checkout")
    src_name = examples[0]["name"]

    client.put("/api/playbooks/draft/in_progress", json={"yaml": "x: 1\n"})
    r = client.post(
        "/api/playbooks/draft/from-example",
        json={"example": src_name, "draft": "in_progress"},
    )
    assert r.status_code == 409
    # In-progress draft is untouched.
    head = client.get("/api/playbooks/draft/in_progress").json()
    assert head["yaml"] == "x: 1\n"


def _backdate_revision(db_path, rev_id: int, seconds_ago: int) -> None:
    """Rewrite a revision's created_ts to N seconds ago. The prune logic
    keys off `created_ts`, so backdating lets a synchronous test cover
    week/month tiers without sleeping."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE draft_revisions SET created_ts = "
        "datetime('now', ? || ' seconds') WHERE id = ?",
        (f"-{seconds_ago}", rev_id),
    )
    conn.commit()
    conn.close()


def _count_auto_revisions(db_path, draft_name: str) -> int:
    import sqlite3
    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM draft_revisions "
        "WHERE draft_name=? AND is_auto=1",
        (draft_name,),
    ).fetchone()[0]
    conn.close()
    return n


def test_pruning_keeps_manual_saves_forever(client):
    """Manual saves are the user's explicit checkpoints — they survive
    every tier of the auto-pruner even when older than a month."""
    name = "manual_survives"
    # One manual save, then backdate it to 60 days ago.
    r = client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "v: 1\n", "reason": "manual checkpoint", "auto": False},
    )
    rev_id = r.json()["revision_id"]
    _backdate_revision(pb_routes.DRAFTS_DB, rev_id, 60 * 24 * 60 * 60)

    # Trigger a fresh save → invokes the prune in-band.
    client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "v: 2\n", "reason": "later edit", "auto": True},
    )

    # Manual revision is still present despite being 60 days old.
    import sqlite3
    conn = sqlite3.connect(pb_routes.DRAFTS_DB)
    row = conn.execute(
        "SELECT id FROM draft_revisions WHERE id=?", (rev_id,)
    ).fetchone()
    conn.close()
    assert row is not None


def test_pruning_collapses_old_auto_revisions_into_buckets(client):
    """Insert many auto-revisions spread across the day-old tier (10min
    buckets) and assert the pruner collapses them down to one per
    bucket. Per the policy, a 60-minute window of auto-saves should
    survive as ~6 rows."""
    name = "auto_bucketed"
    # Seed one manual save to anchor the draft row.
    client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "anchor\n", "reason": "anchor", "auto": False},
    )

    # Insert 12 auto-revisions spread across a 60-minute window inside
    # the day-tier (so they're old enough to be bucketed at 10min
    # granularity, young enough not to hit the 1-week tier).
    import sqlite3
    base_offset = 6 * 60 * 60  # 6 hours ago — squarely in the day tier
    conn = sqlite3.connect(pb_routes.DRAFTS_DB)
    inserted_ids = []
    for i in range(12):
        cur = conn.execute(
            "INSERT INTO draft_revisions"
            "(draft_name, yaml, reason, is_auto, created_ts) "
            "VALUES (?,?,?,?,datetime('now', ? || ' seconds'))",
            (name, f"step {i}\n", "auto", 1, f"-{base_offset + i * 300}"),
        )
        inserted_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()

    # Trigger the prune.
    client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "trigger\n", "reason": "trigger", "auto": True},
    )

    # 12 revisions spanning 60 minutes, bucketed at 10min → 6 buckets
    # survive (plus the just-inserted "trigger" revision which is in
    # the youngest tier still <1min old, so it's exempt). The total
    # count of backdated auto-revisions still present should be <= 6.
    import sqlite3
    conn = sqlite3.connect(pb_routes.DRAFTS_DB)
    surviving = conn.execute(
        "SELECT COUNT(*) FROM draft_revisions WHERE id IN ("
        + ",".join("?" for _ in inserted_ids)
        + ")",
        inserted_ids,
    ).fetchone()[0]
    conn.close()
    assert surviving <= 6, f"expected <=6 buckets in the day tier, got {surviving}"
    # And we must have kept at least one (the whole window shouldn't vanish).
    assert surviving >= 1


def test_pruning_drops_auto_revisions_older_than_one_month(client):
    """Auto-revisions past the longest tier (>30 days) are dropped
    entirely. Without this, an active draft would accumulate forever."""
    name = "old_auto"
    client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "anchor\n", "reason": "anchor", "auto": False},
    )

    import sqlite3
    conn = sqlite3.connect(pb_routes.DRAFTS_DB)
    cur = conn.execute(
        "INSERT INTO draft_revisions"
        "(draft_name, yaml, reason, is_auto, created_ts) "
        "VALUES (?,?,?,?,datetime('now','-45 days'))",
        (name, "ancient\n", "auto", 1),
    )
    ancient_id = cur.lastrowid
    conn.commit()
    conn.close()

    client.put(
        f"/api/playbooks/draft/{name}",
        json={"yaml": "trigger\n", "reason": "trigger", "auto": True},
    )

    conn = sqlite3.connect(pb_routes.DRAFTS_DB)
    row = conn.execute(
        "SELECT id FROM draft_revisions WHERE id=?", (ancient_id,)
    ).fetchone()
    conn.close()
    assert row is None, "auto-revision older than 30d should have been pruned"


def test_get_example_serves_disk_yaml(client):
    listing = client.get("/api/playbooks").json()
    examples = [it for it in listing["items"] if it["kind"] == "example"]
    if not examples:
        pytest.skip("no example fixtures in this checkout")
    name = examples[0]["name"]
    r = client.get(f"/api/playbooks/example/{name}")
    assert r.status_code == 200
    assert r.json()["yaml"]
