#!/usr/bin/env python3
"""Sweep YAML playbooks to use friendly forms for B2/C2/D2.

B2: find_record query: → filters:/limit:/logic:
C2: strip wire-internal fields (fieldOperation: [], tagsOperation: Overwrite,
    __recommend: [], _showJson: false, step_variables: [])
D2: manual_input email_notification: → email:, owner_detail: → assign_to:

Uses ruamel.yaml to preserve comments and formatting.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096

RECORD_CRUD_TYPES = {"create_record", "update_record", "delete_record", "find_record"}


def _strip_wire_internal(step_args: dict, step_type: str) -> bool:
    """C2: strip wire-internal fields from step args. Returns True if changed."""
    changed = False
    for key in ("__recommend", "_showJson"):
        if key in step_args:
            val = step_args[key]
            if val == [] or val is False:
                del step_args[key]
                changed = True
    if "fieldOperation" in step_args and step_args["fieldOperation"] == []:
        del step_args["fieldOperation"]
        changed = True
    if "tagsOperation" in step_args and step_args["tagsOperation"] == "Overwrite":
        del step_args["tagsOperation"]
        changed = True
    if "step_variables" in step_args and step_args["step_variables"] == []:
        del step_args["step_variables"]
        changed = True
    return changed


def _find_record_query_to_filters(step_args: dict) -> bool:
    """B2: unpack query: envelope into filters:/limit:/logic:. Returns True if changed."""
    if "query" not in step_args:
        return False
    q = step_args["query"]
    if not isinstance(q, dict):
        return False
    changed = False
    filters = q.get("filters")
    if isinstance(filters, list) and filters:
        step_args["filters"] = filters
        changed = True
    limit = q.get("limit")
    if limit is not None and limit != 30:
        step_args["limit"] = limit
        changed = True
    logic = q.get("logic")
    if logic is not None and logic != "AND":
        step_args["logic"] = logic
        changed = True
    if changed or not filters:
        del step_args["query"]
        if not filters:
            step_args["query"] = q
        changed = True
    return changed


def _manual_input_friendly(step_args: dict) -> bool:
    """D2: email_notification: → email:, owner_detail: → assign_to:. Returns True if changed."""
    changed = False
    en = step_args.pop("email_notification", None)
    if isinstance(en, dict):
        is_default = en.get("enabled") is False and not en.get("smtpParameters")
        if not is_default:
            email_out = {}
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
            step_args["email"] = email_out
            changed = True
    od = step_args.pop("owner_detail", None)
    if isinstance(od, dict):
        is_default = od.get("isAssigned") is False and not any(
            od.get(k) for k in ("assignedToPerson", "assignedToTeam", "assignedToRecord")
        )
        if not is_default:
            assign_out = {}
            if od.get("assignedToPerson"):
                assign_out["person"] = od["assignedToPerson"]
            team = od.get("assignedToTeam")
            if isinstance(team, list) and team:
                assign_out["team"] = team[0]
            elif isinstance(team, str) and team:
                assign_out["team"] = team
            if od.get("assignedToRecord"):
                assign_out["record_field"] = True
            if assign_out:
                step_args["assign_to"] = assign_out
                changed = True
    return changed


def sweep_file(path: Path) -> list[str]:
    """Sweep a single YAML file. Returns list of change descriptions."""
    original = path.read_text()
    data = yaml.load(original)
    if data is None or not isinstance(data, dict):
        return []
    changes: list[str] = []
    playbooks = data.get("playbooks")
    if not isinstance(playbooks, list):
        return []
    for pb in playbooks:
        if not isinstance(pb, dict):
            continue
        steps = pb.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            stype = step.get("type", "")
            args = step
            if stype == "find_record":
                if _find_record_query_to_filters(args):
                    changes.append("B2: query: → filters:")
            if stype == "manual_input":
                if _manual_input_friendly(args):
                    changes.append("D2: email_notification/owner_detail → email/assign_to")
            if _strip_wire_internal(args, stype):
                changes.append("C2: stripped wire-internal fields")
    if changes:
        import io
        buf = io.StringIO()
        yaml.dump(data, buf)
        new_text = buf.getvalue()
        if new_text != original:
            path.write_text(new_text)
            return changes
    return []


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file-or-dir> [--dry-run]")
        sys.exit(1)
    target = Path(sys.argv[1])
    dry_run = "--dry-run" in sys.argv
    files = []
    if target.is_dir():
        files = sorted(target.rglob("*.yaml"))
    elif target.is_file():
        files = [target]
    else:
        print(f"Error: {target} is not a file or directory")
        sys.exit(1)
    total_changes = 0
    for f in files:
        changes = sweep_file(f)
        if changes:
            total_changes += len(changes)
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"{prefix}{f}")
            for c in changes:
                print(f"  {c}")
    print(f"\n{total_changes} changes across {len(files)} files")


if __name__ == "__main__":
    main()
