"""Runtime step-output-dependency defect: passes static, wrong at run time.

The one bug class static checks structurally cannot catch. A downstream step
references `vars.steps.<Producer>.<path>`; the path is valid Jinja so it
compiles, but whether it RESOLVES depends on the producer's real output shape
(step_output.py). This injects a plausible-but-wrong path into such a reference
and grades a repair by re-rendering the reference against the captured real
shape -- empty render == still broken, non-empty == fixed.

Step names appear in Jinja with spaces replaced by underscores
(`Get Macros` -> `vars.steps.Get_Macros`), matching FSR's own convention.
"""
from __future__ import annotations

import copy
import re
from typing import Any

import yaml

from tooling.evals.corpus_authoring import step_output


def _norm(step_name: str) -> str:
    return re.sub(r"\s+", "_", step_name.strip())


def _walk_strings(obj: Any, path: tuple = ()):
    """Yield (path, string) for every string leaf in a nested dict/list."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, path + (i,))


def refs_to_step(coll: dict, producer: str) -> list[tuple[tuple, str]]:
    """Every (path, expr) in the collection whose Jinja mentions the producer
    step's output (`vars.steps.<Producer_normalized>`)."""
    token = f"vars.steps.{_norm(producer)}"
    out = []
    for path, s in _walk_strings(coll):
        if token in s and ("{{" in s or "{%" in s):
            out.append((path, s))
    return out


def _set_at(coll: dict, path: tuple, value: str) -> None:
    cur: Any = coll
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = value


def grade_runtime_dependency(yaml_text: str, producer: str,
                             shape: dict) -> dict[str, Any]:
    """Does some reference to the producer's output RESOLVE against its real
    shape? has_ref: the playbook reads the producer at all; resolves: at least
    one such reference renders non-empty (i.e. the dependency actually works)."""
    coll = yaml.safe_load(yaml_text)
    refs = refs_to_step(coll, producer)
    resolves = any(step_output.reference_resolves(expr, {_norm(producer): shape})
                   for _path, expr in refs)
    return {"has_ref": bool(refs), "resolves": resolves,
            "refs": [expr for _p, expr in refs]}


def inject_wrong_output_path(yaml_text: str, producer: str,
                             shape: dict) -> dict | None:
    """Rewrite a resolving reference to the producer into a plausible-but-wrong
    sibling path that renders empty against the real shape. Returns a defect
    dict (broken yaml + how to tell it is broken) or None if no fixable ref."""
    coll = yaml.safe_load(yaml_text)
    refs = refs_to_step(coll, producer)
    token = f"vars.steps.{_norm(producer)}"
    is_list = isinstance(shape, dict) and "__list_of__" in shape
    for path, expr in refs:
        if not step_output.reference_resolves(expr, {_norm(producer): shape}):
            continue  # only break one that currently works
        if is_list and re.search(r"\[\s*\d+\s*\]", expr):
            # the classic list-as-scalar gotcha: drop the index, so a list is
            # read as if it were a single record -> the attr renders empty.
            broken_expr = re.sub(r"\[\s*\d+\s*\]", "", expr, count=1)
        else:
            # append a plausible-but-absent child onto the producer's path
            # (e.g. `.data` -> `.data.value`) -> renders empty at run time.
            broken_expr = re.sub(
                token + r"((?:\.[A-Za-z0-9_]+|\[\d+\])*)",
                lambda m: token + m.group(1) + ".value", expr, count=1)
        if broken_expr == expr:
            broken_expr = "{{ " + token + ".value }}"
        c = copy.deepcopy(coll)
        _set_at(c, path, broken_expr)
        return {"yaml": yaml.safe_dump(c, sort_keys=False, allow_unicode=True),
                "kind": "runtime_output_dependency",
                "producer": producer,
                "broken_ref": broken_expr,
                "detail": f"ref to {producer} output rewritten to a non-resolving path",
                "runtime_only": True}
    return None
