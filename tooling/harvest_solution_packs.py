#!/usr/bin/env python3
"""Pull solution-pack playbooks off a FortiSOAR appliance into the corpus.

Solution packs are the material worth mining. Measured across 49,431 playbooks
found on disk, Use Case collections average 10.6 steps and SP collections 6.5,
while the vendor connector samples that dominate by volume average **2.6** and
are 89% start-plus-one-call stubs. ``probe_playbook_steps`` filters those stubs
out; this script supplies the good input.

Flow, per pack::

    content_hub.search_installed_packs()   # what we can export today
    content_hub.search_available_packs()   # what the Content Hub still offers
    solution_packs.ensure_installed(name)  # only with --install
    solution_packs.export_pack(name)       # -> .zip
    unzip -> data/solution_packs/<pack>/   # probe_playbook_steps reads this

``export_pack`` resolves through ``find_installed_pack``, so a pack must be
**installed** before it can be exported -- listing it as available in the
Content Hub is not enough. That is why ``--install`` exists and why it is
opt-in: installing content mutates the appliance.

Usage::

    python -m tooling.harvest_solution_packs --instance 159 --list
    python -m tooling.harvest_solution_packs --instance 159            # export installed
    python -m tooling.harvest_solution_packs --instance 159 --install  # also install available
    python -m tooling.harvest_solution_packs --instance 159 --pack "SOAR Framework"

Then re-ingest::

    python -m tooling.probes.probe_playbook_steps
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "solution_packs"

# Reuse the same instance registry the rest of the toolchain uses rather than
# inventing another credential path.
INSTANCE_ENVS = {
    "159": "~/WebstormProjects/fsr_all_widgets/fortisoar-widget-harness/.env.159",
    "205": "~/PycharmProjects/Miscellaneous/fortisoar/.env",
    "206": "~/WebstormProjects/fsr_all_widgets/fortisoar-widget-harness/.env.206",
}


def _client(instance: str, timeout: float = 180.0):
    """Build a client, proving the credential before we rely on it.

    ``timeout`` is raised well above pyfsr's 30s default: a solution-pack
    export is a server-side job and large packs (fortinetAdvisor) reliably
    exceed 30s, which surfaces as a read timeout that looks like a dead box.
    """
    from dotenv import dotenv_values
    from pyfsr import FortiSOAR

    env_path = INSTANCE_ENVS.get(instance)
    if not env_path:
        sys.exit(f"unknown instance {instance!r}; known: {', '.join(INSTANCE_ENVS)}")
    cfg = dotenv_values(Path(env_path).expanduser())
    base = cfg.get("FSR_BASE_URL") or cfg.get("BASE_URL")
    if not base:
        sys.exit(f"no base url in {env_path}")
    port = cfg.get("FSR_PORT")
    if port and ":" not in base.split("//", 1)[-1]:
        base = f"{base}:{port}"

    api_key = cfg.get("FSR_API_KEY") or cfg.get("API_KEY")
    # On an appliance the UI/API password is the SSH password, so SSH_* is a
    # legitimate fallback when only those are recorded.
    user = cfg.get("FSR_USERNAME") or cfg.get("SSH_USER")
    password = cfg.get("FSR_PASSWORD") or cfg.get("SSH_PASSWORD")

    attempts = []
    if api_key:
        attempts.append(("api key",
                         lambda: FortiSOAR(base, api_key=api_key, verify_ssl=False,
                                          timeout=timeout)))
    if user and password:
        attempts.append((f"user {user}",
                         lambda: FortiSOAR(base, username=user, password=password,
                                           verify_ssl=False, timeout=timeout)))
    if not attempts:
        sys.exit(f"no usable credentials in {env_path}")

    # API keys in these env files go stale silently -- prove the credential
    # before starting a long export run with it.
    for label, build in attempts:
        try:
            client = build()
            client.get("/api/3/solutionpacks", params={"$limit": 1})
            print(f"[{instance}] auth via {label} -> {base}")
            return client
        except Exception as exc:  # noqa: BLE001
            print(f"[{instance}] {label} rejected: {exc}")
    sys.exit(f"no working credential for {instance}")


# The public Content Hub catalog. `<repo>/xf/solutions/content-hub-web.json` is
# a different file entirely (the connector catalog, 4 packs) -- the pack catalog
# lives under /content-hub/ and comes in two variants:
#
#   content-hub-web.json  124 packs, 13 fields  -- trimmed for the UI
#   content-hub.json      126 packs, 30 fields  -- the full record
#
# The full record is a strict superset and is what we read: it adds the two
# packs the web variant omits (fortiGuardLabs-IOCSearch, fortiTIP) plus
# `dependencies` (pack -> pack) and `contents.connectors` (pack -> connector),
# which is the mapping the corpus wants. Each entry's `infoPath` is the
# directory holding `<name>-<version>.zip`, served unauthenticated -- so packs
# can be harvested without installing anything on an appliance.
REPO_BASE = "https://repo.fortisoar.fortinet.com"
CATALOG_URL = f"{REPO_BASE}/content-hub/content-hub.json"

# Written next to the downloaded packs so the dependency/connector mapping
# survives the harvest -- the pack zips themselves do not carry it.
CATALOG_SIDECAR = "_catalog.json"

# `outbreakResponse-*` packs are per-CVE/per-campaign variants generated from
# one template: 59 of the 124 packs, contributing near-identical playbooks
# rather than new argument shapes. Excluded by default.
OUTBREAK_PREFIX = "outbreak"


def harvest_from_repo(include_outbreak: bool = False, force: bool = False,
                      timeout: float = 120.0) -> int:
    """Download solution packs straight from the public Content Hub repo."""
    import urllib.request

    def _get(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            return r.read()

    print(f"catalog: {CATALOG_URL}")
    catalog = json.loads(_get(CATALOG_URL))
    packs = [x for x in catalog if isinstance(x, dict) and x.get("type") == "solutionpack"]
    # The sidecar records EVERY pack, including the outbreak variants we do not
    # download: dependency and connector edges are cheap and are exactly what
    # you want when asking "which packs use this connector" -- an answer that
    # should not be silently narrowed by a download filter.
    all_packs = list(packs)
    if not include_outbreak:
        kept = [p for p in packs if OUTBREAK_PREFIX not in (p.get("name") or "").lower()]
        print(f"  {len(packs)} packs, skipping {len(packs) - len(kept)} outbreak variants "
              f"-> {len(kept)} to fetch")
        packs = kept
    else:
        print(f"  {len(packs)} packs")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zips = OUT_DIR / "_zips"
    zips.mkdir(exist_ok=True)

    sidecar = {
        p["name"]: {
            "version": p.get("version"),
            "label": p.get("label"),
            "category": p.get("category"),
            "fsrMinCompatibility": p.get("fsrMinCompatibility"),
            "dependencies": [
                {"name": d.get("name"), "type": d.get("type"),
                 "version": d.get("version"), "minVersion": d.get("minVersion")}
                for d in (p.get("dependencies") or [])
            ],
            "connectors": [
                {"name": c.get("name"), "apiName": c.get("apiName")}
                for c in ((p.get("contents") or {}).get("connectors") or [])
            ],
        }
        for p in all_packs if p.get("name")
    }
    (OUT_DIR / CATALOG_SIDECAR).write_text(json.dumps(sidecar, indent=2, sort_keys=True))
    print(f"  catalog metadata -> {OUT_DIR / CATALOG_SIDECAR}")

    ok = failed = files = skipped = 0
    for p in packs:
        name, ver = p.get("name"), p.get("version")
        info = p.get("infoPath")
        if not (name and ver and info):
            continue
        safe = f"{name}-{ver}"
        dest = OUT_DIR / safe
        if not force and dest.exists() and any(dest.rglob("*.json")):
            skipped += 1
            continue
        url = f"{REPO_BASE}{info}/{name}-{ver}.zip"
        zip_path = zips / f"{safe}.zip"
        try:
            zip_path.write_bytes(_get(url))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {safe}: {exc}")
            failed += 1
            continue
        n = _unpack(zip_path, dest)
        files += n
        ok += 1
        print(f"  {safe}: {n} playbook file(s)")

    print(f"\n{ok} downloaded, {skipped} already present, {failed} failed, "
          f"{files} playbook file(s) -> {OUT_DIR}")
    return 0


def _pack_name(pack: object) -> str | None:
    if isinstance(pack, dict):
        return pack.get("name") or pack.get("label")
    return getattr(pack, "name", None) or getattr(pack, "label", None)


def _unpack(zip_path: Path, dest: Path) -> int:
    """Extract only the playbook JSON out of a pack zip.

    A pack bundle also carries modules, picklists, view templates and records.
    The corpus only needs playbooks, and pulling the rest in would put
    unrelated JSON in front of the probe's `*.json` walk.
    """
    written = 0
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                low = name.lower()
                if not low.endswith(".json") or "playbook" not in low:
                    continue
                parts = Path(name).parts
                # Keep the collection directory. Pack bundles lay playbooks out
                # as `export_<uuid>/playbooks/<Collection Name>/<Playbook>.json`
                # and that directory is the ONLY place the collection name
                # appears -- individual playbook files carry just an IRI.
                # Flattening loses it, and also collides playbooks that share a
                # name across collections.
                try:
                    idx = [p.lower() for p in parts].index("playbooks")
                    rel = Path(*parts[idx + 1:])
                except ValueError:
                    rel = Path(parts[-1])
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                written += 1
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"    ! could not read {zip_path.name}: {exc}")
    return written


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-repo", action="store_true",
                   help="download packs from the public Content Hub repo instead of an "
                        "appliance. No install, no credentials, no appliance mutation.")
    p.add_argument("--include-outbreak", action="store_true",
                   help="also fetch the ~59 outbreakResponse-* per-CVE variants")
    p.add_argument("--instance", default="159", help=f"one of: {', '.join(INSTANCE_ENVS)}")
    p.add_argument("--list", action="store_true", help="list installed/available packs and exit")
    p.add_argument("--pack", action="append", help="harvest only these packs (repeatable)")
    p.add_argument("--install", action="store_true",
                   help="install available packs before exporting. MUTATES THE APPLIANCE.")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--timeout", type=float, default=180.0,
                   help="per-request timeout; large pack exports exceed pyfsr's 30s default")
    p.add_argument("--force", action="store_true",
                   help="re-export packs already present on disk")
    args = p.parse_args()

    if args.from_repo:
        return harvest_from_repo(include_outbreak=args.include_outbreak,
                                 force=args.force, timeout=args.timeout)

    client = _client(args.instance, timeout=args.timeout)
    installed = client.content_hub.search_installed_packs(limit=args.limit)
    available = client.content_hub.search_available_packs(limit=args.limit)
    inst_names = [n for n in (_pack_name(x) for x in installed) if n]
    avail_names = [n for n in (_pack_name(x) for x in available) if n]

    if args.list:
        print(f"\ninstalled ({len(inst_names)}):")
        for n in sorted(inst_names):
            print("  ", n)
        print(f"\navailable, not installed ({len(set(avail_names) - set(inst_names))}):")
        for n in sorted(set(avail_names) - set(inst_names)):
            print("  ", n)
        return 0

    targets = args.pack or inst_names
    if args.install:
        # export_pack() resolves via find_installed_pack, so anything not yet
        # installed is unreachable without this step.
        for name in (args.pack or avail_names):
            if name in inst_names:
                continue
            try:
                print(f"  installing {name} ...")
                client.solution_packs.ensure_installed(name)
                targets.append(name)
            except Exception as exc:  # noqa: BLE001
                print(f"    ! install failed for {name}: {exc}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zips = OUT_DIR / "_zips"
    zips.mkdir(exist_ok=True)

    ok = failed = files = skipped = 0
    for name in dict.fromkeys(targets):  # de-dup, keep order
        safe = "".join(c if c.isalnum() or c in "-_. " else "_" for c in name).strip()
        zip_path = zips / f"{safe}.zip"
        dest = OUT_DIR / safe
        # Resume rather than restart. Exporting 50 packs is a long run against a
        # lab appliance that drops connections; without this, one network blip
        # means re-exporting everything that already succeeded.
        if not args.force and dest.exists() and any(dest.glob("*.json")):
            skipped += 1
            continue
        try:
            print(f"  exporting {name} ...")
            client.solution_packs.export_pack(name, output_path=str(zip_path))
        except Exception as exc:  # noqa: BLE001
            print(f"    ! export failed: {exc}")
            failed += 1
            continue
        n = _unpack(zip_path, dest)
        files += n
        ok += 1
        print(f"    {n} playbook file(s)")

    print(f"\n{ok} exported, {skipped} already present, {failed} failed, "
          f"{files} playbook file(s) -> {OUT_DIR}")
    print("next: python -m tooling.probes.probe_playbook_steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
