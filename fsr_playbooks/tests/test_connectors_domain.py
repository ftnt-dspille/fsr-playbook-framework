"""fsr_playbooks.connectors: the connector static-validation core folded in from
the standalone connector toolkit. Pins that the move kept the behaviour: a clean
connector validates, a planted defect is caught, and the hardened dispatch
resolver handles incremental registration (no false 'op not dispatched')."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from fsr_playbooks.connectors import (
    Severity,
    resolve_dispatch,
    scan,
    validate_connector,
)
from fsr_playbooks.connectors.lint.runner import load_connector

GOLDEN = Path(__file__).resolve().parents[2] / "tooling/evals/connector_build/golden/cg1_ipinfo"


def _errors(root: Path) -> set[str]:
    return {i.code for i in validate_connector(root) if i.severity == Severity.ERROR}


def test_golden_connector_validates_clean():
    assert _errors(GOLDEN) == set()
    assert scan(GOLDEN) == []


def test_missing_required_info_field_is_flagged(tmp_path):
    for f in ("operations.py", "connector.py"):
        (tmp_path / f).write_text((GOLDEN / f).read_text())
    info = json.loads((GOLDEN / "info.json").read_text())
    info.pop("publisher")
    (tmp_path / "info.json").write_text(json.dumps(info))
    assert "INFO001" in _errors(tmp_path)


def test_incremental_dispatch_resolves(tmp_path):
    (tmp_path / "info.json").write_text(json.dumps({
        "name": "t", "label": "T", "version": "1.0.0", "publisher": "P",
        "operations": [{"operation": o, "title": o, "parameters": []} for o in ("a", "b")]}))
    (tmp_path / "operations.py").write_text(textwrap.dedent("""
        def a(config, params): pass
        def b(config, params): pass
        operations = {}
        operations['a'] = a
        operations['b'] = b
    """))
    (tmp_path / "connector.py").write_text(textwrap.dedent("""
        from connectors.core.connector import Connector
        class C(Connector):
            def execute(self, config, operation, params, **kwargs): pass
            def check_health(self, config): return True
    """))
    disp = resolve_dispatch(load_connector(tmp_path)[0])
    assert set(disp.mapping) == {"a", "b"}
    assert "OP002" not in _errors(tmp_path)
