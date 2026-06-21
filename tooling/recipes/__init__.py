"""Recipe generators that emit ready-to-push FSR JSON playbook collections.

Each recipe kind binds to a validator ruleset (see compiler/rulesets/).
Generated output is guaranteed to validate clean under that ruleset.

Kinds:
- threat-feed: Ingest Bulk Feed → /api/ingest-feeds/threat_intel_feeds (validates under feed-ingest)
- data-ingest: Create Record → /api/3/alerts (validates under data-ingest)  [TODO]
"""
from __future__ import annotations

from .generator import generate_threat_feed_recipe  # noqa: F401
from .generator import generate_data_ingest_recipe  # noqa: F401
