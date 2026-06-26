"""Static Jinja checks — syntax validity + unknown-filter detection.

Two deterministic, high-payoff gaps the pilot's render-path extractor left open
(PILOT_STATIC_ANALYSIS_GAP_PLAN.md "ACTIVE NEXT"):

- **Syntax (jinja_syntax_error).** ``render_paths._extract_from_string`` *swallows*
  ``TemplateSyntaxError`` (``except …: return []``) — a template that won't parse
  produces no consumed paths and otherwise sails through. So a missing ``{% endif %}``
  or a malformed filter inside balanced braces passes ``ready_to_push`` and only
  blows up at runtime. jinja2 *is* the FortiSOAR runtime parser, so surfacing the
  exact ``TemplateSyntaxError`` (it carries ``lineno`` + message) is zero-false-positive.

- **Unknown filter / test (unknown_jinja_filter).** ``{{ ip | uppercasse }}`` parses
  fine but fails at runtime with ``No filter named 'uppercasse'``. We check each
  ``| filter`` and ``is test`` name against the known set (jinja2 built-ins ∪ the
  FortiSOAR custom catalog shipped in ``_data/jinja_filters.json``, generated from
  the Jinja-editor widget by ``tooling/extract_jinja_filters.js``) and emit a
  ``difflib`` did-you-mean. Warning severity — the catalog is a curated subset, so a
  truly-custom-but-real filter shouldn't hard-block.

Pure offline: stdlib + jinja2 (already a compiler dep). No DB, no live FSR.
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

_ENV = Environment(autoescape=False)

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "_data", "jinja_filters.json")


def _load_known() -> tuple[frozenset[str], frozenset[str]]:
    """Known filter and test names = jinja2 built-ins ∪ FortiSOAR custom catalog.

    Unioning with the built-ins keeps the check false-positive-free for stock
    jinja2 filters the widget catalog happens not to list (``tojson``, ``map``,
    ``select``…). The FSR custom catalog adds the ``fortisoar*`` filters the
    runtime registers that jinja2 doesn't know about.
    """
    filters = set(_ENV.filters)
    tests = set(_ENV.tests)
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            cat = json.load(fh)
        # The catalog lists filters (it's a filter palette); fold them into the
        # filter set. They are not jinja tests.
        filters.update(cat.get("filters", {}))
    except (OSError, ValueError):
        pass
    return frozenset(filters), frozenset(tests)


_KNOWN_FILTERS, _KNOWN_TESTS = _load_known()


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
    ``unknown_jinja_filter`` (warning) for filter/test names outside the known
    set. A template that fails to parse is skipped for the filter check (we
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
                "suggestion": ("fix the template — this is the exact error "
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
        out.append({
            "code": "unknown_jinja_filter",
            "message": (f"unknown Jinja {kind} {name!r} at {loc} — not a "
                        f"built-in or a known FortiSOAR {kind}.{did}"),
            "step": step_id, "path": path,
            "location": loc,
            "suggestion": (f"replace with {sug!r}" if sug
                           else f"check the {kind} name against the FSR catalog"),
            "severity": "warning",
        })
    return out
