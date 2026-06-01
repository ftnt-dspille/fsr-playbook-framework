"""RewriterMixin — automatic rewriting of variable references and reserved keys."""
from __future__ import annotations

import re as _re
import sqlite3

from ..errors import CompileError, ErrorCode


class RewriterMixin:
    """Methods for rewriting step refs, input param refs, reserved keys, and jinja."""

    conn: sqlite3.Connection

    def _auto_rewrite_set_var_step_refs(
        self, pb, pi: int, errors: list[CompileError],
        renames: dict[str, str] | None = None,
    ) -> None:
        """Rewrite `vars.steps.<set_var_step>.<key>` → `vars.<key>`.

        SetVariable step outputs live at `vars.<key>` at runtime, not
        under the step-output namespace. The agent commonly reaches for
        `vars.steps.<step_name>.<key>` (correct shape for connector /
        find_record / manual_input outputs), which silently evaluates
        to empty for set_variable steps. Auto-rewrite so the playbook
        does what was intended; emit a warning so the agent learns.
        """
        # Map: jinja-key form of step name (spaces→underscores) → set of
        # variable names that step writes.
        sv_keys: dict[str, set[str]] = {}
        for step in pb.steps:
            if step.type != "set_variable" or not isinstance(step.arguments, dict):
                continue
            jkey = (step.name or step.id or "").replace(" ", "_")
            if not jkey:
                continue
            args = step.arguments
            keys: set[str] = set()
            if isinstance(args.get("arg_list"), list):
                for it in args["arg_list"]:
                    if isinstance(it, dict) and "name" in it:
                        keys.add(it["name"])
            else:
                for k in args.keys():
                    if k != "step_variables":
                        keys.add(k)
            if keys:
                sv_keys[jkey] = keys

        if not sv_keys:
            return

        # vars.steps.<jkey>.<key> or vars.steps.<jkey>['<key>'] / ["<key>"]
        # Tracks (jkey, key) → set of step indices where the rewrite fired,
        # so the warning can point at the offending step instead of the
        # whole playbook.
        rewrites_done: dict[tuple[str, str], set[int]] = {}
        _current_si = [-1]  # closed over by patch(); set by the loop below

        # Build search list: each (key_to_match, replacement_var_name).
        # Includes both current keys AND any pre-rename names so refs
        # written before the auto-rename get caught too.
        renames = renames or {}
        rev_renames = {new: old for old, new in renames.items()}

        def _step_ref_patterns(jkey: str, key: str) -> list:
            """All Jinja access forms for `vars.steps.<jkey>.<key>`.

            Covers any mix of dotted and bracketed access on either the
            step name OR the variable key:
              - vars.steps.<jkey>.<key>
              - vars.steps.<jkey>['<key>']  / ["<key>"]
              - vars.steps['<jkey>'].<key>  / ["<jkey>"].<key>
              - vars.steps['<jkey>']['<key>']  (any quote mix)
              - vars['steps']<step><key>     (rare; same combinatorics)
            """
            esc_j, esc_k = _re.escape(jkey), _re.escape(key)
            vs = r"\bvars(?:\.steps|\[\s*['\"]steps['\"]\s*\])"
            # Use non-capturing groups with character classes for the
            # quote chars — avoids backref numbering issues when
            # composing step + key fragments. Quote-mismatch (e.g.
            # `vars.steps['SV"]`) is a YAML/Jinja syntax error anyway,
            # so character-class quoting is fine.
            sj_dot = r"\." + esc_j
            sj_br  = r"\[\s*['\"]" + esc_j + r"['\"]\s*\]"
            k_dot  = r"\." + esc_k + r"(?=\b|[^A-Za-z0-9_])"
            k_br   = r"\[\s*['\"]" + esc_k + r"['\"]\s*\]"
            k_get  = r"\.get\(\s*['\"]" + esc_k + r"['\"]\s*\)"
            patterns = []
            for sp in (sj_dot, sj_br):
                for kp in (k_dot, k_br, k_get):
                    patterns.append(_re.compile(vs + sp + kp))
            return patterns

        def patch(text: str) -> str:
            for jkey, keys in sv_keys.items():
                # current keys → vars.<current>
                for key in keys:
                    for pat in _step_ref_patterns(jkey, key):
                        new_text, n = pat.subn(f"vars.{key}", text)
                        if n:
                            rewrites_done.setdefault(
                                (jkey, key), set()
                            ).add(_current_si[0])
                            text = new_text
                # pre-rename keys → vars.<current>
                for cur in keys:
                    old = rev_renames.get(cur)
                    if not old:
                        continue
                    for pat in _step_ref_patterns(jkey, old):
                        new_text, n = pat.subn(f"vars.{cur}", text)
                        if n:
                            rewrites_done.setdefault(
                                (jkey, old), set()
                            ).add(_current_si[0])
                            text = new_text
            return text

        for si, step in enumerate(pb.steps):
            _current_si[0] = si
            self._walk_strings_inplace(step.arguments, patch)

        for (jkey, key), step_idxs in rewrites_done.items():
            for si in sorted(i for i in step_idxs if i >= 0):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        f"`vars.steps.{jkey}.{key}` rewritten to `vars.{key}` — "
                        f"set_variable outputs live at top-level vars, not "
                        f"under the step-output namespace. The other form "
                        f"silently evaluates to empty at runtime."
                    ),
                    path=f"playbooks[{pi}].steps[{si}].arguments",
                    severity="warning",
                ))

    def _auto_rewrite_input_param_refs(
        self, pb, pi: int, errors: list[CompileError],
    ) -> None:
        """Rewrite `vars.input.<param>` → `vars.input.params.<param>`
        when `<param>` matches a declared playbook parameter.

        FSR exposes trigger inputs at `vars.input.params.<name>`. The
        agent commonly drops the `.params.` segment, which silently
        evaluates to empty at runtime. Mechanical translation > prompt
        rule (mirrors the SetVariable step-ref rewriter pattern).
        """
        params = [p for p in (pb.parameters or [])
                  if isinstance(p, str) and p
                  and p not in {"params", "records", "record"}]
        if not params:
            return

        rewrites_done: dict[str, set[int]] = {}
        _current_si = [-1]

        # vars.input.<p> | vars.input['<p>']  (dot or bracket on the param,
        # but only `vars.input.` — bracket form on `input` is rare and
        # the substitution would be ambiguous to fix; skip it).
        # Negative lookahead skips already-correct `vars.input.params.<p>`.
        def _patterns(p: str) -> list:
            esc = _re.escape(p)
            vi = r"\bvars\.input(?!\.params\b)"
            tail_dot = r"\." + esc + r"(?=\b|[^A-Za-z0-9_])"
            tail_br  = r"\[\s*['\"]" + esc + r"['\"]\s*\]"
            return [
                (_re.compile(vi + tail_dot), f"vars.input.params.{p}"),
                (_re.compile(vi + tail_br), f"vars.input.params[{p!r}]"),
            ]

        def patch(text: str) -> str:
            for p in params:
                for pat, repl in _patterns(p):
                    new_text, n = pat.subn(repl, text)
                    if n:
                        rewrites_done.setdefault(p, set()).add(_current_si[0])
                        text = new_text
            return text

        for si, step in enumerate(pb.steps):
            _current_si[0] = si
            self._walk_strings_inplace(step.arguments, patch)

        for p in sorted(rewrites_done):
            for si in sorted(i for i in rewrites_done[p] if i >= 0):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    severity="warning",
                    message=(
                        f"`vars.input.{p}` rewritten to "
                        f"`vars.input.params.{p}` — declared playbook "
                        f"parameters live under `vars.input.params.*`; the "
                        f"bare form evaluates to empty at runtime."
                    ),
                    path=f"playbooks[{pi}].steps[{si}].arguments",
                ))

    @classmethod
    def _walk_strings_inplace(cls, value, fn) -> None:
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if isinstance(v, str):
                    value[k] = fn(v)
                else:
                    cls._walk_strings_inplace(v, fn)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if isinstance(v, str):
                    value[i] = fn(v)
                else:
                    cls._walk_strings_inplace(v, fn)
    def _auto_rename_reserved_set_var_keys(
        self, pb, pi: int, errors: list[CompileError],
    ) -> dict[str, str]:
        """Rename any SetVariable keys that collide with FSR's reserved
        runtime names, then rewrite matching `vars.<reserved>` template
        references everywhere in the same playbook.

        Reserved keys (e.g. `message`, `result`, `input`) are treated by
        the FSR engine as structured envelopes; setting them to a plain
        string crashes the runtime with `'str' object has no attribute
        'get'`. Rather than failing compile, we mechanically rename
        `<reserved>` → `<reserved>_var` and patch downstream
        `vars.<reserved>` references so the playbook still does what
        the author meant. A warning is emitted per rename so the agent
        and the user see what we did.
        """
        # Lazy import to avoid a circular dep with validator.py.
        from fsr_core.compiler.validator import _RESERVED_VARS_KEYS

        renames: dict[str, str] = {}
        for si, step in enumerate(pb.steps):
            if step.type != "set_variable" or not isinstance(step.arguments, dict):
                continue
            args = step.arguments
            spath = f"playbooks[{pi}].steps[{si}]"
            # Two shapes: flat dict {name: value} OR arg_list:[{name,value}]
            if isinstance(args.get("arg_list"), list):
                for k, item in enumerate(args["arg_list"]):
                    if isinstance(item, dict) and item.get("name") in _RESERVED_VARS_KEYS:
                        old = item["name"]
                        new = self._safe_rename(old, _RESERVED_VARS_KEYS)
                        item["name"] = new
                        renames[old] = new
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"set_variable key {old!r} is reserved by FSR "
                                f"runtime; auto-renamed to {new!r}. Downstream "
                                f"`vars.{old}` references rewritten to "
                                f"`vars.{new}`."
                            ),
                            path=f"{spath}.arguments.arg_list[{k}].name",
                            severity="warning",
                        ))
            else:
                for old in list(args.keys()):
                    if old in _RESERVED_VARS_KEYS and old != "step_variables":
                        # `message` as a dict is the record-message sugar
                        # (not a user var) — leave it for the message
                        # normalizer downstream.
                        if old == "message" and isinstance(args[old], dict):
                            continue
                        new = self._safe_rename(old, _RESERVED_VARS_KEYS)
                        args[new] = args.pop(old)
                        renames[old] = new
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"set_variable key {old!r} is reserved by FSR "
                                f"runtime; auto-renamed to {new!r}. Downstream "
                                f"`vars.{old}` references rewritten to "
                                f"`vars.{new}`."
                            ),
                            path=f"{spath}.arguments.{old}",
                            severity="warning",
                        ))

        if not renames:
            return renames
        # Walk every string in every step's args and rewrite top-level
        # `vars.<old>` references. NOT `vars.steps.<X>.<old>` — those
        # are step-output reads in a different namespace.
        for step in pb.steps:
            self._rewrite_vars_refs(step.arguments, renames, _re)
        return renames

    @staticmethod
    def _safe_rename(old: str, taken: set[str]) -> str:
        """Pick a non-reserved replacement for a reserved key."""
        for cand in (f"{old}_var", f"my_{old}", f"{old}_value", f"{old}_2"):
            if cand not in taken:
                return cand
        return f"{old}_renamed"

    def _rewrite_vars_refs(cls, value, renames: dict[str, str], _re) -> None:
        """In-place: rewrite `vars.<old>` and `vars['<old>']` to the new
        name throughout a nested args structure. Skips `vars.steps.*`."""
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if isinstance(v, str):
                    value[k] = cls._patch_jinja(v, renames, _re)
                else:
                    cls._rewrite_vars_refs(v, renames, _re)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if isinstance(v, str):
                    value[i] = cls._patch_jinja(v, renames, _re)
                else:
                    cls._rewrite_vars_refs(v, renames, _re)

    @staticmethod
    def _patch_jinja(text: str, renames: dict[str, str], _re) -> str:
        """Rewrite top-level `vars.<old>` (any access form) → `vars.<new>`.

        Catches all three Jinja access forms:
          - dotted:    `vars.message`
          - single:    `vars['message']`
          - double:    `vars["message"]`
        Skips `vars.steps.<X>.<old>` — that's the step-output namespace,
        handled by `_auto_rewrite_set_var_step_refs`.
        """
        for old, new in renames.items():
            esc = _re.escape(old)
            # Form 1: vars.<old>  (negative lookbehind blocks vars.steps.<old>)
            text = _re.sub(
                r"(?<!\.steps)\bvars\." + esc + r"(?=\b|[^A-Za-z0-9_])",
                f"vars.{new}", text,
            )
            # Form 2: vars['<old>'] / vars["<old>"]
            text = _re.sub(
                r"\bvars\[\s*(['\"])" + esc + r"\1\s*\]",
                f"vars.{new}", text,
            )
            # Form 3: vars.get('<old>') / vars.get("<old>")  — keep the
            # .get() call (soft-fail semantics the author chose), just
            # swap the key string.
            text = _re.sub(
                r"(\bvars\.get\(\s*)(['\"])" + esc + r"\2(\s*\))",
                lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(2)}{m.group(3)}",
                text,
            )
        return text

