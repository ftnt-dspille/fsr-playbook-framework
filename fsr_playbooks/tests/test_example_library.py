"""Tests for the example library harvesting and retrieval."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from fsr_playbooks.mcp_server import tools_corpus, tools_recipe


@pytest.fixture
def temp_manifest(tmp_path: Path) -> Path:
    """Create a temporary manifest file pointing to fixture YAMLs."""
    manifest = tmp_path / "test_manifest.txt"
    # Point to the framework examples directory
    manifest.write_text(
        "# Test manifest\n"
        f"../fsr-playbook-framework/examples/demo_alert_on_create.yaml\n"
        f"../fsr-playbook-framework/examples/demo_record_create.yaml\n"
        f"../fsr-playbook-framework/examples/manual_input_then_act.yaml\n"
    )
    return manifest


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary test database."""
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                name            TEXT PRIMARY KEY,
                kind            TEXT NOT NULL,
                when_to_use     TEXT,
                yaml_template   TEXT NOT NULL,
                source_playbook TEXT
            )"""
        )
        # Also create the playbook_steps table (empty for fallback testing)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS playbook_steps (
                step_name       TEXT,
                playbook_name   TEXT,
                source          TEXT,
                source_path     TEXT,
                arguments_json  TEXT,
                step_type_name  TEXT
            )"""
        )
        conn.commit()
    return db_path


def test_harvest_script_finds_valid_files(temp_manifest: Path) -> None:
    """Test that the harvest script can find and process valid YAML files."""
    from scripts.harvest_examples import _expand_manifests, _process_playbook_file

    files = _expand_manifests(temp_manifest)
    assert len(files) > 0, "Should find YAML files from manifest"

    # Check that we found the expected files
    file_names = {f.name for f in files}
    assert "demo_alert_on_create.yaml" in file_names
    assert "demo_record_create.yaml" in file_names


def test_harvest_script_rejects_credentials() -> None:
    """Test that the harvest script refuses files with credentials."""
    from scripts.harvest_examples import _has_credentials_or_ips

    # Files with credentials should be rejected
    yaml_with_password = """
playbooks:
  - name: Test
    steps:
      - name: Step 1
        password: "myRealPassword123!"
"""
    assert _has_credentials_or_ips(yaml_with_password)

    yaml_with_api_key = """
playbooks:
  - name: Test
    steps:
      - name: Step 1
        api_key: "key_abc123def456"
"""
    assert _has_credentials_or_ips(yaml_with_api_key)

    # Real public IPs (not in documentation ranges) should be rejected
    yaml_with_real_public_ip = """
playbooks:
  - name: Test
    steps:
      - name: Step 1
        resolver: "8.8.8.9"
"""
    assert _has_credentials_or_ips(yaml_with_real_public_ip)

    # Private IPs should NOT be rejected
    yaml_with_private_ip = """
playbooks:
  - name: Test
    steps:
      - name: Step 1
        ip_address: "192.168.1.1"
"""
    assert not _has_credentials_or_ips(yaml_with_private_ip)

    # Valid YAML should not be rejected
    clean_yaml = """
playbooks:
  - name: Test
    steps:
      - name: Step 1
        type: decision
"""
    assert not _has_credentials_or_ips(clean_yaml)


def test_find_recipe_returns_ranked_results(temp_db: Path) -> None:
    """Test that find_recipe ranks results by token overlap."""
    # Insert test data
    with sqlite3.connect(str(temp_db)) as conn:
        conn.execute(
            """INSERT INTO recipes
               (name, kind, when_to_use, yaml_template, source_playbook)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "example:block_ip_fortigate:abc123",
                "example",
                "Block an IP on FortiGate using a firewall policy",
                "playbooks:\n  - name: Block IP\n    steps: []",
                "block_ip.yaml",
            ),
        )
        conn.execute(
            """INSERT INTO recipes
               (name, kind, when_to_use, yaml_template, source_playbook)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "example:send_email:def456",
                "example",
                "Send an email notification to users",
                "playbooks:\n  - name: Send Email\n    steps: []",
                "send_email.yaml",
            ),
        )
        conn.commit()

    # Monkey-patch the DB connection
    original_db = tools_recipe._db
    def mock_db(*args, **kwargs):
        class MockContext:
            def __enter__(self):
                conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                return conn
            def __exit__(self, *args):
                pass
        return MockContext()

    tools_recipe._db = mock_db
    try:
        result = tools_recipe.find_recipe("block IP fortigate", limit=3)
        assert result["ok"]
        # The "block ip fortigate" query should rank the FortiGate result higher
        assert len(result["recipes"]) > 0
        # First result should contain "fortigate" since we searched for it
        assert "fortigate" in result["recipes"][0]["when_to_use"].lower()
    finally:
        tools_recipe._db = original_db


def test_find_step_examples_fallback(temp_db: Path) -> None:
    """Test that find_step_examples falls back to examples when playbook_steps is empty."""
    # Insert example with a Decision step
    with sqlite3.connect(str(temp_db)) as conn:
        conn.execute(
            """INSERT INTO recipes
               (name, kind, when_to_use, yaml_template, source_playbook)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "example:decision_logic:abc123",
                "example",
                "Branch logic based on conditions",
                """playbooks:
  - name: Test
    steps:
      - name: Check Severity
        type: decision
        branches:
          - condition: "{{ vars.input.severity > 5 }}"
            do:
              - name: High Severity Handler
                type: set_variable
                variables:
                  - name: severity_level
                    value: high
""",
                "decision_example.yaml",
            ),
        )
        conn.commit()

    # Monkey-patch the DB connection
    original_db = tools_corpus._db
    def mock_db(*args, **kwargs):
        class MockContext:
            def __enter__(self):
                conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                return conn
            def __exit__(self, *args):
                pass
        return MockContext()

    tools_corpus._db = mock_db
    try:
        # When playbook_steps is empty, should fall back to recipes
        result = tools_corpus.find_step_examples("decision", limit=5)
        assert len(result) > 0, "Should find decision examples from recipes"
        # The result should have the right structure
        assert "step_name" in result[0] or "yaml_template" in result[0]
    finally:
        tools_corpus._db = original_db


def test_no_gold_eval_files_in_recipes() -> None:
    """Test that no evaluation gold files are included in the recipes table.

    This is a safety check to ensure eval leakage doesn't happen during harvest.
    """
    from pathlib import Path
    import hashlib

    # Get the DB path
    db_path = Path(__file__).parent.parent / "_data" / "fsr_reference.db"
    if not db_path.exists():
        pytest.skip("Packaged DB not found")

    # Read all recipe yaml_templates and compute their hashes
    recipe_hashes: set[str] = set()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT yaml_template FROM recipes WHERE kind = 'example'"
            ).fetchall()
            for (yaml_text,) in rows:
                if yaml_text:
                    h = hashlib.sha256(yaml_text.encode()).hexdigest()
                    recipe_hashes.add(h)
    except sqlite3.OperationalError:
        pytest.skip("recipes table not found in packaged DB")

    # Check gold eval files
    gold_dir = Path(__file__).parent.parent.parent / "tooling" / "evals" / "golds"
    if not gold_dir.exists():
        pytest.skip("golds directory not found")

    gold_hashes: set[str] = set()
    for yaml_file in gold_dir.glob("**/*.yaml"):
        try:
            content = yaml_file.read_text()
            h = hashlib.sha256(content.encode()).hexdigest()
            gold_hashes.add(h)
        except Exception:
            pass

    # Check for overlap
    overlap = recipe_hashes & gold_hashes
    assert not overlap, f"Found {len(overlap)} gold eval files in recipes table (eval leakage)"


def test_harvest_preserves_db_structure() -> None:
    """Test that harvest adds rows without clobbering core tables.

    Regression test: harvest script must never CREATE TABLE IF NOT EXISTS
    on the packaged DB - it should only INSERT/REPLACE into recipes of
    an existing DB. If the DB loses tables, harvest failed to validate.
    """
    import shutil
    from scripts.harvest_examples import (
        _insert_recipes,
        _validate_db_structure,
    )

    # Use the packaged DB as source of truth
    packaged_db = Path(__file__).parent.parent.parent / "fsr_playbooks" / "_data" / "fsr_reference.db"

    if not packaged_db.exists():
        pytest.skip("packaged DB not found")

    # Count tables and recipes before
    with sqlite3.connect(str(packaged_db)) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        tables_before = cursor.fetchone()[0]

        # Count step_types (should be stable)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM step_types")
            step_types_before = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            step_types_before = 0

        # Count existing recipes
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM recipes")
            recipes_before = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            recipes_before = 0

    # Validate DB structure
    is_valid, error_msg = _validate_db_structure(packaged_db)
    assert is_valid, f"Packaged DB validation failed: {error_msg}"

    # Create a copy and run harvest simulation
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_packaged.db"
        shutil.copy2(packaged_db, test_db)

        # Insert a few test recipes
        test_rows = [
            {
                "name": "Test Recipe",
                "kind": "example",
                "when_to_use": "Test purposes",
                "yaml_template": "playbooks:\n  - name: Test\n    steps: []",
                "source_playbook": "test.yaml",
                "_content_hash": "abc123",
            }
        ]

        inserted, skipped = _insert_recipes(test_db, test_rows)
        assert inserted > 0, "Failed to insert test rows"

        # Verify structure is preserved
        with sqlite3.connect(str(test_db)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )
            tables_after = cursor.fetchone()[0]

            # Must have same number of tables
            assert tables_after == tables_before, (
                f"DB lost tables: {tables_before} → {tables_after}. "
                f"Harvest must only add rows, not alter schema."
            )

            # step_types row count must be unchanged
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM step_types")
                step_types_after = cursor.fetchone()[0]
                assert step_types_after == step_types_before, (
                    f"step_types changed: {step_types_before} → {step_types_after}. "
                    f"Harvest should not modify core tables."
                )
            except sqlite3.OperationalError:
                pass

            # recipes must have gained rows
            cursor = conn.execute("SELECT COUNT(*) FROM recipes")
            recipes_after = cursor.fetchone()[0]
            assert recipes_after >= recipes_before + 1, (
                f"recipes did not gain rows: {recipes_before} → {recipes_after}"
            )
