"""Task-intent prompt + tool-slice resolution (single source of truth).

The agentic surface runs in one of two intents:

  - ``triage``  -- incident-response: investigate the record in front of the
    analyst, pivot across modules, enrich indicators read-only, and stage any
    mutating/containment action via ``emit_action_card`` for approval. The
    YAML-authoring + playbook-mutation tools are dropped.
  - ``build``   -- playbook authoring: the full tool registry.

Both the FortiSOAR connector (``operations.py``) and the local hunt/demo
runner resolve their system prompt + tool list through here, so the prompt
text, the dropped-tool set, and the fallbacks never drift between them. The
prompts themselves live in ``fsr_playbooks/agent/system_prompt_{triage,build}.md``
and are vendored wholesale into the connector by ``scripts/build.sh``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

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
    # Value-level fix card for the OPEN playbook -- meaningless in triage (there
    # is no playbook open to patch), so keep it out of the triage slice.
    "emit_patch_proposal",
    # Enhance mode's write path -- same reasoning: triage has no open playbook
    # to update.
    "emit_enhancement_offer",
})

# Tools that only make sense when an OPEN playbook exists to edit -- the enhance
# verify+write pair. A from-scratch CREATE (build intent, no playbook mounted)
# has nothing to enhance, yet the build slice = full registry minus TRIAGE_ONLY,
# so it still advertises these. A drifting model can then terminate a create via
# emit_enhancement_offer (stop=awaiting_enhancement_offer) instead of delivering
# a NEW playbook via emit_playbook_offer. The connector's _intent_drop_set gates
# this set out of a no-open-playbook build; EnhanceDeliveryGuard is keyed on the
# SAME names (asserted in a test) so the guard and the advertised slice can never
# drift. This is a SUBSET of BUILD_ONLY_TOOLS -- dropping it never touches triage.
ENHANCE_ONLY_TOOLS = frozenset({
    "verify_enhancement", "emit_enhancement_offer",
})

# Triage-only tools dropped from the build slice (ROADMAP §4, three-pillar
# plan Track C5): the live alert/incident investigation + containment-staging
# surface. Build mode authors playbooks -- it discovers ops with
# find_connector/find_operation/get_op_schema and offers them via
# emit_playbook_offer; it must NOT stage live containment action-cards
# (emit_action_card) or run connector ops directly (run_op). find_containment_actions /
# find_enrichment_actions are connector-AWARENESS (authoring) and stay in build.
#
# This set is MUTABLE on purpose: the connector's
# fsr_soc_triage.registry.register_triage_tools() re-injects the alert/incident
# hunt tools (get_record, search_module_records, siem_*, faz_*, fmg_*) into the
# global REGISTRY at import, and extends THIS set with those same names so the
# build slice excludes them too -- mirroring how it already mutates SAFE_TOOLS /
# TOOL_TIERS / REGISTRY (Option-A posture). tools_for_intent reads this global
# at call time, so the connector's additions are visible without a code path
# fork. Framework-standalone (no connector) keeps just the two base names.
TRIAGE_ONLY_TOOLS: set[str] = {
    "emit_action_card",
    "run_op",
}

# ---- Lever 2: run-mode slice + run/author classification ------------------
#
# Prompt/description tuning could not stop gpt-4.1-mini from mis-routing a
# "run the deployed playbook X" request into the authoring tools (verify /
# compile / emit). The deterministic fix removes the temptation: when a turn is
# classified as "run an existing playbook", we replace the advertised slice with
# just run_playbook (the allowlist below), so it is the model's only available
# action. This complements Lever 1 (the dispatch forcing-redirect):
# Lever 1 catches the blank-yaml+name mis-call; Lever 2 also covers the case
# where the model fabricates full YAML with no name to key on.
#
# Run mode is an ALLOWLIST, not a blacklist. Live proof: merely dropping the
# authoring tools still let gpt-4.1-mini "investigate" a run request via the
# left-over read/discovery tools (search_playbooks, list_playbook_runs,
# find_connector, why_did_playbook_fail, …) and end the turn WITHOUT ever
# calling run_playbook. With run_playbook as the ONLY tool on the table, the
# model has one way to act, and it takes it. If the name is approximate,
# run_playbook resolves (or reports not-found) -- no discovery tool needed.
RUN_MODE_KEEP_TOOLS = frozenset({"run_playbook"})

RUN = "run"
AUTHOR = "author"
OTHER = "other"

# Classifier system prompt. It classifies MEANING, not surface words, so it is
# language-agnostic -- no keyword/regex list to enumerate or maintain. We parse
# only our OWN one-word control output (run|author|other), never the analyst's
# free text, so this introduces no language lock-in.
_RUN_AUTHOR_SYSTEM = (
    "You route a SOC analyst's message about FortiSOAR playbooks. Decide the "
    "analyst's INTENT and reply with EXACTLY one lowercase word:\n"
    "  run    - they want to RUN / execute / trigger / launch / start a "
    "playbook that ALREADY EXISTS (they name it, or refer to a deployed / "
    "existing / saved playbook).\n"
    "  author - they want to CREATE, build, write, compose, modify, edit, fix, "
    "or verify playbook YAML.\n"
    "  other  - anything else: questions, explanations, greetings, alert "
    "investigation, or unclear.\n"
    "Judge the meaning regardless of the language the message is written in. "
    "Answer with one word only: run, author, or other."
)


def classify_run_or_author(message: Any, complete: "Callable[[str, str], str]") -> str:
    """Classify a message as ``run`` / ``author`` / ``other`` via an injected LLM.

    ``complete(system, user) -> str`` is supplied by the caller (the connector
    passes its configured provider); this keeps the framework provider-agnostic
    and the function unit-testable with a fake. Fails OPEN to ``other`` (normal
    build behavior) on any empty input or provider error -- a classifier hiccup
    must never block authoring or run.
    """
    if not isinstance(message, str) or not message.strip():
        return OTHER
    try:
        raw = complete(_RUN_AUTHOR_SYSTEM, message)
    except Exception:  # noqa: BLE001 -- fail open, never break the turn
        return OTHER
    tok = (raw or "").strip().lower()
    for w in (RUN, AUTHOR, OTHER):
        if tok.startswith(w):
            return w
    # Model padded the answer ("intent: run") -- look for the token anywhere,
    # preferring the more specific labels over the catch-all. Match on WORD
    # BOUNDARIES: a bare substring scan reads "run" out of "re-runnable" (and
    # "author" out of "authored"), so a model that ignored the one-word contract
    # and replied with prose got classified RUN -- which then narrowed the turn
    # to the run-mode allowlist and stripped the authoring surface it needed.
    if re.search(rf"\b{RUN}\b", tok):
        return RUN
    if re.search(rf"\b{AUTHOR}\b", tok):
        return AUTHOR
    return OTHER


def tools_for_run_mode(base_intent: str = "build") -> list[dict[str, Any]]:
    """The tool slice for a classified RUN request: only the run-mode allowlist
    (run_playbook), so it is the model's single available action. Intersected
    with the base slice so a tool absent there stays absent.

    Fail-open: if the intersection is EMPTY (the allowlist tool isn't in the base
    slice at all) we return the base slice untouched. Advertising zero tools does
    not make the model run a playbook -- it makes the turn incapable of doing
    anything, which is strictly worse than the un-narrowed surface."""
    base = tools_for_intent(base_intent)
    narrowed = [t for t in base if t["name"] in RUN_MODE_KEEP_TOOLS]
    return narrowed or base

# Inline fallbacks used only when the vendored markdown can't be read (keeps
# the agent functional even if packaging drops the .md files).
_FALLBACK_BUILD_PROMPT = (
    "You are a FortiSOAR playbook author. Help the user compose, validate, "
    "and refine YAML playbooks using the tools available. Be concise. Quote "
    "tool errors verbatim and explain the fix. The conversation may open with "
    "a prior triage transcript plus a directive to design a re-runnable "
    "playbook around the operations used during triage -- reproduce those "
    "operations as parameterized steps."
)
_FALLBACK_TRIAGE_PROMPT = (
    "You are a FortiSOAR incident-response assistant triaging the record in "
    "front of you. Use find_connector -> find_operation -> get_op_schema to "
    "locate capabilities. Call run_op directly only for read-only "
    "intelligence; for ANY mutating/containment action (block, isolate, "
    "quarantine, disable, add-to-group, etc.) build the call and emit it via "
    "emit_action_card for analyst approval -- never run it silently. Do not "
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

# Greetings / acks / smoke-test pings -- no investigative direction.
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

    - ``trivial``   -- empty, a greeting, an ack, or a smoke-test ping. The
      caller should orient on the case and offer choices, NOT auto-investigate.
    - ``continue``  -- "what's next" / "keep going". Summarize established state
      and propose the next logical step (ties into the no-repeat fix).
    - ``directive`` -- a real investigative instruction. Auto-investigate.

    Heuristic + cheap on purpose: this gates an expensive tool loop, so a false
    ``directive`` (auto-investigate) is the safe failure -- we only suppress on
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

    Empty string for ``directive`` (no gate -- let the agent investigate).
    """
    case = f" ({scenario_title})" if scenario_title else ""
    if label == TRIVIAL:
        return (
            "\n\n## Low-signal input\n"
            f"The analyst's message carries no investigative direction. Do NOT "
            f"launch an autonomous investigation or call enrichment tools. "
            f"Briefly orient them on the case in front of you{case} -- what it "
            f"is and the few most useful next steps they could ask for -- then "
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
        import fsr_playbooks
        fname = ("system_prompt_triage.md" if intent == "triage"
                 else "system_prompt_build.md")
        p = Path(fsr_playbooks.__file__).resolve().parent / "agent" / fname
        if p.is_file():
            loaded = p.read_text(encoding="utf-8").strip()
            if loaded:
                text = loaded
    except Exception:  # noqa: BLE001
        pass
    _PROMPT_CACHE[intent] = text
    return text


def tools_for_intent(intent: str) -> list[dict[str, Any]]:
    """The tool slice advertised to the model for this intent.

    - ``triage`` -- the full registry minus the build-only (YAML-authoring +
      playbook-mutation) tools.
    - ``build``  -- the full registry minus the triage-only (containment-staging
      ``emit_action_card``, direct ``run_op``, alert/incident investigation)
      tools, so authoring mode never stages containment action-cards.
    """
    from fsr_playbooks.llm.tools import anthropic_tools
    if resolve_intent(intent) == "triage":
        return [t for t in anthropic_tools() if t["name"] not in BUILD_ONLY_TOOLS]
    return [t for t in anthropic_tools() if t["name"] not in TRIAGE_ONLY_TOOLS]


__all__ = [
    "INTENTS", "DEFAULT_INTENT", "BUILD_ONLY_TOOLS", "TRIAGE_ONLY_TOOLS",
    "ENHANCE_ONLY_TOOLS",
    "resolve_intent", "load_intent_prompt", "tools_for_intent",
    "classify_message", "gate_directive",
    "TRIVIAL", "CONTINUE", "DIRECTIVE",
    "RUN_MODE_KEEP_TOOLS", "RUN", "AUTHOR", "OTHER",
    "classify_run_or_author", "tools_for_run_mode",
]
