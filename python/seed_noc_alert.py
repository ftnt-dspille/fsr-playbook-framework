#!/usr/bin/env python3
"""Seed a NOC alert into FortiSOAR from the scenario manifest.

Reads ``scenario["alert"]`` from ``fsr_core/mcp_server/noc_scenarios.json`` and
POSTs it to the **alerts** module (``/api/3/alerts`` on this box — confirmed
2026-06-10; see HANDOFF). Picklist-typed fields (severity, type, status, source)
are resolved name -> IRI via ``picklists.resolve_module_fields`` when live.

Pairs with:
  * ``gen_fs_recipes.py`` — stands up the matching FS fault so FAZ/FMG reflect it.
  * the SOC Assistant widget — open it on the printed IRI / deep-link to triage.

Usage:
    python python/seed_noc_alert.py --scenario vpn_tunnel_down --dry-run
    python python/seed_noc_alert.py --scenario vpn_tunnel_down     # live (needs .env)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "fsr_core" / "mcp_server" / "noc_scenarios.json"

ALERTS_MODULE = "alerts"  # confirmed on 10.99.249.205 (not "incidents")

# Manifest alert.* key -> FortiSOAR alerts field name.
_FIELD_MAP = {
    "title": "name",
    "description": "description",
    "severity": "severity",
    "source": "source",
    "type": "type",
}


def _load_scenario(sid: str) -> dict[str, Any]:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sc = raw.get(sid)
    if not sc:
        avail = [k for k in raw if not k.startswith("_")]
        sys.exit(f"scenario '{sid}' not found. Available: {', '.join(avail)}")
    if "alert" not in sc:
        sys.exit(f"scenario '{sid}' has no alert.* block")
    return sc


def _build_payload(alert: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for mkey, fsr_field in _FIELD_MAP.items():
        if mkey in alert:
            payload[fsr_field] = alert[mkey]
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", required=True, help="scenario id in the manifest")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload without posting (no live box needed)")
    args = ap.parse_args(argv)

    sc = _load_scenario(args.scenario)
    payload = _build_payload(sc["alert"])

    if args.dry_run:
        print(json.dumps({"module": ALERTS_MODULE, "payload": payload}, indent=2,
                         ensure_ascii=False))
        return 0

    # Live path.
    sys.path.insert(0, str(REPO_ROOT / "python"))
    from probes._env import get_client, get_config  # noqa: E402
    import picklists  # noqa: E402

    if not get_config().is_live():
        sys.exit("not live: set FSR_BASE_URL + creds in .env (or use --dry-run)")
    client = get_client()

    # Resolve picklist fields (severity/type/source/status) name -> IRI.
    try:
        payload = picklists.resolve_module_fields(client, ALERTS_MODULE, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: picklist resolution skipped ({exc}); posting raw values",
              file=sys.stderr)

    resp = client.session.post(
        client.base_url + f"/api/3/{ALERTS_MODULE}",
        json=payload, verify=client.verify_ssl,
    )
    if resp.status_code not in (200, 201):
        sys.exit(f"seed failed [{resp.status_code}]: {resp.text[:500]}")
    rec = resp.json()
    iri = rec.get("@id") or rec.get("id") or "?"
    uuid = str(iri).rsplit("/", 1)[-1]
    print(f"seeded alert -> {iri}")
    print(f"widget deep-link: {client.base_url}/alerts/{uuid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
