"""Rules that apply to BOTH data-ingest and feed-ingest playbooks.

These cover the contract documented in
TEC/fortisoar-tips-and-tricks/content/advanced/data-ingestion/index.md:
required tags, three-workflow split (or env_setup variant), step naming.
"""
from __future__ import annotations

from typing import Iterable

import os
import sqlite3
from pathlib import Path

from . import (
    STEP_CONNECTOR,
    STEP_CREATE_RECORD,
    STEP_INGEST_BULK_FEED,
    Issue,
    _all_steps,
    _all_workflows,
    _step_type_uuid,
)


def _has_tag(obj: dict, tag: str) -> bool:
    return tag in (obj.get("recordTags") or [])


def rule_step_type_collection_consistency(doc: dict) -> Iterable[Issue]:
    """Create Record → /api/3/...; Ingest Bulk Feed → /api/ingest-feeds/...
    Also enforces presence/absence of operation/__recommend/fieldOperation.
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        for si, step in _all_steps(wf):
            uuid = _step_type_uuid(step)
            args = step.get("arguments") or {}
            coll = args.get("collection") or ""
            path = f"data[{ci}].workflows[{wi}].steps[{si}]({step.get('name')!r})"
            if uuid == STEP_CREATE_RECORD:
                if not coll.startswith("/api/3/"):
                    yield Issue(
                        rule_id="shared.create_record_collection_prefix",
                        severity="fail",
                        message=f"Create Record collection must start with /api/3/, got {coll!r}",
                        path=path,
                        suggestion="Use Ingest Bulk Feed step type for /api/ingest-feeds/* targets",
                    )
                if "operation" not in args:
                    yield Issue(
                        rule_id="shared.create_record_missing_operation",
                        severity="fail",
                        message="Create Record step missing required 'operation' arg",
                        path=path,
                        suggestion='Set arguments.operation to "Overwrite" or "Update"',
                    )
            elif uuid == STEP_INGEST_BULK_FEED:
                if not coll.startswith("/api/ingest-feeds/"):
                    yield Issue(
                        rule_id="shared.ingest_bulk_feed_collection_prefix",
                        severity="fail",
                        message=f"Ingest Bulk Feed collection must start with /api/ingest-feeds/, got {coll!r}",
                        path=path,
                        suggestion="Use Create Record step type for /api/3/* targets",
                    )
                # Only `operation` reliably distinguishes the two step types
                # in real exports. `__recommend` and `fieldOperation` are
                # auto-added by the FSR designer to both step types.
                if "operation" in args:
                    yield Issue(
                        rule_id="shared.ingest_bulk_feed_unexpected_operation",
                        severity="fail",
                        message="Ingest Bulk Feed step has 'operation' arg (Create-Record-only field)",
                        path=path,
                        suggestion="Remove arguments.operation; Ingest Bulk Feed is implicitly upsert",
                    )


def rule_dataingestion_workflow_tags(doc: dict) -> Iterable[Issue]:
    """If any workflow is tagged `dataingestion`, every workflow that performs
    record creation in that collection must carry the connector slug too.

    Connector slug heuristic: any tag that's not in {dataingestion, ingest,
    fetch, create, ThreatIntel}.
    """
    KNOWN = {"dataingestion", "ingest", "fetch", "create", "ThreatIntel"}
    for ci, coll, wi, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        if "dataingestion" not in tags:
            continue
        slugs = tags - KNOWN
        if not slugs:
            yield Issue(
                rule_id="shared.workflow_missing_connector_slug_tag",
                severity="fail",
                message=(
                    f"Workflow tagged 'dataingestion' has no connector-slug tag "
                    f"(other tags: {sorted(tags)})"
                ),
                path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r})",
                suggestion="Add the connector API name (e.g., 'taxii2-threat-intel-feed') as a workflow tag",
            )


def rule_canonical_step_names(doc: dict) -> Iterable[Issue]:
    """Per the official data-ingestion guide, the wizard's template-import
    path expects:
      - Fetch playbook: connector action step named exactly "Fetch"
      - Fetch playbook: a "Set Variable" step named "Configuration"
      - Create playbook: a "Create Record" step named "Create"
    Hand-authored playbooks (FAZ, FSM, AWS) routinely deviate, so this is WARN.
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        names = [s.get("name", "") for s in wf.get("steps", []) or []]
        path = f"data[{ci}].workflows[{wi}]({wf.get('name')!r})"
        if "fetch" in tags and "create" not in tags:
            if "Fetch" not in names:
                yield Issue(
                    rule_id="shared.fetch_step_canonical_name",
                    severity="warn",
                    message="Fetch playbook should contain a step literally named 'Fetch'",
                    path=path,
                )
            if "Configuration" not in names:
                yield Issue(
                    rule_id="shared.configuration_step_canonical_name",
                    severity="warn",
                    message="Fetch playbook should contain a Set Variable step named 'Configuration'",
                    path=path,
                )


def rule_configuration_schema_on_start(doc: dict) -> Iterable[Issue]:
    """Fetch (or combined fetch+create) workflow's Start step should expose
    `_configuration_schema` so the Data Ingestion Wizard can render a config form.
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        if "fetch" not in tags:
            continue
        trigger_uuid = (wf.get("triggerStep") or "").rsplit("/", 1)[-1]
        for step in wf.get("steps", []) or []:
            if step.get("uuid") != trigger_uuid:
                continue
            sv = (step.get("arguments") or {}).get("step_variables") or {}
            if isinstance(sv, dict) and "_configuration_schema" in sv:
                break
        else:
            yield Issue(
                rule_id="shared.configuration_schema_missing",
                severity="warn",
                message="Fetch workflow Start step missing _configuration_schema; wizard cannot render config form",
                path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r})",
                suggestion="Add step_variables._configuration_schema (JSON-string) to the Start step",
            )


_CANONICAL_INGESTION_TAGS = {"dataingestion", "ingest", "fetch", "create", "ThreatIntel", "ThreatFeedsIngestion"}
# Common typos / case variants we've seen go wrong in practice.
_TAG_TYPOS = {
    "dataingest": "dataingestion",
    "data-ingestion": "dataingestion",
    "data_ingestion": "dataingestion",
    "DataIngestion": "dataingestion",
    "Dataingestion": "dataingestion",
    "Fetch": "fetch",
    "Create": "create",
    "Ingest": "ingest",
    "threat-intel": "ThreatIntel",
    "threatintel": "ThreatIntel",
    "Threatintel": "ThreatIntel",
}


def _all_tags(doc: dict) -> set[str]:
    """Union of every tag found anywhere in the doc (collection + workflows)."""
    seen: set[str] = set()
    for _, coll, _, wf in _all_workflows(doc):
        seen |= set(coll.get("recordTags") or [])
        seen |= set(wf.get("recordTags") or [])
    return seen


def rule_tag_typos(doc: dict) -> Iterable[Issue]:
    """Catch common case/spelling typos on canonical ingestion tags.
    These get past the wizard silently — the playbook just doesn't show up.
    """
    for ci, coll, wi, wf in _all_workflows(doc):
        for source_label, tags in (
            (f"data[{ci}]", coll.get("recordTags") or []),
            (f"data[{ci}].workflows[{wi}]", wf.get("recordTags") or []),
        ):
            for tag in tags:
                if tag in _TAG_TYPOS:
                    yield Issue(
                        rule_id="shared.tag_typo",
                        severity="fail",
                        message=f"Tag {tag!r} looks like a typo for {_TAG_TYPOS[tag]!r}",
                        path=source_label,
                        suggestion=f"Rename to {_TAG_TYPOS[tag]!r} (case- and hyphen-sensitive)",
                    )


def rule_exported_tags_consistency(doc: dict) -> Iterable[Issue]:
    """`exported_tags` at the doc root should be the union of every tag found
    on the collection and its workflows. The FSR exporter populates it
    automatically; mismatch usually means the file was hand-edited.
    """
    declared = set(doc.get("exported_tags") or [])
    if not declared:
        return  # field is optional
    found = _all_tags(doc)
    missing = found - declared
    extra = declared - found
    if missing:
        yield Issue(
            rule_id="shared.exported_tags_missing",
            severity="warn",
            message=f"exported_tags missing tag(s) present on collection/workflows: {sorted(missing)}",
            path="exported_tags",
            suggestion="Re-export from FSR or add the missing tags",
        )
    if extra:
        yield Issue(
            rule_id="shared.exported_tags_extra",
            severity="warn",
            message=f"exported_tags lists tag(s) not used on any collection/workflow: {sorted(extra)}",
            path="exported_tags",
        )


def rule_connector_slug_uniform(doc: dict) -> Iterable[Issue]:
    """Within one collection, the connector slug used as a tag should be the
    same string on every dataingestion-tagged workflow. Catches mid-stream
    renames (e.g., 'aws-feed' on one workflow, 'aws_feed' on another).
    """
    for ci, coll, _, _ in _all_workflows(doc):
        slugs_per_wf: list[set[str]] = []
        for wf in coll.get("workflows", []) or []:
            tags = set(wf.get("recordTags") or [])
            if "dataingestion" not in tags:
                continue
            slugs_per_wf.append(tags - _CANONICAL_INGESTION_TAGS)
        if not slugs_per_wf:
            continue
        common = set.intersection(*slugs_per_wf) if slugs_per_wf else set()
        if not common:
            unioned = sorted(set().union(*slugs_per_wf))
            yield Issue(
                rule_id="shared.connector_slug_inconsistent",
                severity="fail",
                message=(
                    f"dataingestion workflows do not share a common connector-slug tag; "
                    f"observed slug-like tags: {unioned}"
                ),
                path=f"data[{ci}]({coll.get('name')!r})",
                suggestion="Pick one slug (e.g. the connector's `name` from info.json) and apply it to every dataingestion workflow",
            )
        # Once per collection
        break


def rule_collection_or_workflow_has_slug(doc: dict) -> Iterable[Issue]:
    """At least one of {collection.recordTags, every dataingestion workflow's
    recordTags} should carry the connector slug — wizard discovery uses
    either. Some samples (AWS) leave the collection untagged but tag each
    workflow; others (TAXII2) tag the collection too. Both work.
    """
    for ci, coll, _, _ in _all_workflows(doc):
        coll_tags = set(coll.get("recordTags") or [])
        di_wfs = [w for w in (coll.get("workflows") or []) if "dataingestion" in (w.get("recordTags") or [])]
        if not di_wfs:
            continue
        slugs_on_collection = coll_tags - _CANONICAL_INGESTION_TAGS
        slug_present_on_all_wfs = all(
            (set(w.get("recordTags") or []) - _CANONICAL_INGESTION_TAGS)
            for w in di_wfs
        )
        if not slugs_on_collection and not slug_present_on_all_wfs:
            yield Issue(
                rule_id="shared.no_connector_slug_anywhere",
                severity="fail",
                message="No connector-slug tag on collection or on all dataingestion workflows; wizard cannot discover this collection",
                path=f"data[{ci}]({coll.get('name')!r})",
            )
        break


def _open_ref_db() -> sqlite3.Connection | None:
    """Open the reference store read-only. Honors FSRPB_DB; falls back to
    the in-tree store/fsr_reference.db. Returns None when nothing usable
    is available so the rule degrades quietly on a fresh install.
    """
    candidates: list[Path] = []
    env = os.environ.get("FSRPB_DB")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parents[3]
    candidates.append(here / "data" / "fsr_reference.db")
    for p in candidates:
        if p.exists():
            try:
                conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                return conn
            except sqlite3.Error:
                return None
    return None


def rule_connector_param_visibility(doc: dict) -> Iterable[Issue]:
    """Connector steps inside an ingestion playbook must satisfy the same
    operation_params visibility rules the resolver checks at compile time.

    Mirrors `NormalizerMixin._check_param_visibility` against raw FSR
    JSON: when a connector op's params row carries `parent_param_name`,
    the provided params must include the parent with a matching
    `condition_value`. Otherwise FSR hides the field at runtime and the
    op typically rejects the call — the same silent-failure mode that
    bit chat-review session c44c6e36.

    No-ops when the reference store isn't available locally.
    """
    conn = _open_ref_db()
    if conn is None:
        return
    try:
        for ci, _coll, wi, wf in _all_workflows(doc):
            for si, step in _all_steps(wf):
                if _step_type_uuid(step) != STEP_CONNECTOR:
                    continue
                args = step.get("arguments") or {}
                connector = args.get("connector") or ""
                operation = args.get("operation") or ""
                params = args.get("params") or {}
                if not connector or not operation or not isinstance(params, dict):
                    continue
                rules = conn.execute(
                    "SELECT param_name, parent_param_name, condition_value "
                    "FROM operation_params "
                    "WHERE connector_name=? AND op_name=?",
                    (connector, operation),
                ).fetchall()
                if not rules:
                    continue
                by_name: dict[str, list[tuple[str | None, str | None]]] = {}
                for r in rules:
                    by_name.setdefault(r["param_name"], []).append(
                        (r["parent_param_name"], r["condition_value"]),
                    )
                path = (
                    f"data[{ci}].workflows[{wi}].steps[{si}]"
                    f"({step.get('name')!r})"
                )
                for p_name, p_value in params.items():
                    entries = by_name.get(p_name)
                    if not entries:
                        continue
                    if any(parent is None for parent, _ in entries):
                        continue
                    satisfied = False
                    for parent, cond in entries:
                        if (parent in params
                                and str(params[parent]) == str(cond)):
                            satisfied = True
                            break
                    if satisfied:
                        continue
                    conds = ", ".join(
                        f"{parent}={cond!r}" for parent, cond in entries
                    )
                    yield Issue(
                        rule_id="shared.param_visibility_mismatch",
                        severity="warn",
                        message=(
                            f"param {p_name!r} on {connector}.{operation} "
                            f"is only valid when {conds}; FSR will hide "
                            f"the field at runtime and likely reject the "
                            f"call"
                        ),
                        path=f"{path}.arguments.params.{p_name}",
                        suggestion=(
                            f"set the parent param to match, or remove "
                            f"{p_name!r}"
                        ),
                    )
    finally:
        conn.close()


def rule_three_workflow_split_or_env_setup(doc: dict) -> Iterable[Issue]:
    """A dataingestion collection should expose at least one workflow with
    each of {fetch, create, ingest} as tags — distributed across workflows
    OR concentrated on a single workflow that also branches on env_setup.
    """
    for ci, coll in enumerate(doc.get("data", []) or []):
        wfs = coll.get("workflows", []) or []
        di_wfs = [w for w in wfs if "dataingestion" in (w.get("recordTags") or [])]
        if not di_wfs:
            continue
        present = set()
        for w in di_wfs:
            present |= set(w.get("recordTags") or []) & {"fetch", "create", "ingest"}
        missing = {"fetch", "create", "ingest"} - present
        if missing:
            yield Issue(
                rule_id="shared.three_workflow_split",
                severity="warn",
                message=(
                    f"dataingestion collection missing workflow tag(s) "
                    f"{sorted(missing)}; canonical pattern uses fetch+create+ingest"
                ),
                path=f"data[{ci}]({coll.get('name')!r})",
                suggestion="Either split into 3 workflows or tag a single combined workflow with all three and branch on vars.request.env_setup",
            )
