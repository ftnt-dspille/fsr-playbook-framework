#!/usr/bin/env python3
"""Redact secret-looking values from harvested reference data.

The reference DBs are filled by probes that read playbooks, step arguments and
connector configs off a live appliance. Some of those carry real credentials
(an API key pair in a `SetAPIKeys` step, bearer tokens in HTTP headers, a
service-account password in a code snippet). The DBs are packaged into the
wheel and tracked on the public mirror, so the harvest must never store them.

One module, three uses:

* harvest time: the probes call `redact_text` / `redact_obj` on every snippet
  before the INSERT, so a fresh harvest cannot reintroduce a secret;
* build time: `redact_db` rewrites a finished DB in place (UPDATE every text
  cell, VACUUM so free pages drop the old bytes, then re-scan the raw bytes);
* test time: `find_secrets` is the detector the test suite runs over the
  committed DBs and `data/STEP_TYPES.md`.

What is redacted: PEM private and public key bodies, `Bearer` tokens, JWTs,
well-known API key shapes (Google, AWS, GitHub, Slack), and the value of any
key whose name says it is a secret (password, token, api key, authorization ...)
unless the value is empty, templated (`{{ ... }}`, `<...>`), a URL, or one of
the documented vendor placeholders (`changeme`, `fortinet`, ...), which are
vendor sample defaults, not credentials.

Run standalone:

    python scripts/secret_redact.py path/to.db [path/to/file.md ...] [--dry-run]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

KEY_PLACEHOLDER = "<redacted-sample-key>"
TOKEN_PLACEHOLDER = "<redacted-token>"
SECRET_PLACEHOLDER = "<redacted-secret>"

# A PEM block. The body is base64 plus either real newlines or the literal
# two-character `\n` of JSON-escaped text; at least 40 body chars, so prose
# that merely mentions the header ("should start with '-----BEGIN PRIVATE
# KEY-----' and end with ...") is left alone.
_PEM_BODY = r"(?:[A-Za-z0-9+/=]|\s|\\n|\\r){40,}"
PEM_RE = re.compile(
    r"(-----BEGIN ((?:[A-Z0-9]+ )*(?:PRIVATE|PUBLIC) KEY)-----)"
    + _PEM_BODY + r"(-----END \2-----)")

BEARER_RE = re.compile(r"(?i)(\bBearer\s+)(?!<redacted)[A-Za-z0-9_\-.=+/]{16,}")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}")
SHAPES = [
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),           # Google API key
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),         # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),        # GitHub token
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),        # Slack token
]

# A secret-named key. `\b`-less on purpose: `googleMapAPIkey`, `adminRpcPassword`.
SECRET_KEY_RE = re.compile(
    r"(?i)(?![\w-]*(?:time|status|bypass))(?:[\w-]*?)(pass(?:word|wd)?|secret|token|api_?key|private_?key|"
    r"authorization|credential|client_?secret|access_?key|auth_?key)")
# A session id / key in a JSON-RPC style body: only long opaque values count.
SESSION_KEY_RE = re.compile(r"(?i)^session(?:_?id|_?key)?$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_\-.=+/]{16,}$")


def _is_secret_key(k: str, v: str) -> bool:
    if SECRET_KEY_RE.search(k):
        return True
    if LITERAL_KEY_RE.search(k) and _is_literal_kv_secret(k, v):
        return True
    return bool(SESSION_KEY_RE.match(k)) and bool(_OPAQUE.match(v))


# A code literal: 'password': 'value'  /  password = "value"  (Python, JSON).
LITERAL_RE = re.compile(
    r"""(?P<k>(?:['"]?)(?<![A-Za-z_])(?![A-Za-z_]*(?:time|status|bypass|_type)(?![A-Za-z]))(?:[A-Za-z_]*(?:pass(?:word|wd)?|secret|token|api_?key|private_?key|client_?secret|access_?key)[A-Za-z_]*)(?:['"]?)\s*[:=]\s*)"""
    r"""(?P<q>['"])(?P<v>[^'"\\\n]{4,})(?P=q)""", re.I)

# Literal credentials under keys the rules above miss: passwords and session ids
# (`session_id`, `SessionID`, `adminPassword`, `adminRpcPassword`, `new_password`),
# and a bare `token` key. Plural counters (`completion_tokens`, `max_tokens`) and
# `tokenStatus` / `token_type` flags are not credentials and stay out.
LITERAL_KEY_RE = re.compile(
    r"(?i)(?![\w-]*(?:time|status|bypass|_type))(?:password|passwd|secret|api_?key|"
    r"(?<![A-Za-z])pass(?![A-Za-z])|(?<![A-Za-z])session(?![A-Za-z-])|"
    r"[A-Za-z]*session_?(?:id|key)(?![A-Za-z])|(?<![A-Za-z])token(?![A-Za-z]))")
# `key: 'value'`, `key = "value"`, and the same inside a JSON string (`\"key\": \"value\"`).
# The value is a quoted literal with no quote, backslash or newline inside.
LITERAL_KV_RE = re.compile(
    r"""(?P<k>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>\\?['"]?\s*[:=]\s*\\?)(?P<q>['"])(?P<v>[^'"\\\n]{1,400})\\?(?P=q)""")
def _is_literal_kv_secret(k: str, v: str) -> bool:
    """A secret-named key holding a literal string (not a template, angle placeholder or vendor default)."""
    return bool(LITERAL_KEY_RE.search(k)) and not _is_placeholder(v) \
        and not v.startswith("<redacted")


# Vendor sample defaults and obvious placeholders: left alone.
_PLACEHOLDER_VALUE = re.compile(
    r"(?is)^(?:changeme\S*|fortinet|fort!net|demo|password(?:@\d+)?|admin|test|dummy\S*|"
    r"example\S*|none|null|true|false|enabled?|disabled?|default|\*+|x+|<.*>|\{\{.*\}\}|"
    r"https?://\S*|notused|\s*)$")


# JSON Schema type keywords: `"session_id": "string"` in an operation's input schema
# declares a type; it is metadata, not a credential, and must stay in the schema.
_SCHEMA_TYPES = frozenset({"string", "integer", "number", "boolean", "object", "array"})


def _is_placeholder(value: str) -> bool:
    v = value.strip()
    return len(v) < 4 or bool(_PLACEHOLDER_VALUE.match(v)) or "{{" in v or v in _SCHEMA_TYPES


def _redact_header_value(v: str) -> str:
    """`Authorization` style value: keep the scheme, drop the credential."""
    parts = v.split(None, 1)
    if len(parts) == 2 and not _is_placeholder(parts[1]) and not parts[1].startswith("<redacted"):
        return f"{parts[0]} {TOKEN_PLACEHOLDER}"
    return v


def redact_text(s: str) -> str:
    """Redact secrets from a string (plain text or JSON-encoded text)."""
    if not s or not isinstance(s, str):
        return s
    s = PEM_RE.sub(lambda m: f"{m.group(1)}\\n{KEY_PLACEHOLDER}\\n{m.group(3)}"
                   if "\\n" in m.group(0) else
                   f"{m.group(1)}\n{KEY_PLACEHOLDER}\n{m.group(3)}", s)
    s = BEARER_RE.sub(lambda m: m.group(1) + TOKEN_PLACEHOLDER, s)
    s = JWT_RE.sub(TOKEN_PLACEHOLDER, s)
    for rx in SHAPES:
        s = rx.sub(SECRET_PLACEHOLDER, s)

    def lit(m: re.Match) -> str:
        if _is_placeholder(m.group("v")) or m.group("v").startswith("<redacted"):
            return m.group(0)
        return f"{m.group('k')}{m.group('q')}{SECRET_PLACEHOLDER}{m.group('q')}"
    # Only strings that are JSON documents are walked structurally by redact_obj;
    # code snippets embedded in them are handled here by the literal pattern.
    s = LITERAL_RE.sub(lit, s)

    def kv(m: re.Match) -> str:
        if not _is_literal_kv_secret(m.group("k"), m.group("v")):
            return m.group(0)
        full = m.group(0)
        vs, ve = m.start("v") - m.start(0), m.end("v") - m.start(0)
        return full[:vs] + SECRET_PLACEHOLDER + full[ve:]
    return LITERAL_KV_RE.sub(kv, s)


def redact_obj(o: Any) -> Any:
    """Redact a parsed JSON value (dict/list/str). Returns a new value."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, str) and _is_secret_key(str(k), v):
                if str(k).lower() == "authorization":
                    v = _redact_header_value(v)
                elif not _is_placeholder(v) and not v.startswith("<redacted"):
                    v = SECRET_PLACEHOLDER
            out[k] = redact_obj(v)
        return out
    if isinstance(o, list):
        return [redact_obj(v) for v in o]
    if isinstance(o, str):
        t = o.lstrip()[:1]
        if t in ("{", "[") and len(o) > 1:        # JSON carried inside a string
            try:
                parsed = json.loads(o)
            except (ValueError, TypeError):
                parsed = None
            if parsed is not None:
                new = redact_obj(parsed)
                return o if new == parsed else json.dumps(new)
        return redact_text(o)
    return o


def redact_json_text(s: str) -> str:
    """Redact a JSON document held as text, preserving non-JSON input."""
    if not isinstance(s, str) or not s:
        return s
    try:
        doc = json.loads(s)
    except (ValueError, TypeError):
        return redact_text(s)
    new = redact_obj(doc)
    return s if new == doc and redact_text(s) == s else _dump_like(s, new)


def _dump_like(orig: str, new: Any) -> str:
    # Keep compact vs pretty formatting stable so diffs and ordering survive.
    if "\n" in orig:
        return json.dumps(new, indent=2, sort_keys=False)
    sep = (", ", ": ") if ", " in orig[:200] or ": " in orig[:200] else (",", ":")
    return json.dumps(new, separators=sep)


def redact_any(s: str) -> str:
    """Cell-level entry point: JSON-aware first, then the text patterns."""
    return redact_text(redact_json_text(s))


# ------------------------------------------------------------------ detection

_DETECT = [
    ("private-key", re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?:[A-Za-z0-9+/=]|\s|\\n|\\r){40,}")),
    ("public-key", re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PUBLIC KEY-----(?:[A-Za-z0-9+/=]|\s|\\n|\\r){40,}")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+(?!<redacted)[A-Za-z0-9_\-.=+/]{16,}")),
    ("jwt", JWT_RE),
    ("api-key-shape", re.compile("|".join(p.pattern for p in SHAPES))),
]


def find_secrets(text: str) -> list[str]:
    """Names of the secret patterns present in `text` (empty when clean)."""
    hits = [n for n, rx in _DETECT if rx.search(text)]
    for m in LITERAL_RE.finditer(text):
        if not _is_placeholder(m.group("v")) and not m.group("v").startswith("<redacted"):
            hits.append("secret-literal")
            break
    for m in LITERAL_KV_RE.finditer(text):
        if _is_literal_kv_secret(m.group("k"), m.group("v")):
            hits.append("secret-literal-kv")
            break
    return hits


def find_secrets_in_obj(o: Any, _key: str = "") -> list[str]:
    """Like `find_secrets` but also flags secret-named keys with real values."""
    hits: list[str] = []
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and _is_secret_key(str(k), v):
                probe = v.split(None, 1)[1] if str(k).lower() == "authorization" and " " in v else v
                if not _is_placeholder(probe) and not probe.startswith("<redacted"):
                    hits.append(f"secret-key:{k}")
            hits += find_secrets_in_obj(v, str(k))
    elif isinstance(o, list):
        for v in o:
            hits += find_secrets_in_obj(v, _key)
    elif isinstance(o, str):
        if o.lstrip()[:1] in ("{", "[") and len(o) > 1:
            try:
                hits += find_secrets_in_obj(json.loads(o), _key)
            except (ValueError, TypeError):
                pass
        hits += find_secrets(o)
    return hits


def find_secrets_in_cell(s: str) -> list[str]:
    try:
        doc = json.loads(s)
    except (ValueError, TypeError):
        return find_secrets(s)
    return sorted(set(find_secrets_in_obj(doc) + find_secrets(s)))


# ------------------------------------------------------------------ DB / file

def _tables(db: sqlite3.Connection) -> list[str]:
    virtual = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE sql LIKE 'CREATE VIRTUAL TABLE%'")]
    shadow = tuple(f"{v}_" for v in virtual)
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        if r[0] not in virtual and not r[0].startswith(shadow)]


def scan_db(path: str | Path) -> list[tuple[str, str, int, list[str]]]:
    """(table, column, rowid, hits) for every cell that still holds a secret."""
    out = []
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.text_factory = str
    try:
        for t in _tables(db):
            cols = [r[1] for r in db.execute(f'PRAGMA table_info("{t}")')]
            for c in cols:
                for rowid, v in db.execute(
                        f'SELECT rowid, "{c}" FROM "{t}" WHERE typeof("{c}")=\'text\''):
                    h = find_secrets_in_cell(v)
                    if h:
                        out.append((t, c, rowid, h))
    finally:
        db.close()
    return out


def redact_db(path: str | Path, *, dry_run: bool = False, quiet: bool = False) -> int:
    """Redact every text cell in place, VACUUM, then re-scan the raw bytes.
    Returns the number of cells changed."""
    path = Path(path)
    db = sqlite3.connect(path)
    db.text_factory = str
    changed = 0
    for t in _tables(db):
        for c in [r[1] for r in db.execute(f'PRAGMA table_info("{t}")')]:
            rows = db.execute(
                f'SELECT rowid, "{c}" FROM "{t}" WHERE typeof("{c}")=\'text\'').fetchall()
            for rowid, v in rows:
                new = redact_any(v)
                if new != v:
                    changed += 1
                    if not dry_run:
                        db.execute(f'UPDATE "{t}" SET "{c}"=? WHERE rowid=?', (new, rowid))
        if not dry_run:
            db.commit()
    if dry_run:
        db.close()
        if not quiet:
            print(f"{path.name}: {changed} cell(s) would change (dry run)")
        return changed
    db.commit()
    db.execute("VACUUM")     # free pages keep the old bytes until the file is rebuilt
    db.commit()
    db.close()
    raw = path.read_bytes().decode("latin-1")
    residue = [n for n, rx in _DETECT if rx.search(raw)]
    if residue:
        raise SystemExit(f"{path}: secrets survive redaction + VACUUM: {', '.join(residue)}")
    if not quiet:
        print(f"{path.name}: redacted {changed} cell(s); raw-byte scan clean")
    return changed


def redact_file(path: str | Path, *, dry_run: bool = False) -> bool:
    """Redact a text file in place (e.g. data/STEP_TYPES.md). True if changed."""
    p = Path(path)
    old = p.read_text(encoding="utf-8")
    new = redact_text(old)
    if new != old and not dry_run:
        p.write_text(new, encoding="utf-8")
    return new != old


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 2
    dry = "--dry-run" in argv
    for a in args:
        if a.endswith((".db", ".sqlite")):
            redact_db(a, dry_run=dry)
        else:
            print(f"{a}: {'changed' if redact_file(a, dry_run=dry) else 'clean'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
