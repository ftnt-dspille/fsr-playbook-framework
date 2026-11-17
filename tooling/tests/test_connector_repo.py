"""One resolver for the connector checkout (tooling/evals/connector_repo.py)."""
from pathlib import Path

from evals import connector_repo as cr


def test_env_wins_then_legacy_then_monorepo_layout(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.delenv("FSR_CONNECTOR_REPO", raising=False)
    monkeypatch.delenv("FSR_CONNECTOR_DIR", raising=False)
    monkeypatch.setattr(cr, "FRAMEWORK_ROOT", tmp_path / "framework")
    assert cr.connector_repo() is None            # nothing set, no ../connector
    (tmp_path / "connector").mkdir()
    assert cr.connector_repo() == tmp_path / "connector"
    monkeypatch.setenv("FSR_CONNECTOR_DIR", str(b))
    assert cr.connector_repo() == b
    monkeypatch.setenv("FSR_CONNECTOR_REPO", str(a))
    assert cr.connector_repo() == a


def test_unset_env_does_not_auto_find_the_old_sibling_layout(monkeypatch):
    monkeypatch.delenv("FSR_CONNECTOR_REPO", raising=False)
    monkeypatch.delenv("FSR_CONNECTOR_DIR", raising=False)
    assert all("ConnectorsV2" not in str(c) for c in cr.connector_candidates())


def test_consumers_use_the_resolver():
    root = Path(cr.__file__).resolve().parents[1]
    for rel in ("evals/harness.py", "evals/prompt_source.py", "fsr_deploy_mcp.py"):
        assert "evals.connector_repo" in (root / rel).read_text(), rel
