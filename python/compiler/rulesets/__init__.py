"""Optional validation rulesets layered on top of the base validator.

Each ruleset is a list of `Rule` callables that operate on raw FSR JSON
(the `{type: workflow_collections, data: [...]}` shape exported by the
FSR API). Rulesets are opt-in: a caller picks `data-ingest`, `feed-ingest`,
or both, or `auto` to detect from collection contents.

Why raw JSON, not the compiler IR: existing FSR exports (e.g.,
connector_building/<conn>/playbooks/playbooks.json) come as JSON, and the
ingestion-specific checks read fields the IR drops (recordTags, raw step
arguments, stepType UUID). Compiled YAML can be passed through the
emitter first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# Step type UUIDs (canonical, from store/STEP_TYPES.md and live FSR)
STEP_CREATE_RECORD = "2597053c-e718-44b4-8394-4d40fe26d357"
STEP_INGEST_BULK_FEED = "7b221880-716b-4726-a2ca-5e568d330b3e"
STEP_CONNECTOR = "0bfed618-0316-11e7-93ae-92361f002671"


@dataclass
class Issue:
    rule_id: str
    severity: str  # "fail" | "warn"
    message: str
    path: str = ""  # e.g. "data[0].workflows[1].steps[3]"
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "suggestion": self.suggestion,
        }


# A Rule is any callable returning Issues for one workflow_collections doc.
Rule = Callable[[dict], Iterable[Issue]]


def _step_type_uuid(step: dict) -> str:
    iri = step.get("stepType") or ""
    return iri.rsplit("/", 1)[-1]


def _all_workflows(doc: dict) -> Iterable[tuple[int, dict, int, dict]]:
    """Yield (collection_idx, collection, workflow_idx, workflow)."""
    for ci, coll in enumerate(doc.get("data", []) or []):
        for wi, wf in enumerate(coll.get("workflows", []) or []):
            yield ci, coll, wi, wf


def _all_steps(wf: dict) -> Iterable[tuple[int, dict]]:
    for si, step in enumerate(wf.get("steps", []) or []):
        yield si, step


def detect_rulesets(doc: dict) -> list[str]:
    """Pick rulesets to apply based on workflow tags + step types.

    Heuristic:
    - Any workflow tagged `dataingestion` AND containing an Ingest Bulk Feed
      step → feed-ingest.
    - Any workflow tagged `dataingestion` AND containing a Create Record step
      with `/api/3/...` collection → data-ingest.
    - Both can fire if a collection mixes them.
    """
    out: set[str] = set()
    for _, _, _, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        if "dataingestion" not in tags:
            continue
        for _, step in _all_steps(wf):
            uuid = _step_type_uuid(step)
            coll_iri = (step.get("arguments") or {}).get("collection") or ""
            if uuid == STEP_INGEST_BULK_FEED:
                out.add("feed-ingest")
            elif uuid == STEP_CREATE_RECORD and coll_iri.startswith("/api/3/"):
                out.add("data-ingest")
    return sorted(out)


_REGISTRY: dict[str, list[Rule]] = {}


def register(name: str, rules: list[Rule]) -> None:
    _REGISTRY[name] = list(rules)


def available() -> list[str]:
    return sorted(_REGISTRY)


def validate(doc: dict, rulesets: list[str]) -> list[Issue]:
    """Run the given rulesets against the FSR JSON doc; return all issues."""
    seen: list[Issue] = []
    for name in rulesets:
        rules = _REGISTRY.get(name)
        if rules is None:
            seen.append(Issue(
                rule_id="meta.unknown_ruleset",
                severity="warn",
                message=f"unknown ruleset {name!r}; available: {available()}",
            ))
            continue
        for rule in rules:
            seen.extend(rule(doc) or [])
    return seen


# Eager import registers the rulesets.
from . import data_ingest as _data_ingest  # noqa: E402,F401
from . import feed_ingest as _feed_ingest  # noqa: E402,F401
