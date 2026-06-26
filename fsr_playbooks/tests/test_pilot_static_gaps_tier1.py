"""Tier-1 static-analysis gap checks from the 2026-06-25 archetype pilot.

Each test pins a pilot error (E2/E3/E6/E10) to the check that now catches it,
per docs/plans/PILOT_STATIC_ANALYSIS_GAP_PLAN.md:

- B1 (E2): code_snippet top-level `return` → SyntaxError, caught by compile().
- B2 (E3): sandbox-banned `open` (always) + import gating (config-aware).
- E  (E6): manual/notrigger playbook reading `vars.input.params.*`.
- I  (E10): half-overwritten install (ir.Step missing a compiler-expected field).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from fsr_playbooks.compiler.ir import Collection, Playbook, Step
from fsr_playbooks.compiler.linter import lint
from fsr_playbooks.compiler.snippet_checks import check_snippet


def _sev(findings, sev):
    return [f for f in findings if f.severity == sev]


# --------------------------------------------------------------------------- #
# B1 — syntax (E2)
# --------------------------------------------------------------------------- #

def test_b1_top_level_return_is_error():
    findings = check_snippet("x = 1\nreturn x")
    errs = _sev(findings, "error")
    assert errs and errs[0].name == "SyntaxError"
    assert "return" in errs[0].suggestion.lower()


def test_b1_valid_snippet_is_clean():
    assert check_snippet("x = 1\nprint(x)") == []


def test_b1_empty_snippet_is_clean():
    assert check_snippet("") == []
    assert check_snippet(None) == []
    assert check_snippet("   \n  ") == []


# --------------------------------------------------------------------------- #
# B2 — sandbox bans (E3), config-aware imports
# --------------------------------------------------------------------------- #

def test_b2_open_is_always_error():
    errs = _sev(check_snippet('open("/etc/passwd")'), "error")
    assert any(f.name == "open" for f in errs)


def test_b2_banned_module_import_errors_regardless_of_allow_imports():
    # os is banned even when imports are enabled.
    errs = _sev(check_snippet("import os", allow_imports=True), "error")
    assert any(f.name == "os" for f in errs)


def test_b2_plain_import_unknown_config_is_warning():
    findings = check_snippet("import json")  # allow_imports unknown
    assert _sev(findings, "error") == []
    assert any(f.name == "json" for f in _sev(findings, "warning"))


def test_b2_plain_import_allowed_when_config_enables_it():
    # The whole point: imports ARE legal if the connector config enables them.
    assert check_snippet("import json", allow_imports=True) == []


def test_b2_plain_import_error_when_config_disables_it():
    errs = _sev(check_snippet("import json", allow_imports=False), "error")
    assert any(f.name == "json" for f in errs)


# --------------------------------------------------------------------------- #
# linter integration: snippet source extraction (friendly + canonical)
# --------------------------------------------------------------------------- #

def _lint_one(pb: Playbook):
    return lint("", Collection(name="c", playbooks=[pb]))


def test_linter_flags_canonical_params_python_function():
    pb = Playbook(name="p", steps=[
        Step(id="start", type="start"),
        Step(id="snip", type="code_snippet",
             arguments={"params": {"python_function": 'open("/x")'}}),
    ])
    errs = [e for e in _lint_one(pb) if e.severity == "error"]
    assert any("open" in e.message for e in errs)


def test_linter_respects_inline_allow_imports():
    pb = Playbook(name="p", steps=[
        Step(id="start", type="start"),
        Step(id="snip", type="code_snippet",
             arguments={"code": "import json", "allow_imports": True}),
    ])
    assert all("import" not in e.message for e in _lint_one(pb))


# NOTE: the E (notrigger vars.inputs namespace) check was REMOVED after a live
# run contradicted its premise — see grounded_shapes / the plan doc gap E. Its
# tests were removed with it.


# --------------------------------------------------------------------------- #
# I — packaging self-check (E10)
# --------------------------------------------------------------------------- #

def test_i_self_check_passes_on_healthy_install():
    from fsr_playbooks.compiler import pipeline
    # Reset the cache so the probe actually runs.
    pipeline._self_checked = False
    pipeline._self_check_error = None
    assert pipeline._self_check() is None


def test_i_missing_step_field_is_detected(monkeypatch):
    """Simulate a stale ir.Step missing the compiler-expected `description`."""
    from fsr_playbooks.compiler import pipeline

    @dataclass
    class StaleStep:
        id: str
        type: str
        name: str = ""
        arguments: dict = field(default_factory=dict)
        next: Any = None
        branches: dict = field(default_factory=dict)
        unlabeled_next: list = field(default_factory=list)
        comment: Any = None
        # `description` and `for_each` intentionally dropped (the E10 corruption).

    import fsr_playbooks.compiler.ir as ir_mod
    monkeypatch.setattr(ir_mod, "Step", StaleStep)
    pipeline._self_checked = False
    pipeline._self_check_error = None
    problem = pipeline._self_check()
    assert problem is not None
    assert "description" in problem
    # Reset so other tests see a clean cache.
    pipeline._self_checked = False
    pipeline._self_check_error = None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
