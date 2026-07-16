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

from fsr_playbooks.compiler.errors import CompileError, ErrorCode

# FortiSOAR's runtime Jinja engine enables the `do` extension
# ({% do x.append(y) %} — expression statements for mutating variables
# inside loops, heavily used by system playbooks) and `loopcontrols`
# ({% break %} / {% continue %} inside {% for %}). Without these
# extensions the parser raises false-positive syntax errors on valid
# templates. Live-verified on 8.0.0-6034.
_ENV = Environment(autoescape=False,
                   extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "_data", "jinja_filters.json")


def _load_known() -> tuple[frozenset[str], frozenset[str]]:
    """Known names = jinja2 built-ins ∪ FSR widget catalog ∪ Ansible namespace.

    Unioning with the built-ins keeps the check false-positive-free for stock
    jinja2 filters the widget catalog happens not to list (``tojson``, ``map``,
    ``select``…). The FSR custom catalog adds the ``fortisoar*`` filters the
    runtime registers that jinja2 doesn't know about. The ``ansible_filters``/
    ``ansible_tests`` keys carry the Ansible plugin namespace (ansible.builtin
    + community.general, from ``tooling/extract_ansible_filters.py``) — FSR
    playbooks execute through an Ansible-based engine, so ``json_query``,
    ``ternary``, ``combine``… are valid even though the widget palette omits
    them (AGENT_HARDENING_PLAN §G false-positive fix).
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
            "message": (f"Jinja {kind} {name!r} at {loc} is not in the local "
                        f"catalog (jinja2 built-ins + FSR + Ansible) — it may "
                        f"still be valid on the target system.{did}"),
            "step": step_id, "path": path,
            "location": loc,
            "suggestion": (f"if {name!r} was a typo, replace with {sug!r}; "
                           f"if it is a real {kind}, keep it — this is advisory"
                           if sug else
                           f"advisory only — verify the {kind} name; do not "
                           f"rewrite a working template to silence this"),
            "severity": "warning",
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
    precise dotted ``path`` — ``<step_path>.<location>`` (e.g.
    ``playbooks[0].steps[3].arguments.params.code``) — so the diagnostic points
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
