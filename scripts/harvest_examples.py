#!/usr/bin/env python3
"""Harvest example playbooks and step fragments into the recipes table.

Reads from data/example_sources.txt manifest, loads and compiles each YAML,
extracts metadata, deduplicates by content hash, and inserts into both the
dev and packaged DBs.

Usage:
    python scripts/harvest_examples.py [--db PATH] [--manifest PATH]
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml


# Find repo root
REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "data" / "example_sources.txt"
DEV_DB = REPO_ROOT / "data" / "fsr_reference.db"
PACKAGED_DB = REPO_ROOT / "fsr_playbooks" / "_data" / "fsr_reference.db"

def _content_hash(text: str) -> str:
    """Compute SHA-256 content hash."""
    return hashlib.sha256(text.encode()).hexdigest()


def _validate_db_structure(db_path: Path) -> tuple[bool, str]:
    """Validate that DB has the expected core tables.

    Returns (is_valid, error_message).
    Must have at least: step_types, picklists, operations, recipes.
    Refuse to run if DB is missing these tables - harvest must only
    add/replace rows in recipes of an existing DB, never initialize it.
    """
    required_tables = {"step_types", "picklists", "operations", "recipes"}

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            missing = required_tables - existing_tables
            if missing:
                return False, (
                    f"DB {db_path} missing required tables: {missing}. "
                    f"Harvest must only add rows to an existing DB, not initialize it. "
                    f"Restore from main or use a reference DB with all core tables."
                )

            return True, ""
    except Exception as e:
        return False, f"Failed to validate DB {db_path}: {e}"


def _has_real_credentials(text: str) -> bool:
    """Check if text contains real credential values (not placeholders).

    Rejects actual secrets but allows:
    - Variable references like `vars.api_key`, `{{ vars.password }}`
    - Placeholders like `<your-password>`, `<API_KEY>`
    - Parameter names like `api_key:` in step definitions
    """
    import re

    # Real credential values are quoted strings/values, not parameter names or placeholders
    # Look for: password: "something", api_key: "something", token: "something"
    # But NOT: password:, api_key: (parameter definitions)
    # And NOT: <your-password>, <API_KEY> (placeholders)

    # Match quoted credential values that look real
    # password: "abc123" or api_key: "key_xyz" or token: "token_abc"
    real_secret_pattern = r'(?:password|api_key|api_secret|secret|token|credential):\s*"([^"]{4,})"'

    if re.search(real_secret_pattern, text, re.IGNORECASE):
        # Check if the matched value looks like a placeholder or variable
        matches = re.findall(real_secret_pattern, text, re.IGNORECASE)
        for match in matches:
            # Skip if it looks like a placeholder or variable
            if not any(x in match.lower() for x in ['<', 'your', 'replace', 'example', '{{', 'vars.']):
                # It looks like a real credential
                return True

    return False


def _has_real_infrastructure_ips(text: str) -> bool:
    """Check if text contains real public IPs or infrastructure hostnames.

    Allows:
    - Documentation ranges: 192.0.2.x, 198.51.100.x, 203.0.113.x
    - Placeholder ranges: 1.2.3.x, 4.3.2.x
    - Public DNS resolvers (demo values): 8.8.8.8, 8.8.4.4, 1.1.1.1, 1.0.0.1, 9.9.9.9
    - Private ranges: 10.x, 172.16-31.x, 192.168.x
    - Loopback: 127.x, ::1
    - Placeholders: <IP>, <hostname>

    Rejects:
    - Real public IPs (not in documentation/placeholder/demo ranges)
    - Fortinet internal hostnames (*.fortinet.com, *.fortilab)
    """
    import re

    # Check for fortinet.com or fortilab hostnames (internal infrastructure)
    if re.search(r'\.(fortinet\.com|fortilab)\b', text, re.IGNORECASE):
        return True

    # Match public IPs
    ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    ips = re.findall(ip_pattern, text)

    # Public DNS resolvers used as demo values
    demo_ips = {'8.8.8.8', '8.8.4.4', '1.1.1.1', '1.0.0.1', '9.9.9.9'}

    for ip in ips:
        # Skip known demo/resolver IPs
        if ip in demo_ips:
            continue

        octets = ip.split('.')
        first_octet = int(octets[0])
        second_octet = int(octets[1]) if len(octets) > 1 else 0
        third_octet = int(octets[2]) if len(octets) > 2 else 0

        # Skip documentation/example ranges
        if first_octet == 192 and second_octet == 0:  # 192.0.x.x
            continue
        if first_octet == 198 and second_octet == 51:  # 198.51.x.x
            continue
        if first_octet == 203 and second_octet == 0:  # 203.0.x.x
            continue
        # Placeholder ranges
        if first_octet == 1 and second_octet == 2 and third_octet == 3:  # 1.2.3.x
            continue
        if first_octet == 4 and second_octet == 3 and third_octet == 2:  # 4.3.2.x
            continue
        if first_octet == 10:  # 10.x.x.x (private)
            continue
        if first_octet == 172 and 16 <= second_octet <= 31:  # 172.16-31.x.x (private)
            continue
        if first_octet == 192 and second_octet == 168:  # 192.168.x.x (private)
            continue
        if first_octet == 127:  # 127.x.x.x (loopback)
            continue
        if first_octet in (0, 255):  # Special ranges
            continue

        # This IP is not in a documentation, placeholder, demo, or private range - it's real
        return True

    return False


def _has_credentials_or_ips(text: str) -> bool:
    """Check if text contains real credentials or infrastructure details."""
    return _has_real_credentials(text) or _has_real_infrastructure_ips(text)


def _extract_step_types(playbook_data: dict) -> list[str]:
    """Extract all step types used in a playbook."""
    step_types: list[str] = []
    playbooks = playbook_data.get("playbooks") or []
    if not isinstance(playbooks, list):
        playbooks = [playbooks]
    for pb in playbooks:
        if not isinstance(pb, dict):
            continue
        steps = pb.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                step_type = step.get("type")
                if step_type and step_type not in step_types:
                    step_types.append(step_type)
    return step_types


def _extract_connectors(playbook_data: dict) -> list[str]:
    """Extract all connectors/operations referenced in a playbook."""
    connectors: set[str] = set()
    playbooks = playbook_data.get("playbooks") or []
    if not isinstance(playbooks, list):
        playbooks = [playbooks]
    for pb in playbooks:
        if not isinstance(pb, dict):
            continue
        steps = pb.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                if step.get("type") == "connector":
                    connector_ref = step.get("connector")
                    if connector_ref:
                        # Extract connector name from "connector_name@operation"
                        conn_name = connector_ref.split("@")[0].strip()
                        if conn_name:
                            connectors.add(conn_name)
    return sorted(connectors)


def _compile_yaml(yaml_text: str, db_path: Path) -> tuple[bool, str | dict]:
    """Compile YAML using framework compiler. Returns (ok, result)."""
    try:
        from fsr_playbooks.compiler import compile_yaml as fw_compile
        result = fw_compile(yaml_text, str(db_path))
        if isinstance(result, dict):
            return (result.get("ok") is not False), result
        return True, result
    except Exception as e:
        return False, str(e)


def _sanitize_yaml(yaml_text: str) -> str:
    """Remove or mask credentials from YAML before storing."""
    # For now, we reject files with credentials rather than masking.
    # If we need masking later, this is where to add it.
    return yaml_text


def _extract_name_and_description(playbook_data: dict) -> tuple[str, str]:
    """Extract collection name and description from playbook data."""
    collection = playbook_data.get("collection", "Untitled")
    description = playbook_data.get("description", "")
    return str(collection), str(description)


def _get_trigger_kind(playbook_data: dict) -> str:
    """Determine trigger type from playbook definition."""
    playbooks = playbook_data.get("playbooks") or []
    if not isinstance(playbooks, list):
        playbooks = [playbooks]

    for pb in playbooks:
        if not isinstance(pb, dict):
            continue
        steps = pb.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                step_type = step.get("type", "")
                if step_type.startswith("start"):
                    if "on_create" in step_type:
                        return "on_create"
                    elif "on_update" in step_type:
                        return "on_update"
                    elif "on_delete" in step_type:
                        return "on_delete"
                    elif "manual" in step_type:
                        return "manual"
                    elif "schedule" in step_type:
                        return "scheduled"
                    return "manual"
    return "manual"


def _process_playbook_file(
    file_path: Path,
    db_path: Path,
    seen_hashes: set[str],
) -> tuple[bool, str | None, dict | None]:
    """
    Process one YAML file.

    Returns: (success, skip_reason, row_data)
    - success=True, skip_reason=None: file should be inserted
    - success=False, skip_reason=msg: file should be skipped
    - skip_reason="hash_dup": already seen this content
    """
    # Skip test fixtures
    if file_path.name.endswith(".test.yaml"):
        return False, "test_fixture", None

    try:
        yaml_text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read_error: {e}", None

    # Check for credentials/IPs
    if _has_credentials_or_ips(yaml_text):
        return False, f"has_credentials_or_real_infrastructure", None

    # Compute content hash
    content_hash = _content_hash(yaml_text)
    if content_hash in seen_hashes:
        return False, "hash_dup", None
    seen_hashes.add(content_hash)

    # Parse YAML
    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return False, "not_a_dict", None
    except Exception as e:
        return False, f"yaml_parse_error: {e}", None

    # Determine if this is a playbook or step fragment
    # Step fragments from tooling/recipes/steps/ have name, description, steps_yaml, etc.
    # but no "playbooks" key
    if data.get("steps_yaml"):
        # This is a step fragment from tooling/recipes/steps/
        kind = "step"
        name = data.get("name", file_path.stem)
        description = data.get("description", "")
        step_types = data.get("step_types") or []

        return True, None, {
            "name": f"step:{name}".replace(":", "_")[:200],
            "kind": kind,
            "when_to_use": description[:500] or f"Step pattern: {', '.join(step_types)}",
            "yaml_template": (data.get("steps_yaml") or yaml_text)[:6000],  # Use steps_yaml field if present
            "source_playbook": file_path.name,
            "_summary": f"Step pattern: {', '.join(step_types)}",
            "_step_types": ",".join(step_types),
            "_connectors": data.get("connector") or "",
            "_trigger_kind": "fragment",
            "_tags": "step_fragment",
            "_content_hash": content_hash,
        }
    elif "playbooks" in data:
        # Compile playbooks to check validity
        ok, result = _compile_yaml(yaml_text, db_path)
        if not ok:
            error_msg = result if isinstance(result, str) else str(result)[:100]
            return False, f"compile_error: {error_msg}", None

        kind = "example"
        name, description = _extract_name_and_description(data)
        step_types = _extract_step_types(data)
        connectors = _extract_connectors(data)
        trigger_kind = _get_trigger_kind(data)

        # Create a one-line summary
        summary = f"{name}"
        if description:
            summary = description[:80]

        tags = [file_path.parent.name]  # Source dir name
        if any(x in file_path.name.lower() for x in ["lab_", "probe_"]):
            tags.append("lab")

        return True, None, {
            "name": name[:200],
            "kind": kind,
            "when_to_use": description[:500] or f"Trigger: {trigger_kind}",
            "yaml_template": _sanitize_yaml(yaml_text)[:6000],  # Cap at 6KB
            "source_playbook": file_path.name,
            "_summary": summary,
            "_step_types": ",".join(step_types),
            "_connectors": ",".join(connectors),
            "_trigger_kind": trigger_kind,
            "_tags": ",".join(tags),
            "_content_hash": content_hash,
        }
    elif "steps" in data:
        # Generic steps fragment (not the structured format)
        kind = "step"
        step_types = []
        steps = data.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                st = step.get("type")
                if st and st not in step_types:
                    step_types.append(st)

        name = f"{file_path.stem}:step_fragment"
        connectors = _extract_connectors(data)

        return True, None, {
            "name": name[:200],
            "kind": kind,
            "when_to_use": f"Step fragment: {', '.join(step_types)}",
            "yaml_template": _sanitize_yaml(yaml_text)[:6000],
            "source_playbook": file_path.name,
            "_summary": f"Step fragment: {', '.join(step_types)}",
            "_step_types": ",".join(step_types),
            "_connectors": ",".join(connectors),
            "_trigger_kind": "fragment",
            "_tags": "step_fragment",
            "_content_hash": content_hash,
        }
    else:
        return False, "no_playbooks_or_steps", None


def _expand_manifests(manifest_path: Path) -> list[Path]:
    """Expand glob patterns from manifest into actual file paths."""
    files: list[Path] = []
    seen: set[str] = set()

    try:
        manifest_text = manifest_path.read_text()
    except FileNotFoundError:
        print(f"Warning: manifest {manifest_path} not found, will use empty set")
        return []

    for line in manifest_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Resolve relative path
        if line.startswith("../"):
            # Relative to REPO_ROOT's parent
            base = REPO_ROOT.parent
            pattern = line[3:]
        else:
            base = REPO_ROOT
            pattern = line

        # Expand glob
        parts = pattern.split("/")
        current = base
        for part in parts[:-1]:
            if "*" in part:
                # Glob in middle of path
                for match in current.glob(part):
                    if match.is_dir():
                        for f in match.glob("**/*.yaml"):
                            if f.is_file():
                                key = str(f.resolve())
                                if key not in seen:
                                    seen.add(key)
                                    files.append(f)
                break
            else:
                current = current / part
        else:
            # No glob in middle, apply last part
            last_part = parts[-1]
            try:
                for match in current.glob(last_part):
                    if match.is_file():
                        key = str(match.resolve())
                        if key not in seen:
                            seen.add(key)
                            files.append(match)
            except (OSError, ValueError):
                # Invalid glob pattern or path doesn't exist
                pass

    return sorted(set(files))


def _insert_recipes(
    db_path: Path,
    rows: list[dict],
) -> tuple[int, int]:
    """Insert rows into recipes table. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0

    # Delete existing junk rows first
    junk_names = [
        "trigger:cybersponse.action|trigger_pattern",
        "trigger:cybersponse.abstract_trigger|trigger_pattern",
        "trigger:cybersponse.post_update|trigger_pattern",
        "trigger:cybersponse.post_create|trigger_pattern",
        "trigger:cybersponse.api_call|trigger_pattern",
        "trigger:cybersponse.post_delete|trigger_pattern",
        "threat_feed:fake_connector|threat_feed",
        "data_ingest:fake_connector|data_ingest",
    ]

    try:
        with sqlite3.connect(str(db_path)) as conn:
            # Delete junk rows
            for name in junk_names:
                try:
                    conn.execute("DELETE FROM recipes WHERE name = ?", (name,))
                except sqlite3.OperationalError:
                    pass

            # Insert new rows
            for row in rows:
                try:
                    # Create unique name if not already unique
                    name = row["name"]
                    if row.get("kind") == "step":
                        name = f"step:{name}"
                    elif row.get("kind") == "example":
                        # Add hash suffix to make names unique
                        name = f"example:{name}:{row['_content_hash'][:8]}"

                    conn.execute(
                        """INSERT OR REPLACE INTO recipes
                           (name, kind, when_to_use, yaml_template, source_playbook)
                           VALUES (?,?,?,?,?)""",
                        (
                            name,
                            row["kind"],
                            row["when_to_use"],
                            row["yaml_template"],
                            row["source_playbook"],
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"Warning: failed to insert {row['name']}: {e}")
                    skipped += 1

            conn.commit()
    except Exception as e:
        print(f"Error connecting to {db_path}: {e}")
        return 0, len(rows)

    return inserted, skipped


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help=f"Path to manifest (default: {MANIFEST_PATH})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        action="append",
        dest="dbs",
        help="DB to update (can repeat; default: dev + packaged)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done, don't modify DBs",
    )

    args = parser.parse_args()

    dbs = args.dbs or [DEV_DB, PACKAGED_DB]

    print(f"Harvesting examples from {args.manifest}...")

    # Expand manifests
    files = _expand_manifests(args.manifest)
    print(f"Found {len(files)} YAML files")

    # Process each file
    rows: list[dict] = []
    seen_hashes: set[str] = set()
    skipped: dict[str, int] = {}
    refused: list[Path] = []

    for i, file_path in enumerate(files, 1):
        ok, skip_reason, row = _process_playbook_file(file_path, dbs[0], seen_hashes)

        if ok and row:
            rows.append(row)
            status = "✓"
        elif skip_reason and skip_reason == "has_credentials_or_real_infrastructure":
            refused.append(file_path)
            status = "✗ (credentials)"
        else:
            skipped[skip_reason or "unknown"] = skipped.get(skip_reason or "unknown", 0) + 1
            status = f"- ({skip_reason})"

        if (i % 25) == 0 or (i == len(files)):
            print(f"  {i}/{len(files)}: {file_path.name} {status}")

    print(f"\nHarvest summary:")
    print(f"  Total files processed: {len(files)}")
    print(f"  Harvested: {len(rows)}")
    print(f"  Deduplicated (hash): {skipped.get('hash_dup', 0)}")
    print(f"  Refused (credentials): {len(refused)}")
    print(f"  Compile errors: {skipped.get('compile_error', 0)}")
    print(f"  Parse errors: {skipped.get('yaml_parse_error', 0)}")

    if refused:
        print(f"\n  Files with credentials/real infrastructure (REFUSED):")
        for f in refused:
            print(f"    {f}")

    if args.dry_run:
        print(f"\nDry run: would insert {len(rows)} rows into {len(dbs)} DB(s)")
        return 0

    # Validate all DBs have required tables before proceeding
    print(f"\nValidating DB structure...")
    for db_path in dbs:
        if not db_path.exists():
            print(f"  Warning: {db_path} does not exist, will skip it")
            continue

        is_valid, error_msg = _validate_db_structure(db_path)
        if not is_valid:
            print(f"  ERROR: {error_msg}")
            return 1

        # Count tables for verification
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )
            table_count = cursor.fetchone()[0]
            print(f"  ✓ {db_path}: {table_count} tables found")

    # Estimate DB size change
    total_yaml_size = sum(len(r["yaml_template"]) for r in rows)
    estimated_added_mb = total_yaml_size / (1024 * 1024)
    print(f"\nEstimated DB size increase: {estimated_added_mb:.1f} MB")

    if estimated_added_mb > 1.5:
        print(f"Warning: estimated size > 1.5 MB, may exceed target")

    # Insert into DBs
    for db_path in dbs:
        print(f"\nInserting into {db_path}...")
        if not db_path.exists():
            print(f"  Warning: DB does not exist, skipping")
            continue

        inserted, skipped_count = _insert_recipes(db_path, rows)
        print(f"  Inserted: {inserted}, skipped: {skipped_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
