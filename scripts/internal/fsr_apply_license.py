#!/usr/bin/env python3
"""Apply a fresh FortiFlex license to the FSR appliance.

Reuses the helper from `fabric_studio_fixer` which:
  1. Authenticates to FortiFlex (customerapiauth.fortinet.com).
  2. Generates a fresh VM token via FORTIFLEX_CONFIG_ID_SOAR.
  3. POSTs `{action:"install_flex_license", data:{license_token:...}}`
     to /api/public/license on the appliance (no auth required).
  4. Polls /api/public/license {action:"get_status"} until done.

Why a wrapper: this project keeps the FSR/API creds in its own .env
(FSR_USERNAME/FSR_PASSWORD) but FortiFlex creds live in the fabric
studio fixer .env (FORTIFLEX_USER/PASS, FORTIFLEX_CONFIG_ID_SOAR).
We pull from both without copying secrets.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FAB = Path("/Users/dylanspille/PycharmProjects/Miscellaneous/fndn/fabric_studio_fixer")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "10.99.249.205"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443

    _load_dotenv(FAB / ".env")
    flex_user = os.environ.get("FORTIFLEX_USER")
    flex_pass = os.environ.get("FORTIFLEX_PASS")
    config_id = os.environ.get("FORTIFLEX_CONFIG_ID_SOAR")
    if not (flex_user and flex_pass and config_id):
        print("Missing FORTIFLEX_USER / FORTIFLEX_PASS / FORTIFLEX_CONFIG_ID_SOAR "
              f"in {FAB}/.env", file=sys.stderr)
        return 2

    sys.path.insert(0, str(FAB))
    from fortiflex.api import (  # type: ignore
        flex_authenticate, flex_create_entitlement, flex_regenerate_token,
    )
    import time, requests, urllib3
    urllib3.disable_warnings()

    flex_token = flex_authenticate(flex_user, flex_pass)

    # Default config_id is the "soar-mt-mgr" multi-tenant pool from
    # FORTIFLEX_CONFIG_ID_SOAR. For an Enterprise box that produces
    # FSR-Auth-021 ("Enterprise setup cannot be upgraded to Multi-tenant").
    # Override with FSR_LICENSE_CONFIG_ID env var or pass --config-id.
    # Known Enterprise configs:
    #   26901 = FortiSOAR Enterprise 1-user
    #   63891 = SOAR Ent + TIM + 10 seats
    config_id = os.environ.get("FSR_LICENSE_CONFIG_ID", config_id)

    print(f"[+] FortiFlex authenticated; minting SOAR token (config_id={config_id}) for {host}",
          file=sys.stderr)
    ent = flex_create_entitlement(
        flex_token, int(config_id),
        description=f"fsrpb auto-license {host}",
    )
    serial = ent["entitlements"][0]["serialNumber"]
    print(f"[+] Minted serial {serial}; waiting for FortiFlex sync…", file=sys.stderr)

    # Newly-minted serials need a couple minutes before the .lic file is
    # retrievable. Regenerate once the box reports a non-sync error to
    # speed past the FSR-Auth-001 (not-registered) phase.
    s = requests.Session()
    s.verify = False
    install_url = f"https://{host}:{port}/api/public/license"
    token = ent["entitlements"][0]["token"]

    for attempt in range(10):
        s.post(install_url,
               json={"action": "install_flex_license",
                     "data": {"license_token": token}},
               timeout=30)
        time.sleep(15)
        r = s.post(install_url, json={"action": "get_status"}, timeout=15)
        data = r.json() if r.ok else {"depl_status": "?", "depl_message": r.text[:120]}
        msg = data.get("depl_message") or ""
        st = (data.get("depl_status") or "").lower()
        print(f"  [{attempt+1}] {st}: {msg!r}", file=sys.stderr)
        if "success" in msg.lower() or (st == "finished" and not msg):
            print(f"[+] License active: {serial}", file=sys.stderr)
            return 0
        if "sync with server" in msg or "not registered" in msg:
            time.sleep(30)
            token = flex_regenerate_token(flex_token, serial)
            continue
        # other error — bail
        print(f"[!] install failed: {msg}", file=sys.stderr)
        return 1
    print("[!] timed out waiting for license activation", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
