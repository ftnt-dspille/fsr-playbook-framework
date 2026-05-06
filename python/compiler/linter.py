"""Linter v1 — raw-YAML + IR rules that catch FSR foot-guns.

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

from .errors import CompileError, ErrorCode
from .ir import Collection, Step

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
    mode from feedback session 60743f70 — agent emitted
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
    """Reject step names that the FSR designer would refuse to save."""
    name = s.name or s.id
    if not name or _STEP_NAME_OK.match(name):
        return None
    suggestion = _DISALLOWED_RUNS.sub("_", name).strip("_") or "step"
    return CompileError(
        code=ErrorCode.BAD_VALUE,
        message=(f"step name {name!r} contains characters outside "
                 "[A-Za-z0-9 _]; the FSR designer rejects this on save "
                 "with 'Only alphanumeric character, space and _ is "
                 "allowed'"),
        path=f"playbooks[{pi}].steps[{si}].name",
        suggestion=f'rename to "{suggestion}"',
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


def lint(text: str, coll: Collection | None) -> list[CompileError]:
    """Run every linter rule. Pure - no DB, no live FSR."""
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
    return errs
