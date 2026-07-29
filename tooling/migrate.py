"""Migrate playbook YAMLs to the current friendly authoring surface.

Text-based (preserves comments + formatting). Idempotent: running twice
produces no changes the second time. Point at a file or directory:

    fsrpb migrate examples/
    fsrpb migrate examples/demo_alert_on_create.yaml --dry-run

Transforms (applied in order, all are safe on already-migrated files):

1.  ``type: insert_record`` → ``type: create_record``
    The legacy alias was removed; it now hard-errors.

2.  ``arguments:`` wrapper removed -- children hoisted to step level.
    Phase G dropped the ``arguments:`` wrapper on every step type.

3.  ``collection:`` on ``update_record`` → ``record:``
    ``collection:`` on update was the record IRI but collided with
    create_record's module-IRI ``collection`` (the #1 record-CRUD footgun).

3b. ``collection: /api/3/<m>`` on ``create_record`` → ``module: <m>``
    ``collection: /api/3/upsert/<m>`` → ``module: <m>`` + ``is_upsert: true``.
    Non-``/api/3/`` collections pass through (canonical escape hatch).

4.  ``resource:`` on ``create_record``/``update_record`` → ``fields:``
    ``fields:`` is the friendly alias; ``resource:`` was an FSR API term.

5.  ``type: CyopsUtilices`` → ``type: utilities`` (if present).
    The editor's raw canonical is never the friendly surface.

6.  Wire-internal default fields stripped (``step_variables: []``,
    ``fieldOperation: []``, ``tagsOperation: Overwrite``, ``__recommend: []``,
    ``_showJson: false``, default ``owner_detail``/``email_notification``).

7.  ``query:`` on ``find_record`` → ``filters:``/``limit:``/``logic:``.
    Default ``logic: AND`` / ``limit: 30`` and ``__selectFields`` are skipped.

8.  Wire ``owner_detail:`` on ``manual_input`` → friendly ``assign_to:``
    (``assignedToTeam`` → ``team:``, ``assignedToPerson`` → ``person:``).
    Wire ``email_notification:`` → friendly ``email:``
    (``smtpParameters[0]`` → ``recipients``/``subject``/``body``/``from``).
    Defaults (``isAssigned: false`` / ``enabled: false``) already stripped
    by step 6; only real assignment/email data is converted here.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

# Step types that use `resource:` as the record-payload wire key.
_RECORD_CRUD_TYPES = frozenset({"create_record", "update_record"})


def _step_type_after(lines: list[str], idx: int) -> str | None:
    """Find the `type:` value for the step whose list-item starts at idx.

    Handles both ``- type: x`` (type on the list-item line) and a separate
    ``type: x`` line following the list-item dash.
    """
    for i in range(idx, min(idx + 10, len(lines))):
        # `- type: x` -- type: on the list-item line itself
        m = re.match(r"^\s*-\s+type:\s*(\S+)", lines[i])
        if m:
            return m.group(1).rstrip(":")
        # `    type: x` -- type: on a subsequent line
        m = re.match(r"^\s+type:\s*(\S+)", lines[i])
        if m:
            return m.group(1).rstrip(":")
    return None


def _strip_arguments_wrapper(lines: list[str]) -> list[str]:
    """Remove the ``arguments:`` wrapper: dedent all children to step level.

    Handles 2-space and 4-space indentation. Blank lines and comments
    inside the block are preserved. Content of literal block scalars
    (``key: |``) and folded scalars (``key: >``) is NOT dedented -- it is
    literal text where indentation is semantically load-bearing.
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
            in_block_scalar = False
            scalar_key_indent: int = 0
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
                # Detect block-scalar start: `key: |` or `key: >`
                if re.match(r"^\s*\S.*:\s*[|>]\s*$", nxt):
                    in_block_scalar = True
                    scalar_key_indent = nxt_indent
                    dedented = nxt[dedent:] if len(nxt) >= dedent else nxt.lstrip()
                    out.append(dedented)
                    j += 1
                    continue
                # If inside a block scalar, keep the line as-is (don't dedent
                # literal content -- its indentation is semantically load-bearing).
                # A block scalar ends when a line at or below the key's
                # original indent appears -- that's a sibling key, not content.
                if in_block_scalar:
                    if nxt_indent <= scalar_key_indent:
                        in_block_scalar = False
                    else:
                        out.append(nxt)  # literal content -- no dedent
                        j += 1
                        continue
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
    before_args = "".join(lines)
    lines = _strip_arguments_wrapper(lines)
    after_args = "".join(lines)
    if after_args != before_args:
        changes.append("arguments: wrapper removed")

    # 2b. After hoisting, drop keys that were valid under arguments: but
    # collide with step-level IR keys. The compiler re-derives these:
    #   - `name:` (connector display label -- re-derived from the catalog)
    #   - `type: InputBased`/`DecisionBased` (MI mode -- inferred from
    #     `inputs:` presence/absence per Phase G)
    # The step-level `name:`/`type:` appear right after the `- type:` list
    # item; a `name:`/`type:` that appears LATER (after other args like
    # `connector:`, `operation:`, `module:`, etc.) is the hoisted duplicate.
    out2: list[str] = []
    current_type_val: str | None = None
    seen_step_type = False
    seen_other_key = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*-\s+(type|name):", line):
            # New step starts -- reset tracking
            seen_step_type = False
            seen_other_key = False
            current_type_val = _step_type_after(lines, i)
            # If the list item has `name:` on the same line, mark it
            if re.match(r"^\s*-\s+name:", line):
                pass  # step name on the list-item line
            if re.match(r"^\s*-\s+type:", line):
                seen_step_type = True
            out2.append(line)
            continue

        stripped = line.lstrip()
        # Track what we've seen in this step
        if re.match(r"^\s+name:", line) and not seen_other_key:
            out2.append(line)
            continue
        if re.match(r"^\s+type:", line) and not seen_other_key:
            seen_step_type = True
            out2.append(line)
            continue

        # Any non-name/type key means subsequent name:/type: are duplicates
        if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            if not re.match(r"^\s+(name|type):", line):
                seen_other_key = True

        # Drop duplicate `name:` that appears after other keys
        if re.match(r"^\s+name:\s+", line) and seen_other_key:
            changes.append("dropped duplicate name: (connector label)")
            continue
        # Drop `type: InputBased`/`DecisionBased` on manual_input after other keys
        if (current_type_val == "manual_input" and seen_step_type
                and seen_other_key
                and re.match(r"^\s+type:\s*(InputBased|DecisionBased)", line)):
            changes.append("dropped type: (inferred from inputs:)")
            continue

        out2.append(line)
    lines = out2

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
            elif current_type == "create_record":
                # collection: /api/3/<m> → module: <m>
                # collection: /api/3/upsert/<m> → module: <m> + is_upsert: true
                # non-/api/3/ collection passes through (canonical escape hatch)
                m = re.match(
                    r'^(\s+)collection:\s*["\']?/api/3/upsert/([^"\'\s]+)["\']?\s*$',
                    line)
                if m:
                    line = (f"{m.group(1)}module: {m.group(2)}\n"
                            f"{m.group(1)}is_upsert: true\n")
                    changes.append("collection: → module: (create_record, upsert)")
                else:
                    m = re.match(
                        r'^(\s+)collection:\s*["\']?/api/3/([^"\'\s]+)["\']?\s*$',
                        line)
                    if m:
                        line = f"{m.group(1)}module: {m.group(2)}\n"
                        changes.append("collection: → module: (create_record)")
            nl = re.sub(r"^(\s+)resource:", r"\1fields:", line)
            if nl != line:
                changes.append("resource: → fields:")
            line = nl

        out.append(line)
    lines = out

    # 6. C2: strip wire-internal fields (empty/default values the compiler
    # re-creates via setdefault). These are noise in hand-authored YAML.
    c2_patterns = [
        (r"^\s*step_variables:\s*\[\]\s*\n", "step_variables: []"),
        (r"^\s*fieldOperation:\s*\[\]\s*\n", "fieldOperation: []"),
        (r"^\s*tagsOperation:\s*Overwrite\s*\n", "tagsOperation: Overwrite"),
        (r"^\s*__recommend:\s*\[\]\s*\n", "__recommend: []"),
        (r"^\s*_showJson:\s*false\s*\n", "_showJson: false"),
        # D2: strip default manual_input owner_detail/email_notification blocks
        (r"^\s*owner_detail:\s*\n\s*isAssigned:\s*false\s*\n",
         "owner_detail: {isAssigned: false} (default)"),
        (r"^\s*email_notification:\s*\n\s*enabled:\s*false\s*\n\s*smtpParameters:\s*\[\]\s*\n",
         "email_notification: {enabled: false, smtpParameters: []} (default)"),
    ]
    text = "".join(lines)
    for pat, label in c2_patterns:
        new_text = re.sub(pat, "", text, flags=re.MULTILINE)
        if new_text != text:
            changes.append(f"stripped {label} (wire-internal)")
            text = new_text
    lines = text.splitlines(keepends=True)

    # 7. B2: find_record query: → filters:/limit:/logic:
    # Unpack the query: envelope by removing the query: line and dedenting
    # its children to the step level. Skip default logic: AND / limit: 30.
    out: list[str] = []
    current_type = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*-\s+(type|name):", line):
            current_type = _step_type_after(lines, i)

        if current_type == "find_record" and re.match(r"^(\s+)query:", line):
            query_indent = len(re.match(r"^(\s+)", line).group(1))
            changes.append("B2: query: → filters: (find_record)")
            i += 1
            # Calculate dedent from the first non-blank child line
            dedent: int | None = None
            while i < len(lines):
                inner = lines[i]
                stripped = inner.rstrip("\n\r")
                if not stripped.strip():
                    out.append(inner)
                    i += 1
                    continue
                inner_indent = len(inner) - len(inner.lstrip())
                if inner_indent <= query_indent:
                    break  # exited query: block
                if dedent is None:
                    dedent = inner_indent - query_indent
                # Skip default logic: AND and limit: 30
                if (re.match(r"^\s*logic:\s*AND\s*$", stripped)
                        and inner_indent - query_indent <= 2):
                    i += 1
                    continue
                if (re.match(r"^\s*limit:\s*30\s*$", stripped)
                        and inner_indent - query_indent <= 2):
                    i += 1
                    continue
                # Skip __selectFields -- wire-internal; the normalizer strips
                # it from query: when checkboxFields is false (the default).
                if (re.match(r"^\s*__selectFields:", stripped)
                        and inner_indent - query_indent <= 2):
                    i += 1
                    continue
                # Skip sort: [] (empty sort list -- not a valid find_record
                # step-level key; the query DSL sort is handled by the
                # compiler's Query object, not by a step-level sort: key)
                if (re.match(r"^\s*sort:\s*\[\]\s*$", stripped)
                        and inner_indent - query_indent <= 2):
                    i += 1
                    continue
                # Dedent the line by the fixed offset
                d = dedent if dedent > 0 else 0
                out.append(inner[d:] if d > 0 else inner)
                i += 1
            continue
        out.append(line)
        i += 1
    lines = out

    # 8. D1: wire owner_detail:/email_notification: → friendly assign_to:/email:
    # on manual_input steps. The C2 patterns above already stripped the
    # default (isAssigned: false / enabled: false) envelopes; what remains
    # is real assignment/email data that should use the friendly keys.
    lines = _transform_manual_input_wire_blocks(lines, changes)

    return "".join(lines), changes


def _transform_manual_input_wire_blocks(
    lines: list[str], changes: list[str],
) -> list[str]:
    """Convert wire ``owner_detail:``/``email_notification:`` blocks to
    friendly ``assign_to:``/``email:`` on manual_input steps.

    Mirrors the decompiler's reverse (``_decompile_step`` D1 section).
    Uses ``yaml.safe_load`` on the extracted block to robustly parse the
    nested structure (``assignedToTeam`` can be a list of dicts with
    ``iri``/``teamname``, a list of strings, or a bare string).
    Comments inside the block are consumed by the YAML parser -- they
    describe the wire shape being replaced, so losing them is correct.
    """
    out: list[str] = []
    current_type: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*-\s+(type|name):", line):
            current_type = _step_type_after(lines, i)

        if current_type == "manual_input":
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # owner_detail: → assign_to:
            if re.match(r"^\s*owner_detail:\s*$", line):
                block, end = _extract_block(lines, i, indent)
                replacement = _owner_detail_to_assign_to(block, indent, changes)
                if replacement is not None:
                    out.extend(replacement)
                    i = end
                    continue

            # email_notification: → email:
            if re.match(r"^\s*email_notification:\s*$", line):
                block, end = _extract_block(lines, i, indent)
                replacement = _email_notification_to_email(block, indent, changes)
                if replacement is not None:
                    out.extend(replacement)
                    i = end
                    continue

        out.append(line)
        i += 1
    return out


def _extract_block(
    lines: list[str], start: int, block_indent: int,
) -> tuple[list[str], int]:
    """Extract the indented block starting at ``start``.

    Returns (block_lines, next_index_after_block).
    """
    block = [lines[start]]
    j = start + 1
    while j < len(lines):
        nxt = lines[j]
        nxt_stripped = nxt.lstrip()
        if nxt_stripped == "" or nxt_stripped.startswith("#"):
            block.append(nxt)
            j += 1
            continue
        nxt_indent = len(nxt) - len(nxt_stripped)
        if nxt_indent <= block_indent:
            break
        block.append(nxt)
        j += 1
    return block, j


def _owner_detail_to_assign_to(
    block: list[str], indent: int, changes: list[str],
) -> list[str] | None:
    """Convert a wire ``owner_detail:`` block to friendly ``assign_to:``."""
    import yaml as _yaml

    dedented = _dedent_block(block)
    try:
        data = _yaml.safe_load(dedented)
    except Exception:
        return None
    od = data.get("owner_detail") if isinstance(data, dict) else None
    if not isinstance(od, dict):
        return None

    is_default = (
        od.get("isAssigned") is False
        and not any(
            od.get(k) for k in
            ("assignedToPerson", "assignedToTeam", "assignedToRecord")
        )
    )
    if is_default:
        return None  # C2 already stripped it

    assign_out: dict[str, Any] = {}
    if od.get("assignedToPerson"):
        assign_out["person"] = od["assignedToPerson"]
    team = od.get("assignedToTeam")
    if isinstance(team, list) and team:
        first = team[0]
        if isinstance(first, dict):
            assign_out["team"] = first.get("teamname", first.get("iri", ""))
        else:
            assign_out["team"] = first
    elif isinstance(team, str) and team:
        assign_out["team"] = team
    if od.get("assignedToRecord"):
        assign_out["record_field"] = True
    if not assign_out:
        return None

    changes.append("owner_detail: → assign_to: (manual_input)")
    friendly = _yaml.dump(
        {"assign_to": assign_out},
        default_flow_style=False, indent=2, sort_keys=False,
    )
    return _indent_block(friendly, indent)


def _email_notification_to_email(
    block: list[str], indent: int, changes: list[str],
) -> list[str] | None:
    """Convert a wire ``email_notification:`` block to friendly ``email:``."""
    import yaml as _yaml

    dedented = _dedent_block(block)
    try:
        data = _yaml.safe_load(dedented)
    except Exception:
        return None
    en = data.get("email_notification") if isinstance(data, dict) else None
    if not isinstance(en, dict):
        return None

    is_default = (
        en.get("enabled") is False
        and not en.get("smtpParameters")
    )
    if is_default:
        return None  # C2 already stripped it

    email_out: dict[str, Any] = {}
    if "enabled" in en:
        email_out["enabled"] = en["enabled"]
    params = en.get("smtpParameters") or []
    if params and isinstance(params[0], dict):
        p = params[0]
        if p.get("to") is not None:
            email_out["recipients"] = p["to"]
        for k in ("subject", "body", "from"):
            if p.get(k) is not None:
                email_out[k] = p[k]
    if not email_out:
        return None

    changes.append("email_notification: → email: (manual_input)")
    friendly = _yaml.dump(
        {"email": email_out},
        default_flow_style=False, indent=2, sort_keys=False,
    )
    return _indent_block(friendly, indent)


def _dedent_block(block: list[str]) -> str:
    """Dedent a block to column 0 for YAML parsing."""
    min_indent = min(
        (len(l) - len(l.lstrip())) for l in block if l.strip()
    )
    return "\n".join(
        l[min_indent:] if l.strip() else l for l in block
    )


def _indent_block(text: str, indent: int) -> list[str]:
    """Re-indent a YAML string to the given indent level."""
    prefix = " " * indent
    return [
        prefix + line if line.strip() else line
        for line in text.splitlines(keepends=True)
    ]


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
    """`fsrpb migrate` -- rewrite playbook YAMLs to the current friendly surface."""
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
