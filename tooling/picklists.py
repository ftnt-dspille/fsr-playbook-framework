"""Picklist resolution: name discovery, value lookup, IRI mapping.

Replaces the runner's hardcoded `_MODULE_PICKLIST_FIELDS` table. Used by:
  - e2e/runner.py    (setup record insert + mutate PUT field resolution)
  - mcp_server.py    (picklist authoring tools exposed to agents)
  - compiler         (future: compile-time validation of picklist values)

Discovery strategy for `(module, field) → picklist_name`:
  1. Check on-disk cache (store/picklist_name_map.json).
  2. Read valid item values from local DB (`module_fields.picklist_options`).
  3. Live-fetch all picklist names from `/api/3/picklist_names`.
  4. Score each picklist by Jaccard overlap of itemValues vs. valid values;
     the best non-trivial match wins.
  5. Persist the answer.
Heuristic candidates (`<ModuleSingular><Field>`, `<Field>`) are tried first
to short-circuit the scan when they happen to exist.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "fsr_reference.db"
CACHE_PATH = REPO_ROOT / "data" / "picklist_name_map.json"

# In-process caches.
_iri_cache: dict[str, str] = {}                   # "ListName:itemvalue" → IRI
_values_cache: dict[str, list[dict]] = {}         # "ListName" → [{itemValue, uuid}]
_names_cache: list[str] | None = None             # all picklist names (live)
_module_field_pl: dict[str, str] | None = None    # "module.field" → picklist_name


# ---------- on-disk cache for (module, field) → picklist_name ----------

def _load_cache() -> dict[str, str]:
    global _module_field_pl
    if _module_field_pl is not None:
        return _module_field_pl
    if CACHE_PATH.exists():
        try:
            _module_field_pl = json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            _module_field_pl = {}
    else:
        _module_field_pl = {}
    return _module_field_pl


def _save_cache() -> None:
    if _module_field_pl is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_module_field_pl, indent=2, sort_keys=True))


# ---------- local DB: valid values per (module, field) ----------

def valid_values(module: str, field: str) -> list[str]:
    """Return cached itemValues from store/fsr_reference.db (offline)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT picklist_options FROM module_fields "
            "WHERE module_name=? AND field_name=?",
            (module, field),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return []
    try:
        opts = json.loads(row[0])
        return [str(v) for v in opts] if isinstance(opts, list) else []
    except Exception:  # noqa: BLE001
        return []


# ---------- live: picklist names + values ----------

def list_picklist_names(client) -> list[str]:
    global _names_cache
    if _names_cache is not None:
        return _names_cache
    r = client.session.get(
        client.base_url + "/api/3/picklist_names?$limit=500",
        verify=client.verify_ssl,
    )
    if r.status_code != 200:
        _names_cache = []
        return _names_cache
    _names_cache = sorted({
        m.get("name") for m in (r.json().get("hydra:member") or [])
        if m.get("name")
    })
    return _names_cache


def picklist_values(client, picklist_name: str) -> list[dict]:
    """List items of a picklist as [{itemValue, uuid, iri}, ...]."""
    if picklist_name in _values_cache:
        return _values_cache[picklist_name]
    qs = urllib.parse.urlencode({"listName.name": picklist_name, "$limit": 200})
    r = client.session.get(client.base_url + f"/api/3/picklists?{qs}",
                           verify=client.verify_ssl)
    if r.status_code != 200:
        return []
    out = []
    for m in r.json().get("hydra:member") or []:
        u = m.get("uuid")
        out.append({
            "itemValue": m.get("itemValue"),
            "uuid": u,
            "iri": f"/api/3/picklists/{u}" if u else None,
            "ordinal": m.get("ordinal"),
        })
    _values_cache[picklist_name] = out
    return out


# ---------- discovery: (module, field) → picklist_name ----------

def picklist_name_for(client, module: str, field: str) -> str | None:
    cache = _load_cache()
    key = f"{module}.{field}"
    if key in cache:
        return cache[key] or None
    valid = set(v.lower() for v in valid_values(module, field))
    if not valid:
        return None
    # Heuristic candidates first.
    singular = module.rstrip("s").capitalize() if module else ""
    field_cap = field[:1].upper() + field[1:] if field else ""
    candidates = [
        f"{singular}{field_cap}",                # AlertStatus
        field_cap,                               # Status
        f"{singular} {field_cap}",               # Alert Status
    ]
    names = list_picklist_names(client)
    for cand in candidates:
        if cand in names and _matches(client, cand, valid):
            cache[key] = cand
            _save_cache()
            return cand
    # Fallback: best Jaccard overlap.
    best_name, best_score = None, 0.0
    for n in names:
        items = {(it["itemValue"] or "").lower() for it in picklist_values(client, n)}
        if not items:
            continue
        inter = len(items & valid)
        if not inter:
            continue
        union = len(items | valid)
        score = inter / union
        if score > best_score:
            best_score, best_name = score, n
    if best_name and best_score >= 0.5:  # require strong overlap
        cache[key] = best_name
        _save_cache()
        return best_name
    cache[key] = ""  # negative cache
    _save_cache()
    return None


def _matches(client, picklist_name: str, valid_lower: set[str]) -> bool:
    items = {(it["itemValue"] or "").lower()
             for it in picklist_values(client, picklist_name)}
    if not items:
        return False
    # Accept if at least 50% of declared valid values appear.
    overlap = len(items & valid_lower)
    return overlap >= max(1, len(valid_lower) // 2)


# ---------- IRI resolution ----------

def resolve_iri(client, value: str, *, picklist_name: str | None = None,
                module: str | None = None, field: str | None = None) -> str | None:
    """Resolve a friendly value (e.g., 'High') to '/api/3/picklists/<uuid>'.

    Accepts either an explicit `picklist_name`, or `(module, field)` to
    auto-discover. Already-IRI strings pass through unchanged. Returns
    None if the value isn't found in the resolved picklist.
    """
    if not isinstance(value, str):
        return None
    if value.startswith("/api/"):
        return value
    if picklist_name is None:
        if not (module and field):
            return None
        picklist_name = picklist_name_for(client, module, field)
        if not picklist_name:
            return None
    cache_key = f"{picklist_name}:{value.lower()}"
    if cache_key in _iri_cache:
        return _iri_cache[cache_key]
    for it in picklist_values(client, picklist_name):
        if (it.get("itemValue") or "").lower() == value.lower():
            iri = it.get("iri")
            if iri:
                _iri_cache[cache_key] = iri
            return iri
    return None


def resolve_module_fields(client, module: str, fields: dict[str, Any]
                          ) -> dict[str, Any]:
    """Walk a record-fields dict, resolving any picklist-typed field whose
    value is a friendly string (not already an IRI). Fields not flagged
    as picklists in module_fields are passed through unchanged.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT field_name, type FROM module_fields WHERE module_name=?",
            (module,),
        ).fetchall()
    finally:
        conn.close()
    pl_fields = {r[0] for r in rows if r[1] == "picklists"}
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if (k in pl_fields and isinstance(v, str)
                and not v.startswith("/api/")):
            iri = resolve_iri(client, v, module=module, field=k)
            if iri:
                out[k] = iri
                continue
        out[k] = v
    return out
