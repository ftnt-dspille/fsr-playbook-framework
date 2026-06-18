"""AI-driven "describe → step" drafter.

Powers the inspector's ``✨ Describe what you want`` button. Given a
natural-language intent + the active step type (and, where relevant,
the picked module), returns a JSON ``arguments`` body the user can
preview against the current step and one-click apply.

Design choices for the MVP:

* **Non-streaming, single round-trip.** The agent does not call MCP
  tools mid-turn. Instead, the route handler pre-loads the corpus
  patterns and module schema for the relevant module and stuffs them
  into the system prompt, then asks for one JSON object back. This
  keeps latency + cost bounded and the contract simple.

* **One ground-truth schema example per step type.** The model gets
  three things in its system prompt: (1) what the step does, (2) the
  canonical wire shape — drawn from the same corpus that powers
  ``step_examples``, (3) the user's intent. The output schema is
  enforced via the existing JSON-mode contract on the provider.

* **No round-trip through the YAML compiler from this module.**
  The frontend feeds the proposed args through ``setArgs`` which
  goes through the visual store; the resolver + validator only run
  on save. That keeps the drafter cheap to call repeatedly.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from backend.step_examples import cluster_examples, STEP_TYPE_TO_CORPUS

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "fsr_reference.db"


# Per-step-type "what does this step do" intro the model reads first.
# Keep terse — the corpus examples below carry the structural detail.
STEP_INTROS: dict[str, str] = {
    "decision":
        "Branches the playbook on Jinja predicates. Args go under "
        "`conditions:[{option, condition?, default?, step_iri?}]`. "
        "Exactly one branch should set `default: true` (the else).",
    "manual_input":
        "Pauses the playbook and prompts an analyst. Friendly authoring "
        "shape: `arguments.{title, description, inputs:[{name, label, "
        "formType, required, defaultValue?, tooltip?}], options:[{option, "
        "primary?, next?}]}`. The resolver expands `inputs` → "
        "`input.schema.inputVariables` and `options` → "
        "`response_mapping.options` at compile time.",
    "find_record":
        "Queries records from a module. Args: `module: '<name>?$limit=N'`, "
        "`query: {logic: 'AND'|'OR', filters: [<leaf|group>], sort: [], "
        "limit: N, __selectFields?: [...]}`. Each leaf is "
        "`{field, operator, value, type}` with operator one of "
        "eq/neq/lt/lte/gt/gte/in/nin/like/contains/exists/isnull. "
        "Groups recurse via `{logic, filters:[...]}`.",
    "create_record":
        "Creates a record. Args: `collection: '/api/3/<module>'`, "
        "`operation: 'Overwrite'`, `resource: {<fieldName>: <value>, ...}`, "
        "optional `__bulk: bool`, optional "
        "`fieldOperation: {<fieldName>: 'Overwrite'|'Append'|'Replace'}`.",
    "update_record":
        "Updates a record. Same shape as create_record but `collection` "
        "can be a Jinja IRI to the existing record. `operation` "
        "defaults to `Overwrite`; `Append` / `Replace` are also valid.",
    "set_variable":
        "Stores values into `vars`. Friendly shape (preferred): "
        "`arg_list: [{name, value}, ...]`. Each `name` becomes "
        "`vars.<name>` for downstream steps.",
    "delay":
        "Pauses the playbook. Friendly shape: top-level `seconds`/"
        "`minutes`/`hours`/`days` integers (any combination is summed).",
    "workflow_reference":
        "Calls a child playbook. Args: `workflowReference: '/api/3/"
        "workflows/<uuid>'` (or a Jinja expression resolving to one), "
        "`arguments: {<inputName>: <value>, ...}` for the target's "
        "input parameters, plus `apply_async`, `pass_input_record`, "
        "`pass_parent_env` flags.",
    "code_snippet":
        "Runs an inline Python snippet. Args: "
        "`params: {python_function: '<source>'}`. The function may "
        "reference `vars.X` directly; jinja-python is enabled.",
    "raise_exception":
        "Halts the run with a descriptive message. Args: "
        "`{message: '<reason>'}`.",
    "terminate":
        "Ends the current run. Args: `{message?: '<reason>'}`.",
    "assert":
        "Fails the run when the predicate evaluates falsy. Args: "
        "`{condition: '{{ <jinja> }}', message?: '<reason>'}`.",
    "start_on_create":
        "Trigger that fires when a record is created on a module. "
        "Args: `resource: '<module>'`, `resources: ['<module>']`, "
        "`fieldbasedtrigger: {logic, filters:[...], sort:[], limit:30}`, "
        "`triggerOnSource: true`, `triggerOnReplicate: false`.",
    "start_on_update":
        "Trigger that fires when a record is updated. Same shape as "
        "start_on_create. The `is_changed` operator is unique to update "
        "triggers — emits a leaf with no `value`, gated on any change "
        "to that field.",
    "start":
        "Manual / designer trigger — runs on demand against `resource`.",
    "manual_action":
        "Trigger that fires when an analyst clicks an action button on "
        "a record.",
    "api_call":
        "Trigger that fires when an external system POSTs to this "
        "playbook's endpoint.",
}


JSON_FENCE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model response.

    Models occasionally wrap output in fences or add prose around it
    despite our instructions. Try a fenced block first, then the
    first balanced `{...}` slice. Returns ``None`` on parse failure.
    """
    for source in (JSON_FENCE.search(text), None):
        if source:
            try:
                return json.loads(source.group(1).strip())
            except json.JSONDecodeError:
                pass
    # Fallback: greedy first/last brace.
    first = text.find("{")
    last = text.rfind("}")
    if first < 0 or last <= first:
        return None
    try:
        return json.loads(text[first:last + 1])
    except json.JSONDecodeError:
        return None


def _format_field_catalog(fields: list[dict[str, Any]]) -> str:
    """Compact, model-friendly rendering of a module's field list.

    One field per line: ``name (type, [picklist=…]) — title``. We
    truncate after 60 fields so the prompt stays bounded on wide
    modules like ``alerts`` (which has 90+).
    """
    lines: list[str] = []
    for f in fields[:60]:
        bits = [f.get("name", "?")]
        type_ = f.get("type")
        if type_:
            bits.append(f"({type_})")
        if f.get("required"):
            bits.append("REQUIRED")
        title = f.get("title")
        if title and title.strip() and title.strip() != f.get("name"):
            bits.append(f"— {title}")
        line = " ".join(bits)
        if f.get("picklist_options"):
            try:
                vals = json.loads(f["picklist_options"])
                if isinstance(vals, list) and vals:
                    line += f"   picklist: [{', '.join(map(str, vals[:8]))}{', …' if len(vals) > 8 else ''}]"
            except (json.JSONDecodeError, TypeError):
                pass
        lines.append(line)
    if len(fields) > 60:
        lines.append(f"… and {len(fields) - 60} more fields")
    return "\n".join(lines)


def _format_corpus_examples(examples: list[dict[str, Any]]) -> str:
    """Render up to 3 corpus skeletons + summaries for prompt context."""
    blocks: list[str] = []
    for ex in examples[:3]:
        blocks.append(
            f"# Pattern (seen {ex['frequency']}× in {ex['playbook_count']} playbooks)\n"
            f"# Summary: {ex['summary']}\n"
            f"{json.dumps(ex['arguments'], indent=2)}"
        )
    return "\n\n".join(blocks)


def build_system_prompt(step_type: str, module: str | None,
                        intent: str, current_args: dict[str, Any] | None) -> str:
    """Build the focused system prompt for a single step-type draft.

    The prompt has four sections: intro (what the step does), schema
    + corpus patterns, current draft (when iterating), and the strict
    output contract.
    """
    intro = STEP_INTROS.get(step_type,
        f"Author a `{step_type}` step. Output JSON only — see contract below.")

    sections: list[str] = [
        f"You are drafting a single FortiSOAR playbook step of type "
        f"`{step_type}`.",
        f"\n## What this step does\n{intro}",
    ]

    # Module schema — only relevant for trigger / find_record / record CRUD.
    if module:
        if not DB_PATH.exists():
            module_block = f"(module catalog unavailable; module name is `{module}`)"
        else:
            with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as c:
                c.row_factory = sqlite3.Row
                rows = c.execute(
                    "SELECT field_name, title, type, required, picklist_options "
                    "FROM module_fields WHERE module_name = ? ORDER BY field_name",
                    (module,),
                ).fetchall()
            field_dicts = [
                {
                    "name": r["field_name"],
                    "title": r["title"],
                    "type": r["type"],
                    "required": bool(r["required"]),
                    "picklist_options": r["picklist_options"],
                }
                for r in rows
            ]
            module_block = (
                f"Module: {module}\n"
                f"Fields available:\n{_format_field_catalog(field_dicts)}"
            )
        sections.append(f"\n## Schema\n{module_block}")

    # Corpus examples — pulled from the same data store the Examples
    # tab uses so the model sees real production patterns.
    if DB_PATH.exists() and step_type in STEP_TYPE_TO_CORPUS:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as c:
            c.row_factory = sqlite3.Row
            examples = cluster_examples(c, step_type, limit=3)
        if examples:
            sections.append(
                f"\n## Patterns from production\n"
                f"Real `{step_type}` shapes mined from existing playbooks:\n\n"
                f"{_format_corpus_examples(examples)}"
            )

    if current_args:
        sections.append(
            "\n## Current draft (refine if helpful)\n"
            f"```json\n{json.dumps(current_args, indent=2)}\n```"
        )

    sections.append(
        "\n## Output contract\n"
        "Return ONE valid JSON object. No prose, no fences, no commentary.\n"
        "The object IS the proposed `arguments:` block for the step.\n"
        "Use the friendly authoring shape where the step type has one — the\n"
        "compiler resolver will expand to canonical FSR form.\n"
        "Prefer values from picklist enumerations when the field has them.\n"
        "Use `{{ vars.input.records[0].<field> }}` for record-bound values\n"
        "and `{{ vars.input.params['<name>'] }}` for playbook inputs.\n"
        "If the user's intent is ambiguous, pick the most common pattern\n"
        "from the corpus above and add a short `_note: '...'` key the user\n"
        "will see in the diff."
    )

    sections.append(f"\n## User's intent\n{intent.strip()}")
    return "\n".join(sections)


def validate_proposed_args(step_type: str,
                           proposed: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the proposed args through the YAML compiler and return only
    the errors/warnings scoped to this step.

    Synthesises a minimal one-step playbook YAML around the proposal,
    delegates to the existing `compile_yaml` (parse → resolve →
    validate), and filters the resulting diagnostics to those whose
    `path` references `steps[0]` so unrelated structural noise (e.g.
    missing trigger on a fragment that wasn't meant to be a complete
    playbook) doesn't pollute the diff.

    Returns a list — empty on clean validate. Each entry has
    ``{severity, code, path, message, suggestion}``. Wraps any
    compiler-side import failure in a single ``severity: 'unknown'``
    diagnostic so the route handler can render it gracefully.
    """
    import sys
    repo_python = REPO_ROOT / "tooling"
    if str(repo_python) not in sys.path:
        sys.path.insert(0, str(repo_python))
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile  # type: ignore[import-not-found]
    except ImportError as exc:
        return [{
            "severity": "unknown",
            "code": "compiler_unavailable",
            "path": "",
            "message": f"compiler module not importable: {exc}",
            "suggestion": "",
        }]

    # Use the YAML emitter to produce the step body — naive json.dumps
    # would quote keys and break compatibility with the parser. PyYAML
    # is already a dependency for the compiler so it's a safe import.
    import yaml as _yaml
    step = {
        "name": "Drafted Step",
        "type": step_type,
        "arguments": proposed,
    }
    playbook_doc = {
        "collection": {"name": "_drafter_validation"},
        "playbooks": [{
            "name": "validate",
            "description": "",
            "steps": [step],
        }],
    }
    yaml_text = _yaml.safe_dump(playbook_doc, sort_keys=False)
    result = _compile(yaml_text, DB_PATH)

    diagnostics: list[dict[str, Any]] = []
    for e in (result.errors or []):
        diagnostics.append({
            "severity": "error",
            "code": getattr(e, "code", "unknown"),
            "path": getattr(e, "path", "") or "",
            "message": getattr(e, "message", str(e)),
            "suggestion": getattr(e, "suggestion", "") or "",
        })
    for w in (result.warnings or []):
        diagnostics.append({
            "severity": "warning",
            "code": getattr(w, "code", "unknown"),
            "path": getattr(w, "path", "") or "",
            "message": getattr(w, "message", str(w)),
            "suggestion": getattr(w, "suggestion", "") or "",
        })
    # Only return diagnostics that point at our synthesised step. The
    # compiler also raises whole-playbook structural errors (e.g. "no
    # trigger") that don't apply to a step fragment under review.
    return [d for d in diagnostics if "steps[0]" in d["path"] or not d["path"]]


async def draft_step_args(
    step_type: str,
    intent: str,
    module: str | None = None,
    current_args: dict[str, Any] | None = None,
    provider_name: str | None = None,
) -> dict[str, Any]:
    """Generate proposed `arguments` for a step from a natural-language
    intent.

    Returns ``{ok: bool, proposed_args?: dict, raw_text?: str,
    error?: str, prompt_chars: int}``. The ``prompt_chars`` field
    helps the UI show a "this used N tokens of context" hint without
    needing a tokenizer dependency.
    """
    from fsr_playbooks.llm.factory import get_provider
    from fsr_playbooks.llm.provider import (
        Message, TextEvent, ErrorEvent, DoneEvent,
    )

    system = build_system_prompt(step_type, module, intent, current_args)

    provider = get_provider(provider_name)
    messages = [Message(role="user", content=intent.strip() or "(no intent)")]
    text_chunks: list[str] = []
    error: str | None = None

    async for ev in provider.stream(
        system=system,
        messages=messages,
        tools=[],
        tags={"feature": "step_drafter", "step_type": step_type},
    ):
        if isinstance(ev, TextEvent):
            text_chunks.append(ev.text)
        elif isinstance(ev, ErrorEvent):
            error = ev.message
            break
        elif isinstance(ev, DoneEvent):
            break

    raw = "".join(text_chunks).strip()
    if error:
        return {"ok": False, "error": error, "raw_text": raw,
                "prompt_chars": len(system)}

    parsed = extract_json(raw)
    if parsed is None:
        return {
            "ok": False,
            "error": "model did not return parseable JSON",
            "raw_text": raw[:2000],
            "prompt_chars": len(system),
        }
    # Run the proposal through the compiler so the modal can flag any
    # structural problems before the user clicks Apply. Failures here
    # don't reject the draft (the user might be intentionally producing
    # a partial fragment); they're surfaced as warnings on the diff.
    diagnostics: list[dict[str, Any]] = []
    try:
        diagnostics = validate_proposed_args(step_type, parsed)
    except Exception as exc:  # noqa: BLE001 — best-effort validation
        diagnostics = [{
            "severity": "unknown",
            "code": "validate_crash",
            "path": "",
            "message": f"validation crashed: {exc}",
            "suggestion": "",
        }]
    return {
        "ok": True,
        "proposed_args": parsed,
        "raw_text": raw[:2000],
        "prompt_chars": len(system),
        "diagnostics": diagnostics,
    }
