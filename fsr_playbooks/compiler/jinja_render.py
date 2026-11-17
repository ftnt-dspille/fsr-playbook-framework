"""Local Jinja analysis for validation -- catches undefined bare names
that static regex-based checks miss.

Phase 0 of DYNAMIC_JINJA_RENDER_PLAN.md. The AST-based approach parses
each template with Jinja2 and walks the AST for ``Name`` nodes with
``ctx='load'`` that aren't in the known set (Jinja2 builtins + FSR
globals + locally-defined names like loop variables). This catches
references like ``{{ items | length }}`` where ``items`` is never
defined -- the existing ``_check_undefined_vars`` only matches
``vars.<name>`` regex patterns, so bare names go unchecked.

Pure offline -- stdlib + jinja2 (already a dep). No rendering, no DB,
no live FSR. The render-based approach (SandboxedEnvironment +
StrictUndefined) is the next layer; this module ships the AST walk
first because it is zero-false-positive and directly addresses the
gap.
"""
from __future__ import annotations

from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateSyntaxError

_ENV = Environment(autoescape=False,
                    extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

# Always-available bare names in FSR's Jinja context:
# - ``vars`` -- the root context object (always injected by FSR)
# - Jinja2 built-in globals
# - ``globalVars`` -- FSR context var (jinja_context_vars table)
# - ``workflow`` -- injected by FSR playbook runtime (not in
#   jinja_globals table but present in system playbooks)
_KNOWN_BARE_NAMES: frozenset[str] = frozenset({
    "vars",
    "range", "dict", "lipsum", "cycler", "joiner", "namespace",
    "globalVars", "workflow",
})


def _load_globals_from_db() -> set[str]:
    """Augment the known set with FSR global names from the packaged DB."""
    try:
        import sqlite3

        from fsr_playbooks._db import PACKAGED_SLIM_DB
        with sqlite3.connect(str(PACKAGED_SLIM_DB)) as conn:
            rows = conn.execute("SELECT name FROM jinja_globals").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:  # noqa: BLE001 -- DB is optional; fall back to hardcoded set
        return set()


_KNOWN_BARE_NAMES |= _load_globals_from_db()


def _collect_local_names(ast: nodes.Node) -> set[str]:
    """Collect names defined locally within a template AST.

    Includes loop variables (``{% for x in … %}``), set variables
    (``{% set x = … %}``), and macro names + arguments.  These are
    always safe to read inside their scope, so they should not be
    flagged as undefined.
    """
    local: set[str] = set()
    for for_node in ast.find_all(nodes.For):
        if isinstance(for_node.target, nodes.Name):
            local.add(for_node.target.name)
    for assign_node in ast.find_all(nodes.Assign):
        if isinstance(assign_node.target, nodes.Name):
            local.add(assign_node.target.name)
    for macro_node in ast.find_all(nodes.Macro):
        local.add(macro_node.name)
        for arg in macro_node.args:
            if isinstance(arg, nodes.Name):
                local.add(arg.name)
    return local


def find_undefined_bare_names(
    template: str,
    extra_known: set[str] | None = None,
) -> list[tuple[str, int]]:
    """Parse a Jinja template and return ``(name, lineno)`` for every bare
    ``Name`` node with ``ctx='load'`` that isn't in the known set.

    Bare names are variable references that don't go through
    ``vars.*`` (e.g. ``{{ items | length }}`` where ``items`` is a
    bare name, not ``vars.items``).  The existing static checks only
    match ``vars.<name>`` regex patterns, so bare names go unchecked.

    ``extra_known`` adds step-specific names (e.g. set_variable vars
    surfaced at the top level -- though in practice FSR keeps them
    under ``vars.*``, so this is empty for now).

    Returns unique names (no duplicates) in first-occurrence order.
    """
    if "{{" not in template and "{%" not in template:
        return []
    try:
        ast = _ENV.parse(template)
    except TemplateSyntaxError:
        return []  # syntax errors are already caught by jinja_checks
    known = _KNOWN_BARE_NAMES
    if extra_known:
        known = known | extra_known
    local = _collect_local_names(ast)
    result: list[tuple[str, int]] = []
    seen: set[str] = set()
    for node in ast.find_all(nodes.Name):
        if node.ctx != "load":
            continue
        if node.name in known or node.name in local or node.name in seen:
            continue
        seen.add(node.name)
        result.append((node.name, getattr(node, "lineno", 0)))
    return result
