"""probe_connectors -- populate connectors / operations / operation_params.

Live source (preferred):
  GET  /api/integration/connectors/?page_size=1000&active=true
       → list of installed/active connectors (summary; no operations).
  POST /api/integration/connectors/{name}/{version}/?format=json
       → full record incl. operations[], config_schema, conditional onchange.

Trust ladder (per Dylan's rule, local sources never become trusted):
  - connector existence: tested_pass via live_api_get  (we read its record)
  - operation declaration: seen via live_api_get       (we read; haven't run)
  - param declaration:    seen via live_api_get
  Operations only become tested_pass once exercised via /api/integration/execute/.

Local fallback (only runs when live unavailable):
  fortisoar-rpm-extracted/*/info.json -- written as `seen` via rpm_info_json.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tarfile
import urllib.request
import warnings
from pathlib import Path

from fsr_playbooks import warmup
from fsr_playbooks.warmup import upsert_connector_detail

from . import _env
from .common import (
    RPM_EXTRACTED_DIR,
    STORE_DIR,
    probe_session,
    record_verification,
)

# Public Fortinet repo -- provides RPMs for every published connector,
# whether or not it's installed on the local FSR instance.
FORTINET_REPO_BASE = "https://repo.fortisoar.fortinet.com"
FORTINET_REPO_INDEX = f"{FORTINET_REPO_BASE}/connectors/info/connectors.json"
FORTINET_REPO_RPM_DIR = f"{FORTINET_REPO_BASE}/connectors/x86_64"
RPM_CACHE_DIR = STORE_DIR / "rpm_cache"

PROBE_NAME = "probe_connectors"

# ----------------------- live -----------------------

def _live(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, ["env not configured"]
    return warmup.load_installed_connectors(conn, client)


# ----------------------- catalog (uninstalled) -----------------------

def _fetch_connector_detail(client, name: str, version: str) -> dict | None:
    """Try POST /api/integration/connectors/{name}/{version}/ for full param schema.

    Works for installed connectors AND catalog connectors that are registered
    in the integrations service.  Returns None on 404 / any error.
    """
    try:
        return client.post(
            f"/api/integration/connectors/{name}/{version}/?format=json", {}
        )
    except Exception:  # noqa: BLE001
        return None


def _live_catalog(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """POST /api/query/solutionpacks for connectors not installed on this box.

    For each catalog connector, first tries POST /api/integration/connectors/
    {name}/{version}/ to get the full schema including parameters (works for
    most connectors even when not installed). Falls back to infoContent summary
    (no parameters) when the detail endpoint returns 404.
    """
    client = _env.get_client()
    if client is None:
        return 0, ["env not configured"]

    page = 1
    limit = 100
    total: int | None = None
    items_seen = 0           # raw count from the server (for pagination math)
    upserts = 0              # connector rows we actually wrote
    skipped_installed = 0    # rows whose name is already a live install
    errors: list[str] = []
    seen_ids: set[str] = set()   # detect duplicate pages / runaway loops
    MAX_PAGES = 100              # safety cap (limit*MAX_PAGES = 10k rows ceiling)

    # /api/query/solutionpacks pagination: $limit + $page in the URL query.
    # Body `page`/`limit` fields are silently ignored. A stable sort makes
    # pagination deterministic.
    body = {
        "logic": "AND",
        "sort": [{"field": "label", "direction": "ASC"}],
        "filters": [
            {"field": "type", "operator": "in", "value": ["connector"]},
            {"field": "installed", "operator": "eq", "value": False},
        ],
    }

    while page <= MAX_PAGES:
        try:
            r = client.post(
                f"/api/query/solutionpacks?$limit={limit}&$page={page}",
                data=body,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"solutionpacks p{page}: {e!r}")
            break

        members = r.get("hydra:member") or r.get("data") or []
        if total is None:
            total = r.get("hydra:totalItems") or r.get("totalItems")
        if not members:
            break

        page_new = 0
        for sp in members:
            sp_id = str(sp.get("uuid") or sp.get("@id") or sp.get("name"))
            if sp_id in seen_ids:
                # Server returned an item we already processed -- pagination
                # is looping. Bail out before we double-count.
                continue
            seen_ids.add(sp_id)
            page_new += 1
            items_seen += 1

            info = sp.get("infoContent") or {}
            name = info.get("name") or sp.get("name")
            version = sp.get("version") or info.get("version") or ""
            if not name:
                continue

            # Installed rows always win -- they already have full data from _live.
            existing = conn.execute(
                "SELECT source FROM connectors WHERE name = ?",
                (name,),
            ).fetchone()
            # Preserve richer rows: live_api_get has full params, and
            # fortinet_repo_rpm has full schema from canonical RPMs.
            # Catalog (solutionpack) data only carries summary fields.
            if existing and existing[0] in ("live_api_get", "fortinet_repo_rpm"):
                skipped_installed += 1
                continue

            # Try the full detail endpoint first -- it returns operations with
            # parameters even for non-installed connectors on most FSR versions.
            detail = _fetch_connector_detail(client, name, version)
            if detail and isinstance(detail, dict) and detail.get("operations"):
                source = "live_api_get"
                upsert_connector_detail(conn, detail, source=source)
            else:
                # Fall back to infoContent (summary only, no params).
                if not info.get("name"):
                    info = {
                        "name": name,
                        "version": version,
                        "label": sp.get("label"),
                        "description": sp.get("description"),
                        "publisher": sp.get("publisher"),
                        "category": sp.get("category"),
                        "operations": [],
                        "config_schema": {},
                    }
                source = "solutionpack_catalog"
                upsert_connector_detail(conn, info, source=source)

            record_verification(
                conn, kind="connector", key=name,
                method="solutionpack_catalog", status="seen",
                notes=f"sp_id={sp_id} detail={'ok' if detail else 'fallback'}",
            )
            upserts += 1

        # Termination: server returned no NEW items, OR we've hit totalItems,
        # OR a short page (< limit) signals last page.
        if page_new == 0:
            break
        if total is not None and items_seen >= total:
            break
        if len(members) < limit:
            break
        page += 1

    if page > MAX_PAGES:
        errors.append(f"hit MAX_PAGES={MAX_PAGES} before completion")

    record_verification(
        conn, kind="api_endpoint",
        key="POST /api/query/solutionpacks",
        method="live_api_get", status="tested_pass",
        notes=f"items_seen={items_seen} totalItems={total} upserts={upserts} skipped_installed={skipped_installed}",
    )
    print(f"  catalog: {items_seen}/{total} items, {upserts} upserts, {skipped_installed} skipped (installed)")
    return upserts, errors


# ----------------------- repo RPM tier -----------------------

def _fetch_repo_index() -> dict | None:
    """Fetch /connectors/info/connectors.json -- index of every published RPM."""
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(FORTINET_REPO_INDEX, context=ctx, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _download_rpm(rpm_full_name: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    url = f"{FORTINET_REPO_RPM_DIR}/{rpm_full_name}"
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=60) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f)
        return dest.stat().st_size > 0
    except Exception:  # noqa: BLE001
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


_RPM_DIR_LISTING: list[str] | None = None


def _rpm_dir_listing() -> list[str]:
    """Cached scrape of /connectors/x86_64/ -- used to recover from stale
    buildNumbers in connectors.json (the index sometimes points at builds
    that have been replaced; the actual file lives under a different number).
    """
    global _RPM_DIR_LISTING
    if _RPM_DIR_LISTING is not None:
        return _RPM_DIR_LISTING
    import re
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(
            FORTINET_REPO_RPM_DIR + "/", context=ctx, timeout=30,
        ) as r:
            html = r.read().decode("utf-8", errors="ignore")
        _RPM_DIR_LISTING = re.findall(r'href="(cyops-connector-[^"]+\.rpm)"', html)
    except Exception:  # noqa: BLE001
        _RPM_DIR_LISTING = []
    return _RPM_DIR_LISTING


def _resolve_rpm_by_prefix(name: str, version: str) -> str | None:
    """Find the actual RPM filename for <name>-<version>-* in the repo dir."""
    prefix = f"cyops-connector-{name}-{version}-"
    for fn in _rpm_dir_listing():
        if fn.startswith(prefix):
            return fn
    return None


def _extract_info_from_rpm(rpm_path: Path, work_dir: Path) -> dict | None:
    """RPM → inner <name>.tgz → <name>/info.json (full schema with params).

    Uses bsdtar (available on macOS + most Linux distros) since stdlib has no
    RPM/CPIO reader. Inner tgz extracted with tarfile.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["bsdtar", "-xf", str(rpm_path), "-C", str(work_dir)],
            check=True, capture_output=True, timeout=30,
        )
    except Exception:  # noqa: BLE001
        return None
    tgz = next(work_dir.rglob("*.tgz"), None)
    if tgz is None:
        return None
    try:
        with tarfile.open(tgz, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.endswith("/info.json") and m.name.count("/") <= 2:
                    f = tf.extractfile(m)
                    if f is None:
                        continue
                    return json.loads(f.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return None


def _repo_rpm(conn: sqlite3.Connection, only_missing_params: bool = True) -> tuple[int, list[str]]:
    """Backfill catalog connectors using info.json from public Fortinet RPMs.

    Targets connectors that need ingest. A connector needs ingest if EITHER:
      - it lacks params (the live API can't return params for uninstalled
        connectors -- but the RPM info.json has the full schema), OR
      - it has no rpm_fingerprint yet (so the diff layer can populate one).
    The fingerprint check inside the loop short-circuits the extract+ingest
    when the cached RPM matches what we already have in the DB.
    """
    if shutil.which("bsdtar") is None:
        return 0, ["bsdtar not found -- install libarchive (macOS: built-in; Linux: yum install bsdtar)"]
    index = _fetch_repo_index()
    if not index:
        return 0, ["repo connectors.json fetch failed"]

    RPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, str, str]] = []  # (name, version, rpm_full_name)
    for key, meta in index.items():
        name = meta.get("name")
        version = meta.get("version")
        rpm_full = meta.get("rpm_full_name")
        if not (name and version and rpm_full):
            continue
        if only_missing_params:
            row = conn.execute(
                "SELECT (SELECT COUNT(*) FROM operation_params p "
                "         WHERE p.connector_name = c.name) AS pc, "
                "       c.rpm_fingerprint "
                "FROM connectors c WHERE c.name = ?", (name,),
            ).fetchone()
            # Skip only when params present AND fingerprint already stamped.
            # That way the first incremental pass over the existing DB still
            # backfills fingerprints; subsequent runs short-circuit.
            if row and row[0] > 0 and row[1]:
                continue
        targets.append((name, version, rpm_full))

    upserts = 0
    skipped = 0
    errors: list[str] = []
    print(f"  repo: {len(targets)} connectors need RPM backfill")
    for i, (name, version, rpm_full) in enumerate(targets):
        if i and i % 50 == 0:
            print(f"    .. {i}/{len(targets)} processed ({upserts} upserts, {skipped} unchanged)")
        rpm_path = RPM_CACHE_DIR / rpm_full
        if not _download_rpm(rpm_full, rpm_path):
            # Index buildNumber stale -- resolve the actual file by prefix.
            alt = _resolve_rpm_by_prefix(name, version)
            if alt and alt != rpm_full:
                rpm_path = RPM_CACHE_DIR / alt
                if not _download_rpm(alt, rpm_path):
                    errors.append(f"{name}: download failed (tried {rpm_full} and {alt})")
                    continue
                rpm_full = alt
            else:
                errors.append(f"{name}: download failed (no prefix match for {rpm_full})")
                continue

        # Diff: if DB already has this exact RPM (same filename + size),
        # skip the extract/parse/ingest cycle entirely.
        fingerprint = f"{rpm_full}:{rpm_path.stat().st_size}"
        existing_fp = conn.execute(
            "SELECT rpm_fingerprint FROM connectors WHERE name = ?", (name,),
        ).fetchone()
        if existing_fp and existing_fp[0] == fingerprint:
            skipped += 1
            continue

        work_dir = RPM_CACHE_DIR / "_extract" / name
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        info = _extract_info_from_rpm(rpm_path, work_dir)
        shutil.rmtree(work_dir, ignore_errors=True)
        if not info or not info.get("name"):
            errors.append(f"{name}: info.json not found in RPM")
            continue
        # info.json uses 'configuration' for connection config; live API uses 'config_schema'.
        if "config_schema" not in info and "configuration" in info:
            info["config_schema"] = {"fields": info.get("configuration") or []}
        upsert_connector_detail(conn, info, source="fortinet_repo_rpm")
        conn.execute(
            "UPDATE connectors SET rpm_fingerprint = ? WHERE name = ?",
            (fingerprint, name),
        )
        record_verification(
            conn, kind="connector", key=name,
            method="fortinet_repo_rpm", status="tested_pass",
            notes=f"rpm={rpm_full}",
        )
        upserts += 1

    record_verification(
        conn, kind="api_endpoint",
        key=f"GET {FORTINET_REPO_INDEX}",
        method="fortinet_repo_rpm", status="tested_pass",
        notes=f"index_size={len(index)} backfilled={upserts}",
    )
    print(f"  repo: {upserts} connectors backfilled from RPMs")
    return upserts, errors


# ----------------------- local fallback -----------------------

def _local(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    if not RPM_EXTRACTED_DIR.exists():
        return 0, [f"missing {RPM_EXTRACTED_DIR}"]
    count = 0
    errors: list[str] = []
    for info_path in RPM_EXTRACTED_DIR.rglob("info.json"):
        try:
            rec = json.loads(info_path.read_text())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{info_path}: {e!r}")
            continue
        if not isinstance(rec, dict) or not rec.get("name"):
            continue
        # rpm info.json uses 'configuration' for connection config vs.
        # 'config_schema' from the live API. Normalize.
        if "config_schema" not in rec and "configuration" in rec:
            rec["config_schema"] = {"fields": rec.get("configuration") or []}
        upsert_connector_detail(conn, rec, source="rpm_info_json")
        # Override the connector source_path so we know where it came from.
        conn.execute(
            "UPDATE connectors SET source_path = ? WHERE name = ?",
            (str(info_path), rec["name"]),
        )
        count += 1
    return count, errors


# ----------------------- entry -----------------------

def main() -> int:
    warnings.filterwarnings("ignore")  # silence InsecureRequestWarning
    cfg = _env.get_config()
    sources = []
    if cfg.is_live():
        sources.append(Path(cfg.base_url + "/api/integration/connectors/"))

    with probe_session(PROBE_NAME, sources) as conn:
        # Incremental by default: INSERT OR REPLACE + rpm_fingerprint diff
        # in _repo_rpm let re-runs skip unchanged connectors. To force a full
        # rebuild, delete data/fsr_reference.db and re-run.
        pass

        live_count, live_errs = (0, [])
        catalog_count, catalog_errs = (0, [])
        if cfg.is_live():
            live_count, live_errs = _live(conn)
            catalog_count, catalog_errs = _live_catalog(conn)
            sources.append(Path(cfg.base_url + "/api/query/solutionpacks"))

        # Repo-RPM backfill: catalog connectors that came back without params
        # (the live integrations service 404s for uninstalled connectors).
        # info.json inside each public Fortinet RPM has the full schema.
        repo_count, repo_errs = _repo_rpm(conn, only_missing_params=True)
        if repo_count:
            sources.append(Path(FORTINET_REPO_INDEX))

        local_count, local_errs = (0, [])
        if not cfg.is_live() or (live_count == 0 and catalog_count == 0 and repo_count == 0):
            local_count, local_errs = _local(conn)
            sources.append(RPM_EXTRACTED_DIR)

        notes = json.dumps({
            "live_count": live_count,
            "catalog_count": catalog_count,
            "repo_count": repo_count,
            "local_count": local_count,
            "errors": (live_errs + catalog_errs + repo_errs + local_errs)[:30],
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] live={live_count}  catalog={catalog_count}  "
              f"repo={repo_count}  local={local_count}  "
              f"errors={len(live_errs)+len(catalog_errs)+len(repo_errs)+len(local_errs)}")
        for e in (live_errs + catalog_errs + repo_errs + local_errs)[:10]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
