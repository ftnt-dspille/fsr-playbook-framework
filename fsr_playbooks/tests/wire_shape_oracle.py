"""Loader for the editor-derived wire-shape oracle (docs/STEP_WIRE_SHAPES.json).

The oracle is the source of truth for per-step argument shapes and the editor's
**compile transforms**, reverse-engineered from the FortiSOAR 8.0 editor bundle.
`test_wire_shape_conformance.py` turns it into executable assertions.

The oracle's `step` field is a human title, not the canonical FSR step-type name,
so we map each entry to (canonical_name, short_type) here. short_type is None for
step types the compiler does not yet expose a friendly alias for (coverage gaps).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ORACLE_PATH = Path(__file__).resolve().parents[2] / "docs" / "STEP_WIRE_SHAPES.json"

# Substring (lowercased, matched against the oracle `step` title) -> (canonical FSR
# step-type name, short YAML type or None if no alias exists yet).
_TITLE_TO_TYPE: list[tuple[str, tuple[str, Optional[str]]]] = [
    ("reverse-engineered connector step", ("Connectors", "connector")),
    ("fastrigger", ("cybersponse.abstract_trigger", "start")),
    ("setvariables step type", ("SetVariable", "set_variable")),
    ("findrecords step type", ("FindRecords", "find_record")),
    ("referenceplaybook", ("WorkflowReference", "workflow_reference")),
    ("wait step (delay", ("Delay", "delay")),
    ("onupdate", ("cybersponse.post_update", "start_on_update")),
    ("decision step type", ("Decision", "decision")),
    ("utilitynoop", ("CyopsUtilites", "stop")),
    ("updaterecord-step", ("UpdateRecord", "update_record")),
    ("createrecord (insertdata)", ("InsertData", "create_record")),
    ("manualstart (action_trigger)", ("cybersponse.action", "start")),
    ("oncreate step type", ("cybersponse.post_create", "start_on_create")),
    ("ingestbulkfeed", ("IngestBulkFeed", "ingest_bulk_feed")),
    ("sendemail step", ("SendEmail", "send_email")),
    ("manualinput-step", ("ManualInput", "manual_input")),
    ("approval-step-type", ("Approval", "approval")),
    ("createtask step type", ("ManualTask", "create_task")),
    ("apiendpoint step type", ("cybersponse.api_call", "api_endpoint")),
    ("codesnippet step type", ("CodeSnippet", "code_snippet")),
    ("setapikeys-step-type", ("SetAPIKeys", "set_api_keys")),
]


@dataclass
class StepShape:
    title: str
    canonical_name: str
    short_type: Optional[str]
    confidence: str
    required_keys: frozenset[str]
    optional_keys: frozenset[str]
    compile_transforms: str
    # raw argument rows: key -> {type, required, default, enum, notes}
    arguments: dict[str, dict]
    # True when the oracle documents a `[key: string]` wildcard row, i.e. the
    # step accepts arbitrary user-chosen keys at the arguments root (SetVariable
    # variable names). A documented-keys subset check is meaningless for these.
    has_open_keys: bool = False

    @property
    def all_keys(self) -> frozenset[str]:
        return self.required_keys | self.optional_keys


def _classify(title: str) -> tuple[str, Optional[str]]:
    t = title.lower()
    for needle, mapped in _TITLE_TO_TYPE:
        if needle in t:
            return mapped
    raise KeyError(f"no canonical-name mapping for oracle step title: {title!r}")


def load_oracle(path: Path = _ORACLE_PATH) -> dict[str, StepShape]:
    """Return {canonical_name: StepShape}. Top-level (non-`conditions[n].x`) keys only."""
    raw = json.loads(path.read_text())
    out: dict[str, StepShape] = {}
    for entry in raw["steps"]:
        title = entry["step"]
        canonical, short = _classify(title)
        req, opt, args = set(), set(), {}
        has_open = False
        for a in entry.get("arguments", []):
            key = a["key"]
            # Some oracle entries (e.g. Approval) prefix every root argument
            # with `arguments.`; others (SendEmail, ManualTask) list bare keys.
            # Normalize: a single leading `arguments.` segment IS the arguments
            # root, so strip it before deciding whether the key is nested.
            if key.startswith("arguments."):
                key = key[len("arguments."):]
            # Skip nested/dynamic-key rows (e.g. "conditions[n].step_iri",
            # "resource.playbookiri", "[key: string]")
            if "." in key or key.startswith("["):
                if key.startswith("["):
                    has_open = True
                continue
            args[key] = a
            (req if a.get("required") else opt).add(key)
        out[canonical] = StepShape(
            title=title,
            canonical_name=canonical,
            short_type=short,
            confidence=str(entry.get("confidence", "")),
            required_keys=frozenset(req),
            optional_keys=frozenset(opt),
            compile_transforms=str(entry.get("compile_transforms", "")),
            arguments=args,
            has_open_keys=has_open,
        )
    return out


# Editor envelope/UI-state keys we never emit (they are editor-only or layout noise).
# The conformance test ignores these when checking "emitted ⊆ documented".
EDITOR_ONLY_KEYS = frozenset({
    "annotation", "dynamicallySelected", "pickFromTenant", "_showJson",
    "__recommend", "_promptexpanded", "checkboxFields", "_tmp", "__triggerLimit",
    "executeButtonText", "showToasterMessage", "displayConditions",
    "singleRecordExecution", "noRecordExecution", "_expanded",
})


def normalize_emitted_keys(keys) -> set[str]:
    return {k for k in keys if k not in EDITOR_ONLY_KEYS}
