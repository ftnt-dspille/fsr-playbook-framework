"""Shared pytest fixtures.

Tests run against the live `store/fsr_reference.db` produced by the
probes. We don't ship a synthetic DB — the probes are part of the
contract and the real data is what the compiler is built against.
If the DB is missing, tests are skipped with a clear message.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PYTHON = REPO / "tooling"
DB = REPO / "store" / "fsr_reference.db"
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
