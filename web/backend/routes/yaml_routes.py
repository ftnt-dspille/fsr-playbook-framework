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
            step_start_line = None
            step_start_indent = -1
            for i, ln in enumerate(lines, start=1):
                stripped = ln.lstrip()
                if stripped.startswith("steps:"):
                    in_steps = True
                    continue
                if in_steps and stripped.startswith("- "):
                    seen += 1
                    if seen == step_n:
                        step_start_line = i
                        step_start_indent = len(ln) - len(stripped)
                    elif seen > step_n:
                        break
            if step_start_line is not None:
                # If the path ends in `.<key>` (e.g. ".type", ".arguments"),
                # find that key inside this step block so the squiggle
                # lands on the offending line, not the step header.
                key_match = re.search(r"\.([a-zA-Z_][a-zA-Z0-9_]*)$", path)
                if key_match:
                    key = key_match.group(1)
                    for j in range(step_start_line, len(lines) + 1):
                        ln = lines[j - 1]
                        stripped_j = ln.lstrip()
                        indent_j = len(ln) - len(stripped_j)
                        # Bail out when we leave this step's indentation
                        # (next step or a dedent past the step block).
                        if j > step_start_line and (
                            stripped_j.startswith("- ")
                            and indent_j <= step_start_indent
                        ):
                            break
                        if stripped_j.startswith(key + ":"):
                            return j
                return step_start_line
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


@router.post("/compile")
def compile_(body: YamlIn) -> dict[str, Any]:
    res = _compile_yaml(body.text, DEFAULT_DB)
    markers = [_err_to_marker(body.text, e).model_dump() for e in res.errors]
    return {
        "ok": res.ok,
        "fsr_json": res.fsr_json,
        "markers": markers,
    }


@router.post("/shapes")
def shapes(body: YamlIn) -> dict[str, Any]:
    """Fast typed-walker pass over the buffer — used by the variable
    picker / Monaco completions to surface real step output shapes
    without forcing the user to run the full verify_playbook gate.

    No live probe, no diagnostics — just `per_step_jinja_shapes` and a
    flag per step indicating *why* its shape is unknown so the picker
    can prompt the user to verify (or otherwise enrich) it.
    """
    from compiler.typed_walker import walk_playbook
    from compiler.parser import parse_yaml
    try:
        coll, errs = parse_yaml(body.text)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "shapes": {}}
    if coll is None:
        return {
            "ok": False,
            "error": "; ".join(str(e) for e in errs) or "parse failed",
            "shapes": {},
        }
    try:
        walk = walk_playbook(coll)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "shapes": {}}

    shapes_by_jkey: dict[str, dict[str, Any]] = {}
    # Top-level vars created by `set_variable` steps. FSR exposes these
    # as `vars.<name>` (NOT `vars.steps.<step>.<name>` — the corpus
    # makes this clear: `{{vars.cicd_env}}`, `{{vars.source_control_base_url}}`).
    top_level_vars: dict[str, dict[str, Any]] = {}
    needs_verify: list[dict[str, str]] = []

    def _collect_top_level(step):
        """Pull set_variable arg_list / vars: keys and record their shape
        under the top-level `vars.<name>` namespace (real FSR runtime)."""
        if step.type != "set_variable":
            return
        a = step.arguments or {}
        arg_list = a.get("arg_list") or a.get("vars") or []
        entries: list[tuple[str, Any]] = []
        if isinstance(arg_list, list):
            for entry in arg_list:
                if isinstance(entry, dict):
                    k = entry.get("key") or entry.get("name")
                    if isinstance(k, str) and k:
                        entries.append((k, entry.get("value")))
        elif isinstance(arg_list, dict):
            for k, v in arg_list.items():
                if isinstance(k, str) and k:
                    entries.append((k, v))
        for k, _v in entries:
            # We don't (yet) infer the value's type from the literal —
            # set_variable values are often Jinja templates whose type
            # depends on the rendered output. Mark as `any`.
            top_level_vars[k] = {"kind": "scalar", "type": "any"}

    for pb in coll.playbooks:
        for s in pb.steps:
            _collect_top_level(s)
            jkey = (s.name or s.id or "").strip().replace(" ", "_")
            if not jkey:
                continue
            sh = walk.per_step_shapes.get(s.id)
            if sh is None:
                continue
            shapes_by_jkey[jkey] = sh
            if sh.get("kind") == "unknown":
                needs_verify.append({
                    "step": jkey,
                    "step_id": s.id,
                    "reason": str(sh.get("reason") or "shape not inferable"),
                })
    return {
        "ok": True,
        "shapes": shapes_by_jkey,
        "top_level_vars": top_level_vars,
        "needs_verify": needs_verify,
    }
