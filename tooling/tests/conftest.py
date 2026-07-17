"""Shared pytest fixtures.

The gate resolves connectors against a small, committed fixture DB
(`fixtures/tooling_reference.db`, ~3 MB) that holds exactly the connectors
these tests reference, at full param fidelity, plus the infra tables the
compiler needs. It is built by `fixtures/build_tooling_fixture.py` from the
committed slim catalog + the public Fortinet RPM repo, so the gate is
reproducible from git and immune to a clobbered dev cache.

This deliberately replaces the old "read the live `data/fsr_reference.db`"
contract: that DB is gitignored and gets clobbered whenever a local
connector-op probe fires warmup (it re-syncs the box catalog over the dev
corpus), which reds the gate for a reason unrelated to the change under test.
Set `FSRPB_DB` to point the whole suite at a different DB (e.g. the full dev
cache) when you deliberately want broader coverage.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PYTHON = REPO / "tooling"
FIXTURE_DB = Path(__file__).resolve().parent / "fixtures" / "tooling_reference.db"


def _resolve_db() -> Path:
    """An explicit FSRPB_DB override wins; otherwise use the committed fixture.

    The committed fixture is copied to a temp file the suite actually opens:
    compile paths connect read-write, so opening the committed file directly
    would touch it (WAL/header) and make pre-commit's "files modified by hook"
    check fail. The copy keeps the tracked bytes pristine.
    """
    if os.environ.get("FSRPB_DB"):
        return Path(os.environ["FSRPB_DB"])
    if not FIXTURE_DB.exists():
        return FIXTURE_DB  # db_path fixture will skip with a clear message
    tmp = Path(tempfile.gettempdir()) / "fsrpb_tooling_fixture.db"
    shutil.copyfile(FIXTURE_DB, tmp)
    return tmp


# Export FSRPB_DB so subprocess-based tests (cli.py) and any in-process
# `default_db_path()` call resolve the SAME DB the `db_path` fixture returns.
DB = _resolve_db()
os.environ.setdefault("FSRPB_DB", str(DB))
CORPUS = REPO.parent / "FSRPlaybookConversion" / "pb_examples" / "all_fsr_evoke_playbooks.json"

# Repo root must be on path for `fsr_playbooks.*`; python/ for `probes.*`,
# `store.*`, `cli`, `agent.*`, `evals.*`, `recipes.*`, `chat_review`.
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PYTHON))


@pytest.fixture(scope="session")
def db_path() -> Path:
    if not DB.exists():
        pytest.skip(f"reference DB missing: {DB}")
    return DB


@pytest.fixture(scope="session")
def corpus_path() -> Path:
    if not CORPUS.exists():
        pytest.skip(f"corpus missing: {CORPUS}")
    return CORPUS


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO
