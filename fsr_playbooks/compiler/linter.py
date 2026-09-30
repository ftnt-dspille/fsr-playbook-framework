"""Linter v1 -- raw-YAML + IR rules that catch FSR foot-guns.

The compiler's other passes work off the parsed IR, but a few important
checks need the *original YAML text* because YAML 1.1 has already
silently coerced the offending tokens (bare ``yes``/``no`` -> Python
``True``/``False``) by the time we reach the IR. This module runs over
both surfaces and emits structured ``CompileError`` warnings so the
existing tooling (CLI, MCP, frontend Monaco markers) shows them
without any wiring change.

Rules implemented:
1. **Norway problem** - bare ``yes``/``no``/``on``/``off``/``y``/``n``/
   ``true``/``false`` (case-insensitive) used as a Decision step
   ``branches:`` key or ``option:`` value. FSR's runtime keys routes off
   the literal string the designer renders; YAML coerces these to
   booleans, so the route lookup later returns ``CS-WF-10: Either the
   Step IRI or the Condition is not set``.
2. **Step-name charset** - FSR's designer enforces ``[A-Za-z0-9 _]`` on
   step ``name``. Em-dashes, hyphens, ``?``, ``:``, parens, etc. all push
   fine via the API but the playbook becomes uneditable in the UI.
3. **Missing ``mock_result`` on Fetch / IngestBulkFeed** - templates that
   expect ``--mock`` plumbing validation need a placeholder body.
   ``IngestBulkFeed`` is *not* in ``EXCLUDED_FROM_MOCK_OUTPUT``, so it
   runs live even under ``useMockOutput=true`` - missing
   ``mock_result`` surfaces resolveRange/picklist errors against TODO
   placeholders during a mock run.

Severity policy:
- (1) and (2) are blocking errors (FSR-level breakage).
- (3) is a warning - it doesn't break a real run, only mock plumbing.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .errors import CompileError, ErrorCode
from .ir import Collection, Step
from .snippet_checks import check_snippet

# YAML 1.1 boolean tokens (case-insensitive). Quoting any of these
# in a string-keyed context preserves the literal.
_NORWAY_TOKENS = {
    "yes", "no", "on", "off", "y", "n", "true", "false",
}

_STEP_NAME_OK = re.compile(r"^[A-Za-z0-9 _]+$")
_DISALLOWED_RUNS = re.compile(r"[^A-Za-z0-9 _]+")

# Match `branches:` block keys at YAML key positions. We only care about
# unquoted scalars - quoted forms are already safe.
_BRANCH_KEY_RE = re.compile(
    r"""(?mx)                # multiline + verbose
    ^[ \t]+                  # any indent
    ( yes | no | on | off | y | n | true | false )
    [ \t]* :                 # mapping key marker
    """,
    re.IGNORECASE,
)

# Match `display: <bare-token>` (decision/manual_input branch label).
_DISPLAY_BARE_RE = re.compile(
    r"""(?mx)
    ^[ \t]*-?[ \t]*          # list-item or plain key
    display [ \t]* :
    [ \t]+
    ( yes | no | on | off | y | n | true | false )
    [ \t]*$                  # nothing else on the line
    """,
    re.IGNORECASE,
)


def _scan_norway(text: str) -> list[CompileError]:
    """Find unquoted yes/no/etc. in decision/manual_input `display:` values.

    The regex is intentionally textual: by the time we have the IR,
    `True`/`False` (Python booleans) are indistinguishable from a user
    who genuinely meant the strings ``"True"``/``"False"`` quoted.
    Working off the raw YAML lets us blame the original token.
    """
    errs: list[CompileError] = []
    for m in _DISPLAY_BARE_RE.finditer(text):
        tok = m.group(1)
        ln_no = text.count("\n", 0, m.start()) + 1
        errs.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(f"display value {tok!r} is parsed as a YAML 1.1 "
                     "boolean; the route label will not match at runtime. "
                     "Quote it."),
            path=f"<line {ln_no}>",
            suggestion=f'use display: "{tok}" instead of display: {tok}',
        ))
    return errs


_UUID_RE = __import__("re").compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _slugify(name: str) -> str:
    """Best-effort slug for a step's display name. Mirrors the
    designer's allowed charset: alphanumeric / space / underscore."""
    import re
    s = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    return s or "step"


def _check_step_id_uuid(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when a step `id:` looks like a UUID. Compiles fine but
    breaks every cross-reference idiom (`branches: { yes: <id> }`,
    `next: <id>`) and makes the YAML unreadable. Real-world failure
    mode from feedback session 60743f70 -- agent emitted
    `id: 550e8400-...` for every step instead of short slugs.
    """
    if not s.id or not _UUID_RE.match(s.id):
        return None
    suggestion = _slugify(s.name or "step")
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        message=(f"step id {s.id!r} is a UUID; FSR step ids should be "
                 f"short slugs you can reference from `next:` and "
                 f"`branches:` (the compiler generates real UUIDs at "
                 f"emit time)"),
        path=f"playbooks[{pi}].steps[{si}].id",
        suggestion=f"rename id to {suggestion!r}",
        severity="warning",
    )


def _check_step_name(s: Step, pi: int, si: int) -> CompileError | None:
    """Auto-fix step names that the FSR designer would refuse to save.

    The designer rejects any character outside `[A-Za-z0-9 _]` on save
    (em-dash, hyphen, ?, :, parens, etc). We rewrite the name in place
    by substituting disallowed runs with `_`, and emit a warning. The
    parser's `name_to_id` map already includes the substituted form so
    `next:` references with the original chars still resolve.
    """
    name = s.name or s.id
    if not name or _STEP_NAME_OK.match(name):
        return None
    fixed = _DISALLOWED_RUNS.sub("_", name).strip("_") or "step"
    s.name = fixed
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        severity="warning",
        message=(f"step name {name!r} contains characters outside "
                 "[A-Za-z0-9 _] (the FSR designer rejects these on save) "
                 f"-- auto-renamed to {fixed!r}"),
        path=f"playbooks[{pi}].steps[{si}].name",
    )


def _check_mock_result(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when a mock-incompatible step lacks a `mock_result`.

    Two trigger cases:
    - Step name starts with "Fetch" (the canonical recipe-template
      Fetch step) and type is `connector`.
    - Step uses the IngestBulkFeed handler / step type, which runs live
      even under ``useMockOutput=true``.
    """
    name = (s.name or s.id or "").strip()
    args = s.arguments or {}
    has_mock = any(
        k in args for k in ("mock_result", "mockResult", "mock_data")
    )
    if has_mock:
        return None

    is_ingest_bulk = (
        s.type in ("ingest_bulk_feed", "IngestBulkFeed")
        or (s.handler or "").lower() == "ingestbulkfeed"
    )
    is_fetch_named = (
        s.type == "connector" and name.lower().startswith("fetch")
    )
    if not (is_ingest_bulk or is_fetch_named):
        return None

    why = ("IngestBulkFeed runs live even under useMockOutput=true; "
           "without a mock_result, --mock runs will hit live picklist "
           "lookups against TODO placeholders") if is_ingest_bulk else (
           "this Fetch step has no mock_result; --mock runs will return "
           "an empty payload, hiding downstream wiring bugs")
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        message=(f"step {name!r} has no `mock_result`. {why}."),
        path=f"playbooks[{pi}].steps[{si}].arguments.mock_result",
        suggestion="add a mock_result with a representative payload",
        severity="warning",
    )


_SEVERITY_TO_CODE = {
    "error": ErrorCode.BAD_VALUE,
    "warning": ErrorCode.BAD_VALUE,
}


def _snippet_body(s: Step) -> str | None:
    """Pull the Python body out of a code_snippet step, friendly or canonical.

    Friendly authoring puts it under ``arguments.code`` / ``arguments.python``;
    the canonical CodeSnippet shape (post-expand, or a decompiled playbook) puts
    it under ``arguments.params.python_function``. Return the first non-empty
    string found, else None.
    """
    if s.type != "code_snippet":
        return None
    args = s.arguments or {}
    for key in ("code", "python"):
        v = args.get(key)
        if isinstance(v, str) and v.strip():
            return v
    params = args.get("params")
    if isinstance(params, dict):
        v = params.get("python_function")
        if isinstance(v, str) and v.strip():
            return v
    return None


def _snippet_allow_imports(s: Step) -> bool | None:
    """Best-effort read of the snippet's import setting from its own args.

    The connector config that ultimately governs imports lives on the live box,
    but an author can also set the knob inline under ``arguments`` /
    ``arguments.params`` (``allow_imports``). Return the bool if present, else
    None (= unknown → the manifest default decides, and an import is a warning).
    """
    args = s.arguments or {}
    raw_params = args.get("params")
    for container in (args, raw_params if isinstance(raw_params, dict) else {}):
        for key in ("allow_imports", "allowImports"):
            v = container.get(key)
            if isinstance(v, bool):
                return v
    return None


def _check_code_snippet(
    s: Step, pi: int, si: int, *, default_allow_imports: bool | None = None
) -> list[CompileError]:
    """B1 (syntax) + B2 (sandbox bans) for a code_snippet step.

    Delegates the actual analysis to ``snippet_checks.check_snippet`` and maps
    its findings onto ``CompileError`` rows pointed at the snippet body.

    ``default_allow_imports`` is the connector's default config import setting,
    resolved from the warmed catalog's ``connector_configs`` table.  When the
    step doesn't set ``allow_imports`` inline, this value is used instead --
    so a box whose default code-snippet config already allows imports
    suppresses the import warning without an inline ``allow_imports: true``.
    """
    body = _snippet_body(s)
    if body is None:
        return []
    args = s.arguments or {}
    version = args.get("version")
    if not isinstance(version, str):
        version = None
    inline = _snippet_allow_imports(s)
    allow_imports = inline if inline is not None else default_allow_imports
    findings = check_snippet(
        body,
        version=version,
        allow_imports=allow_imports,
    )
    out: list[CompileError] = []
    for f in findings:
        out.append(CompileError(
            code=_SEVERITY_TO_CODE.get(f.severity, ErrorCode.BAD_VALUE),
            severity=f.severity,
            message=f"code_snippet {(s.name or s.id)!r}: {f.message}",
            path=f"playbooks[{pi}].steps[{si}].arguments.code (snippet line {f.lineno})",
            suggestion=f.suggestion,
            check="snippet_sandbox",
        ))
    return out


# NOTE: a Tier-1 `_check_input_namespace` check (warn when a notrigger playbook
# reads `vars.input.params.*`, per pilot E6) was REMOVED after a live run on .205
# (run 686525) contradicted its premise: an API-triggered notrigger run populated
# `vars.input.params.first_name` correctly and had no `vars.inputs` key at all.
# The `vars.inputs` (plural) form is specific to the designer "Run" button path,
# which we can't distinguish statically -- so the check was a false positive for
# the common API/child-workflow case. See docs/plans/PILOT_STATIC_ANALYSIS_GAP_PLAN.md
# (gap E) for the evidence and the open question.


def _check_raise_exception_mock(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when a ``raise_exception`` step is reachable under ``--mock``.

    ``cyops_utilities.raise_exception`` honors ``useMockOutput=true`` and
    returns null instead of raising. A playbook that routes a failure branch
    through a ``raise_exception`` step will report ``finished`` (not ``failed``)
    under ``--mock``, masking the failure path. Authors testing with ``--mock``
    get a false green.

    The fix is to add a ``mock_result`` that includes an ``error`` key so the
    mock run surfaces the failure downstream, or to exclude the step from mock
    runs (not currently supported by FSR).
    """
    args = s.arguments or {}
    connector = args.get("connector")
    operation = args.get("operation")
    if not (connector == "cyops_utilities" and operation == "raise_exception"):
        return None
    if any(k in args for k in ("mock_result", "mockResult")):
        return None  # has a mock, so the behavior is at least intentional
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        message=(
            f"step {(s.name or s.id)!r} calls cyops_utilities.raise_exception "
            f"without a mock_result. Under useMockOutput=true it returns null "
            f"instead of raising, so a --mock run will report 'finished' even "
            f"though the failure branch executed -- a false green."
        ),
        path=f"playbooks[{pi}].steps[{si}].arguments.mock_result",
        suggestion="add a mock_result with an error key so --mock surfaces the failure",
        severity="warning",
    )


def _check_find_record_mock_shape(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when a find_record mock_result uses the envelope shape.

    Live-verified on FSR 8.0.0-6034: find_record's REAL output (no mock)
    is a raw list of records, NOT the ``{data, status, message, operation}``
    envelope. But authors commonly write ``mock_result: {data: [...],
    status: "Success"}`` -- which makes mock runs work with ``.data`` refs
    that break in production (the real list has no ``.data`` key).

    The correct mock_result for find_record is a bare list:
    ``mock_result: [{name: test}]`` -- matching the real output shape.
    """
    if s.type != "find_record":
        return None
    args = s.arguments or {}
    mock = args.get("mock_result") or args.get("mockResult")
    if not isinstance(mock, dict):
        return None  # already a list or absent
    if "data" in mock or "status" in mock:
        return CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                f"find_record step {(s.name or s.id)!r} has a mock_result "
                f"with envelope keys (data/status) but find_record's real "
                f"output is a raw list (live-verified 8.0.0). Mock runs "
                f"using `.data` refs will work but break in production. "
                f"Use a bare list: `mock_result: [{{name: test}}]`"
            ),
            path=f"playbooks[{pi}].steps[{si}].arguments.mock_result",
            suggestion="use a bare list mock_result to match real output",
            severity="warning",
        )
    return None


def _check_message_record(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when a ``message:`` block (comment) has no explicit ``record:``.

    FSR's ``message:`` block posts a collaboration comment to a record after
    the step runs.  When ``record:`` / ``records:`` is omitted, FSR defaults to
    the **trigger record** (``vars.input.records[0]``).  This is correct for
    record-triggered playbooks but fails with "No record found for posting
    the given message" in:

    - ``--mock`` runs (which use ``notrigger`` mode -- no trigger record)
    - Manual / API-triggered runs without a record

    Authors who intend the comment to attach to the trigger record can make
    this explicit with ``record: "{{ vars.input.records[0]['@id'] }}"``.
    For mock-friendly output that doesn't need a record, use ``vars:`` instead
    of ``message:``.
    """
    args = s.arguments or {}
    msg = args.get("message")
    if not isinstance(msg, dict):
        return None
    rec = msg.get("record") or msg.get("records")
    if rec:
        return None
    name = s.name or s.id or "?"
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        severity="warning",
        message=(
            f"step {name!r} has a `message:` block (comment) without an "
            f"explicit `record:` / `records:`. FSR defaults to the trigger "
            f"record (vars.input.records[0]), which is correct for "
            f"record-triggered playbooks but fails with 'No record found' "
            f"in --mock runs and manual/API-triggered runs without a record."
        ),
        path=f"playbooks[{pi}].steps[{si}].arguments.message",
        suggestion='add record: "{{ vars.input.records[0][\'@id\'] }}" to be '
                   'explicit, or use vars: instead of message: for mock-friendly output',
    )


# Step types whose REAL output is the `{data, status, message, operation}`
# envelope but whose MOCK output (mock_result) is the raw payload with NO
# envelope. A `.data` reference therefore renders EMPTY in a `--mock` run and
# only a direct reference works there -- the mirror image of production.
# Connector and code_snippet steps with mock_result return it verbatim (no
# envelope) under --mock.  BUT if the mock_result itself has a top-level
# `data` key, the author has shaped it to include the envelope and `.data`
# refs are fine -- the per-step check below skips those.
_MOCK_ENVELOPE_STEP_TYPES = {"connector", "code_snippet"}

# Regex matching `vars.steps.<key>.data.<field>` (and the bare `steps.` form
# the connector-output-rewriter also repairs). Anchored so it only fires on the
# `.data` segment, not `.data` appearing elsewhere.
_MOCK_DATA_REF_RE = re.compile(
    r"\b(?:vars\.)?steps\.([A-Za-z0-9_]+)\.data\.([A-Za-z0-9_]+)"
)


def _step_jinja_key(s: Step) -> str:
    """Jinja key FSR builds for a step output (display name, spaces -> _)."""
    base = (s.name or s.id or "").strip()
    return base.replace(" ", "_")


def _walk_strings(node, out: list[tuple[str, str, int]] | None = None,
                  where: str = "") -> list[tuple[str, str, int]]:
    """Yield (parent_step_jinja_key, jinja_string, nesting_depth) for every
    string leaf containing a Jinja expression, walking nested args/lists."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            _walk_strings(v, out, where=f"{where}.{k}" if where else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_strings(v, out, where=f"{where}[{i}]")
    elif isinstance(node, str) and "{{" in node:
        out.append((where, node, 0))
    return out


def _check_mock_step_data_refs(pb, pi: int) -> list[CompileError]:
    """Warn when a downstream reference reads `.data` off a connector or
    code_snippet step that carries a ``mock_result``.

    Live-verified on FSR 8.0 (2026-09-30): under ``--mock`` the runtime returns
    ``mock_result`` VERBATIM -- connector output lands at
    ``vars.steps.<step>.<field>`` and code_snippet output at
    ``vars.steps.<step>.code_output``, with NO ``{data, status, message,
    operation}`` envelope. A reference written as
    ``vars.steps.<step>.data.<field>`` -- which the connector-output rewriter
    actively endorses and which is CORRECT in production -- silently evaluates
    to an empty string in mock mode. That empties ``set_variable`` values and
    breaks ``for_each`` with the cryptic ``CS-WF-3: Invalid format of value for
    for_each loop ''``.

    This is a known-not-working-issue: the author is testing in mock mode (that
    is the point of ``mock_result``) and the reference they are told is correct
    will blank out exactly the values they are trying to verify. Emit a warning
    so the failure is visible at authoring time instead of as a runtime 500.
    """
    errs: list[CompileError] = []
    if not pb.steps:
        return errs

    # Steps whose output this playbook MIGHT read via `.data`: connector
    # steps that carry a mock_result.  (Code_snippets are excluded -- their
    # results are always wrapped in {data: {code_output: …}} even in mock.)
    mock_steps: dict[str, Step] = {}
    for s in pb.steps:
        if (s.type or "").lower() not in _MOCK_ENVELOPE_STEP_TYPES:
            continue
        args = s.arguments or {}
        if "mock_result" not in args and "mockResult" not in args:
            continue
        # If the mock_result itself has a top-level `data` key, the author
        # has shaped it to include the envelope -- `.data` refs WILL work
        # in mock mode, so skip the warning for this step.
        mr = args.get("mock_result") or args.get("mockResult") or {}
        if isinstance(mr, dict) and "data" in mr:
            continue
        mock_steps[_step_jinja_key(s)] = s

    if not mock_steps:
        return errs

    for s in pb.steps:
        if (s.type or "").lower() in _MOCK_ENVELOPE_STEP_TYPES:
            continue
        for _where, text, _depth in _walk_strings(s.arguments):
            for m in _MOCK_DATA_REF_RE.finditer(text):
                key = m.group(1)
                target = mock_steps.get(key)
                if target is None:
                    continue
                field = m.group(2)
                # Correct mock-mode path is the reference with the `.data`
                # envelope segment dropped -- the payload sits directly at
                # `vars.steps.<key>.<field>` (for a connector, `<field>` is the
                # op field; for a code_snippet, it is `code_output`).
                correct = f"vars.steps.{key}.{field}"
                errs.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    severity="warning",
                    message=(
                        f"step {s.name or s.id!r} reads "
                        f"`vars.steps.{key}.data.{field}` off a connector/"
                        f"code_snippet step ({key!r}) that carries a "
                        f"mock_result. Under --mock the output is returned "
                        f"verbatim with NO `.data` envelope, so this reference "
                        f"evaluates EMPTY in a mock run (and breaks for_each "
                        f"with CS-WF-3). Use `{correct}` for mock runs; "
                        f"`.data` is only correct in production."
                    ),
                    path=f"playbooks[{pi}].steps",
                    suggestion=correct,
                ))
    return errs


def _resolve_allow_imports(
    db_path: str | Path | None,
    config_name: str | None,
) -> bool | None:
    """Read a code-snippet config's ``allow_imports`` from the warmed catalog.

    ``config_name`` selects a specific named config; ``None`` picks the default
    (the ``__default__`` row, then the ``is_default`` row, then any single
    config).  Returns ``True``/``False`` when the config has the setting,
    ``None`` when the catalog is unwarmed, the table/column is absent, or no
    matching config exists.
    """
    if not db_path:
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            if config_name:
                row = conn.execute(
                    "SELECT allow_imports FROM connector_configs "
                    "WHERE connector = 'code-snippet' AND config_name = ?",
                    (config_name,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT allow_imports FROM connector_configs "
                    "WHERE connector = 'code-snippet' "
                    "ORDER BY (config_name = '__default__') DESC, "
                    "is_default DESC LIMIT 1"
                ).fetchone()
        finally:
            conn.close()
    except (sqlite3.OperationalError, OSError):
        return None
    if row is None or row[0] is None:
        return None
    return bool(row[0])


def _step_config_name(s: Step) -> str | None:
    """The config name a code_snippet step pins, or ``None`` for the default.

    At lint time (pre-resolution) ``arguments.config`` holds the author's
    raw value -- a config name string, a UUID/IRI, or absent.  We only return
    a name when it's a plain string that doesn't look like a UUID/IRI (those
    can't be looked up by name in the catalog).
    """
    args = s.arguments or {}
    val = args.get("config")
    if isinstance(val, str) and val.strip() and not _looks_like_uuid(val):
        return val.strip()
    return None


def _looks_like_uuid(s: str) -> bool:
    """True when ``s`` looks like a UUID or an IRI (not a friendly config name)."""
    if s.startswith("/"):
        return True
    parts = s.split("-")
    if len(parts) == 5 and all(len(p) in (8, 4, 4, 4, 12) for p in parts):
        return True
    return False


# Regex matching `| tojson` applied to a whole step result or .data (which
# may contain booleans like `debug: true` that the sandbox bans as `true`).
_TOJSON_ON_STEP_RE = re.compile(
    r"\|\s*tojson\b"
)
# Patterns where tojson is SAFE: applied to specific string fields extracted
# via map(attribute=...) | list, or to individual leaf values.
_SAFE_TOJSON_RE = re.compile(
    r"(?:map\s*\(\s*attribute\s*=\s*['\"][^'\"]+['\"]\s*\)\s*\|\s*list"
    r"|vars\.steps\.[A-Za-z0-9_]+\.[A-Za-z0-9_.]+\s*\|\s*tojson"
    r"|vars\.[A-Za-z_][A-Za-z0-9_]*\s*\|\s*tojson"
    r"|['\"][^'\"]*['\"]\s*\|\s*tojson)"
)


def _check_tojson_booleans(s: Step, pi: int, si: int) -> CompileError | None:
    """Warn when ``| tojson`` in a code_snippet may inject booleans.

    FSR's ``tojson`` filter renders Python booleans as ``true``/``false``
    (lowercase), which the code-snippet sandbox bans as name references
    (``true`` is not a Python keyword, so it's parsed as ``ast.Name`` and
    rejected). The most common trap is applying ``tojson`` to a whole step
    result (``vars.steps.X | tojson``) or the full data envelope
    (``vars.steps.X.data | tojson``), which includes system metadata like
    ``debug: true``.

    Safe patterns: ``map(attribute='field') | list | tojson`` extracts only
    string values; deeper field references (``vars.steps.X.data.field | tojson``)
    are typically safe because they extract specific values.
    """
    if (s.type or "").lower() != "code_snippet":
        return None
    args = s.arguments or {}
    code = args.get("code") or args.get("python_function") or ""
    if not isinstance(code, str) or "| tojson" not in code and "|tojson" not in code:
        return None
    # Dangerous patterns: tojson on a whole step result or data envelope.
    # These almost always contain `debug: true` or other booleans.
    _DANGEROUS = [
        # vars.steps.X | tojson  (whole step result -- has debug, task_id, ...)
        re.compile(r"vars\.steps\.[A-Za-z0-9_]+\s*\|\s*tojson"),
        # vars.steps.X.data | tojson  (full data envelope)
        re.compile(r"vars\.steps\.[A-Za-z0-9_]+\.data\s*\|\s*tojson"),
        # vars.input.params.X | tojson  (whole input object)
        re.compile(r"vars\.input\.params\.[A-Za-z0-9_.]+\s*\|\s*tojson"),
    ]
    for m in re.finditer(r"\{\{(.+?)\}\}", code, re.DOTALL):
        expr = m.group(1).strip()
        if "| tojson" not in expr and "|tojson" not in expr:
            continue
        # Skip if map(attribute=...) is present (extracts specific fields)
        if "map(" in expr and "attribute" in expr:
            continue
        for pat in _DANGEROUS:
            if pat.search(expr):
                return CompileError(
                    code=ErrorCode.BAD_VALUE,
                    severity="warning",
                    message=(
                        f"code_snippet step {s.name or s.id!r} uses `| tojson` "
                        f"on `{expr[:80]}` which may contain booleans (e.g. "
                        f"`debug: true`). FSR's tojson renders booleans as "
                        f"`true`/`false` (lowercase), and the sandbox bans "
                        f"`true` as a name reference. Use "
                        f"`map(attribute='field') | list | tojson` to extract "
                        f"only string values."
                    ),
                    path=f"playbooks[{pi}].steps[{si}].arguments.code",
                    suggestion=(
                        "extract only the fields you need: "
                        "`{{ vars.steps.X|map(attribute='field')|list|tojson }}`"
                    ),
                )
    return None


def lint(
    text: str,
    coll: Collection | None,
    *,
    db_path: str | Path | None = None,
) -> list[CompileError]:
    """Run every linter rule.

    ``db_path`` optionally points at the warmed reference catalog so the
    snippet checker can read the config's ``allow_imports`` setting and
    suppress the import warning when the box already allows imports.  The
    lookup is per-step: a step that pins ``config: my-config`` reads that
    config's setting; a step without ``config:`` reads the default.  Without
    a catalog (or an unwarmed one), the behavior is unchanged -- imports
    produce a warning.
    """
    errs: list[CompileError] = []
    errs.extend(_scan_norway(text))
    if coll is not None:
        for pi, pb in enumerate(coll.playbooks):
            for si, s in enumerate(pb.steps):
                e = _check_step_name(s, pi, si)
                if e:
                    errs.append(e)
                e = _check_step_id_uuid(s, pi, si)
                if e:
                    errs.append(e)
                e = _check_mock_result(s, pi, si)
                if e:
                    errs.append(e)
                e = _check_raise_exception_mock(s, pi, si)
                if e:
                    errs.append(e)
                e = _check_find_record_mock_shape(s, pi, si)
                if e:
                    errs.append(e)
                e = _check_message_record(s, pi, si)
                if e:
                    errs.append(e)
                # Resolve the step's config's allow_imports from the catalog.
                # Per-step: a pinned config name reads that config; no pin reads
                # the default.  An inline allow_imports on the step always wins.
                cfg_name = _step_config_name(s)
                catalog_ai = _resolve_allow_imports(db_path, cfg_name)
                errs.extend(
                    _check_code_snippet(s, pi, si, default_allow_imports=catalog_ai)
                )
                # Warn when |tojson in a code_snippet may inject booleans
                e = _check_tojson_booleans(s, pi, si)
                if e:
                    errs.append(e)
            # Whole-playbook check: mock connector/code_snippet steps referenced
            # via `.data` render empty in --mock runs.
            errs.extend(_check_mock_step_data_refs(pb, pi))
            # Whole-playbook check: workflow_reference children that end with
            # `end`/`stop` return {data:null} -- the parent gets no data.
            errs.extend(_check_workflow_ref_child_terminal(coll, pb, pi))
    return errs


def _child_terminal_steps(pb) -> list:
    """Steps with no outgoing edge (next/branches/unlabeled_next)."""
    terminals: list = []
    for s in pb.steps:
        has_next = bool(getattr(s, "next", None))
        has_branches = bool(getattr(s, "branches", None))
        has_unlabeled = bool(getattr(s, "unlabeled_next", None))
        if not (has_next or has_branches or has_unlabeled):
            terminals.append(s)
    return terminals


def _set_variable_var_names(s) -> set[str]:
    """Names of variables a set_variable step exports."""
    args = s.arguments if isinstance(s.arguments, dict) else {}
    names: set[str] = set()
    if isinstance(args.get("arg_list"), list):
        for it in args["arg_list"]:
            if isinstance(it, dict) and "name" in it:
                names.add(it["name"])
    elif isinstance(args.get("variables"), list):
        for it in args["variables"]:
            if isinstance(it, dict) and "name" in it:
                names.add(it["name"])
    elif isinstance(args.get("step_variables"), dict):
        names.update(args["step_variables"].keys())
    return names


def _check_workflow_ref_child_terminal(coll, pb, pi: int) -> list:
    """Warn when a workflow_reference targets a child whose terminal steps
    are `end`/`stop` (return {data:null}) -- the parent gets no data.

    Also warn when the parent reads ``vars.steps.<wf_ref>.<field>`` and the
    child's terminal set_variable steps don't export that field.
    """
    errs: list[CompileError] = []
    # Build name → playbook map for child lookup.
    by_name: dict[str, object] = {}
    for cp in coll.playbooks:
        by_name[cp.name] = cp

    for s in pb.steps:
        if (s.type or "").lower() != "workflow_reference":
            continue
        args = s.arguments if isinstance(s.arguments, dict) else {}
        target = args.get("target") or ""
        child = by_name.get(target)
        if child is None:
            continue  # resolver/linter will catch missing target separately

        terminals = _child_terminal_steps(child)
        if not terminals:
            continue

        # Check if any terminal step is a set_variable (exports data).
        exported: set[str] = set()
        for ts in terminals:
            if (ts.type or "").lower() == "set_variable":
                exported.update(_set_variable_var_names(ts))

        has_end = any((ts.type or "").lower() in ("end", "stop") for ts in terminals)

        if not exported and has_end:
            errs.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                severity="warning",
                message=(
                    f"workflow_reference step {s.name or s.id!r} targets "
                    f"{target!r} whose terminal step is `end`/`stop`. FSR "
                    f"returns only the LAST executed step's output to the "
                    f"parent -- `end` returns {{data: null}}, so the parent "
                    f"gets no data. Add a `set_variable` step as the child's "
                    f"last data step (before `end`) to export variables."
                ),
                path=f"playbooks[{pi}].steps",
                suggestion=(
                    f"add a `set_variable` step before `end` in {target!r} "
                    f"that exports the fields the parent needs"
                ),
            ))

        # If we know what the child exports, check parent refs against it.
        if exported:
            jkey = _step_jinja_key(s)
            for ds in pb.steps:
                if ds is s:
                    continue
                for _where, text, _depth in _walk_strings(ds.arguments):
                    for m in re.finditer(
                        rf"\bvars\.steps\.{re.escape(jkey)}\.([A-Za-z_][A-Za-z0-9_]*)",
                        text,
                    ):
                        field = m.group(1)
                        if field in ("data", "status", "message", "operation",
                                     "id", "name", "uuid", "@id", "@type"):
                            continue
                        if field not in exported:
                            errs.append(CompileError(
                                code=ErrorCode.BAD_VALUE,
                                severity="warning",
                                message=(
                                    f"step {ds.name or ds.id!r} reads "
                                    f"`vars.steps.{jkey}.{field}` from "
                                    f"workflow_reference {s.name or s.id!r}, "
                                    f"but child {target!r}'s terminal "
                                    f"set_variable exports only "
                                    f"{sorted(exported)!r}. Field {field!r} "
                                    f"will evaluate empty."
                                ),
                                path=f"playbooks[{pi}].steps",
                                suggestion=(
                                    f"add `{field}` to the set_variable "
                                    f"step in {target!r}, or reference a "
                                    f"field the child actually exports"
                                ),
                            ))
    return errs
