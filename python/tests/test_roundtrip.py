"""Corpus-wide round-trip — the headline regression test.

Iterates every workflow in the bundled FSR export, decompiles to IR,
re-emits, and asserts semantic equivalence. Slow-ish (~10s) but the
single most valuable regression check we have. Marked `slow` so it can
be skipped via `-m 'not slow'` for fast inner-loop runs.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from fsr_playbooks.compiler.roundtrip import roundtrip


@pytest.mark.slow
def test_corpus_roundtrip_clean(corpus_path, db_path):
    src = json.loads(corpus_path.read_text())
    conn = sqlite3.connect(db_path)
    type_by_uuid = {r[0]: r[1] for r in conn.execute("SELECT uuid, name FROM step_types")}
    conn.close()

    failures: list[tuple[str, str, list[str]]] = []
    skipped = 0
    total_ok = 0

    for col in src["data"]:
        for wf in col.get("workflows", []):
            steps = wf.get("steps", [])
            if not steps:
                skipped += 1
                continue
            types = [
                type_by_uuid.get((s.get("stepType") or "").rsplit("/", 1)[-1], "?")
                for s in steps
            ]
            if "?" in types:
                skipped += 1
                continue
            extract = {
                "type": "workflow_collections",
                "macros": [],
                "exported_tags": [],
                "data": [{
                    "@type": "WorkflowCollection",
                    "name": col["name"],
                    "description": col.get("description", ""),
                    "visible": col.get("visible", True),
                    "uuid": col["uuid"],
                    "workflows": [wf],
                }],
            }
            try:
                ok, diffs = roundtrip(extract, db_path)
            except Exception as e:  # noqa: BLE001
                failures.append((col["name"], wf["name"], [f"EXC: {e!r}"]))
                continue
            if ok:
                total_ok += 1
            else:
                failures.append((col["name"], wf["name"], diffs[:5]))

    assert not failures, (
        f"\n{len(failures)} workflow(s) failed round-trip "
        f"(ok={total_ok}, skipped={skipped}):\n"
        + "\n".join(f"  {c} | {w}\n    " + "\n    ".join(d) for c, w, d in failures[:5])
    )
    assert total_ok > 1000, f"corpus shrank? only {total_ok} workflows passed"
