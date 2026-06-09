"""Source-level auto-fixers for the editor's "Fix warnings" UI.

These mirror the IR-level rewriters in `parser.py` / `resolver.py` /
`linter.py`, but operate on the raw YAML text so we can return clean
text-range patches the editor applies as Monaco edits (undoable via
the editor's normal undo stack).

Each fix is a `Fix` record with:
- `line` / `col` / `end_line` / `end_col`  (1-based, inclusive line numbers,
  exclusive end column — matches Monaco's `Range` shape minus the +1)
- `original`     the substring being replaced (for sanity checks)
- `replacement`  the new substring
- `code`         a stable code (e.g. `stop_to_end`)
- `message`      one-line explanation
- `severity`     always "warning" — these are foot-guns, not errors

Skipped on purpose: Decision-`next:`-without-default. That fix is a
structural YAML insertion (synthesize a `conditions[]` entry) and the
compiler already auto-synthesizes it during compile; the UI doesn't
need to materialize it in the source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

import yaml


@dataclass
class Fix:
    line: int
    col: int
    end_line: int
    end_col: int
    original: str
    replacement: str
    code: str
    message: str
    severity: str = "warning"

    def to_dict(self) -> dict:
        return asdict(self)


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based (line, col) for a character offset into `text`."""
    if offset <= 0:
        return 1, 1
    head = text[:offset]
    line = head.count("\n") + 1
    last_nl = head.rfind("\n")
    col = offset - (last_nl + 1) + 1
    return line, col


def _emit_match(text: str, m: re.Match, replacement: str, code: str,
                message: str) -> Fix:
    line, col = _line_col(text, m.start())
    end_line, end_col = _line_col(text, m.end())
    return Fix(
        line=line, col=col, end_line=end_line, end_col=end_col,
        original=m.group(0), replacement=replacement,
        code=code, message=message,
    )


# --- (1) `type: stop` → `type: end` ----------------------------------------

_STOP_RE = re.compile(r"(?m)^(\s*type:\s*)stop(\s*(?:#.*)?)$")


def _fix_stop_to_end(text: str) -> list[Fix]:
    out: list[Fix] = []
    for m in _STOP_RE.finditer(text):
        replacement = m.group(1) + "end" + m.group(2)
        out.append(_emit_match(
            text, m, replacement,
            "stop_to_end",
            "step type 'stop' is a near-synonym for 'end'; rename for clarity",
        ))
    return out


# --- (2) `vars.input.<param>` → `vars.input.params.<param>` ----------------

# Reserved tail tokens we never rewrite — `params`, `records`, `record` are
# legitimate input shapes.
_INPUT_RESERVED = {"params", "records", "record"}


def _fix_input_param_refs(text: str, declared_params: list[str]) -> list[Fix]:
    """Rewrite `vars.input.<param>` → `vars.input.params.<param>` when
    <param> is a declared playbook parameter. Mirrors the resolver's
    `_auto_rewrite_input_param_refs`."""
    out: list[Fix] = []
    params = [p for p in (declared_params or [])
              if isinstance(p, str) and p
              and p not in _INPUT_RESERVED]
    if not params:
        return out
    for p in params:
        # Two access forms: dotted and bracketed. Negative lookahead
        # ensures we don't double-rewrite `vars.input.params.<p>`.
        esc = re.escape(p)
        for pat, repl_fmt in (
            (rf"\bvars\.input(?!\.params\b)\.{esc}(?=\b|[^A-Za-z0-9_])",
             f"vars.input.params.{p}"),
            (rf"\bvars\.input(?!\.params\b)\[\s*['\"]{esc}['\"]\s*\]",
             f"vars.input.params[{p!r}]"),
        ):
            for m in re.finditer(pat, text):
                out.append(_emit_match(
                    text, m, repl_fmt,
                    "input_param_ref",
                    (f"declared parameter {p!r} lives at "
                     f"`vars.input.params.{p}` — bare form evaluates to "
                     f"empty at runtime"),
                ))
    return out


# --- (3) Norway problem: bare yes/no/on/off in `display:` ------------------

_NORWAY_RE = re.compile(
    r"(?im)^(\s*-?\s*display:\s*)(yes|no|on|off|true|false|y|n)(\s*(?:#.*)?)$"
)


def _fix_norway(text: str) -> list[Fix]:
    out: list[Fix] = []
    for m in _NORWAY_RE.finditer(text):
        head, val, tail = m.group(1), m.group(2), m.group(3)
        replacement = f'{head}"{val}"{tail}'
        out.append(_emit_match(
            text, m, replacement,
            "norway_quote",
            (f"YAML parses bare {val!r} as a boolean (Norway problem); "
             f"quote it so FSR's branch lookup keys off the literal string"),
        ))
    return out


# --- (4) Step name charset: disallowed chars in `name:` --------------------

_NAME_RE = re.compile(r"(?m)^(\s*-?\s*name:\s*)(.*?)(\s*(?:#.*)?)$")
_BAD_CHAR_RUN = re.compile(r"[^A-Za-z0-9 _\"]+")
_NAME_OK = re.compile(r"^[A-Za-z0-9 _]+$")


def _strip_quotes(s: str) -> tuple[str, str, str]:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[0], s[1:-1], s[-1]
    return "", s, ""


def _fix_step_name_charset(text: str) -> list[Fix]:
    """Rewrite step `name:` values that contain characters outside
    `[A-Za-z0-9 _]` — the FSR designer rejects these on save. Substitutes
    runs of disallowed chars with `_`. Conservative: only fires when the
    surrounding line clearly looks like a step `name:` (we can't know
    structure without parsing, so a `playbook.name` may also match — but
    those are typically clean strings, so the regex stays harmless).
    """
    out: list[Fix] = []
    for m in _NAME_RE.finditer(text):
        head, raw, tail = m.group(1), m.group(2), m.group(3)
        ql, inner, qr = _strip_quotes(raw)
        if not inner or _NAME_OK.match(inner):
            continue
        # Rewrite disallowed runs to `_`. Keep quotes if the source had
        # them; add quotes when the new value still contains spaces and
        # the source was unquoted (defensive — current substitution
        # never introduces quote-requiring chars, but keeps shape stable).
        fixed = re.sub(r"[^A-Za-z0-9 _]+", "_", inner).strip("_")
        if not fixed or fixed == inner:
            continue
        replacement = f"{head}{ql}{fixed}{qr}{tail}"
        out.append(_emit_match(
            text, m, replacement,
            "step_name_charset",
            (f"step name {inner!r} contains characters outside "
             f"[A-Za-z0-9 _]; the FSR designer rejects this on save"),
        ))
    return out


# --- declared-parameter sniff (cheap; avoids pulling the parser in) -------

_PARAMETERS_RE = re.compile(
    r"(?m)^\s*parameters:\s*\[([^\]]*)\]\s*$"
)
_PARAMETERS_BLOCK_RE = re.compile(
    r"(?m)^(\s*)parameters:\s*\n((?:\1\s+-\s+\S.*\n)+)"
)
_LIST_ITEM_RE = re.compile(r"-\s+(\S[^\s#]*)")


def _sniff_parameters(text: str) -> list[str]:
    """Pull declared playbook `parameters:` from the source — both the
    flow `[a, b]` and block `- a\n  - b` forms. Best-effort; the IR
    rewriter in resolver.py is authoritative."""
    out: list[str] = []
    for m in _PARAMETERS_RE.finditer(text):
        items = [s.strip().strip("'\"") for s in m.group(1).split(",")]
        out.extend([s for s in items if s])
    for m in _PARAMETERS_BLOCK_RE.finditer(text):
        body = m.group(2)
        for im in _LIST_ITEM_RE.finditer(body):
            out.append(im.group(1).strip("'\""))
    # de-dup, preserve order
    seen = set()
    uniq = []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


# --- (5/6) set_variable: reserved-key rename + vars.steps.X.K namespace ---
#
# These mirror the IR-level rewrites in resolver.py
# (`_auto_rename_reserved_set_var_keys` and `_auto_rewrite_set_var_step_refs`)
# so the editor's Fixes panel has applicable patches matching the warnings
# the compiler emits. Renames the declaration site AND every downstream
# `vars.<old>` reference; rewrites `vars.steps.<set_var_step>.<key>` →
# `vars.<key>`. The reserved-key list is sourced from validator.py.


@dataclass
class _SetVarStep:
    name: str          # display name as written in YAML
    jkey: str          # spaces→underscores form used in `vars.steps.<jkey>`
    keys: list[str]    # declared variable names
    # Per-key declaration site as 0-based (line, start_col, end_col). Used
    # to emit a precise rename Fix on the key token only. `arg_list` form
    # points at the value of `name:` inside the list item; flat form
    # points at the bare key.
    key_marks: dict[str, tuple[int, int, int]]


def _sniff_set_variable_steps(text: str) -> list[_SetVarStep]:
    """Walk the YAML once via `yaml.compose` to collect every set_variable
    step's name + declared keys + per-key source marks. Returns an empty
    list if the YAML doesn't parse — source_fixer is best-effort, so a
    half-typed buffer just yields no fixes."""
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return []
    if root is None:
        return []

    out: list[_SetVarStep] = []

    def _scalar(n) -> str | None:
        return n.value if isinstance(n, yaml.ScalarNode) else None

    def _map_items(n):
        return n.value if isinstance(n, yaml.MappingNode) else []

    def _seq_items(n):
        return n.value if isinstance(n, yaml.SequenceNode) else []

    def _walk_step(step_node):
        if not isinstance(step_node, yaml.MappingNode):
            return
        fields = {_scalar(k): v for k, v in _map_items(step_node)}
        if _scalar(fields.get("type")) != "set_variable":
            return
        name = _scalar(fields.get("name")) or ""
        if not name:
            return
        keys: list[str] = []
        marks: dict[str, tuple[int, int, int]] = {}
        # Three shapes the resolver/parser accept: arguments.arg_list,
        # arguments.<flat>, top-level vars:/set:.
        decl: yaml.Node | None = None
        is_arg_list = False
        args = fields.get("arguments")
        if isinstance(args, yaml.MappingNode):
            arg_fields = {_scalar(k): v for k, v in _map_items(args)}
            if isinstance(arg_fields.get("arg_list"), yaml.SequenceNode):
                decl = arg_fields["arg_list"]
                is_arg_list = True
            else:
                decl = args
        elif isinstance(fields.get("vars"), yaml.MappingNode):
            decl = fields["vars"]
        elif isinstance(fields.get("set"), yaml.MappingNode):
            decl = fields["set"]
        elif isinstance(fields.get("arg_list"), yaml.SequenceNode):
            decl = fields["arg_list"]
            is_arg_list = True

        if decl is None:
            return
        if is_arg_list:
            for item in _seq_items(decl):
                if not isinstance(item, yaml.MappingNode):
                    continue
                item_fields = {_scalar(k): v for k, v in _map_items(item)}
                name_node = item_fields.get("name")
                if not isinstance(name_node, yaml.ScalarNode):
                    continue
                k = name_node.value
                if not isinstance(k, str):
                    continue
                keys.append(k)
                sm = name_node.start_mark
                em = name_node.end_mark
                marks[k] = (sm.line, sm.column, em.column)
        else:
            for k_node, _v in _map_items(decl):
                k = _scalar(k_node)
                if not isinstance(k, str) or k == "step_variables":
                    continue
                keys.append(k)
                sm = k_node.start_mark
                marks[k] = (sm.line, sm.column, sm.column + len(k))
        if not keys:
            return
        out.append(_SetVarStep(
            name=name,
            jkey=name.replace(" ", "_"),
            keys=keys,
            key_marks=marks,
        ))

    # Find every `steps:` sequence under any playbook and feed each item
    # to _walk_step. Cheap recursive walk — depth is bounded by IR shape.
    def _hunt(node):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                if _scalar(k) == "steps" and isinstance(v, yaml.SequenceNode):
                    for item in v.value:
                        _walk_step(item)
                else:
                    _hunt(v)
        elif isinstance(node, yaml.SequenceNode):
            for v in node.value:
                _hunt(v)

    _hunt(root)
    return out


def _reserved_keys() -> set[str]:
    """Lazy import of the authoritative reserved-keys set so we never
    drift from the validator/resolver."""
    from fsr_core.compiler.validator import _RESERVED_VARS_KEYS
    return _RESERVED_VARS_KEYS


def _safe_rename(old: str, taken: set[str]) -> str:
    """Mirror of `Resolver._safe_rename` — keep replacements aligned so
    the source-fix replacement matches what the IR rewriter would pick."""
    for cand in (f"{old}_var", f"my_{old}", f"{old}_value", f"{old}_2"):
        if cand not in taken:
            return cand
    return f"{old}_renamed"


def _fix_set_var_reserved_keys(
    text: str, sv_steps: list[_SetVarStep],
) -> list[Fix]:
    """For each set_variable step, rename any declared key that collides
    with FSR's reserved `vars.*` names AND rewrite every downstream
    `vars.<old>` reference (excluding `vars.steps.*` and `vars.input.*`,
    which live in different namespaces).
    """
    out: list[Fix] = []
    if not sv_steps:
        return out
    reserved = _reserved_keys()
    # Track aggregate renames across the file so the matching reference
    # rewriter can find them. (Two set_var steps with the same reserved
    # key both get the same `<key>_var` replacement — that's fine; the
    # references are top-level `vars.<key>` either way.)
    renames: dict[str, str] = {}

    for sv in sv_steps:
        for k in sv.keys:
            if k not in reserved or k == "step_variables":
                continue
            new = _safe_rename(k, reserved)
            renames[k] = new
            line0, col0, end_col0 = sv.key_marks[k]
            line = line0 + 1
            col = col0 + 1
            end_col = end_col0 + 1
            out.append(Fix(
                line=line, col=col, end_line=line, end_col=end_col,
                original=k, replacement=new,
                code="set_var_reserved_key",
                message=(
                    f"set_variable key {k!r} is reserved by FSR runtime "
                    f"(`vars.{k}` is a structured envelope); rename to "
                    f"{new!r} so the runtime doesn't crash"
                ),
            ))

    if not renames:
        return out

    # Rewrite every `vars.<old>` (any access form) in the source —
    # except `vars.steps.*` (step-output namespace) and
    # `vars.input.*` (trigger-input namespace), neither of which the
    # SetVariable rename touches.
    for old, new in renames.items():
        esc = re.escape(old)
        # Negative lookbehind for `.steps` / `.input` paths and for
        # `<word>_<old>` (don't rewrite `previous_message`).
        # Two access forms: `vars.<old>` and `vars['<old>']` / ["<old>"].
        for pat, repl in (
            (
                rf"(?<![A-Za-z0-9_])vars\.{esc}(?=\b|[^A-Za-z0-9_])",
                f"vars.{new}",
            ),
            (
                rf"(?<![A-Za-z0-9_])vars\[\s*['\"]{esc}['\"]\s*\]",
                f"vars[{new!r}]",
            ),
        ):
            for m in re.finditer(pat, text):
                out.append(_emit_match(
                    text, m, repl,
                    "set_var_reserved_key",
                    (
                        f"`vars.{old}` references the renamed set_variable "
                        f"key (was reserved by FSR); rewrite to `vars.{new}`"
                    ),
                ))
    return out


def _fix_set_var_step_namespace(
    text: str, sv_steps: list[_SetVarStep],
) -> list[Fix]:
    """Rewrite `vars.steps.<sv_step>.<key>` (and bracket forms) to
    `vars.<key>` for every set_variable step's declared keys. Mirrors
    `Resolver._auto_rewrite_set_var_step_refs`."""
    out: list[Fix] = []
    if not sv_steps:
        return out
    reserved = _reserved_keys()
    for sv in sv_steps:
        if not sv.jkey:
            continue
        esc_j = re.escape(sv.jkey)
        for k in sv.keys:
            esc_k = re.escape(k)
            # Pick the post-rename name for the replacement target if the
            # key was reserved — keeps source coherent if both fixers run
            # together. (The reserved-key fixer also rewrites bare
            # `vars.<old>`, but that pattern excludes `vars.steps.*`,
            # so we resolve the new name here.)
            new_k = _safe_rename(k, reserved) if (k in reserved and k != "step_variables") else k
            vs = r"(?<![A-Za-z0-9_])vars(?:\.steps|\[\s*['\"]steps['\"]\s*\])"
            sj = rf"(?:\.{esc_j}|\[\s*['\"]{esc_j}['\"]\s*\])"
            kt_dot = rf"\.{esc_k}(?=\b|[^A-Za-z0-9_])"
            kt_br  = rf"\[\s*['\"]{esc_k}['\"]\s*\]"
            for kt in (kt_dot, kt_br):
                pat = re.compile(vs + sj + kt)
                for m in re.finditer(pat, text):
                    out.append(_emit_match(
                        text, m, f"vars.{new_k}",
                        "set_var_step_namespace",
                        (
                            f"`vars.steps.{sv.jkey}.{k}` evaluates to empty "
                            f"at runtime — set_variable outputs live at "
                            f"top-level `vars.{new_k}`"
                        ),
                    ))
    return out


def collect_fixes(text: str) -> list[Fix]:
    """Top-level: run every source-level fixer and return all fixes,
    sorted by source position so the editor can apply them bottom-up
    (a list-reverse before the apply loop) without invalidating earlier
    line/col offsets."""
    fixes: list[Fix] = []
    fixes.extend(_fix_stop_to_end(text))
    fixes.extend(_fix_input_param_refs(text, _sniff_parameters(text)))
    fixes.extend(_fix_norway(text))
    fixes.extend(_fix_step_name_charset(text))
    sv_steps = _sniff_set_variable_steps(text)
    fixes.extend(_fix_set_var_reserved_keys(text, sv_steps))
    fixes.extend(_fix_set_var_step_namespace(text, sv_steps))
    fixes.sort(key=lambda f: (f.line, f.col))
    return fixes
