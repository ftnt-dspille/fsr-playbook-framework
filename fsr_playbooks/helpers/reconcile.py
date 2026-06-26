"""Set-diff reconciliation for ``code_snippet`` playbook steps.

Compare two record lists (e.g. FortiCloud/FortiCare assets vs ServiceNow CMDB
configuration items) by a shared key (e.g. serial number), classifying records
that exist on only one side and records present on both but with differing
field values.

Stdlib-only; returns a JSON-safe dict so it drops straight into step variables
and serializes into a playbook run's results without conversion.

Example::

    from fsr_playbooks.helpers import reconcile
    r = reconcile(forticloud_assets, snow_cis, key="serial", fields=["name", "location"])
    csv_rows = [{
        "serial": m["key"],
        "field": next(iter(m["fields"])),
        "value_a": next(iter(m["fields"].values()))["a"],
        "value_b": next(iter(m["fields"].values()))["b"],
    } for m in r["mismatches"]]

Assumes ``key`` is unique within each side; duplicate keys collapse to the
last record seen (reconciliation is between canonical, de-duplicated sources).
"""
from __future__ import annotations

from typing import Any


def _keyof(record: dict[str, Any], key: str) -> str:
    return str(record.get(key, ""))


def reconcile(
    source_a: list[dict[str, Any]],
    source_b: list[dict[str, Any]],
    key: str,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Reconcile two lists of dict records by a shared ``key`` field.

    Returns a JSON-safe dict with:

    - ``only_in_a``: records present in ``source_a`` whose ``key`` is absent
      from ``source_b``.
    - ``only_in_b``: the converse.
    - ``mismatches``: records present on both sides where at least one
      compared field differs. Each entry is ``{"key": <value>, "fields":
      {<f>: {"a": <val>, "b": <val>}, ...}, "record_a": {...}, "record_b": {...}}``.
    - ``matched``: count of records present on both sides with no field
      differences.
    - ``summary``: ``{only_in_a, only_in_b, mismatches, matched, total_a,
      total_b}`` counts.

    ``fields`` scopes which fields are compared; without it, the keys common
    to both records are compared. The ``key`` field itself is never reported
    as a mismatch (it is, by construction, equal on both sides of a pair).
    """
    index_a: dict[str, dict[str, Any]] = {}
    for rec in source_a:
        index_a[_keyof(rec, key)] = rec
    index_b: dict[str, dict[str, Any]] = {}
    for rec in source_b:
        index_b[_keyof(rec, key)] = rec

    keys_a = set(index_a)
    keys_b = set(index_b)

    only_in_a = [index_a[k] for k in index_a if k not in keys_b]
    only_in_b = [index_b[k] for k in index_b if k not in keys_a]

    mismatches: list[dict[str, Any]] = []
    matched = 0
    for k in keys_a & keys_b:
        ra, rb = index_a[k], index_b[k]
        compare = fields if fields else [f for f in ra if f in rb]
        diff: dict[str, dict[str, Any]] = {}
        for f in compare:
            if f == key:
                continue
            va, vb = ra.get(f), rb.get(f)
            if va != vb:
                diff[f] = {"a": va, "b": vb}
        if diff:
            mismatches.append(
                {"key": k, "fields": diff, "record_a": ra, "record_b": rb}
            )
        else:
            matched += 1

    return {
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "mismatches": mismatches,
        "matched": matched,
        "summary": {
            "only_in_a": len(only_in_a),
            "only_in_b": len(only_in_b),
            "mismatches": len(mismatches),
            "matched": matched,
            "total_a": len(source_a),
            "total_b": len(source_b),
        },
    }
