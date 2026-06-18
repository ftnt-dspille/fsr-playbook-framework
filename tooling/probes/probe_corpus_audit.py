"""probe_corpus_audit — diff resolver whitelists against the live
playbook_steps corpus, plus audit ManualInput inputVariables tuples
against the hardcoded _INPUT_FIELD_KINDS map.

Run quarterly (or after any normalizer/whitelist change) to catch:

  - Corpus-observed argument keys that no normalizer expects (drift
    risk: real FSR playbooks ship a key our resolver doesn't recognise,
    so authors hitting that pattern get spurious unknown_param errors).
  - Canonical keys in the resolver whitelists that never appear in any
    real playbook (suspect: probably a spec-only or dead key).
  - `(formType, dataType, type, templateUrl)` tuples on ManualInput
    inputVariables that no friendly `kind:` projects to — these are
    inputs authors can't currently express via the friendly form.

Implements TODO items I13 (corpus shape audit) and I14 (auto-derive
_INPUT_FIELD_KINDS — actually a drift check, since friendly kind names
have no in-corpus signal).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from . import _env  # noqa: F401  (loads .env)
from .common import REPO_ROOT

PROBE_NAME = "probe_corpus_audit"

# Universal step-level wrappers allowed across every step type.
# Mirrors python/compiler/resolver/catalog.py:_UNIVERSAL_STEP_KEYS.
UNIVERSAL_STEP_KEYS: set[str] = {
    "when", "for_each", "do_until", "ignore_errors", "message", "name",
    "agent", "agentId", "apply_async", "pass_input_record",
    "pass_parent_env", "mock_result", "useMockOutput", "condition",
}

# Canonical-keys snapshot, mined from python/compiler/resolver/normalizers.py.
# Keyed by FSR's internal step_type_name (the column value in
# playbook_steps.step_type_name). Update this map when the corresponding
# _FRIENDLY / _CANONICAL set in the resolver changes. The audit's whole
# job is to surface drift between these two — keep them paired.
#
# Step types not listed here are reported as 'unclassified' — observed
# keys are still tallied but not diff'd against any expected set.
EXPECTED_KEYS: dict[str, dict[str, set[str]]] = {
    "cybersponse.post_create": {
        "friendly":  {"module", "modules", "when", "mock_result", "condition"},
        "canonical": {"resource", "resources", "step_variables",
                      "triggerOnSource", "triggerOnReplicate",
                      "__triggerLimit", "fieldbasedtrigger", "useMockOutput",
                      "version"},
    },
    "cybersponse.post_update": {
        "friendly":  {"module", "modules", "when", "mock_result", "condition"},
        "canonical": {"resource", "resources", "step_variables",
                      "triggerOnSource", "triggerOnReplicate",
                      "__triggerLimit", "fieldbasedtrigger", "useMockOutput",
                      "version"},
    },
    "InsertData": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource", "operation",
                      "fieldOperation", "__recommend", "_showJson",
                      "step_variables", "__bulk", "for_each",
                      "tagsOperation", "is_upsert", "config", "version"},
    },
    "UpdateRecord": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource", "operation",
                      "fieldOperation", "__recommend", "_showJson",
                      "step_variables", "__bulk", "for_each",
                      "tagsOperation", "is_upsert", "config", "version"},
    },
    "FindRecords": {
        "friendly":  set(),
        "canonical": {"module", "query", "partial", "mock_result",
                      "condition", "step_variables", "checkboxFields"},
    },
    "ManualInput": {
        "friendly":  {"title", "description", "options", "inputs",
                      "mode", "audience", "assignee"},
        "canonical": {"type", "input", "record", "is_approval",
                      "isRecordLinked", "owner_detail", "step_variables",
                      "response_mapping", "email_notification",
                      "inline_channel_list", "external_channel_list",
                      "unauthenticated_input", "resources",
                      "agent_id", "timeout", "inputExternalUser",
                      "inputInternalUsers", "internal_email_subject",
                      "external_email_subject", "customEmailExternal",
                      "customEmailInternal", "custom_email_body_external",
                      "custom_email_body_internal",
                      "external_email_attachments",
                      "internal_email_attachments", "message", "label"},
    },
    "CodeSnippet": {
        "friendly":  {"code", "tooling", "config", "mock_result", "condition"},
        "canonical": {"connector", "operation", "operationTitle", "version",
                      "params", "step_variables", "pickFromTenant"},
    },
    "Delay": {
        "friendly":  {"seconds", "minutes", "hours", "days", "mock_result",
                      "condition"},
        "canonical": {"type", "delay", "rule", "step_variables", "timeout"},
    },
}

# Friendly→canonical projection used by the resolver
# (python/compiler/resolver/picklists.py:_INPUT_FIELD_KINDS). Each value
# tuple is (formType, dataType, type, templateUrl). Drift against the
# corpus is what I14 audits.
_WEBADDR = "app/components/form/fields/webAddress.html"
_INPUT_HTML = "app/components/form/fields/input.html"
_FIELD_KIND_TUPLES: dict[str, tuple[str, str, str, str | None]] = {
    "text":     ("text",     "text",     "string",   _INPUT_HTML),
    "textarea": ("textarea", "text",     "string",   "app/components/form/fields/textarea.html"),
    "richtext": ("richtext", "text",     "string",   "app/components/form/fields/markdownEditor.html"),
    "html":     ("html",     "text",     "string",   "app/components/form/fields/htmlEditor.html"),
    "password": ("password", "text",     "string",   "app/components/form/fields/password.html"),
    "ipv4":     ("ipv4",     "text",     "string",   _WEBADDR),
    "ipv6":     ("ipv6",     "text",     "string",   _WEBADDR),
    "domain":   ("domain",   "text",     "string",   _WEBADDR),
    "email":    ("email",    "text",     "string",   _WEBADDR),
    "url":      ("url",      "text",     "string",   _WEBADDR),
    "phone":    ("phone",    "text",     "string",   _WEBADDR),
    "filehash": ("filehash", "text",     "string",   _WEBADDR),
    "integer":  ("integer",  "text",     "integer",  _INPUT_HTML),
    "decimal":  ("decimal",  "text",     "number",   _INPUT_HTML),
    "checkbox": ("checkbox", "checkbox", "boolean",  "app/components/form/fields/checkbox.html"),
    "datetime": ("datetime", "text",     "string",   _INPUT_HTML),
    "date":     ("date",     "text",     "string",   _INPUT_HTML),
    "select":   ("dynamicList",          "dynamicList", "array",    "app/components/form/fields/dynamicList.html"),
    "multiselect": ("multiselect",       "dynamicList", "array",    "app/components/form/fields/dynamicList.html"),
    "picklist":   ("picklist",           "picklist",    "picklists","app/components/form/fields/typeahead.html"),
    "multiselectpicklist": ("multiselectpicklist", "picklist", "picklists", "app/components/form/fields/typeahead.html"),
    # lookup `type` is the target module — wildcard-matched in the audit
    "lookup":   ("lookup",   "lookup",   "*lookup*", "app/components/form/fields/typeahead.html"),
    "file":     ("file",     "file",     "string",   "app/components/form/fields/file.html"),
    "image":    ("image",    "file",     "string",   "app/components/form/fields/file.html"),
    "json":     ("object",   "object",   "object",   "app/components/form/fields/json.html"),
}


def _top_level_keys(args_json: str) -> set[str]:
    try:
        d = json.loads(args_json)
    except (json.JSONDecodeError, TypeError):
        return set()
    return set(d.keys()) if isinstance(d, dict) else set()


def _input_variables(args_json: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(args_json)
    except (json.JSONDecodeError, TypeError):
        return []
    return (d.get("input", {}) or {}).get("schema", {}).get(
        "inputVariables") or []


def audit_step_keys(conn: sqlite3.Connection) -> dict[str, Any]:
    """Per step type: tally top-level argument keys, diff against
    EXPECTED_KEYS. Returns a structured report."""
    rows = conn.execute(
        "SELECT step_type_name, arguments_json FROM playbook_steps"
    ).fetchall()
    by_type: dict[str, Counter] = {}
    for type_name, args in rows:
        if not type_name:
            continue
        by_type.setdefault(type_name, Counter()).update(_top_level_keys(args))

    out: dict[str, Any] = {}
    for type_name, counts in sorted(by_type.items()):
        total = sum(counts.values())
        spec = EXPECTED_KEYS.get(type_name)
        observed = set(counts)
        entry: dict[str, Any] = {
            "row_count": conn.execute(
                "SELECT COUNT(*) FROM playbook_steps WHERE step_type_name = ?",
                (type_name,),
            ).fetchone()[0],
            "distinct_keys": len(counts),
            "top_keys": counts.most_common(15),
        }
        if spec is None:
            entry["status"] = "unclassified"
        else:
            expected = spec["friendly"] | spec["canonical"] | UNIVERSAL_STEP_KEYS
            entry["status"] = "classified"
            entry["expected_keys"] = sorted(expected)
            entry["unexpected_keys"] = sorted(observed - expected)
            # Friendly keys are expanded by the resolver, so corpus
            # (post-resolution) is expected to never contain them.
            # Only canonical keys never seen are real drift signal.
            entry["never_observed"] = sorted(spec["canonical"] - observed)
        out[type_name] = entry
        del total  # unused; kept for future percentages
    return out


def audit_input_field_kinds(conn: sqlite3.Connection) -> dict[str, Any]:
    """For ManualInput: collect distinct (formType, dataType, type,
    templateUrl) tuples and flag tuples not projected by any kind."""
    tuples: Counter = Counter()
    for (args,) in conn.execute(
        "SELECT arguments_json FROM playbook_steps "
        "WHERE step_type_name = 'ManualInput'"
    ):
        for iv in _input_variables(args):
            if not isinstance(iv, dict):
                continue
            t = iv.get("type")
            t_norm = json.dumps(t) if isinstance(t, (list, dict)) else t
            tuples[(iv.get("formType"), iv.get("dataType"),
                    t_norm, iv.get("templateUrl"))] += 1

    projected = {v for v in _FIELD_KIND_TUPLES.values()}

    def covered(t: tuple) -> str | None:
        """Match a corpus tuple to a friendly kind.

        templateUrl is treated as advisory: live FSR is inconsistent
        about it (UI strips/leaves stale values when authors switch
        field types). Match strictly on (formType, dataType, type) and
        only check templateUrl as a tiebreaker when multiple kinds
        share the same triple.
        """
        triple_hits = [
            (k, s) for k, s in _FIELD_KIND_TUPLES.items()
            if s[0] == t[0] and s[1] == t[1]
            and (s[2] == "*lookup*" or s[2] == t[2])
        ]
        if not triple_hits:
            return None
        if len(triple_hits) == 1:
            return triple_hits[0][0]
        for k, s in triple_hits:
            if s[3] == t[3]:
                return k
        return triple_hits[0][0]

    drift = []
    for tup, n in tuples.most_common():
        kind = covered(tup)
        drift.append({
            "tuple": list(tup),
            "count": n,
            "covered_by_kind": kind,
        })
    uncovered = [d for d in drift if d["covered_by_kind"] is None]
    unused_kinds = sorted({
        kind for kind, spec in _FIELD_KIND_TUPLES.items()
        if not any(spec[0] == t[0] and spec[1] == t[1]
                   and (spec[2] == "*lookup*" or spec[2] == t[2])
                   for t in tuples)
    })
    del projected  # informational
    return {
        "distinct_tuples": len(tuples),
        "uncovered_tuples": uncovered,
        "kinds_never_observed": unused_kinds,
        "all": drift,
    }


def render_markdown(step_report: dict[str, Any],
                    field_report: dict[str, Any]) -> str:
    lines = ["# Corpus shape audit", ""]
    lines.append("## Step argument keys vs resolver whitelists")
    lines.append("")
    for tname, e in step_report.items():
        lines.append(f"### `{tname}` — {e['row_count']} rows, "
                     f"{e['distinct_keys']} distinct keys")
        if e["status"] == "unclassified":
            lines.append("_no resolver normalizer; observed keys only_")
            lines.append("")
            lines.append("Top keys: " + ", ".join(
                f"`{k}`×{n}" for k, n in e["top_keys"]))
        else:
            if e["unexpected_keys"]:
                lines.append("**UNEXPECTED (not in resolver whitelist):** "
                             + ", ".join(f"`{k}`" for k in e["unexpected_keys"]))
            else:
                lines.append("✓ no unexpected keys")
            if e["never_observed"]:
                lines.append("Never observed in corpus: "
                             + ", ".join(f"`{k}`" for k in e["never_observed"]))
        lines.append("")
    lines.append("## ManualInput inputVariables tuple drift")
    lines.append("")
    lines.append(f"Distinct tuples: {field_report['distinct_tuples']}")
    if field_report["uncovered_tuples"]:
        lines.append("")
        lines.append("**Uncovered tuples** (no friendly `kind:` projects to them):")
        for d in field_report["uncovered_tuples"]:
            t = d["tuple"]
            lines.append(f"- formType={t[0]!r} dataType={t[1]!r} "
                         f"type={t[2]!r} templateUrl={t[3]!r} ×{d['count']}")
    else:
        lines.append("✓ every observed tuple is covered by some `kind:`")
    if field_report["kinds_never_observed"]:
        lines.append("")
        lines.append("Kinds never observed in corpus: "
                     + ", ".join(f"`{k}`" for k in field_report["kinds_never_observed"]))
    return "\n".join(lines) + "\n"


def run(db_path: Path, out_dir: Path,
        only_type: str | None = None) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    step_report = audit_step_keys(conn)
    if only_type:
        step_report = {k: v for k, v in step_report.items() if k == only_type}
    field_report = audit_input_field_kinds(conn)
    conn.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus_audit.json").write_text(json.dumps(
        {"step_keys": step_report, "input_field_kinds": field_report},
        indent=2, default=list))
    md = render_markdown(step_report, field_report)
    (out_dir / "corpus_audit.md").write_text(md)
    return {"step_report": step_report, "field_report": field_report,
            "out_dir": str(out_dir)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=PROBE_NAME)
    p.add_argument("--db", default=str(REPO_ROOT / "store" / "fsr_reference.db"))
    p.add_argument("--out", default=str(REPO_ROOT / "docs" / "corpus_audit"))
    p.add_argument("--type", default=None,
                   help="filter to one step_type_name (e.g. ManualInput)")
    args = p.parse_args(argv)
    result = run(Path(args.db), Path(args.out), only_type=args.type)
    sr = result["step_report"]
    fr = result["field_report"]
    drift = sum(1 for e in sr.values()
                if e.get("unexpected_keys"))
    uncovered = len(fr["uncovered_tuples"])
    print(f"audit-shapes: {len(sr)} step types · "
          f"{drift} with unexpected keys · "
          f"{uncovered} uncovered MI field tuples")
    print(f"report: {result['out_dir']}/corpus_audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
