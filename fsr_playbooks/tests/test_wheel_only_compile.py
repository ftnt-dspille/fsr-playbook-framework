"""Wheel-only operation guard (Phase 9 item 4).

The compiler must run from the installed wheel alone — it must never import the
dev-only ``tooling/`` tree (e.g. the old ``connector_configs`` module) at
compile time, and config-UUID resolution must read the warmed
``connector_configs`` catalog table instead.

Two proofs:

1. Compiling a friendly ``code:`` snippet does NOT import ``connector_configs``
   (the dev-only module), and degrades to an unresolved config offline.
2. ``Resolver.resolve_config_id`` reads the warmed ``connector_configs`` table.
"""
from __future__ import annotations

import sqlite3
import sys

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.resolver import Resolver

_SNIPPET_YAML = """
collection: 00-test
playbooks:
  - name: Snippet
    steps:
      - name: Start
        type: start
        next: Run
      - name: Run
        type: code_snippet
        arguments:
          code: |
            print("hi")
          config: prod
"""


def test_code_snippet_compiles_without_importing_tooling(monkeypatch):
    # Ensure the dev-only module isn't already imported, and trap any attempt
    # to import it during compile.
    monkeypatch.delitem(sys.modules, "connector_configs", raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def guard(name, *a, **k):
        if name == "connector_configs" or name.startswith("connector_configs."):
            raise AssertionError(
                "compiler imported dev-only `connector_configs` (not wheel-safe)"
            )
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", guard)
    res = compile_yaml(_SNIPPET_YAML, PACKAGED_SLIM_DB)
    # Compiles offline; config unresolved against the empty slim catalog -> "".
    assert res.ok, [e for e in res.errors if e.severity != "warning"]
    assert "connector_configs" not in sys.modules


def test_resolve_config_id_reads_warmed_table(tmp_path):
    db = tmp_path / "ref.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE connector_configs ("
        " connector TEXT, config_name TEXT, config_id TEXT, is_default INTEGER,"
        " PRIMARY KEY(connector, config_name));"
        "INSERT INTO connector_configs VALUES"
        " ('code-snippet','prod','uuid-prod',0),"
        " ('code-snippet','__default__','uuid-def',1);"
    )
    conn.commit()
    conn.close()

    r = Resolver(db)
    try:
        assert r.resolve_config_id("code-snippet", "prod") == "uuid-prod"
        assert r.resolve_config_id("code-snippet", None) == "uuid-def"
        assert r.resolve_config_id("code-snippet", "missing") is None
        assert r.resolve_config_id("nope", None) is None
    finally:
        r.close()


def test_resolve_config_id_unwarmed_returns_none(tmp_path):
    # A DB without the connector_configs table (old/slim) must not crash.
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE x (a)")
    conn.commit()
    conn.close()
    r = Resolver(db)
    try:
        assert r.resolve_config_id("code-snippet", "prod") is None
    finally:
        r.close()
