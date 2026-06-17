"""Render-path extractor — find every ``vars.…`` reference inside a
step's arguments.

Used by the render-path validator (RENDER_PATH_VALIDATOR_PLAN.md
Phase 2) to know what each step *consumes*. Pairing producers
(``output_shape``) with consumers (``consumed_paths``) is what lets
the analyzer flag unreachable refs, missing-key access, type mismatch,
and dead steps.

Pure offline — no live FSR, no jinja rendering, just AST walk.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateSyntaxError


@dataclass(frozen=True)
class ConsumedPath:
    """One ``vars.…`` reference found inside a step's arguments.

    ``path`` is dotted (``vars.steps.fetch.data.id``); ``segments`` is
    the same path split for analyzer convenience. ``source_step_id``
    is the producer step name normalized to its FSR Jinja key (spaces
    → underscores) — empty string for ``vars.input.*`` and other
    non-step refs. ``location`` is a dotted path into the step's
    ``arguments`` showing where the reference appeared, useful for
    UI deep-linking.
    """
    path: str
    segments: tuple[str, ...]
    root: str  # 'steps' | 'input' | 'item' | other
    source_step_id: str  # producer step Jinja key (or "")
    location: str  # arguments.<...> dotted location of the template


_ENV = Environment(autoescape=False)


def _node_to_path(node: nodes.Node) -> tuple[str, ...] | None:
    """Reduce a jinja AST node to a dotted-path tuple.

    Handles ``vars.steps.X.Y``, ``vars.input.Z``, ``vars.steps[X].Y``
    (subscript form), and ``vars.item``. Anything that isn't a pure
    chain of Name + Getattr + constant Getitem yields ``None`` —
    those references involve runtime values we can't statically
    resolve, and the analyzer should skip them.
    """
    parts: list[str] = []
    cur = node
    while True:
        if isinstance(cur, nodes.Name):
            parts.append(cur.name)
            break
        if isinstance(cur, nodes.Getattr):
            parts.append(cur.attr)
            cur = cur.node
            continue
        if isinstance(cur, nodes.Getitem):
            arg = cur.arg
            if isinstance(arg, nodes.Const) and isinstance(arg.value,
                                                            (str, int)):
                parts.append(str(arg.value))
                cur = cur.node
                continue
            return None
        return None
    parts.reverse()
    return tuple(parts)


def _walk_ast(root: nodes.Node) -> Iterator[tuple[str, ...]]:
    """Yield each fully-resolved attribute chain rooted at ``vars``."""
    seen_chains: set[tuple[str, ...]] = set()

    # We want each maximal chain once. Walk Getattr/Getitem nodes and,
    # for any whose terminal Name is `vars`, emit the path. Skip nodes
    # whose parent is itself a Getattr/Getitem rooted at vars so we
    # don't double-emit the same chain at every depth.
    for node in root.find_all((nodes.Getattr, nodes.Getitem, nodes.Name)):
        path = _node_to_path(node)
        if not path or path[0] != "vars":
            continue
        if path in seen_chains:
            continue
        # Only emit if this is the *outermost* such reference for
        # this chain — i.e. the parent isn't another Getattr/Getitem
        # extending it. Easiest: track all emitted prefixes and skip
        # any path that's a prefix of one we'll see later. Two-pass.
        seen_chains.add(path)

    # Drop strict prefixes of longer chains so callers see the
    # deepest reference per template.
    pruned: list[tuple[str, ...]] = []
    sorted_chains = sorted(seen_chains, key=len, reverse=True)
    covered: set[tuple[str, ...]] = set()
    for chain in sorted_chains:
        if any(chain == c[:len(chain)] and chain != c for c in covered):
            continue
        pruned.append(chain)
        covered.add(chain)
    yield from sorted(pruned)


def _ref_to_consumed(chain: tuple[str, ...], location: str) -> ConsumedPath:
    """Build a ConsumedPath from a vars-rooted chain like
    ``('vars', 'steps', 'fetch_alert', 'data', 'id')``."""
    segments = chain[1:]  # drop leading 'vars'
    root = segments[0] if segments else ""
    source_step_id = ""
    if root == "steps" and len(segments) >= 2:
        source_step_id = segments[1]
    return ConsumedPath(
        path=".".join(chain),
        segments=segments,
        root=root,
        source_step_id=source_step_id,
        location=location,
    )


def _extract_from_string(template: str, location: str) -> list[ConsumedPath]:
    if "{{" not in template and "{%" not in template:
        return []
    try:
        ast = _ENV.parse(template)
    except TemplateSyntaxError:
        return []
    return [_ref_to_consumed(chain, location) for chain in _walk_ast(ast)]


def extract_consumed_paths(value: Any,
                           location: str = "arguments") -> list[ConsumedPath]:
    """Walk a step's arguments tree and collect every ``vars.…``
    reference found inside any string template.

    The ``location`` parameter is the dotted path into ``arguments``;
    nested calls extend it (``arguments.params.url``).
    """
    out: list[ConsumedPath] = []
    if isinstance(value, str):
        out.extend(_extract_from_string(value, location))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(extract_consumed_paths(v, f"{location}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(extract_consumed_paths(v, f"{location}[{i}]"))
    return out


_PICKLIST_RE = __import__("re").compile(
    r"""['"]([^'"]+)['"]\s*\|\s*picklist\(\s*['"]([^'"]+)['"]\s*\)"""
)


def extract_picklist_refs(value: Any,
                          location: str = "arguments"
                          ) -> list[dict[str, str]]:
    """Find every ``{{ 'PicklistName' | picklist('value') }}`` filter
    invocation in a step's arguments tree.

    Static — pure regex over template strings. Returns one dict per
    call: ``{picklist, value, location}``. The analyzer's C4 check
    uses these to validate values against the live FSR's picklists
    via ``precheck_picklist_value``.
    """
    out: list[dict[str, str]] = []
    if isinstance(value, str):
        for m in _PICKLIST_RE.finditer(value):
            out.append({
                "picklist": m.group(1),
                "value": m.group(2),
                "location": location,
            })
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(extract_picklist_refs(v, f"{location}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(extract_picklist_refs(v, f"{location}[{i}]"))
    return out


def consumed_paths_dict(value: Any,
                        location: str = "arguments") -> list[dict[str, Any]]:
    """JSON-serializable form for the MCP trace and frontend."""
    return [
        {
            "path": cp.path,
            "segments": list(cp.segments),
            "root": cp.root,
            "source_step_id": cp.source_step_id,
            "location": cp.location,
        }
        for cp in extract_consumed_paths(value, location)
    ]
