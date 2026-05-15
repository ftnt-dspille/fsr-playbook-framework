"""Resolver — looks up references against the SQLite reference store.

The resolver is the only compiler component that touches the DB. It
turns short YAML names into FSR-canonical identifiers (step type UUIDs,
connector versions, handler functions) and surfaces structured errors
with "did you mean…" suggestions.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..errors import CompileError
from ..ir import Collection
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

    def resolve(self, collection: Collection) -> list[CompileError]:
        errors: list[CompileError] = []
        # Build name→Playbook map for in-collection workflow_reference targets.
        pb_by_name = {pb.name: pb for pb in collection.playbooks}
        for pi, pb in enumerate(collection.playbooks):
            # Order matters: rename reserved keys first, capture the
            # rename map, then the step-ref rewriter uses BOTH the new
            # and old names so legacy `vars.steps.<S>.<old>` references
            # (which the agent may have written) get translated too.
            renames = self._auto_rename_reserved_set_var_keys(pb, pi, errors)
            self._auto_rewrite_set_var_step_refs(pb, pi, errors, renames)
            self._auto_rewrite_input_param_refs(pb, pi, errors)
            seen_ids = {s.id for s in pb.steps}
            for si, step in enumerate(pb.steps):
                path = f"playbooks[{pi}].steps[{si}]"
                self._resolve_step(step, path, errors, pb_by_name, pb.name)
                self._check_routing(step, seen_ids, path, errors)
        return errors
