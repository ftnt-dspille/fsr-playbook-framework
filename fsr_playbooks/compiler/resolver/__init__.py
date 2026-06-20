"""Resolver — looks up references against the SQLite reference store.

The resolver is the only compiler component that touches the DB. It
turns short YAML names into FSR-canonical identifiers (step type UUIDs,
connector versions, handler functions) and surfaces structured errors
with "did you mean…" suggestions.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import difflib

from ..errors import CompileError, ErrorCode
from ..ir import Collection, PRIORITY_LIST_NAME, Playbook
from ._constants import SHORT_TYPE_TO_FSR, _looks_like_uuid
from .catalog import CatalogLookupMixin
from .connector_args import ConnectorArgsMixin
from .normalizers import NormalizerMixin
from .picklists import PicklistMixin
from .rewriters import RewriterMixin

__all__ = ["Resolver", "SHORT_TYPE_TO_FSR", "_looks_like_uuid"]


class Resolver(
    CatalogLookupMixin,
    RewriterMixin,
    PicklistMixin,
    NormalizerMixin,
    ConnectorArgsMixin,
):
    """Main resolver class combining all mixins."""

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def _resolve_priority(self, pb: Playbook, path: str,
                          errors: list[CompileError]) -> None:
        """Map a playbook's `priority:` name to its live picklist IRI.

        Reads the synced `picklists` table (listName WorkflowPriority) so the
        emitted IRI is the running instance's own system value. Unknown name →
        warning with a 'did you mean' suggestion, priority left unset."""
        if not pb.priority:
            return
        row = self.conn.execute(
            "SELECT item_iri FROM picklists WHERE list_name=? AND item_value=?",
            (PRIORITY_LIST_NAME, pb.priority),
        ).fetchone()
        if row:
            pb.priority_iri = row[0]
            return
        candidates = [r[0] for r in self.conn.execute(
            "SELECT item_value FROM picklists WHERE list_name=?",
            (PRIORITY_LIST_NAME,),
        ).fetchall()]
        if not candidates:
            # The WorkflowPriority picklist was never synced into this
            # reference DB (zero rows) — we have nothing to validate against.
            # An unsynced reference table is a setup gap, not an authoring
            # bug: leave priority unset SILENTLY rather than emit a spurious
            # bad_value warning the author can't act on.
            pb.priority = None
            return
        sug = difflib.get_close_matches(pb.priority, candidates, n=1, cutoff=0.5)
        valid = ", ".join(sorted(candidates)) or "(none synced — run the modules probe)"
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(f"unknown priority {pb.priority!r}; valid: {valid} — "
                     "leaving priority unset"),
            path=f"{path}.priority",
            near=sug[0] if sug else None,
            suggestion=(f"did you mean {sug[0]!r}?" if sug else None),
            severity="warning",
        ))
        pb.priority = None

    def resolve(self, collection: Collection) -> list[CompileError]:
        errors: list[CompileError] = []
        # Multi-instance guard: if a target SOAR is configured (FSR_BASE_URL)
        # but the cached catalog was warmed from a different one, picklist IRIs
        # and connector configs may silently mis-resolve. Surface it up front.
        from ..._catalog_meta import instance_guard
        instance_guard(self.conn, errors)
        # Build name→Playbook map for in-collection workflow_reference targets.
        pb_by_name = {pb.name: pb for pb in collection.playbooks}
        for pi, pb in enumerate(collection.playbooks):
            self._resolve_priority(pb, f"playbooks[{pi}]", errors)
            # Order matters: rename reserved keys first, capture the
            # rename map, then the step-ref rewriter uses BOTH the new
            # and old names so legacy `vars.steps.<S>.<old>` references
            # (which the agent may have written) get translated too.
            renames = self._auto_rename_reserved_set_var_keys(pb, pi, errors)
            self._auto_rewrite_set_var_step_refs(pb, pi, errors, renames)
            self._auto_rewrite_input_param_refs(pb, pi, errors)
            self._validate_input_param_refs(pb, pi, errors)
            seen_ids = {s.id for s in pb.steps}
            for si, step in enumerate(pb.steps):
                path = f"playbooks[{pi}].steps[{si}]"
                self._resolve_step(step, path, errors, pb_by_name, pb.name)
                self._check_routing(step, seen_ids, path, errors)
        return errors
