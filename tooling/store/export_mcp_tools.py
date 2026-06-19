"""Generate store/MCP_TOOLS.md from mcp_server.py via AST.

Run: python python/store/export_mcp_tools.py

Walks every `@mcp.tool()`-decorated function and emits its name, signature,
docstring, and section grouping (preserved from the `# ---` banners that
already organize mcp_server.py).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "tooling" / "mcp_server.py"
OUT = REPO_ROOT / "store" / "MCP_TOOLS.md"


def _is_mcp_tool(decorators: list[ast.expr]) -> bool:
    for d in decorators:
        # @mcp.tool() — Call(Attribute(Name('mcp'), 'tool'))
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name)
                and d.func.value.id == "mcp" and d.func.attr == "tool"):
            return True
    return False


def _format_arg(a: ast.arg, default: ast.expr | None) -> str:
    s = a.arg
    if a.annotation is not None:
        s += f": {ast.unparse(a.annotation)}"
    if default is not None:
        s += f" = {ast.unparse(default)}"
    return s


def _signature(fn: ast.FunctionDef) -> str:
    args = fn.args
    posonly = list(args.posonlyargs)
    pos = list(args.args)
    kwonly = list(args.kwonlyargs)

    defaults = list(args.defaults)  # rightmost positional defaults
    n_pos = len(posonly) + len(pos)
    pos_defaults: list[ast.expr | None] = [None] * (n_pos - len(defaults)) + defaults
    kw_defaults = list(args.kw_defaults)

    parts: list[str] = []
    for i, a in enumerate(posonly):
        parts.append(_format_arg(a, pos_defaults[i]))
    if posonly:
        parts.append("/")
    for j, a in enumerate(pos):
        parts.append(_format_arg(a, pos_defaults[len(posonly) + j]))
    if kwonly:
        parts.append("*")
        for k, a in enumerate(kwonly):
            parts.append(_format_arg(a, kw_defaults[k]))

    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns is not None else ""
    return f"{fn.name}({', '.join(parts)}){ret}"


def _section_for(line: int, banners: list[tuple[int, str]]) -> str:
    """Find the most recent `# ---` banner above `line`."""
    current = "Misc"
    for ln, label in banners:
        if ln > line:
            break
        current = label
    return current


def _extract_banners(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, label), ...] for the section banners in mcp_server.py.

    Banner pattern is two `# ---...` lines bracketing a `# Label` line.
    """
    out: list[tuple[int, str]] = []
    lines = source.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("# --") and i + 2 < len(lines):
            mid = lines[i + 1]
            if mid.startswith("# ") and not mid.startswith("# --"):
                label = mid[2:].strip()
                out.append((i + 1, label))
    return out


# Hand-curated mapping of tool name → category. Keeps the doc structured
# without depending on file ordering or comment-banner heuristics.
CATEGORIES: dict[str, str] = {
    # Reference store — read-only lookups
    "find_connector": "Reference / lookup",
    "find_operation": "Reference / lookup",
    "get_op_schema": "Reference / lookup",
    "get_connector_source": "Reference / lookup",
    "get_step_type": "Reference / lookup",
    "search_playbooks": "Reference / lookup",
    "list_picklists": "Reference / lookup",
    "get_picklist": "Reference / lookup",
    "picklist_for_field": "Reference / lookup",
    "resolve_picklist_value": "Reference / lookup",
    "list_tags": "Reference / lookup",
    # Jinja
    "find_jinja_filter": "Jinja",
    "find_jinja_pattern": "Jinja",
    "get_filter_examples": "Jinja",
    "render_jinja": "Jinja",
    # Compiler
    "validate_yaml": "Compiler",
    "compile_yaml": "Compiler",
    # Authoring loop (push / run / triage)
    "push_playbook": "Authoring loop",
    "run_playbook": "Authoring loop",
    "dry_run_playbook": "Authoring loop",
    "get_run_env": "Authoring loop",
    "list_recent_failed_runs": "Authoring loop",
    "list_playbook_runs": "Authoring loop",
    # Live FSR — connector execution + health
    "run_op": "Live FSR",
    "list_configured_connectors": "Live FSR",
    "healthcheck_connector": "Live FSR",
}
SECTION_ORDER = ["Reference / lookup", "Jinja", "Compiler",
                 "Authoring loop", "Live FSR", "Misc"]


def main() -> None:
    src = SRC.read_text()
    tree = ast.parse(src)

    tools: list[tuple[str, str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and _is_mcp_tool(node.decorator_list):
            sig = _signature(node)
            doc = ast.get_docstring(node) or ""
            tools.append((node.name, sig, doc))

    grouped: dict[str, list[tuple[str, str, str]]] = {s: [] for s in SECTION_ORDER}
    for name, sig, doc in tools:
        grouped.setdefault(CATEGORIES.get(name, "Misc"), []).append((name, sig, doc))
    for items in grouped.values():
        items.sort(key=lambda t: t[0])

    lines: list[str] = []
    lines.append("# MCP Tools — fsrpb agent surface\n")
    lines.append("Auto-generated from `python/mcp_server.py` by "
                 "`python/store/export_mcp_tools.py`. **Do not hand-edit.**\n")
    n_groups = sum(1 for s in SECTION_ORDER if grouped.get(s))
    lines.append(f"**{len(tools)} tools** across **{n_groups} categories**.\n")

    lines.append("## Index\n")
    for section in SECTION_ORDER:
        items = grouped.get(section) or []
        if not items:
            continue
        names = ", ".join(f"[`{n}`](#{n.replace('_','-')})" for n, _, _ in items)
        lines.append(f"- **{section}** — {names}")
    lines.append("\n---\n")

    for section in SECTION_ORDER:
        items = grouped.get(section) or []
        if not items:
            continue
        lines.append(f"## {section}\n")
        for name, sig, doc in items:
            lines.append(f"### `{name}`\n")
            lines.append("```python")
            lines.append(sig)
            lines.append("```\n")
            if doc:
                lines.append(doc)
                lines.append("")
        lines.append("---\n")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(tools)} tools, {n_groups} categories)")


if __name__ == "__main__":
    main()
