"""Pivot keys: values a tool result revealed that the turn never searched with.

A weak model stops once the first hop gives a plausible story: a result names a
host, an account, an address, and the turn ends without sending that value to the
source that holds its activity. This module reads the VALUES a run_op result
revealed by type, and reports the ones no call this turn used as a search key.

Typing, never wording:
  * address / hash   IPv4 and file-hash shapes (the evidence scorer's patterns)
  * domain           dotted labels ending in an alphabetic label
  * name             an identifier-shaped token: letters and digits joined by
                     ``-``, ``_`` or ``.``, with a digit or two joiners (a host,
                     a service account). Shape only, so it holds in any language
                     and inside any prose or log line.
  * entity           the value of a result field whose NAME is an entity field
                     (account, owner, host, user ...). Field names are schema,
                     not sentences; values are compared as opaque tokens.

No sentence is ever parsed for meaning. Results of threat-intel connectors are
not read: a reputation report lists a hundred related indicators that belong to
the internet, not to this environment.
"""
from __future__ import annotations

import json
import re
from typing import Any

_MAX_PER_RESULT = 12
_MAX_DEPTH = 7
_MAX_ROWS = 60
_MIN_LEN = 3
_MAX_LEN = 80

# Normalised (lowercase alphanumerics only) result-field names whose value names
# a person, an account or a machine.
ENTITY_FIELDS = frozenset({
    "samaccountname", "username", "user", "userprincipalname", "accountname",
    "account", "owner", "ownedby", "assignedto", "managedby", "manager",
    "callerid", "requestedfor", "openedby", "hostname", "host", "computername",
    "dnshostname", "devname", "cmdbci", "srcuser", "dstuser", "targetuser",
    "loginname", "email", "sender", "recipient", "device", "asset",
})

_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._@\-]*[A-Za-z0-9])?")
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_HASH = re.compile(r"^(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_DOMAIN = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)+$")

#: Rank when a result reveals more than fit: typed entity fields first.
_RANK = {"entity": 0, "address": 1, "hash": 2, "domain": 3, "name": 4}


def _norm_key(k: Any) -> str:
    return "".join(ch for ch in str(k).lower() if ch.isalnum())


def _shape(tok: str) -> str | None:
    """The type of one token by shape alone, or None."""
    if len(tok) < _MIN_LEN or len(tok) > _MAX_LEN or _UUID.match(tok):
        return None
    if _IPV4.match(tok):
        return "address" if all(int(p) <= 255 for p in tok.split(".")) else None
    if _HASH.match(tok):
        return "hash"
    if tok[0].isdigit():
        return None  # a date, a time, a version, a bare number
    if "@" in tok:
        return "entity" if _DOMAIN.match(tok.split("@", 1)[1]) else None
    if _DOMAIN.match(tok):
        return "domain"
    if _NAME.match(tok):
        joiners = sum(tok.count(c) for c in "-_.")
        if any(c.isdigit() for c in tok) or joiners >= 2:
            return "name"
    return None


def pivot_keys(result: Any) -> list[dict[str, str]]:
    """Values a run_op result revealed, ``[{"v": value, "t": type}]``, typed,
    deduplicated and bounded. Empty for an error or an empty answer."""
    found: dict[str, dict[str, str]] = {}

    def add(v: str, t: str) -> None:
        key = v.lower()
        prior = found.get(key)
        if prior is None or _RANK[t] < _RANK[prior["t"]]:
            found[key] = {"v": v, "t": t}

    def entity(v: Any) -> None:
        if isinstance(v, str):
            s = v.strip()
            if _MIN_LEN <= len(s) <= _MAX_LEN and any(c.isalpha() for c in s):
                add(s, "entity")
        elif isinstance(v, list):
            for x in v[:5]:
                entity(x)
        elif isinstance(v, dict):
            entity(v.get("name") or v.get("value") or v.get("display_value"))

    def walk(node: Any, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if _norm_key(k) in ENTITY_FIELDS and isinstance(v, (str, list, dict)):
                    entity(v)
                else:
                    walk(v, depth + 1)
        elif isinstance(node, list):
            for x in node[:_MAX_ROWS]:
                walk(x, depth + 1)
        elif isinstance(node, str):
            for tok in _TOKEN.findall(node[:4000]):
                t = _shape(tok)
                if t:
                    add(tok, t)

    walk(result, 0)
    ordered = sorted(found.values(), key=lambda d: _RANK[d["t"]])
    return ordered[:_MAX_PER_RESULT]


def _pieces(value: str) -> list[str]:
    """Search-sized pieces of a value, lowercased: "Kay Fenwick (kfenwick)"
    gives kay, fenwick, kfenwick; "wks-eng-31" stays whole."""
    return [t.lower() for t in _TOKEN.findall(value) if len(t) >= 4]


def used_as_key(value: str, haystack: str) -> bool:
    """True when the value, or any search-sized piece of it, appears in the text
    of the calls the turn searched with (``haystack``, lowercased)."""
    if value.lower() in haystack:
        return True
    return any(p in haystack for p in _pieces(value))


def call_text(args: Any) -> str:
    """What one call searched with, as lowercased text: a run_op's params (not
    the connector or op names), any other call's own arguments."""
    if isinstance(args, dict) and isinstance(args.get("params"), dict):
        args = args["params"]
    try:
        return json.dumps(args, default=str).lower()
    except Exception:  # noqa: BLE001
        return str(args).lower()
