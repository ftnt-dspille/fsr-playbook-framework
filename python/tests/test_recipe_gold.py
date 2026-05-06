"""Recipe gold-standard byte-equality fixtures.

The recipe generators (`generate_threat_feed_recipe`,
`generate_data_ingest_recipe`) emit FSR JSON whose UUIDs are derived
deterministically from the connector slug. That means we can lock the
*entire* generator output into a fixture and assert byte-for-byte
equality on every run — any silent change to step ordering, arg
shapes, or picklist macros breaks the test loudly instead of leaking
into a real recipe months later.

Two fixtures live under `python/tests/fixtures/recipes/`:
- `synthetic_threat_feed_info.json` + `.gold.json`
- `synthetic_data_ingest_info.json` + `.gold.json`

Regenerating: bump the gold by re-running
`python -c "..."` (see top of test_recipe_gold.py docstring) ONLY when
a generator change is intentional.
"""
from __future__ import annotations

import json
from pathlib import Path

from recipes import (generate_data_ingest_recipe,
                     generate_threat_feed_recipe)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recipes"


def _normalize(blob) -> str:
    """Sort-keyed pretty JSON — same shape the gold was written with,
    so dict-key reordering by the generator can't false-positive."""
    return json.dumps(blob, indent=2, sort_keys=True)


def test_threat_feed_recipe_byte_equal_to_gold():
    info = json.loads(
        (FIXTURES / "synthetic_threat_feed_info.json").read_text()
    )
    gold = (FIXTURES / "synthetic_threat_feed.gold.json").read_text()
    out = generate_threat_feed_recipe(
        info, connector_config_uuid="REPLACE_WITH_CONFIG_UUID",
    )
    assert _normalize(out) == gold, (
        "threat-feed generator output drifted from "
        "synthetic_threat_feed.gold.json — re-bake the fixture only if "
        "the change is intentional"
    )


def test_data_ingest_recipe_byte_equal_to_gold():
    info = json.loads(
        (FIXTURES / "synthetic_data_ingest_info.json").read_text()
    )
    gold = (FIXTURES / "synthetic_data_ingest.gold.json").read_text()
    out = generate_data_ingest_recipe(
        info,
        target_module="alerts",
        severity_enum=["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
        status_enum=["Open", "Investigating", "Resolved", "Closed"],
        connector_config_uuid="REPLACE_WITH_CONFIG_UUID",
    )
    assert _normalize(out) == gold, (
        "data-ingest generator output drifted from "
        "synthetic_data_ingest.gold.json — re-bake the fixture only if "
        "the change is intentional"
    )


def test_recipe_uuids_are_deterministic():
    """Two back-to-back invocations on the same input must produce
    identical UUIDs — that's the whole point of deriving them via
    `_uuid_from(seed)` rather than uuid4(). If this regresses, every
    upstream test that relies on stable IRIs will start flapping."""
    info = json.loads(
        (FIXTURES / "synthetic_threat_feed_info.json").read_text()
    )
    a = generate_threat_feed_recipe(info,
                                    connector_config_uuid="X")
    b = generate_threat_feed_recipe(info,
                                    connector_config_uuid="X")
    assert _normalize(a) == _normalize(b)
