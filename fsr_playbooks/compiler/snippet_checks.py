"""Static checks for ``code_snippet`` step bodies (pilot gaps B1 + B2).

FortiSOAR's code-snippet connector runs the authored Python inside a
restricted sandbox (the ``python_inline_code_editor`` operation). Two whole
classes of failure are deterministic and catchable *before* a live run — they
bit the 2026-06-25 archetype pilot as errors E2 and E3:

- **B1 — syntax (E2).** A top-level ``return`` (or any other ``SyntaxError``)
  fails the snippet the instant the sandbox compiles it. ``compile(src,
  "<snippet>", "exec")`` reproduces the exact error in microseconds with zero
  dependencies, so we never need a heavyweight Pyodide/sandbox exec to find it.

- **B2 — sandbox bans (E3).** The sandbox bans a *specific* set of names and
  modules (``open``, ``os``, ``sys``, ``subprocess``, ``importlib``, ``imp``)
  and — unless the connector config enables it — bans ``import`` outright. A
  snippet that ``open()``\\s a file or imports ``os`` passes a vanilla Python
  ``compile()`` (and even Pyodide, which *has* ``open``) yet fails FortiSOAR at
  runtime with ``Uses of ['open'] is restricted``. We model the ban with a
  small **per-version manifest** (``SANDBOX_CONSTRAINTS``) — the natural sibling
  of ``STEP_WIRE_SHAPES.json``'s per-step shapes — and an ``ast.walk``.

The import ban is **config-aware**: the sandbox's *default* config disallows
imports, but a config with ``allow_imports`` enabled relaxes it. The always-banned
names (``open`` and friends) are restricted regardless of ``allow_imports``.
Callers resolve the connector config and pass ``allow_imports=`` so the import
check reflects the config that will actually run the snippet.

This module is pure (stdlib only, no DB, no live FSR). It returns plain tuples;
the linter maps them onto ``CompileError`` so the existing CLI / MCP / Monaco
surfaces light up with no wiring change.
"""
from __future__ import annotations

import ast
from typing import NamedTuple, Optional


class SnippetFinding(NamedTuple):
    """One static finding about a snippet body.

    ``severity`` is ``"error"`` (will fail the sandbox at runtime) or
    ``"warning"`` (likely to fail, but depends on a config we can't fully
    resolve offline). ``name`` is the offending symbol, used for dedupe and
    messaging.
    """
    severity: str
    name: str
    message: str
    suggestion: str
    lineno: int


# Per-connector-version sandbox constraints. Keyed by the code-snippet
# connector version (``arguments.version``, default "2.1.4"). The default
# entry covers every version we haven't pinned explicitly.
#
# - ``banned_names``: identifiers/modules the sandbox restricts *regardless* of
#   ``allow_imports`` — used both as bare names (``open(...)``) and as import
#   targets (``import os``). FortiSOAR raises ``Uses of [...] is restricted``.
# - ``imports_allowed_by_default``: whether ``import`` works without a config
#   that enables it. The sandbox default is False — imports are off unless the
#   connector config turns them on.
#
# This mirrors the FortiSOAR code-snippet sandbox (v2.1.4) observed in the pilot.
# Graduate to a JSON manifest (sibling of STEP_WIRE_SHAPES.json) if it grows.
_DEFAULT_CONSTRAINTS = {
    "banned_names": frozenset({
        "open", "os", "sys", "subprocess", "importlib", "imp",
        "eval", "exec", "compile", "__import__",
    }),
    "imports_allowed_by_default": False,
}

SANDBOX_CONSTRAINTS: dict[str, dict] = {
    "2.1.4": _DEFAULT_CONSTRAINTS,
}


def _constraints_for(version: Optional[str]) -> dict:
    return SANDBOX_CONSTRAINTS.get(version or "", _DEFAULT_CONSTRAINTS)


def check_snippet(
    code: Optional[str],
    *,
    version: Optional[str] = None,
    allow_imports: Optional[bool] = None,
) -> list[SnippetFinding]:
    """Statically vet a code-snippet body.

    ``code``: the snippet source (``arguments.code`` / ``arguments.python`` /
        ``arguments.params.python_function``). Empty/None → no findings.
    ``version``: the code-snippet connector version, to pick the constraint set.
    ``allow_imports``: the resolved connector config's import setting. ``None``
        means "unknown" → fall back to the manifest's default; in that case an
        ``import`` is a *warning* (it may be allowed by a config we can't see).
        ``False`` makes it an error; ``True`` suppresses the import check.

    Returns findings in source order. B1 (syntax) short-circuits: a snippet that
    doesn't parse can't be AST-walked, so we return the single syntax finding.
    """
    if not code or not isinstance(code, str) or not code.strip():
        return []

    # --- B1: syntax. ---
    # `compile(..., "exec")` runs the symbol-table pass too, so it catches
    # `'return' outside function` (E2) — `ast.parse` alone does not, since that
    # error is raised during compilation, not parsing. We compile() to vet, then
    # ast.parse() the same source for the B2 walk.
    try:
        compile(code, "<snippet>", "exec")
        tree = ast.parse(code, "<snippet>", "exec")
    except SyntaxError as e:
        return [SnippetFinding(
            severity="error",
            name="SyntaxError",
            message=(f"code-snippet body is not valid Python: {e.msg} "
                     f"(line {e.lineno})"),
            suggestion=(
                "fix the syntax; a top-level `return` is the usual culprit — "
                "the sandbox runs the body at module scope, so use a bare "
                "expression/assignment or wrap it in a function you then call"
                if e.msg and "return" in e.msg.lower()
                else "fix the syntax error before pushing"),
            lineno=e.lineno or 1,
        )]

    # --- B2: sandbox bans. ---
    cons = _constraints_for(version)
    banned: frozenset = cons["banned_names"]
    imports_default = cons["imports_allowed_by_default"]
    imports_ok = imports_default if allow_imports is None else allow_imports

    findings: list[SnippetFinding] = []
    seen: set[tuple[str, int]] = set()

    def _add(f: SnippetFinding) -> None:
        key = (f.name, f.lineno)
        if key not in seen:
            seen.add(key)
            findings.append(f)

    for node in ast.walk(tree):
        # Bare/attribute name use of a banned symbol: open(...), os.system(...)
        if isinstance(node, ast.Name) and node.id in banned:
            _add(SnippetFinding(
                severity="error",
                name=node.id,
                message=(f"code-snippet uses {node.id!r}, which the FortiSOAR "
                         f"sandbox restricts — runtime fails with "
                         f"\"Uses of ['{node.id}'] is restricted\""),
                suggestion=(f"remove the use of {node.id!r}; the sandbox has no "
                            "filesystem/process access"),
                lineno=getattr(node, "lineno", 1),
            ))
        # import os / import subprocess as sp / from os import path
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            else:
                mods = [(node.module or "").split(".")[0]]
            ln = getattr(node, "lineno", 1)
            for mod in mods:
                if mod in banned:
                    _add(SnippetFinding(
                        severity="error",
                        name=mod,
                        message=(f"code-snippet imports {mod!r}, which the "
                                 "FortiSOAR sandbox restricts regardless of "
                                 "the import setting"),
                        suggestion=(f"don't import {mod!r}; use "
                                    "fsr_playbooks.helpers or a connector op "
                                    "instead"),
                        lineno=ln,
                    ))
                elif not imports_ok:
                    sev = "error" if allow_imports is False else "warning"
                    qual = ("the connector config disables imports"
                            if allow_imports is False
                            else "the sandbox disables imports unless the "
                                 "connector config enables them")
                    _add(SnippetFinding(
                        severity=sev,
                        name=mod or "import",
                        message=(f"code-snippet imports {mod!r}, but {qual}"),
                        suggestion=("enable allow_imports on the code-snippet "
                                    "connector config, or drop the import"),
                        lineno=ln,
                    ))

    findings.sort(key=lambda f: (f.lineno, f.name))
    return findings
