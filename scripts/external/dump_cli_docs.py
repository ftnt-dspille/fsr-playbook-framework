#!/usr/bin/env python3
"""Dump the fsrpb argparse tree to docs/CLI.md.

Walks every (sub)parser in `cli.build_parser()` and emits a Markdown
reference. Zero new dependencies — works off the parser objects we
already construct at runtime, so the doc never drifts from what the CLI
actually accepts.

Run manually:

    python3 scripts/external/dump_cli_docs.py

Or from a pre-commit hook so a stale CLI.md fails CI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "python"))

from cli import build_parser  # noqa: E402

OUT = REPO / "docs" / "CLI.md"


def _action_table(actions: Iterable[argparse.Action]) -> list[str]:
    """Format positional + optional arguments as a markdown table."""
    rows: list[str] = []
    for a in actions:
        if isinstance(a, argparse._SubParsersAction):
            continue
        if isinstance(a, argparse._HelpAction):
            continue
        # Skip the synthetic --version action if any.
        if isinstance(a, argparse._VersionAction):
            continue
        if a.option_strings:
            name = ", ".join(f"`{s}`" for s in a.option_strings)
        else:
            name = f"`{a.dest}`"
        meta = []
        if a.choices:
            meta.append("choices: " + ", ".join(f"`{c}`" for c in a.choices))
        if a.default not in (None, argparse.SUPPRESS, False) and not a.option_strings:
            meta.append(f"default: `{a.default}`")
        elif a.default not in (None, argparse.SUPPRESS, False):
            meta.append(f"default: `{a.default}`")
        if a.required and a.option_strings:
            meta.append("required")
        line = f"| {name} | {(a.help or '').replace('|', '\\|')} | {' · '.join(meta) or '—'} |"
        rows.append(line)
    if not rows:
        return []
    return [
        "| arg | help | meta |",
        "| --- | --- | --- |",
        *rows,
    ]


def _walk(parser: argparse.ArgumentParser, path: list[str], depth: int,
          out: list[str]) -> None:
    title = " ".join(path) if path else "fsrpb"
    out.append(f"{'#' * (depth + 2)} `{title}`")
    out.append("")
    if parser.description:
        out.append(parser.description.strip())
        out.append("")
    if parser.epilog:
        out.append("> " + parser.epilog.strip().replace("\n", "\n> "))
        out.append("")

    rows = _action_table(parser._actions)
    if rows:
        out.extend(rows)
        out.append("")

    # Recurse into subparsers
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for sub_name, sub in sorted(action.choices.items()):
            _walk(sub, path + [sub_name], depth + 1, out)


def _toc(parser: argparse.ArgumentParser) -> list[str]:
    lines = ["## Commands", ""]
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, sub in sorted(action.choices.items()):
            help_text = (action.choices[name].description or "").strip().splitlines()
            lead = help_text[0] if help_text else ""
            anchor = f"#fsrpb-{name}".replace("_", "-")
            lines.append(f"- [`fsrpb {name}`]({anchor}) — {lead}")
            # Second-level subcommands inline (one indent)
            for inner in sub._actions:
                if not isinstance(inner, argparse._SubParsersAction):
                    continue
                for sub_name in sorted(inner.choices):
                    a2 = f"#fsrpb-{name}-{sub_name}".replace("_", "-")
                    lines.append(f"  - [`fsrpb {name} {sub_name}`]({a2})")
    lines.append("")
    return lines


def main() -> int:
    parser = build_parser()
    out: list[str] = []
    out.append("# fsrpb CLI reference")
    out.append("")
    out.append(
        "_Auto-generated from `cli.build_parser()` — re-run "
        "`python3 scripts/external/dump_cli_docs.py` after touching the CLI."
    )
    out.append("")
    if parser.description:
        out.append(parser.description.strip())
        out.append("")
    out.extend(_toc(parser))
    _walk(parser, [], 0, out)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out).rstrip() + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}  ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
