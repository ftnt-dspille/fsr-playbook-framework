"""Antipattern linter for FSR connectors.

Scans a connector's operations.py for known bug shapes. AST-based where
precision matters, grep-based for fast textual patterns.

Patterns (codes are stable, used by callers):
  AP001  params.update(<user dict>) -- merges arbitrary user dict into the
         query string. APIs reject unknown query keys. Real ticket: MS Teams
         batch (4 ops, one source fix closed 4 tickets).
  AP002  Hardcoded verify=False on requests.* / helper calls -- TLS bypass,
         security review will block release.
  AP003  Missing status check between requests call and .json() -- handler
         will parse the error body as data and produce misleading errors.
  AP004  .format() / f-string URL with user-supplied path segment but no
         urllib.parse.quote -- breaks on user input containing /, %, spaces.
  AP005  Enum/csv coercion via .split(',') on a user-typed field without
         validating against the API's accepted set -- silent acceptance of
         garbage values that the API later rejects with a 400.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    code: str
    line: int
    message: str
    snippet: str = ""

    def fmt(self) -> str:
        return f"  [{self.code}] line {self.line}: {self.message}"


# Heuristics for "this is a user-controlled dict"
_USER_DICT_NAMES = {
    "params", "custom_attributes", "extra_params", "additional_params",
    "user_params", "kwargs", "extra_fields", "body_extras",
}


def _src_line(src_lines: list[str], lineno: int) -> str:
    if 0 < lineno <= len(src_lines):
        return src_lines[lineno - 1].strip()
    return ""


class _Visitor(ast.NodeVisitor):
    def __init__(self, src_lines: list[str]):
        self.src_lines = src_lines
        self.findings: list[Finding] = []
        # track json-calls per function, to compare against response-status
        # bookkeeping needs is overkill for this pass; we just flag textually.

    # AP001: params.update(<name>) where name looks user-controlled
    # AP002: verify=False kwarg in any Call
    # AP003: .json() chained or called on a request return whose status
    #         hasn't been checked (heuristic -- flag if no raise_for_status
    #         or status_code check appears in same function).
    # AP004: f-string / .format on URL with user segment, no quote()
    # AP005: .split(',') on a value that becomes an API arg

    def visit_Call(self, node: ast.Call):
        # AP001
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "update"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "params"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in _USER_DICT_NAMES
                and node.args[0].id != "params"):
            self.findings.append(Finding(
                "AP001", node.lineno,
                f"params.update({node.args[0].id}) merges a user-controlled dict "
                f"into the query string; APIs reject unknown query keys. "
                f"Filter to the accepted set or move to the request body.",
                _src_line(self.src_lines, node.lineno),
            ))
        # AP002 verify=False
        for kw in node.keywords:
            if (kw.arg == "verify" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False):
                self.findings.append(Finding(
                    "AP002", kw.value.lineno,
                    "verify=False disables TLS validation; make it configurable "
                    "via connector config['verify_ssl'] instead.",
                    _src_line(self.src_lines, kw.value.lineno),
                ))
        self.generic_visit(node)


def _scan_status_check_pattern(tree: ast.Module, src_lines: list[str]) -> list[Finding]:
    """AP003: inside any function, if .json() is called but no raise_for_status()
    nor any `status_code` reference appears anywhere in the function, flag the
    .json() call."""
    out: list[Finding] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        json_calls: list[ast.Call] = []
        has_check = False
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if sub.func.attr == "json" and not sub.args and not sub.keywords:
                    json_calls.append(sub)
                if sub.func.attr == "raise_for_status":
                    has_check = True
            if isinstance(sub, ast.Attribute) and sub.attr == "status_code":
                has_check = True
            if isinstance(sub, ast.Name) and sub.id in ("raise_for_error", "raise_if_error"):
                has_check = True
        if not has_check:
            for c in json_calls:
                out.append(Finding(
                    "AP003", c.lineno,
                    f"in {fn.name}(): .json() called without a prior raise_for_status() "
                    f"or status_code check; error bodies will be parsed as success data.",
                    _src_line(src_lines, c.lineno),
                ))
    return out


def _scan_url_format(tree: ast.Module, src_lines: list[str]) -> list[Finding]:
    """AP004: f-string / .format() building a URL with a param interpolated
    into a path segment, but no urllib.parse.quote (or quote_plus) in the
    same function. Heuristic -- flags candidates."""
    out: list[Finding] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_quote = False
        candidates: list[tuple[int, str]] = []
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if sub.func.attr in ("quote", "quote_plus"):
                    has_quote = True
            # also recognise the imported-name form: `from urllib.parse import
            # quote; quote(seg)` -- otherwise idiomatic safe code false-positives.
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id in ("quote", "quote_plus"):
                    has_quote = True
            if isinstance(sub, ast.JoinedStr):  # f-string
                # Look for "/{name}" patterns
                s = src_lines[sub.lineno - 1] if 0 < sub.lineno <= len(src_lines) else ""
                if ("/{" in s or "/' +" in s) and ("http" in s.lower() or "/api/" in s or "endpoint" in s.lower() or "url" in s.lower()):
                    candidates.append((sub.lineno, s.strip()))
            elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "format":
                s = src_lines[sub.lineno - 1] if 0 < sub.lineno <= len(src_lines) else ""
                if "/{" in s and ("http" in s.lower() or "/api/" in s or "endpoint" in s.lower() or "url" in s.lower()):
                    candidates.append((sub.lineno, s.strip()))
        if not has_quote:
            for lineno, snip in candidates:
                out.append(Finding(
                    "AP004", lineno,
                    "URL built from interpolated path segment without urllib.parse.quote(); "
                    "user input containing /, %, or spaces will produce malformed requests.",
                    snip,
                ))
    return out


def _scan_split_csv(tree: ast.Module, src_lines: list[str]) -> list[Finding]:
    """AP005: .split(',') applied to a parameter value, with no allowlist
    check nearby. Heuristic -- flags every .split(',') usage on a Name; user
    can dismiss false positives."""
    out: list[Finding] = []
    for sub in ast.walk(tree):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "split"
                and len(sub.args) == 1
                and isinstance(sub.args[0], ast.Constant)
                and sub.args[0].value == ","):
            target = sub.func.value
            # only flag when splitting a Name (likely a user-supplied string),
            # not a literal
            if isinstance(target, ast.Name):
                out.append(Finding(
                    "AP005", sub.lineno,
                    f"'{target.id}'.split(',') coerces a user-typed string into a list "
                    f"without validating values against the API's accepted enum set; "
                    f"unknown values reach the API and produce confusing 400s.",
                    _src_line(src_lines, sub.lineno),
                ))
    return out


def scan(connector_dir: Path) -> list[Finding]:
    ops_py = connector_dir / "operations.py"
    if not ops_py.exists():
        return []
    src = ops_py.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Finding("AP000", e.lineno or 0, f"operations.py syntax error: {e}")]

    findings: list[Finding] = []
    v = _Visitor(src_lines)
    v.visit(tree)
    findings.extend(v.findings)
    findings.extend(_scan_status_check_pattern(tree, src_lines))
    findings.extend(_scan_url_format(tree, src_lines))
    findings.extend(_scan_split_csv(tree, src_lines))
    findings.sort(key=lambda f: (f.line, f.code))
    return findings
