"""YAML validate / compile endpoints.

Wraps the existing `compiler` package. Adds line/col extraction from
PyYAML errors so the frontend can place Monaco markers; non-parse errors
fall back to line 1 with the structured path attached.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from compiler import compile_yaml as _compile_yaml
from compiler.parser import parse_yaml
from compiler.resolver import Resolver
from compiler.validator import validate as _validate
from compiler.arg_validator import ArgValidator
from compiler.source_fixer import collect_fixes as _collect_fixes

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO_ROOT / "store" / "fsr_reference.db"

router = APIRouter(prefix="/api/yaml", tags=["yaml"])


class YamlIn(BaseModel):
    text: str


class Marker(BaseModel):
    line: int            # 1-based
    col: int             # 1-based
    severity: str        # "error" | "warning" | "info"
    code: str
    message: str
    path: str = ""
    suggestion: str | None = None


def _yaml_mark_for(text: str, err) -> tuple[int, int]:
    mark = getattr(err, "problem_mark", None)
    if mark is not None:
        return (mark.line + 1, mark.column + 1)
    return (1, 1)


_STEPS_IDX_RE = re.compile(r"steps\[(\d+)\]")


def _path_to_line(text: str, path: str) -> int:
    """Best-effort: locate the `steps` block / step index in the source.

    We don't have real source positions on IR errors, so we fall back to
    finding the nth `- id:` line under the relevant playbook's `steps:`.
    Returns 1 if we can't pin it down.

    NOTE: extract ONLY the `steps[N]` index — paths like
    `playbooks[0].steps[2].arguments.conditions[0]` carry trailing
    indices for the option/condition that aren't step indices. Reading
    the last `[N]` would mis-attribute the marker to step 0.
    """
    if not path:
        return 1
    lines = text.splitlines()
    if "steps[" in path:
        m = _STEPS_IDX_RE.search(path)
        if m:
            step_n = int(m.group(1))
            in_steps = False
            seen = -1
            for i, ln in enumerate(lines, start=1):
                stripped = ln.lstrip()
                if stripped.startswith("steps:"):
                    in_steps = True
                    continue
                if in_steps and stripped.startswith("- "):
                    seen += 1
                    if seen == step_n:
                        return i
    if path == "collection":
        for i, ln in enumerate(lines, start=1):
            if ln.lstrip().startswith("collection:"):
                return i
    if path == "playbooks":
        for i, ln in enumerate(lines, start=1):
            if ln.lstrip().startswith("playbooks:"):
                return i
    return 1


def _err_to_marker(text: str, e) -> Marker:
    return Marker(
        line=_path_to_line(text, e.path),
        col=1,
        severity=e.severity,
        code=e.code.value,
        message=e.message,
        path=e.path,
        suggestion=e.suggestion or e.near,
    )


@router.post("/validate")
def validate(body: YamlIn) -> dict[str, Any]:
    text = body.text

    # Catch raw YAML parse errors with real line/col first.
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        line, col = _yaml_mark_for(text, e)
        return {
            "ok": False,
            "markers": [Marker(
                line=line, col=col, severity="error",
                code="parse_error", message=str(e), path="",
            ).model_dump()],
        }

    coll, errs = parse_yaml(text)
    if errs or coll is None:
        return {"ok": not any(e.severity != "warning" for e in errs),
                "markers": [_err_to_marker(text, e).model_dump() for e in errs]}

    markers: list[Marker] = []
    resolver = Resolver(DEFAULT_DB)
    try:
        markers += [_err_to_marker(text, e) for e in resolver.resolve(coll)]
        if not any(m.severity == "error" for m in markers):
            markers += [_err_to_marker(text, e) for e in ArgValidator(resolver.conn).validate(coll)]
    finally:
        resolver.close()
    if not any(m.severity == "error" for m in markers):
        markers += [_err_to_marker(text, e) for e in _validate(coll)]

    ok = not any(m.severity == "error" for m in markers)
    # Bundle source-level auto-fixes inline so the editor's Fixes panel
    # can render without a second roundtrip per keystroke.
    fixes = [f.to_dict() for f in _collect_fixes(text)]
    return {"ok": ok, "markers": [m.model_dump() for m in markers], "fixes": fixes}


@router.post("/fixes")
def fixes(body: YamlIn) -> dict[str, Any]:
    """Source-level auto-fixes for the editor's "Fix warnings" UI.

    Returns one entry per known foot-gun (em-dash step name, bare `yes`
    in `display:`, `vars.input.<param>` missing the `.params.` segment,
    `type: stop`). Each entry carries a Monaco-shaped range so the
    editor can apply the patch as a normal edit (undoable via Cmd-Z).
    """
    return {"fixes": [f.to_dict() for f in _collect_fixes(body.text)]}


@router.post("/compile")
def compile_(body: YamlIn) -> dict[str, Any]:
    res = _compile_yaml(body.text, DEFAULT_DB)
    markers = [_err_to_marker(body.text, e).model_dump() for e in res.errors]
    return {
        "ok": res.ok,
        "fsr_json": res.fsr_json,
        "markers": markers,
    }
