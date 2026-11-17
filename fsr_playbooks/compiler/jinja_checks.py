"""Static Jinja checks -- syntax validity + unknown-filter detection.

Two deterministic, high-payoff gaps the pilot's render-path extractor left open
(PILOT_STATIC_ANALYSIS_GAP_PLAN.md "ACTIVE NEXT"):

- **Syntax (jinja_syntax_error).** ``render_paths._extract_from_string`` *swallows*
  ``TemplateSyntaxError`` (``except …: return []``) -- a template that won't parse
  produces no consumed paths and otherwise sails through. So a missing ``{% endif %}``
  or a malformed filter inside balanced braces passes ``ready_to_push`` and only
  blows up at runtime. jinja2 *is* the FortiSOAR runtime parser, so surfacing the
  exact ``TemplateSyntaxError`` (it carries ``lineno`` + message) is zero-false-positive.

- **Unknown filter / test (unknown_jinja_filter).** ``{{ ip | uppercasse }}`` parses
  fine but fails at runtime with ``No filter named 'uppercasse'``. We check each
  ``| filter`` and ``is test`` name against the known set (jinja2 built-ins ∪ the
  FortiSOAR custom catalog shipped in ``_data/jinja_filters.json``, generated from
  the Jinja-editor widget by ``tooling/extract_jinja_filters.js``) and emit a
  ``difflib`` did-you-mean. **Filters stay warning-severity** -- the catalog is a
  curated subset, so a truly-custom-but-real filter shouldn't hard-block.
  **Unknown tests are errors** when the packaged DB carries the
  backend-introspected ``jinja_tests`` registry harvested off the live workflow
  engine (``probe_jinja_backend``): absence there is appliance-authoritative and
  the template fails at render time -- live-verified on 8.0.x, where
  ``is not empty`` (no ``empty`` test in stock Jinja2 or on the box) crashed a
  child playbook mid-run while the compiler emitted this finding as a warning
  nobody was shown.
- **Non-boolean decision condition (non_boolean_condition).** FSR's decision
  engine requires each route condition's render to be a Python ``bool`` -- a
  bare ``{{ vars.steps.X.data.foo }}`` renders whatever sits in that slot and
  the step fails at runtime. ``non_boolean_condition`` below checks one
  expression's AST for a provably-boolean shape (comparison / ``is`` test /
  ``not`` / and-or over boolean operands / ``| bool``); the linter walks every
  decision route with it, and undecidable shapes stay silent so the gate never
  false-fires on exotic-but-working templates.

Pure offline: stdlib + jinja2 (already a compiler dep) + the packaged reference
DB (backend-introspected registries; no live FSR calls).
Functions return plain ``dict`` findings in the same shape the per-step schema
checks use, so wiring is a one-liner.
"""
from __future__ import annotations

import difflib
import json
import os
from typing import Any

from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateSyntaxError

from fsr_playbooks.compiler.errors import CompileError, ErrorCode

# FortiSOAR's runtime Jinja engine enables the `do` extension
# ({% do x.append(y) %} -- expression statements for mutating variables
# inside loops, heavily used by system playbooks) and `loopcontrols`
# ({% break %} / {% continue %} inside {% for %}). Without these
# extensions the parser raises false-positive syntax errors on valid
# templates. Live-verified on 8.0.0-6034.
_ENV = Environment(autoescape=False,
                   extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "_data", "jinja_filters.json")


def _load_known() -> tuple[frozenset[str], frozenset[str]]:
    """Known names = jinja2 built-ins ∪ FSR widget catalog ∪ Ansible namespace
    ∪ curated jinja_macros table.

    Unioning with the built-ins keeps the check false-positive-free for stock
    jinja2 filters the widget catalog happens not to list (``tojson``, ``map``,
    ``select``…). The FSR custom catalog adds the ``fortisoar*`` filters the
    runtime registers that jinja2 doesn't know about. The ``ansible_filters``/
    ``ansible_tests`` keys carry the Ansible plugin namespace (ansible.builtin
    + community.general, from ``tooling/extract_ansible_filters.py``) -- FSR
    playbooks execute through an Ansible-based engine, so ``json_query``,
    ``ternary``, ``combine``… are valid even though the widget palette omits
    them (AGENT_HARDENING_PLAN §G false-positive fix).

    The ``jinja_macros`` table (curated, in the packaged DB) carries filter
    names mined from the live corpus + Ansible + FSR runtime -- 43 filters the
    JSON catalog doesn't list (``picklist``, ``ipaddr``, ``resolveRange``…).
    Loading from it catches the FSR-custom filters the widget palette omits
    without needing a JSON catalog rebuild for every new filter discovered.

    The ``jinja_tests`` table rides along in the same packaged DB: it is the
    backend-introspected appliance test registry (via ``probe_jinja_backend``),
    and both its presence (the authority for error-severity unknown tests --
    see ``_LIVE_TESTS``) and its names (known tests) load here.
    """
    filters = set(_ENV.filters)
    tests = set(_ENV.tests)
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            cat = json.load(fh)
        # "filters" is the widget filter palette; it lists filters only.
        filters.update(cat.get("filters", {}))
        filters.update(cat.get("ansible_filters", {}))
        tests.update(cat.get("ansible_tests", {}))
    except (OSError, ValueError):
        pass
    # The curated jinja_macros table is the superset of known filter names.
    # The jinja_tests table (same DB) carries the appliance's own test
    # registry, backend-introspected off the live workflow engine.
    try:
        import sqlite3

        from fsr_playbooks._db import PACKAGED_SLIM_DB
        with sqlite3.connect(str(PACKAGED_SLIM_DB)) as conn:
            rows = conn.execute("SELECT name FROM jinja_macros").fetchall()
            trows = conn.execute("SELECT name FROM jinja_tests").fetchall()
        filters.update(r[0] for r in rows if r[0])
        tests.update(r[0] for r in trows if r[0])
    except Exception:  # noqa: BLE001 -- DB is optional; fall back to JSON
        pass
    return frozenset(filters), frozenset(tests)


_KNOWN_FILTERS, _KNOWN_TESTS = _load_known()


def _load_live_tests() -> frozenset[str]:
    """The appliance's own test registry, backend-introspected from the live
    workflow engine's Jinja Environment (``dump_jinja_filters.py`` on the box
    -> ``probe_jinja_backend`` ingest -- 39 names on the current instance,
    stock Jinja2 only: no widget, Ansible, or FSR-custom tests exist at render
    time).

    When non-empty it is *authoritative*: an ``is <name>`` check outside it
    fails at render time on the box, guaranteeing the crash the
    error-severity unknown-test finding describes. When empty (DB missing or
    not harvested), unknown tests fall back to the advisory warning.
    """
    try:
        import sqlite3

        from fsr_playbooks._db import PACKAGED_SLIM_DB
        with sqlite3.connect(str(PACKAGED_SLIM_DB)) as conn:
            rows = conn.execute("SELECT name FROM jinja_tests").fetchall()
        return frozenset(r[0] for r in rows if r[0])
    except Exception:  # noqa: BLE001 -- DB is optional
        return frozenset()


_LIVE_TESTS = _load_live_tests()


def _iter_templates(value: Any, location: str):
    """Yield ``(template_str, location)`` for every string in an args tree."""
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            yield value, location
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _iter_templates(v, f"{location}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _iter_templates(v, f"{location}[{i}]")


def _suggest(name: str, known: frozenset[str]) -> str | None:
    # cutoff=0.6 is difflib's own default and the empirical sweet spot: it
    # catches real typos a stricter 0.7 misses (`uppercasse`→`upper`,
    # `jsonify`→`tojson`) without the noise 0.5 pulls in (`escape`, `float`).
    near = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    return near[0] if near else None


def check_jinja(value: Any, *, step_id: str, path: str,
                location: str = "arguments") -> list[dict[str, Any]]:
    """Validate every Jinja template in a step's arguments.

    Emits ``jinja_syntax_error`` (error) for un-parseable templates and
    ``unknown_jinja_filter`` for filter/test names outside the known set --
    warning for *filters* (curated catalog), error for *tests* when the
    backend-introspected appliance registry (``_LIVE_TESTS``) is loaded. A
    template that fails to parse is skipped for the filter check (we
    have no AST), so each template yields at most a syntax finding *or*
    filter findings, not both.
    """
    findings: list[dict[str, Any]] = []
    for template, loc in _iter_templates(value, location):
        try:
            ast = _ENV.parse(template)
        except TemplateSyntaxError as exc:
            lineno = getattr(exc, "lineno", None)
            where = f" (line {lineno})" if lineno else ""
            findings.append({
                "code": "jinja_syntax_error",
                "message": (f"Jinja template at {loc} won't parse{where}: "
                            f"{exc.message}"),
                "step": step_id, "path": path,
                "location": loc,
                "suggestion": ("fix the template -- this is the exact error "
                               "FortiSOAR's Jinja engine raises at runtime"),
                "severity": "error",
            })
            continue
        findings.extend(_check_filter_names(ast, step_id, path, loc))
    return findings


def _check_filter_names(ast: nodes.Node, step_id: str, path: str,
                        loc: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for node, known, kind in (
        *((n, _KNOWN_FILTERS, "filter") for n in ast.find_all(nodes.Filter)),
        *((n, _KNOWN_TESTS, "test") for n in ast.find_all(nodes.Test)),
    ):
        name = node.name
        if not name or name in known or (kind, name) in seen:
            continue
        seen.add((kind, name))
        sug = _suggest(name, known)
        did = f" Did you mean {sug!r}?" if sug else ""
        if kind == "test" and _LIVE_TESTS:
            # The jinja_tests registry is the box's own render-time test set
            # (inspect.signature over the live workflow engine), so absence
            # there is not "maybe valid elsewhere" -- the template fails at
            # render, guaranteed. Live-verified on 8.0.x: `is not empty`
            # (stock Jinja2 has no `empty` test; the box registers none
            # either) killed a live child run while this finding sat at
            # warning severity nobody was shown.
            message = (f"Jinja test {name!r} at {loc} is not in the "
                       f"appliance's backend-introspected test registry "
                       f"(jinja_tests: {len(_LIVE_TESTS)} names) -- the "
                       f"template fails at render time on the box.{did}")
            suggestion = (
                f"replace {name!r} with a registry test"
                + (f" ({sug!r}?)" if sug else "")
                + " (the standard emptiness guard is "
                  "`{{ x | default('', true) | string | length > 0 }}`); "
                  "re-harvest the reference DB if this is a newer FSR version")
            severity = "error"
        else:
            message = (f"Jinja {kind} {name!r} at {loc} is not in the local "
                       f"catalog (jinja2 built-ins + FSR + Ansible) -- it may "
                       f"still be valid on the target system.{did}")
            suggestion = (f"if {name!r} was a typo, replace with {sug!r}; "
                          f"if it is a real {kind}, keep it -- this is advisory"
                          if sug else
                          f"advisory only -- verify the {kind} name; do not "
                          f"rewrite a working template to silence this")
            severity = "warning"
        out.append({
            "code": "unknown_jinja_filter",
            "message": message,
            "step": step_id, "path": path,
            "location": loc,
            "suggestion": suggestion,
            "severity": severity,
        })
    return out


# Code string → ErrorCode member. ``check_jinja`` emits the two codes below;
# the fallback keeps the bridge forward-compatible if a new code is added.
_CODE_TO_ENUM = {
    "jinja_syntax_error": ErrorCode.JINJA_SYNTAX_ERROR,
    "unknown_jinja_filter": ErrorCode.UNKNOWN_JINJA_FILTER,
}


def to_compile_errors(findings: list[dict[str, Any]]) -> list[CompileError]:
    """Convert ``check_jinja`` dict findings into ``CompileError`` objects.

    ``check_jinja`` returns the per-step-schema finding shape (plain dicts);
    the compile path works in ``CompileError`` objects. This bridges the two,
    mapping each code string to its ``ErrorCode`` member and reconstructing the
    precise dotted ``path`` -- ``<step_path>.<location>`` (e.g.
    ``playbooks[0].steps[3].arguments.params.code``) -- so the diagnostic points
    at the exact argument, matching the location precision the old brace-count
    check emitted.
    """
    out: list[CompileError] = []
    for f in findings:
        loc = f.get("location", "")
        path = f"{f['path']}.{loc}" if loc else f.get("path", "")
        out.append(CompileError(
            code=_CODE_TO_ENUM.get(f["code"], ErrorCode.BAD_VALUE),
            message=f["message"],
            path=path,
            suggestion=f.get("suggestion"),
            severity=f.get("severity", "error"),
        ))
    return out


# ---------------------------------------------------------------------------
# Decision-route boolean gate
#
# FSR's decision engine evaluates each route condition's render and requires
# a strict Python bool (an isinstance check -- live-verified on 8.0.x, where
# four `{{ vars.steps.X.data.Y }}` routes rendered plain strings and crashed
# their child playbooks mid-run). `check_jinja` has no step-type context, so
# the linter owns the per-decision walk; these helpers own the single
# expression verdict so every consumer shares one AST definition of
# "provably boolean".

# Filters whose application yields a bool. `bool` is the live-proven idiom
# (the ingestion playbooks' request guards end in `| default(false) | bool`).
_BOOLEAN_FILTERS = frozenset({"bool"})


def _bool_terminal(node: nodes.Node) -> bool:
    """Is this expression node guaranteed to *render* a Python bool?"""
    if isinstance(node, nodes.Compare):
        return True                          # any comparison is bool
    if isinstance(node, nodes.Test):
        return True                          # `is (not) test` is bool
    if isinstance(node, nodes.Const):
        return isinstance(node.value, bool)  # `true` / `false` literals
    if isinstance(node, nodes.Not):
        return True                          # `not x` is always bool
    if isinstance(node, (nodes.And, nodes.Or)):
        # Jinja `and`/`or` return the last evaluated *operand value*, not a
        # bool, so both sides must themselves render bools.
        return _bool_terminal(node.left) and _bool_terminal(node.right)
    if isinstance(node, nodes.Filter):
        return isinstance(node.name, str) and node.name in _BOOLEAN_FILTERS
    return False


def _non_bool_shape(node: nodes.Node) -> str:
    """Short human phrase for why the node is not provably boolean."""
    if isinstance(node, (nodes.And, nodes.Or)):
        return ("an and/or whose operand sides can become the rendered "
                "value (Jinja and/or return an operand, not a bool)")
    if isinstance(node, nodes.Filter):
        return f"an unguarded `| {node.name}` chain"
    if isinstance(node, (nodes.Name, nodes.Getattr, nodes.Getitem)):
        return "a bare reference (its runtime value's type is unknown)"
    return "a value expression"


def non_boolean_condition(text: str) -> str | None:
    """Decide whether a decision-route condition is provably NOT boolean.

    Returns ``None`` when the expression provably renders a bool -- **or**
    when the verdict is undecidable (a template with statements/folds,
    more than one expression, unparsed syntax, or a non-Jinja string).
    Callers warn only on a definite non-bool shape; undecidable stays
    silent so the gate never false-fires on exotic-but-working templates.
    """
    if "{{" not in text:
        return None                     # literal routing value -- not ours
    try:
        ast = _ENV.parse(text)
    except TemplateSyntaxError:
        return None                     # the syntax check reports this
    body = list(getattr(ast, "body", []))
    if len(body) != 1 or not isinstance(body[0], nodes.Output):
        return None                     # statements/folds around the value
    exprs = [n for n in body[0].nodes
             if not (isinstance(n, nodes.TemplateData)
                     and not str(getattr(n, "data", "") or "").strip())]
    if len(exprs) != 1:
        return None                     # multi-expression (or zero) -- skip
    node = exprs[0]
    if _bool_terminal(node):
        return None
    return _non_bool_shape(node)
