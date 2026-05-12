"""Corpus-mined step-type examples + deterministic English summaries.

Powers the Examples tab on every step type. Reads ``playbook_steps``
(the trained ``store/fsr_reference.db``) and:

  1. Maps the friendly step type the visual editor uses
     (``decision``, ``manual_input``, …) to the corpus's
     ``step_type_name`` (``Decision``, ``ManualInput``, …).
  2. Canonicalises each row's ``arguments_json`` into a structural
     skeleton — keys, value *types*, and select enum values
     preserved; everything else (Jinja templates, free-text content,
     IRIs, UUIDs, large arrays) collapsed so semantically-identical
     bodies cluster together.
  3. Counts skeletons, picks a representative row per cluster, and
     renders a one-line English summary so users see "what does this
     do" at a glance instead of parsing JSON.

No LLM — same code path will later feed the AI step builder so the
model can read existing patterns in plain English.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from typing import Any


# Friendly step type → list of corpus ``step_type_name`` values that
# represent it. Some friendlies merge multiple corpus types
# (start_on_create rolls up post_create rows; create_record collapses
# both InsertData + IngestBulkFeed).
STEP_TYPE_TO_CORPUS: dict[str, list[str]] = {
    "decision":         ["Decision"],
    "manual_input":     ["ManualInput"],
    "set_variable":     ["SetVariable"],
    "find_record":      ["FindRecords"],
    "create_record":    ["InsertData"],
    "insert_record":    ["InsertData"],
    "update_record":    ["UpdateRecord"],
    "delete_record":    ["UpdateRecord"],  # FSR uses UpdateRecord with __delete
    "ingest_bulk_feed": ["IngestBulkFeed"],
    "delay":            ["Delay"],
    "code_snippet":     ["CodeSnippet"],
    "workflow_reference": ["WorkflowReference"],
    "start_on_create":  ["cybersponse.post_create"],
    "start_on_update":  ["cybersponse.post_update"],
    "start":            ["cybersponse.abstract_trigger"],
    "manual_action":    ["cybersponse.action"],
    "api_call":         ["cybersponse.api_call"],
}


# Keys whose VALUES we keep verbatim during canonicalisation because
# they shape the cluster (operator, logic, formType, …). Everything
# else has its scalar replaced with a type token (`<str>`, `<int>`,
# `<jinja>`) so two rows that differ only in user-supplied data still
# cluster as the same shape.
_VALUE_KEEP_KEYS = frozenset({
    "logic", "operator", "_operator", "type", "formType", "dataType",
    "direction", "default", "primary", "is_approval",
    "isRecordLinked", "triggerOnSource", "triggerOnReplicate",
    "__triggerLimit", "checkboxFields", "apply_async",
    "pass_input_record", "pass_parent_env", "duplicateOption",
    "operation",
})


_JINJA_RE = re.compile(r"\{\{|\}\}|\{%|%\}")


def _scalar_token(v: Any) -> str:
    if isinstance(v, bool):
        return "<bool>"
    if isinstance(v, int):
        return "<int>"
    if isinstance(v, float):
        return "<num>"
    if v is None:
        return "<null>"
    if isinstance(v, str):
        if _JINJA_RE.search(v):
            return "<jinja>"
        if not v:
            return "<empty>"
        return "<str>"
    return f"<{type(v).__name__}>"


def _canonicalise(node: Any, key: str | None = None) -> Any:
    """Recursively replace user-supplied values with type tokens.

    Keys in ``_VALUE_KEEP_KEYS`` retain their original scalar so the
    skeleton still distinguishes ``operator: eq`` from
    ``operator: like``. Lists are reduced to their unique
    canonicalised element (small lists) or collapsed to a length
    bucket (long ones) so a 3-element ``options[]`` and a 50-element
    one don't share a cluster.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        # Sorted-keys so two dicts with the same content cluster the
        # same regardless of insertion order from the corpus.
        for k in sorted(node.keys()):
            out[k] = _canonicalise(node[k], k)
        return out
    if isinstance(node, list):
        if len(node) == 0:
            return []
        canon_items = [_canonicalise(x, key) for x in node]
        # Dedupe: lists of identical-shape items should canonicalise
        # to a single-element list with a length annotation; that
        # makes a `filters: [{op:eq}, {op:eq}]` cluster the same as
        # one with three eq filters but different from one with mixed
        # operators.
        seen: list[Any] = []
        for it in canon_items:
            if it not in seen:
                seen.append(it)
        if len(seen) == 1:
            # Bucketize length so 3 rows ≠ 30 rows in the cluster key.
            n = len(node)
            bucket = 1 if n == 1 else "few" if n <= 5 else "many"
            return [seen[0], {"_len": bucket}]
        return seen
    if key is not None and key in _VALUE_KEEP_KEYS:
        # Keep the literal so `operator: eq` and `operator: like`
        # cluster separately.
        return node
    return _scalar_token(node)


def _skeleton_hash(args: dict[str, Any]) -> str:
    canon = _canonicalise(args)
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Per-step-type English summarisers. Each takes the representative
# row's ``arguments`` dict and returns a one-liner. None of them call
# out to the LLM — this is the deterministic ground truth the AI step
# builder will later condition on.
# ---------------------------------------------------------------------------

def _humanize(field: str) -> str:
    if "." in field:
        root, _, rest = field.partition(".")
        return f"{_humanize(root)}'s {_humanize(rest)}"
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", field.replace("_", " ")).lower()


_OP_ENGLISH = {
    "eq": "is", "neq": "is not", "lt": "<", "lte": "≤", "gt": ">",
    "gte": "≥", "in": "is one of", "nin": "is not one of",
    "like": "contains", "contains": "contains", "exists": "has",
    "isnull": "is empty", "changed": "changes", "in_all": "matches all of",
}


def _value_label(leaf: dict[str, Any]) -> str:
    hint = leaf.get("_value")
    if isinstance(hint, dict):
        for k in ("itemValue", "display"):
            v = hint.get(k)
            if isinstance(v, str) and v.strip():
                return v
    v = leaf.get("value")
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("{{") and s.endswith("}}"):
            return s.strip("{} ")
        return v
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if v is None:
        return ""
    return json.dumps(v)


def _summarise_filter_tree(group: dict[str, Any] | None) -> str:
    if not isinstance(group, dict):
        return ""
    filters = group.get("filters") or []
    if not filters:
        return ""
    conn = " or " if str(group.get("logic", "AND")).upper() == "OR" else " and "
    parts: list[str] = []
    for f in filters:
        if not isinstance(f, dict):
            continue
        if "logic" in f and "filters" in f:
            inner = _summarise_filter_tree(f)
            if inner:
                parts.append(f"({inner})")
            continue
        op = f.get("operator", "eq")
        field = _humanize(str(f.get("field", "")))
        if op == "isnull":
            v = str(f.get("value", "true")).lower()
            parts.append(f"{field} is not empty" if v == "false" else f"{field} is empty")
        elif op == "exists":
            parts.append(f"{field} exists")
        elif op == "changed":
            parts.append(f"{field} changes")
        else:
            parts.append(f"{field} {_OP_ENGLISH.get(op, op)} {_value_label(f)}".rstrip())
    return conn.join(p for p in parts if p)


def summarise_decision(args: dict[str, Any]) -> str:
    conds = args.get("conditions") or []
    if not isinstance(conds, list) or not conds:
        return "Branches with no conditions configured."
    parts: list[str] = []
    for c in conds:
        if not isinstance(c, dict):
            continue
        opt = c.get("option") or c.get("display") or "(unnamed)"
        if c.get("default"):
            parts.append(f"else → {opt}")
        else:
            cond = c.get("condition") or c.get("when") or "<missing>"
            cond = str(cond).strip().strip("{}").strip()
            parts.append(f"if {cond} → {opt}")
    return "; ".join(parts) + "."


def summarise_trigger(args: dict[str, Any], corpus_type: str) -> str:
    verb = {
        "cybersponse.post_create": "On create of",
        "cybersponse.post_update": "On update of",
        "cybersponse.action":      "When an analyst runs an action on",
        "cybersponse.api_call":    "When the API endpoint is called for",
        "cybersponse.abstract_trigger": "On manual run against",
    }.get(corpus_type, "On")
    module = args.get("resource") or "records"
    fbt = args.get("fieldbasedtrigger") if isinstance(args.get("fieldbasedtrigger"), dict) else None
    body = _summarise_filter_tree(fbt) if fbt else ""
    if not body:
        return f"{verb} all {module}."
    return f"{verb} {module} where {body}."


def summarise_manual_input(args: dict[str, Any]) -> str:
    schema = (args.get("input") or {}).get("schema") if isinstance(args.get("input"), dict) else None
    fields = []
    if isinstance(schema, dict):
        for v in schema.get("inputVariables") or []:
            if isinstance(v, dict) and v.get("name"):
                fields.append(str(v["name"]))
    rm = args.get("response_mapping") if isinstance(args.get("response_mapping"), dict) else None
    buttons = []
    if isinstance(rm, dict):
        for o in rm.get("options") or []:
            if isinstance(o, dict) and o.get("option"):
                buttons.append(str(o["option"]))
    title = ""
    if isinstance(schema, dict) and schema.get("title"):
        title = str(schema["title"])
    head = f"Prompt {title!r}" if title else "Prompt"
    if fields and buttons:
        return f"{head} asks for {', '.join(fields)} and shows [{' / '.join(buttons)}]."
    if buttons:
        return f"{head} shows [{' / '.join(buttons)}] (no fields)."
    if fields:
        return f"{head} asks for {', '.join(fields)}."
    return f"{head} (no fields, no buttons)."


def summarise_find_record(args: dict[str, Any]) -> str:
    module = (args.get("module") or "records").split("?", 1)[0]
    q = args.get("query") if isinstance(args.get("query"), dict) else None
    body = _summarise_filter_tree(q) if q else ""
    base = f"Find all {module}." if not body else f"Find {module} where {body}."
    sort = (q or {}).get("sort") if isinstance(q, dict) else None
    if isinstance(sort, list) and sort:
        s0 = sort[0]
        if isinstance(s0, dict) and s0.get("field"):
            base = base.rstrip(".") + f", sorted by {_humanize(str(s0['field']))} {s0.get('direction', 'ASC').lower()}."
    return base


def summarise_record_write(args: dict[str, Any], corpus_type: str) -> str:
    coll = args.get("collection")
    module = (coll.rsplit("/", 1)[-1] if isinstance(coll, str) and coll else "<module>")
    op = args.get("operation") or ("Create" if corpus_type == "InsertData" else "Update")
    resource = args.get("resource") if isinstance(args.get("resource"), dict) else {}
    fields = [k for k in resource.keys() if not k.startswith("_") and k not in ("__replace",)]
    if not fields:
        return f"{op} a {module} record (no fields set)."
    head = ", ".join(fields[:5])
    if len(fields) > 5:
        head += f", + {len(fields) - 5} more"
    return f"{op} a {module} record with {head}."


def summarise_workflow_ref(args: dict[str, Any]) -> str:
    target = args.get("workflowReference") or "<target>"
    inputs = args.get("arguments") if isinstance(args.get("arguments"), dict) else {}
    keys = list(inputs.keys())
    if isinstance(target, str) and target.startswith("/api/3/workflows/"):
        target = target.rsplit("/", 1)[-1]
    if not keys:
        return f"Calls playbook {target} with no inputs."
    return f"Calls playbook {target} with {', '.join(keys[:5])}{'…' if len(keys) > 5 else ''}."


def summarise_delay(args: dict[str, Any]) -> str:
    d = args.get("delay") if isinstance(args.get("delay"), dict) else None
    parts = []
    if isinstance(d, dict):
        for unit in ("days", "hours", "minutes", "seconds"):
            v = d.get(unit)
            if v:
                parts.append(f"{v} {unit}")
    else:
        for unit in ("days", "hours", "minutes", "seconds"):
            v = args.get(unit)
            if v:
                parts.append(f"{v} {unit}")
    if not parts:
        return "Delay (duration not set)."
    return f"Wait {' '.join(parts)}."


def summarise_set_variable(args: dict[str, Any]) -> str:
    # Two shapes coexist: friendly `arg_list:[{name,value}]` (post-parse)
    # and the canonical FSR shape where every top-level arg key IS a
    # variable name (flat dict). Try friendly first, fall through.
    names: list[str] = []
    al = args.get("arg_list")
    if isinstance(al, list):
        for v in al:
            if isinstance(v, dict) and v.get("name"):
                names.append(str(v["name"]))
    if not names:
        # Canonical: every key is a var name. Strip system keys
        # (`mock_result`, `when`, …) so the summary lists what the
        # author actually set.
        SYS = {"mock_result", "when", "do_until", "for_each", "step_variables",
               "comment", "type", "config", "connector", "operation"}
        names = [k for k in args.keys() if k not in SYS]
    if not names:
        return "Set variables (none configured)."
    head = ", ".join(names[:5])
    if len(names) > 5:
        head += f", + {len(names) - 5} more"
    return f"Sets {head}."


def summarise_code_snippet(args: dict[str, Any]) -> str:
    params = args.get("params") if isinstance(args.get("params"), dict) else {}
    code = params.get("python_function") if isinstance(params, dict) else None
    if not isinstance(code, str) or not code.strip():
        return "Run a Python snippet (empty)."
    first = next((ln.strip() for ln in code.splitlines() if ln.strip()), "")
    return f"Run Python: `{first[:80]}`{'…' if len(first) > 80 else ''}"


def _summarise(args: dict[str, Any], friendly: str, corpus: str) -> str:
    if friendly == "decision":            return summarise_decision(args)
    if friendly.startswith("start_on") or friendly in ("start", "manual_action", "api_call"):
        return summarise_trigger(args, corpus)
    if friendly == "manual_input":        return summarise_manual_input(args)
    if friendly == "find_record":         return summarise_find_record(args)
    if friendly in ("create_record", "insert_record",
                    "update_record", "delete_record", "ingest_bulk_feed"):
        return summarise_record_write(args, corpus)
    if friendly == "workflow_reference":  return summarise_workflow_ref(args)
    if friendly == "delay":               return summarise_delay(args)
    if friendly == "set_variable":        return summarise_set_variable(args)
    if friendly == "code_snippet":        return summarise_code_snippet(args)
    return ""


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def cluster_examples(conn: sqlite3.Connection, friendly: str,
                     limit: int = 10) -> list[dict[str, Any]]:
    """Return the top-N skeletons for a friendly step type.

    Each result has ``frequency`` (matching rows in the corpus),
    ``summary`` (deterministic English), ``arguments`` (a representative
    row's body, JSON-decoded), ``playbook`` (which playbook produced
    the representative row), and ``corpus_type`` (the original
    ``step_type_name``).
    """
    corpus_types = STEP_TYPE_TO_CORPUS.get(friendly)
    if not corpus_types:
        return []
    placeholders = ",".join("?" * len(corpus_types))
    rows = conn.execute(
        f"SELECT step_type_name, playbook_name, arguments_json "
        f"FROM playbook_steps WHERE step_type_name IN ({placeholders}) "
        f"AND arguments_json IS NOT NULL",
        corpus_types,
    ).fetchall()
    if not rows:
        return []

    # Cluster by canonicalised arg-shape; first row in the cluster is
    # the representative we render + summarise.
    clusters: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"frequency": 0, "playbooks": set(), "rep": None, "corpus_type": None}
    )
    for r in rows:
        try:
            args = json.loads(r["arguments_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(args, dict):
            continue
        h = _skeleton_hash(args)
        c = clusters[h]
        c["frequency"] += 1
        if r["playbook_name"]:
            c["playbooks"].add(r["playbook_name"])
        if c["rep"] is None:
            c["rep"] = args
            c["corpus_type"] = r["step_type_name"]

    ordered = sorted(clusters.values(), key=lambda x: -x["frequency"])
    out: list[dict[str, Any]] = []
    for c in ordered[:limit]:
        rep = c["rep"]
        corpus = c["corpus_type"] or ""
        out.append({
            "frequency": c["frequency"],
            "playbook_count": len(c["playbooks"]),
            "summary": _summarise(rep, friendly, corpus),
            "arguments": rep,
            "corpus_type": corpus,
        })
    return out
