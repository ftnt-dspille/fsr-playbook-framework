"""What fields a module has -- the one lookup every record check shares.

Four places used to ask the store this question with their own SQL (the trigger
field validator, the resource picklist rewriter, and two verify helpers), and
all four got the same wrong answer for the same reason: ``module_fields`` is
filled from ``staging_model_metadatas.attributes``, and that list omits the
fields the platform adds to every record. A filter on ``createDate`` or a write
to ``recordTags`` -- both on thousands of shipped playbook steps -- read as
"unknown field", so every field check had to stay a warning, and a genuinely
invented field (``slaDueDate``) was a warning too and shipped.

Answer it once, here, and include those implicit fields.

Severity follows provenance: a catalog warmed from the target box
(``_catalog_meta`` carries its ``base_url``) is that box's actual schema, so a
field it lacks will not exist at run time either -- an error. An unstamped
catalog is a generic snapshot a Solution Pack or custom field may be missing
from -- a warning. See :func:`catalog_is_instance`.
"""
from __future__ import annotations

import sqlite3

# Fields every record carries that the module metadata's `attributes` list does
# not declare. Measured against the reference corpus: each is written or
# filtered by real shipped playbook steps on modules whose `module_fields` rows
# lack it (recordTags 165 steps, id 139, tenant 107, owners 100, createDate 73,
# systemAssignedQueue 56, createUser/modifyDate/modifyUser 54 each). Some are
# gated by module flags (`taggable`, `ownable`, `trackable`, `queueable`) the
# store does not keep; accepting them on every module trades a rare miss for
# never blocking a valid step.
SYSTEM_FIELDS: frozenset[str] = frozenset({
    "id", "@id", "@type", "uuid", "tenant",
    "createDate", "modifyDate", "createUser", "modifyUser",
    "owners", "users", "recordTags", "systemAssignedQueue",
})


# Names authors reach for that are not the platform's field, where spelling
# similarity cannot find the right one. Every tag filter and tag write in the
# reference corpus uses `recordTags` (none use `tags`); a filter on `tags`
# compiles, runs, and matches nothing.
FIELD_HINTS: dict[str, str] = {
    "tags": ("use `recordTags` -- tags are filtered as "
             "`field: recordTags, operator: in, "
             "value: ['/api/3/tags/<name>']`"),
}


def module_name(ref: object) -> str | None:
    """The bare module name from a module reference as steps carry it.

    Accepts ``incidents``, ``/api/3/incidents``, and ``incidents?$limit=100``
    (find_record appends query flags to the module). ``None`` for anything that
    is not a static name -- a Jinja expression resolves at run time.
    """
    if not isinstance(ref, str) or not ref or "{{" in ref or "{%" in ref:
        return None
    name = ref.split("?", 1)[0].rstrip("/")
    if name.startswith("/api/"):
        name = name.rsplit("/", 1)[-1]
    if name.startswith("upsert/"):
        name = name[len("upsert/"):]
    return name or None


def declared_fields(conn: sqlite3.Connection, module: str) -> set[str]:
    """Fields the store declares for `module`. Empty when un-warmed."""
    try:
        return {r[0] for r in conn.execute(
            "SELECT field_name FROM module_fields WHERE module_name=?",
            (module,))}
    except sqlite3.Error:
        return set()


def field_names(conn: sqlite3.Connection, module: str) -> set[str]:
    """Every field a record of `module` can carry: declared ∪ system.

    Empty when the store knows nothing about the module, so callers keep
    their "can't check, don't flag" gate on an un-warmed catalog.
    """
    declared = declared_fields(conn, module)
    return declared | SYSTEM_FIELDS if declared else set()


def picklist_fields_holding(
    conn: sqlite3.Connection, module: str, value: str, *, exclude: str = "",
) -> list[str]:
    """Other picklist fields on `module` whose list contains `value`.

    The cross-field hint for the commonest picklist mistake: the value is real,
    it just belongs to a sibling field (``state: Open`` -- ``Open`` is an
    ``IncidentStatus``, the field is ``status``).
    """
    try:
        rows = conn.execute(
            "SELECT DISTINCT mf.field_name FROM module_fields mf "
            "JOIN picklists p ON p.list_name = mf.picklist_name "
            "WHERE mf.module_name=? AND (p.item_value=? OR p.item_iri=?) "
            "AND mf.field_name != ? ORDER BY mf.field_name",
            (module, value, value, exclude)).fetchall()
    except sqlite3.Error:
        return []
    return [r[0] for r in rows]


def catalog_is_instance(conn: sqlite3.Connection) -> bool:
    """True when the module schema was read from a specific box.

    That is when "not in the catalog" means "not on the box", which is what
    lets a missing field be an error rather than a guess. Two markers say so:
    ``base_url_hash`` (a dev/CLI warm stamps the URL it read) and
    ``modules_warmed_at`` (the connector's on-platform warm, which has no URL
    to stamp -- it reaches its own appliance -- but read that appliance's
    modules). Checking only the first left every real box on warnings.
    """
    try:
        from . import _catalog_meta
        return bool(_catalog_meta.get(conn, "base_url_hash")
                    or _catalog_meta.get(conn, "modules_warmed_at"))
    except sqlite3.Error:
        return False
