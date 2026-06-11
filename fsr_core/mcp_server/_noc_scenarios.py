"""Loader for the NOC scenario manifest (``noc_scenarios.json``).

One source of truth shared by three consumers (see
``docs/plans/NOC_SCENARIO_CATALOG.md``):

  * the live alert seeder    -> ``scenario["alert"]``
  * the Fabric Studio recipe -> ``scenario["induce"]`` (setup/teardown CLI)
  * the offline sim fixtures -> ``scenario["fmg_row"]`` + ``scenario["faz_logs"]``

``device`` ties an agent tool call (FMG device name / FAZ ``devid``) back to its
scenario, so multiple NOC stories coexist without colliding.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_MANIFEST = os.path.join(os.path.dirname(__file__), "noc_scenarios.json")


@lru_cache(maxsize=1)
def load() -> dict[str, dict[str, Any]]:
    """Return the scenario manifest keyed by scenario id (``_README`` dropped)."""
    try:
        with open(_MANIFEST, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def scenarios() -> list[dict[str, Any]]:
    """All scenario entries (each augmented with its ``id``)."""
    return [{"id": k, **v} for k, v in load().items()]


def by_device(device: str) -> dict[str, Any] | None:
    """The scenario whose managed device matches ``device`` (name or serial)."""
    if not device:
        return None
    dev = str(device).strip().lower()
    for sc in scenarios():
        if dev in (str(sc.get("device", "")).lower(),
                   str(sc.get("serial", "")).lower()):
            return sc
    return None
