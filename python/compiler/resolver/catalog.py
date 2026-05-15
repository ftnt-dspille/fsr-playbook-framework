"""CatalogLookupMixin — database query methods for step types, connectors, operations."""
from __future__ import annotations

import difflib
import json
import sqlite3
from typing import Optional

from ..errors import CompileError, ErrorCode
from ._constants import SHORT_TYPE_TO_FSR


class CatalogLookupMixin:
    """Methods for querying step types, connectors, and operations from the SQLite DB."""

    conn: sqlite3.Connection

    @staticmethod
    def _check_unknown_keys(
        a: dict,
        kind: str,
        friendly: set[str],
        canonical: set[str],
        path: str,
        errors: list[CompileError],
    ) -> bool:
        """Strict-whitelist guard. Mirrors `_normalize_manual_input_args`.

        Returns True when an unknown key was found (caller bails out so we
        don't run the normalizer on a malformed dict). Without this guard
        unknown keys are silently dropped — a recurring class of bug where
        a misspelled friendly key (e.g. `mins:` instead of `minutes:`)
        compiles green but produces the wrong wire shape.
        """
        unknown = sorted(set(a) - friendly - canonical)
        if not unknown:
            return False
        errors.append(CompileError(
            code=ErrorCode.UNKNOWN_PARAM,
            message=(
                f"{kind}: unknown argument(s) "
                f"{', '.join(repr(k) for k in unknown)}; "
                f"FSR drops these silently at runtime"
            ),
            path=f"{path}.arguments",
            suggestion=(
                f"friendly: {', '.join(sorted(friendly)) or '(none)'} · "
                f"canonical: {', '.join(sorted(canonical)) or '(none)'}"
            ),
        ))
        return True
    def step_type(self, short_or_canonical: str) -> Optional[sqlite3.Row]:
        canonical = SHORT_TYPE_TO_FSR.get(short_or_canonical, short_or_canonical)
        return self.conn.execute(
            "SELECT * FROM step_types WHERE name = ?", (canonical,),
        ).fetchone()
    def suggest_step_type(self, name: str) -> Optional[str]:
        rows = self.conn.execute("SELECT name FROM step_types").fetchall()
        names = list(SHORT_TYPE_TO_FSR.keys()) + [r["name"] for r in rows]
        m = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
        return m[0] if m else None
    def handler_for_step_type(self, step_type_row: sqlite3.Row) -> Optional[str]:
        schema = step_type_row["args_schema_json"]
        if not schema:
            return None
        try:
            obj = json.loads(schema)
        except Exception:
            return None
        script = obj.get("script") if isinstance(obj, dict) else None
        if not isinstance(script, str):
            return None
        return script.rsplit("/", 1)[-1]
    def connector(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM connectors WHERE name = ?", (name,),
        ).fetchone()
    def suggest_connector(self, name: str) -> Optional[str]:
        rows = self.conn.execute("SELECT name FROM connectors").fetchall()
        m = difflib.get_close_matches(name, [r["name"] for r in rows], n=1, cutoff=0.6)
        return m[0] if m else None
    def operation(self, connector: str, op: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM operations WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchone()
    def suggest_operation(self, connector: str, op: str) -> Optional[str]:
        # Score each op by max(ratio(input, op_name), ratio(input, snake_title)).
        # Title match catches the case where the agent guessed an op name from
        # the human-readable label (`get_ip_reputation` ≈ "Get IP Reputation"
        # = title of `query_ip`).
        rows = self.conn.execute(
            "SELECT op_name, title FROM operations WHERE connector_name = ?",
            (connector,),
        ).fetchall()
        if not rows:
            return None
        needle = op.lower()
        best_name, best_score = None, 0.0
        for r in rows:
            name = r["op_name"]
            title_snake = (r["title"] or "").lower().replace(" ", "_")
            score = max(
                difflib.SequenceMatcher(None, needle, name.lower()).ratio(),
                difflib.SequenceMatcher(None, needle, title_snake).ratio() if title_snake else 0.0,
            )
            if score > best_score:
                best_name, best_score = name, score
        return best_name if best_score >= 0.6 else None
    def suggest_operations_topn(self, connector: str, op: str, n: int = 5) -> list[str]:
        """Return top-N close-ish op names (using both op_name and title), for picklist hints."""
        rows = self.conn.execute(
            "SELECT op_name, title FROM operations WHERE connector_name = ?",
            (connector,),
        ).fetchall()
        needle = op.lower()
        scored = []
        for r in rows:
            name = r["op_name"]
            title_snake = (r["title"] or "").lower().replace(" ", "_")
            score = max(
                difflib.SequenceMatcher(None, needle, name.lower()).ratio(),
                difflib.SequenceMatcher(None, needle, title_snake).ratio() if title_snake else 0.0,
            )
            if score >= 0.3:
                scored.append((score, name))
        scored.sort(reverse=True)
        return [name for _, name in scored[:n]]
    def operation_params(self, connector: str, op: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT param_name FROM operation_params "
            "WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchall()
        return [r["param_name"] for r in rows]
    def operation_param_rules(
        self, connector: str, op: str,
    ) -> list[tuple[str, str | None, str | None]]:
        """Return (param_name, parent_param_name, condition_value) rows.

        A param is visible iff parent_param_name IS NULL, or the parent
        param is itself visible AND the parent's *provided value* equals
        condition_value. Used to reject mutually-exclusive arg sets like
        block_ip_new(method=Quarantine Based, ip_block_policy=…).
        """
        rows = self.conn.execute(
            "SELECT param_name, parent_param_name, condition_value "
            "FROM operation_params "
            "WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchall()
        return [(r["param_name"], r["parent_param_name"], r["condition_value"])
                for r in rows]
