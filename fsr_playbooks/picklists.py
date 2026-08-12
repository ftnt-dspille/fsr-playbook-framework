"""Picklist lookup for the authoring tools -- reference-DB first, live optional.

The MCP picklist tools used to `from picklists import ...` / `from
recipes.prechecks import ...`, which resolve only when this repo's `tooling/`
directory happens to be on `sys.path`. It never is on an appliance, so all
five picklist tools were dead there: every call raised ImportError or returned
"FSR instance not configured", and the agent burned ~5 calls per turn
rediscovering that. This module ships INSIDE `fsr_playbooks`, so the tools
work wherever the package does.

Order of resolution, and why:

1. **The reference store** (`picklists`, `module_fields`). `warmup` writes the
   TARGET appliance's rows here, so this is both offline and instance-correct.
   The compiler already resolves picklist tokens from exactly these tables
   (`compiler/resolver/picklists.py`), so the authoring tools now agree with
   the compiler by construction -- previously they consulted different
   sources and could disagree.
2. **The live instance**, when the store has no rows for the list. Results are
   written back into the store when it is writable, so the second call is
   offline.
3. **Neither** -> the caller raises `NoPicklistData`, which carries what was
   tried and what would fix it. Never a bare empty list (AGENT_HARDENING_PLAN
   §H): "no values" and "nowhere to look" are different answers.

The slim shipped catalog carries `(list_name, item_value)` for the built-in
picklists with `item_iri` blanked -- the values are globally stable, the
IRIs are per-install. So value *validation* works out of the box; IRI *resolution*
still needs a warmed store or a live instance, and says so.
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse

_PICKLIST_IRI_RE = re.compile(r"^/api/3/picklists/[0-9a-fA-F-]{32,}$")


class NoPicklistData(Exception):
    """No picklist source could answer -- store empty AND no live instance.

    Carries `code`/`message`/`suggestions` so a tool can hand it straight to
    `_err()` instead of inventing prose at each call site.
    """

    def __init__(self, what: str, live_tried: bool):
        self.code = "no_picklist_data"
        self.what = what
        self.message = (
            "no picklist data available for " + what + ": the reference "
            "store holds no picklist rows"
            + (" and the live instance returned none"
               if live_tried else
               " and no FortiSOAR instance is configured")
            + "."
        )
        self.suggestions = [
            "run `warmup` against the target appliance to populate the "
            "`picklists` table (this is the offline, instance-correct path)",
            "or configure FSR_BASE_URL + FSR_USERNAME/FSR_PASSWORD (or "
            "FSR_API_KEY) so the value can be fetched live",
        ]
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"ok": False, "code": self.code, "message": self.message,
                "suggestions": self.suggestions}


# ---------------------------------------------------------------------------
# Reference store
# ---------------------------------------------------------------------------

def _store_names(conn: sqlite3.Connection) -> list:
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT list_name FROM picklists "
            "WHERE list_name IS NOT NULL ORDER BY list_name")]
    except sqlite3.Error:
        return []


def _store_items(conn: sqlite3.Connection, name: str) -> list:
    try:
        rows = conn.execute(
            "SELECT item_value, item_iri FROM picklists WHERE list_name=? "
            "ORDER BY item_value", (name,)).fetchall()
    except sqlite3.Error:
        return []
    out = []
    for value, iri in rows:
        uuid = iri.rsplit("/", 1)[-1] if iri else None
        out.append({"itemValue": value, "uuid": uuid, "iri": iri})
    return out


def _store_write_items(conn: sqlite3.Connection, name: str,
                       items: list) -> None:
    """Cache live rows into the store. Best-effort: a read-only DB on an
    appliance must degrade to "live every time", never to a failed tool."""
    try:
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO picklists "
                "(list_name, item_value, item_iri) VALUES (?, ?, ?)",
                [(name, it.get("itemValue"), it.get("iri")) for it in items
                 if it.get("itemValue")],
            )
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------------------
# Live instance
# ---------------------------------------------------------------------------

def _live_names(client) -> list:
    if client is None:
        return []
    try:
        r = client.session.get(
            client.base_url + "/api/3/picklist_names?$limit=500",
            verify=client.verify_ssl)
        if r.status_code != 200:
            return []
        return sorted({m.get("name")
                       for m in (r.json().get("hydra:member") or [])
                       if m.get("name")})
    except Exception:  # noqa: BLE001 -- a network blip is "no live data"
        return []


def _live_items(client, name: str) -> list:
    if client is None:
        return []
    qs = urllib.parse.urlencode({"listName.name": name, "$limit": 200})
    try:
        r = client.session.get(client.base_url + "/api/3/picklists?" + qs,
                               verify=client.verify_ssl)
        if r.status_code != 200:
            return []
        members = r.json().get("hydra:member") or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in members:
        u = m.get("uuid")
        out.append({"itemValue": m.get("itemValue"), "uuid": u,
                    "iri": "/api/3/picklists/" + u if u else None,
                    "ordinal": m.get("ordinal")})
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def picklist_names(conn: sqlite3.Connection, client=None) -> dict:
    """`{names, count, source}`. Raises NoPicklistData when nothing answers."""
    names = _store_names(conn)
    if names:
        return {"names": names, "count": len(names), "source": "reference_db"}
    names = _live_names(client)
    if names:
        return {"names": names, "count": len(names), "source": "live"}
    raise NoPicklistData("the picklist name list", live_tried=client is not None)


def picklist_items(conn: sqlite3.Connection, name: str, client=None) -> dict:
    """`{name, items, count, source}` for one picklist.

    A name that is simply absent from a populated store is a *different*
    answer from an empty store -- the first gets near-matches, the second
    raises. Conflating them is how "unknown picklist" reads as "no data".
    """
    items = _store_items(conn, name)
    if items:
        return {"name": name, "items": items, "count": len(items),
                "source": "reference_db"}
    items = _live_items(client, name)
    if items:
        _store_write_items(conn, name, items)
        return {"name": name, "items": items, "count": len(items),
                "source": "live"}
    known = _store_names(conn) or _live_names(client)
    if not known:
        raise NoPicklistData("picklist " + repr(name),
                             live_tried=client is not None)
    import difflib
    near = difflib.get_close_matches(name, known, n=5, cutoff=0.4)
    return {"name": name, "items": [], "count": 0, "source": "reference_db",
            "unknown_picklist": True, "near": near,
            "note": ("no picklist named " + repr(name) + " in this instance"
                     + (" -- did you mean " + ", ".join(near) + "?" if near
                        else " (call list_picklists for the full list)"))}


def valid_values(conn: sqlite3.Connection, module: str, field: str) -> list:
    """Offline itemValues for a module field, from `module_fields`."""
    try:
        row = conn.execute(
            "SELECT picklist_options FROM module_fields "
            "WHERE module_name=? AND field_name=?", (module, field)).fetchone()
    except sqlite3.Error:
        return []
    if not row or not row[0]:
        return []
    try:
        opts = json.loads(row[0])
    except (ValueError, TypeError):
        return []
    return [str(v) for v in opts] if isinstance(opts, list) else []


def picklist_name_for(conn: sqlite3.Connection, module: str, field: str,
                      client=None) -> str | None:
    """Which picklist backs `module.field`.

    `module_fields.picklist_name` is the recorded answer; when it is absent we
    score every known picklist by value overlap with the field's cached
    options, which is how the old `tooling/picklists.py` discovered a name
    without a live round-trip per guess.
    """
    try:
        row = conn.execute(
            "SELECT picklist_name FROM module_fields "
            "WHERE module_name=? AND field_name=?", (module, field)).fetchone()
    except sqlite3.Error:
        row = None
    if row and row[0]:
        return str(row[0])

    values = {v.lower() for v in valid_values(conn, module, field)}
    if not values:
        return None
    best_name, best_score = None, 0.0
    for name in _store_names(conn) or _live_names(client):
        items = {(it.get("itemValue") or "").lower()
                 for it in _store_items(conn, name) or _live_items(client, name)}
        items.discard("")
        if not items:
            continue
        overlap = len(values & items) / float(len(values | items))
        if overlap > best_score:
            best_name, best_score = name, overlap
    # Below half-overlap the "match" is coincidence -- two picklists sharing
    # 'High'. Returning a wrong name is worse than returning none: the caller
    # resolves against it and gets a confidently wrong IRI.
    return best_name if best_score >= 0.5 else None


def resolve_iri(conn: sqlite3.Connection, value: str, picklist_name: str,
                client=None) -> dict:
    """Friendly value -> `/api/3/picklists/<uuid>`.

    `{ok, iri, source}` on a hit; on a miss `{ok: False, valid_values,
    suggestions}` so the caller can self-correct. Raises NoPicklistData only
    when there was nowhere to look.
    """
    if value.startswith("/api/3/") and _PICKLIST_IRI_RE.match(value):
        return {"ok": True, "iri": value, "picklist_name": picklist_name,
                "value": value, "source": "passthrough"}

    found = picklist_items(conn, picklist_name, client)
    items = found.get("items") or []
    if found.get("unknown_picklist"):
        return {"ok": False, "picklist_name": picklist_name, "value": value,
                "code": "unknown_picklist", "near": found.get("near"),
                "message": found.get("note")}

    vl = value.strip().lower()
    for it in items:
        if (it.get("itemValue") or "").lower() == vl:
            iri = it.get("iri")
            if iri:
                return {"ok": True, "iri": iri, "value": it.get("itemValue"),
                        "picklist_name": picklist_name,
                        "source": found.get("source")}
            # The value is real but this store carries no IRI for it -- the
            # slim shipped catalog NULLs them because IRIs are per-install.
            # Say that, rather than reporting the value as invalid.
            return {"ok": False, "code": "iri_unavailable",
                    "picklist_name": picklist_name, "value": it.get("itemValue"),
                    "value_is_valid": True,
                    "message": (repr(value) + " is a valid " + picklist_name
                                + " value, but this catalog has no IRI for it "
                                "-- picklist IRIs are per-install."),
                    "suggestions": [
                        "run `warmup` against the target appliance, or "
                        "configure a live FSR instance, to get the IRI",
                        "in YAML you can write {{ '" + str(it.get("itemValue"))
                        + "' | picklist('" + picklist_name + "') }} and let "
                        "the compiler resolve it at push time",
                    ]}

    valid = [it.get("itemValue") for it in items if it.get("itemValue")]
    suggestions = [v for v in valid
                   if v.lower().startswith(vl) or vl in v.lower()
                   or v.lower() in vl]
    return {"ok": False, "code": "invalid_value",
            "picklist_name": picklist_name, "value": value,
            "valid_values": valid, "suggestions": suggestions[:5],
            "source": found.get("source"),
            "message": (repr(value) + " is not a value of " + picklist_name
                        + "; valid: " + ", ".join(valid[:12] or ["(none)"]))}
