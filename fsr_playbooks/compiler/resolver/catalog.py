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

    # Universal step-level wrapper keys observed across every step type
    # in the corpus (probe_corpus_audit, 2026-05-16): control-flow and
    # UI metadata that FSR layers over the step-type-specific arguments.
    # Allowed unconditionally so per-type normalizers don't reject them.
    _UNIVERSAL_STEP_KEYS: set[str] = {
        "when", "for_each", "do_until", "ignore_errors", "message", "name",
        "agent", "agentId", "apply_async", "pass_input_record",
        "pass_parent_env", "mock_result", "useMockOutput", "condition",
        "pickFromTenant",
    }

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
        unknown = sorted(
            set(a) - friendly - canonical
            - CatalogLookupMixin._UNIVERSAL_STEP_KEYS
        )
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
    def resolve_module_name(
        self,
        raw: str,
        path: str,
        errors: list[CompileError],
    ) -> str:
        """Validate / canonicalize a friendly module name against the
        ``modules`` catalog. Returns the canonical lowercase type name.

        FSR module *type* names are lowercase plural tokens ('alerts',
        'incidents', 'indicators') — the same token that goes into a
        ``/api/3/<module>`` IRI and a trigger's ``resource``. Authors
        routinely write the UI label instead ('Alerts'); the trigger /
        record-CRUD normalizers used to copy that through verbatim, so a
        capital-A 'Alerts' resource shipped to FSR and silently never
        matched. Case-fix it here with a warning.

        Provenance handling mirrors ``_resolve_priority``: when the
        ``modules`` table is empty (an unwarmed / pre-name-catalog slim
        DB) we have nothing to validate against, so pass the value
        through SILENTLY rather than emit a warning the author can't act
        on. Unknown-but-non-empty names are a *warning* (not a hard
        error) because a target install may carry custom modules that
        aren't in the shipped baseline catalog.
        """
        if not isinstance(raw, str) or not raw.strip():
            return raw
        name = raw.strip()
        # Already an IRI — caller handles the /api/3/ form; don't touch.
        if name.startswith("/api/"):
            return name
        known = [r[0] for r in self.conn.execute(
            "SELECT name FROM modules").fetchall()]
        if not known:
            # Unwarmed catalog (no module names shipped/synced) — silent.
            return name
        if name in known:
            return name
        by_lower = {k.lower(): k for k in known}
        canon = by_lower.get(name.lower())
        if canon is not None:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    f"module {name!r} is not the canonical FSR type name "
                    f"(module names are lowercase) — rewrote to {canon!r}"
                ),
                path=path,
                near=canon,
                suggestion=f"use {canon!r}",
                severity="warning",
            ))
            return canon
        sug = difflib.get_close_matches(name.lower(), known, n=1, cutoff=0.6)
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                f"unknown module {name!r} — not in the reference catalog "
                f"(ignore if it's a custom module on the target install)"
            ),
            path=path,
            near=sug[0] if sug else None,
            suggestion=(f"did you mean {sug[0]!r}?" if sug else None),
            severity="warning",
        ))
        return name

    def resolve_config_id(
        self, connector: str, config_name: Optional[str] = None
    ) -> Optional[str]:
        """Return the per-instance config UUID for ``connector`` (+ optional
        friendly ``config_name``), read from the warmed ``connector_configs``
        table. ``None`` when unwarmed or unknown.

        This is the in-package replacement for the dev-only
        ``tooling/connector_configs.py``: the compiler must resolve configs
        offline from the warmed catalog, never by importing ``tooling/`` or
        hitting the network. When ``config_name`` is None we return the
        instance's default config (``config_name = '__default__'``), falling
        back to any single config for the connector.
        """
        try:
            if config_name:
                row = self.conn.execute(
                    "SELECT config_id FROM connector_configs "
                    "WHERE connector = ? AND config_name = ?",
                    (connector, config_name),
                ).fetchone()
                return (row[0] or None) if row else None
            # default: the '__default__' row, else the is_default row, else any.
            row = self.conn.execute(
                "SELECT config_id FROM connector_configs "
                "WHERE connector = ? "
                "ORDER BY (config_name = '__default__') DESC, is_default DESC "
                "LIMIT 1",
                (connector,),
            ).fetchone()
            return (row[0] or None) if row else None
        except sqlite3.OperationalError:
            # Table absent on an old/slim DB — unwarmed, nothing to resolve.
            return None

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
    def operation_param_enum(
        self, connector: str, op: str, param: str,
    ) -> tuple[str | None, list[str] | None]:
        """Return (type, allowed_values) for one param, or (None, None)
        if not found. Allowed values are returned only when `type` is a
        picklist-shaped widget (`select` / `multiselect`, plus the
        observed typo variants) and `options_json` parses to a list of
        strings. Otherwise `allowed_values` is None even when the type
        is set."""
        import json as _json
        row = self.conn.execute(
            "SELECT type, options_json FROM operation_params "
            "WHERE connector_name = ? AND op_name = ? AND param_name = ?",
            (connector, op, param),
        ).fetchone()
        if row is None:
            return None, None
        ptype = row["type"]
        if (ptype or "").lower() not in {"select", "multiselect", "mutiselect"}:
            return ptype, None
        raw = row["options_json"]
        if not raw:
            return ptype, None
        try:
            opts = _json.loads(raw)
        except Exception:  # noqa: BLE001
            return ptype, None
        if isinstance(opts, list) and all(isinstance(o, str) for o in opts):
            return ptype, opts
        return ptype, None

    def operation_param_observed_type(
        self, connector: str, op: str, param: str,
    ) -> tuple[str | None, str | None]:
        """Return (observed_type, coerces_from) for one top-level param.

        Populated by `probes.probe_param_types`. Tier 2.0 fills this in
        from the widget column for typed widgets; Tier 2.2 refines via
        live-probe evidence. Returns (None, None) when the column is
        unset (text-widget params with no probe evidence) or the param
        does not exist."""
        row = self.conn.execute(
            "SELECT observed_type, coerces_from FROM operation_params "
            "WHERE connector_name = ? AND op_name = ? AND param_name = ? "
            "  AND parent_param_name IS NULL AND condition_value IS NULL",
            (connector, op, param),
        ).fetchone()
        if row is None:
            return None, None
        return row["observed_type"], row["coerces_from"]

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
        # Some ingestion paths store a top-level (always-visible) param with an
        # empty-string parent/condition instead of NULL. Coerce '' → None so the
        # visibility checker treats them as unconditional — otherwise a plain
        # required param like virustotal.query_ip(ip) is mis-flagged as "only
        # valid when =''" and a spurious param-set conflict is raised.
        return [(r["param_name"],
                 (r["parent_param_name"] or None),
                 (r["condition_value"] or None))
                for r in rows]

    def operation_param_required_rules(
        self, connector: str, op: str,
    ) -> list[tuple[str, str | None, str | None, bool, str | None]]:
        """Return (param_name, parent_param_name, condition_value, required,
        default_value) rows.

        Like `operation_param_rules` but also carries the `required` flag and
        the param's `default_value`. Used for conditional-required completeness:
        when a parent's (provided-or-default) value activates a child param that
        is marked required, the child must be present or FSR rejects the call at
        runtime (e.g. block_ip_new(method='Policy Based') requires ip_type +
        ip_block_policy; ip_type='IPv4' then requires ip)."""
        rows = self.conn.execute(
            "SELECT param_name, parent_param_name, condition_value, "
            "required, default_value FROM operation_params "
            "WHERE connector_name = ? AND op_name = ?",
            (connector, op),
        ).fetchall()
        # See operation_param_rules: coerce empty-string parent/condition → None
        # so always-visible params aren't treated as conditionally gated.
        return [(r["param_name"],
                 (r["parent_param_name"] or None),
                 (r["condition_value"] or None),
                 bool(r["required"]), r["default_value"])
                for r in rows]
