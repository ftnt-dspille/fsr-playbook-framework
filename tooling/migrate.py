"""Migrate playbook YAMLs to the current friendly authoring surface.

Text-based (preserves comments + formatting). Idempotent: running twice
produces no changes the second time. Point at a file or directory:

    fsrpb migrate examples/
    fsrpb migrate examples/demo_alert_on_create.yaml --dry-run

Transforms (applied in order, all are safe on already-migrated files):

1.  ``type: insert_record`` → ``type: create_record``
    The legacy alias was removed; it now hard-errors.

2.  ``arguments:`` wrapper removed — children hoisted to step level.
    Phase G dropped the ``arguments:`` wrapper on every step type.

3.  ``collection:`` on ``update_record`` → ``record:``
    ``collection:`` on update was the record IRI but collided with
    create_record's module-IRI ``collection`` (the #1 record-CRUD footgun).

4.  ``resource:`` on ``create_record``/``update_record`` → ``fields:``
    ``fields:`` is the friendly alias; ``resource:`` was an FSR API term.

5.  ``type: CyopsUtilices`` → ``type: utilities`` (if present).
    The editor's raw canonical is never the friendly surface.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# Step types that use `resource:` as the record-payload wire key.
_RECORD_CRUD_TYPES = frozenset({"create_record", "update_record"})


def _step_type_after(lines: list[str], idx: int) -> str | None:
    """Find the `type:` value for the step whose list-item starts at idx."""
    for i in range(idx, min(idx + 10, len(lines))):
        m = re.match(r"^\s*type:\s*(\S+)", lines[i])
        if m:
            return m.group(1).rstrip(":")
    return None


def _strip_arguments_wrapper(lines: list[str]) -> list[str]:
    """Remove the ``arguments:`` wrapper: dedent all children to step level.

    Handles 2-space and 4-space indentation. Blank lines and comments
    inside the block are preserved.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("arguments:") and not stripped.startswith("#"):
            base_indent = len(line) - len(stripped)
            j = i + 1
            dedent: int | None = None
            while j < len(lines):
                nxt = lines[j]
                nxt_stripped = nxt.lstrip()
                if nxt_stripped == "" or nxt_stripped.startswith("#"):
                    out.append(nxt)
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt_stripped)
                if nxt_indent <= base_indent:
                    break
                if dedent is None:
                    dedent = nxt_indent - base_indent
                    if dedent not in (2, 4):
                        dedent = 2
                dedented = nxt[dedent:] if len(nxt) >= dedent else nxt.lstrip()
                out.append(dedented)
                j += 1
            i = j
        else:
            out.append(line)
            i += 1
    return out


def _transform_text(text: str) -> tuple[str, list[str]]:
    """Apply all transforms; return (new_text, list_of_change_descriptions)."""
    changes: list[str] = []
    lines = text.splitlines(keepends=True)

    # 1. insert_record → create_record
    new_lines = []
    for line in lines:
        nl = re.sub(r"(\s*type:\s*)insert_record", r"\1create_record", line)
        if nl != line:
            changes.append("insert_record → create_record")
        new_lines.append(nl)
    lines = new_lines

    # 5. CyopsUtilices → utilities (raw canonical → friendly)
    new_lines = []
    for line in lines:
        nl = re.sub(r"(\s*type:\s*)CyopsUtilices", r"\1utilities", line)
        if nl != line:
            changes.append("CyopsUtilices → utilities")
        new_lines.append(nl)
    lines = new_lines

    # 2. Remove arguments: wrapper
    before = len(lines)
    lines = _strip_arguments_wrapper(lines)
    if len(lines) != before or any("arguments:" not in l for l in lines):
        # Heuristic: if any arguments: line was removed, report it
        if any("arguments:" in l and not l.lstrip().startswith("#")
               for l in lines):
            pass  # some arguments: remain (e.g. in a different context)
        else:
            if before != len(lines) or text.count("arguments:") != "".join(lines).count("arguments:"):
                changes.append("arguments: wrapper removed")

    # 3+4. Context-aware key renames on record-CRUD steps
    out: list[str] = []
    current_type: str | None = None
    for i, line in enumerate(lines):
        # Detect step start: a list item with type: or name:
        if re.match(r"^\s*-\s+(type|name):", line):
            current_type = _step_type_after(lines, i)

        if current_type in _RECORD_CRUD_TYPES:
            if current_type == "update_record":
                nl = re.sub(r"^(\s+)collection:", r"\1record:", line)
                if nl != line:
                    changes.append("collection: → record: (update_record)")
                line = nl
            nl = re.sub(r"^(\s+)resource:", r"\1fields:", line)
            if nl != line:
                changes.append("resource: → fields:")
            line = nl

        out.append(line)
    lines = out

    return "".join(lines), changes


def migrate_file(path: Path, dry_run: bool = False) -> list[str]:
    """Migrate a single file. Returns list of changes (empty if no-op)."""
    original = path.read_text()
    transformed, changes = _transform_text(original)
    if transformed != original and not dry_run:
        path.write_text(transformed)
    return changes if transformed != original else []


def migrate_path(target: str, dry_run: bool = False) -> int:
    """Migrate a file or directory. Returns count of changed files."""
    path = Path(target)
    if path.is_file():
        changes = migrate_file(path, dry_run)
        label = "would change" if dry_run else "changed"
        if changes:
            unique = sorted(set(changes))
            print(f"  {label}: {path}")
            for c in unique:
                print(f"    - {c}")
            return 1
        print(f"  (already current) {path}")
        return 0

    yaml_files = sorted(path.rglob("*.yaml"))
    changed = 0
    for yp in yaml_files:
        if "__pycache__" in yp.parts or ".venv" in yp.parts:
            continue
        c = migrate_file(yp, dry_run)
        if c:
            unique = sorted(set(c))
            print(f"  {'would change' if dry_run else 'changed'}: {yp}")
            for ch in unique:
                print(f"    - {ch}")
            changed += 1
    return changed


def cmd_migrate(args: argparse.Namespace) -> int:
    """`fsrpb migrate` — rewrite playbook YAMLs to the current friendly surface."""
    count = migrate_path(args.path, dry_run=args.dry_run)
    verb = "would change" if args.dry_run else "changed"
    print(f"\n{verb} {count} file(s)")
    return 0


def add_parser(sub) -> None:
    sp = sub.add_parser(
        "migrate",
        help="rewrite playbook YAMLs to the current friendly authoring surface",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("path", help="file or directory to migrate")
    sp.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing")
    sp.set_defaults(func=cmd_migrate)
