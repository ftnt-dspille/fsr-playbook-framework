"""Task-intent prompt + tool-slice resolution (single source of truth).

The agentic surface runs in one of two intents:

  - ``triage``  — incident-response: investigate the record in front of the
    analyst, pivot across modules, enrich indicators read-only, and stage any
    mutating/containment action via ``emit_action_card`` for approval. The
    YAML-authoring + playbook-mutation tools are dropped.
  - ``build``   — playbook authoring: the full tool registry.

Both the FortiSOAR connector (``operations.py``) and the local hunt/demo
runner resolve their system prompt + tool list through here, so the prompt
text, the dropped-tool set, and the fallbacks never drift between them. The
prompts themselves live in ``fsr_core/agent/system_prompt_{triage,build}.md``
and are vendored wholesale into the connector by ``scripts/build.sh``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

INTENTS = ("triage", "build")
DEFAULT_INTENT = "build"

# Build-only tools dropped from the triage slice: the YAML-authoring +
# playbook-mutation surface. Triage keeps discovery, picklists, run_op
# (read-only intel), get_record/search (pivoting), the HITL emit_* cards,
# and run-history diagnostics.
BUILD_ONLY_TOOLS = frozenset({
    "validate_yaml", "compile_yaml", "build_playbook_from_trace",
    "analyze_playbook",
    "verify_playbook", "verify_enhancement", "emit_decision_step",
    "search_playbooks", "get_step_type",
    "find_jinja_filter", "find_jinja_pattern", "get_filter_examples",
    "step_through_playbook", "dry_run_playbook",
    "diagnose_yaml_against_pb_execution",
    "push_playbook", "run_playbook",
})

# Inline fallbacks used only when the vendored markdown can't be read (keeps
# the agent functional even if packaging drops the .md files).
_FALLBACK_BUILD_PROMPT = (
    "You are a FortiSOAR playbook author. Help the user compose, validate, "
    "and refine YAML playbooks using the tools available. Be concise. Quote "
    "tool errors verbatim and explain the fix. The conversation may open with "
    "a prior triage transcript plus a directive to design a re-runnable "
    "playbook around the operations used during triage — reproduce those "
    "operations as parameterized steps."
)
_FALLBACK_TRIAGE_PROMPT = (
    "You are a FortiSOAR incident-response assistant triaging the record in "
    "front of you. Use find_connector -> find_operation -> get_op_schema to "
    "locate capabilities. Call run_op directly only for read-only "
    "intelligence; for ANY mutating/containment action (block, isolate, "
    "quarantine, disable, add-to-group, etc.) build the call and emit it via "
    "emit_action_card for analyst approval — never run it silently. Do not "
    "author YAML here. Be concise; quote tool errors verbatim."
)

_PROMPT_CACHE: dict[str, str] = {}


# --- P3: low-signal input gate --------------------------------------------
#
# A one-word `test` or a bare `hi` should not launch a 9-tool autonomous hunt.
# Classify the user's message so the live caller can short-circuit the
# auto-investigation: orient on the case + offer choices (trivial) or
# summarize state + propose the next step (continue), instead of re-running a
# full investigation. A real directive ("build the attack timeline") is the
# only class that should auto-investigate.

# Greetings / acks / smoke-test pings — no investigative direction.
_TRIVIAL_TOKENS = frozenset({
    "hi", "hello", "hey", "yo", "sup", "hiya", "howdy",
    "test", "testing", "ping", "pong", "ok", "okay", "k",
    "thanks", "thank you", "ty", "thx", "cool", "nice", "great",
    "yes", "no", "yep", "nope", "y", "n",
})

# Phrases that mean "advance from where we are" rather than start fresh.
_CONTINUE_PHRASES = (
    "what's next", "whats next", "what next", "what now", "what else",
    "continue", "go on", "go ahead", "proceed", "keep going", "next step",
    "next", "and then", "then what", "more",
)

TRIVIAL = "trivial"
CONTINUE = "continue"
DIRECTIVE = "directive"


def classify_message(text: Any) -> str:
    """Classify a user message into ``trivial`` / ``continue`` / ``directive``.

    - ``trivial``   — empty, a greeting, an ack, or a smoke-test ping. The
      caller should orient on the case and offer choices, NOT auto-investigate.
    - ``continue``  — "what's next" / "keep going". Summarize established state
      and propose the next logical step (ties into the no-repeat fix).
    - ``directive`` — a real investigative instruction. Auto-investigate.

    Heuristic + cheap on purpose: this gates an expensive tool loop, so a false
    ``directive`` (auto-investigate) is the safe failure — we only suppress on
    high-confidence trivial/continue matches.
    """
    if not isinstance(text, str):
        return DIRECTIVE
    norm = " ".join(text.strip().lower().split())
    norm = norm.strip(" .!?,")
    if not norm:
        return TRIVIAL
    if norm in _TRIVIAL_TOKENS:
        return TRIVIAL
    # Single very-short token that isn't a real word → treat as trivial.
    if len(norm) <= 2 and " " not in norm:
        return TRIVIAL
    if norm in _CONTINUE_PHRASES:
        return CONTINUE
    # A short message that is *exactly* a continue phrase plus filler
    # ("ok what's next") still reads as continue.
    if len(norm) <= 24 and any(p in norm for p in _CONTINUE_PHRASES):
        return CONTINUE
    return DIRECTIVE


def gate_directive(label: str, scenario_title: str | None = None) -> str:
    """The system-prompt addendum for a low-signal message.

    Empty string for ``directive`` (no gate — let the agent investigate).
    """
    case = f" ({scenario_title})" if scenario_title else ""
    if label == TRIVIAL:
        return (
            "\n\n## Low-signal input\n"
            f"The analyst's message carries no investigative direction. Do NOT "
            f"launch an autonomous investigation or call enrichment tools. "
            f"Briefly orient them on the case in front of you{case} — what it "
            f"is and the few most useful next steps they could ask for — then "
            f"ask which they'd like, or invite a specific question. One short "
            f"paragraph."
        )
    if label == CONTINUE:
        return (
            "\n\n## Continue\n"
            "The analyst wants to advance, not restart. Do NOT re-run "
            "enrichment or pivots you already completed earlier in this "
            "conversation. Briefly restate what is already established, then "
            "take or propose the next logical step (correlation, containment, "
            "or response). If nothing remains, say so and recommend a "
            "disposition."
        )
    return ""


def resolve_intent(value: Any) -> str:
    """Map a raw intent value to a known task intent.

    Any value that isn't exactly a known intent is treated as legacy free
    text (the pre-discriminator contract carried the user message here) and
    defaults to ``build``."""
    return value if value in INTENTS else DEFAULT_INTENT


def load_intent_prompt(intent: str) -> str:
    """Load the intent's system prompt from the vendored markdown, cached.
    Falls back to an inline string if the file is missing/empty."""
    intent = resolve_intent(intent)
    if intent in _PROMPT_CACHE:
        return _PROMPT_CACHE[intent]
    fallback = _FALLBACK_TRIAGE_PROMPT if intent == "triage" else _FALLBACK_BUILD_PROMPT
    text = fallback
    try:
        import fsr_core
        fname = ("system_prompt_triage.md" if intent == "triage"
                 else "system_prompt_build.md")
        p = Path(fsr_core.__file__).resolve().parent / "agent" / fname
        if p.is_file():
            loaded = p.read_text(encoding="utf-8").strip()
            if loaded:
                text = loaded
    except Exception:  # noqa: BLE001
        pass
    _PROMPT_CACHE[intent] = text
    return text


def tools_for_intent(intent: str) -> list[dict[str, Any]]:
    """The tool slice advertised to the model for this intent. ``build``
    returns ``[]`` (the provider self-fills the full registry); ``triage``
    returns the full registry minus the build-only tools."""
    if resolve_intent(intent) != "triage":
        return []
    from fsr_core.llm.tools import anthropic_tools
    return [t for t in anthropic_tools() if t["name"] not in BUILD_ONLY_TOOLS]


__all__ = [
    "INTENTS", "DEFAULT_INTENT", "BUILD_ONLY_TOOLS",
    "resolve_intent", "load_intent_prompt", "tools_for_intent",
    "classify_message", "gate_directive",
    "TRIVIAL", "CONTINUE", "DIRECTIVE",
]
