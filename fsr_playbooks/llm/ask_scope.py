"""Ask scope -- the effort of a turn matches the size of the ask.

A turn is one of five scopes:

* ``answer``      one fact, or a short explanation from the record in hand
* ``lookup``      a focused question about one entity that needs a tool or two
* ``investigate`` a hunt that ends on a verdict (the drawer-open default)
* ``act``         stage an action
* ``build``       author a playbook or configuration

The scope is decided once per turn, before the loop runs, and the MODEL
declares it for every typed ask (`declare_scope`: one no-tools call that
returns a scope and a short reason), in whatever language the ask is written.
There is no keyword or phrase logic anywhere: when the call fails the turn is
unscoped, which is the full investigation as ever. A turn with no typed ask
(the drawer opening, a quick-action chip, an unattended turn, a resume) is
unscoped by structure.

``answer`` and ``lookup`` change what the loop does: the hunt sweep, record
writes and verdict / action / offer cards are refused at dispatch (and so not
advertised), the tool rounds are capped (3 and 6), the end-of-turn guards that
demand a verdict or a coverage sweep stand down, and a turn that ends without
text gets one forced wrap-up round. A lookup may name strong evidence of
compromise and offer the full investigation, as a choice card the analyst
accepts; it never escalates on its own.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

ANSWER, LOOKUP, INVESTIGATE, ACT, BUILD = (
    "answer", "lookup", "investigate", "act", "build")
SCOPES = (ANSWER, LOOKUP, INVESTIGATE, ACT, BUILD)
#: The scopes that end on a short text answer instead of a verdict.
NARROW = (ANSWER, LOOKUP)
#: The scopes whose tool calls are capped and whose end-of-turn guards (the
#: forced verdict, the coverage sweep) stand down. An act turn stages the
#: action it was asked for and stops: a demo "Block ip 198.51.100.10" without
#: this cap hunted SIEM, EDR, tickets and four intel sources, was forced into a
#: verdict, and never staged the block.
CAPPED = NARROW + (ACT,)

#: Tool calls a narrow turn may make. A lookup or two answers a question;
#: past this the turn answers from what it has.
ANSWER_MAX_TOOL_CALLS = 3
LOOKUP_MAX_TOOL_CALLS = 6
#: find the action, read its schema, maybe read the record for the target,
#: stage the card, with one spare for a failed call.
ACT_MAX_TOOL_CALLS = 5


def max_tool_calls(scope: str | None) -> int | None:
    return {ANSWER: ANSWER_MAX_TOOL_CALLS,
            LOOKUP: LOOKUP_MAX_TOOL_CALLS,
            ACT: ACT_MAX_TOOL_CALLS}.get(scope or "")

#: The hunt surface and the prior-case sweep: what an investigation spends.
_HUNT = frozenset({"edr_host", "faz_search", "fmg_device", "siem_search",
                   "prior_cases"})
#: Cards that deliver a verdict, stage an action or offer a change.
_DELIVERABLE_CARDS = frozenset({"verdict", "action", "playbook_offer",
                                "enhancement_offer"})
#: What an act turn withholds: the hunt, the enrichment sweep, and the cards
#: that are not the action (a verdict would displace the action card).
_ACT_WITHHELD_TOOLS = _HUNT | frozenset({"mcp_utility__global_search"})
_ACT_WITHHELD_CARDS = _DELIVERABLE_CARDS - {"action"}

#: Said at the end of every tool round (and in every forced end-of-turn
#: directive), where a long prompt cannot dilute it. It names no language: the
#: model reads the analyst's own message and matches it.
REPLY_LANGUAGE_NOTE = (
    "Write your reply, and any note you write between tool calls, in the "
    "language of the analyst's own message, not the language of tool output "
    "or of these instructions. Quoted values, ids and code stay as they are.")


#: The offer a lookup makes on strong evidence: a choice card needs two
#: options (one alone is refused unless free text is allowed), so declining is
#: an option too. The first one starts the full investigation when picked.
ESCALATION_OPTIONS = (
    {"label": "Run the full investigation", "value": "investigate"},
    {"label": "Not now", "value": "stop"},
)


def escalation_directive() -> str:
    """The prompt text that tells a narrow turn when and how to offer the full
    investigation. Built from ESCALATION_OPTIONS so the words the model reads
    and the options the card carries cannot drift apart."""
    first, second = ESCALATION_OPTIONS
    return (
        "If what you read shows strong signs of compromise (several intel "
        "sources calling it malicious, or a live hit), say so in the answer and "
        "offer the full investigation with one `emit_card(card_type='choice')` "
        "that has exactly two options, "
        f"\"{first['label']}\" (value \"{first['value']}\") and "
        f"\"{second['label']}\" (value \"{second['value']}\"). Offer it only "
        "on strong evidence, and never start the investigation yourself.\n")


def language_note(analyst_text: str | None, language: str | None = None) -> str:
    """The reply-language reminder for the tail of a tool round.

    With a `language` (named by the model when it declared the scope) the note
    names it: asking the model to infer the language from a quote fails on an
    ask that shows none, and live "block ip 198.51.100.23" was answered in
    German, a timeline in Spanish and a block in Russian. Without one it quotes
    the start of the analyst's own message so the model matches it. Nothing
    here reads or classifies the words."""
    lang = clean_language(language)
    if lang:
        return (f"[reply language] Write every sentence you produce next, the "
                f"short notes between tool calls included, in {lang}, even when "
                "the tool output is in another language. Quoted values, ids "
                "and code stay as they are.")
    said = " ".join(str(analyst_text or "").split())[:80]
    if not said:
        return REPLY_LANGUAGE_NOTE
    return (f'[reply language] The analyst wrote: "{said}". Write every sentence '
            "you produce next, the short notes between tool calls included, in "
            "that same language, even when the tool output is in another. "
            "Quoted values, ids and code stay as they are.")


def clean_language(value: Any) -> str:
    """A declared language name fit to quote in a prompt, or "". It must look
    like a language name (letters, spaces, hyphens, under 30 chars): it is
    model output and is pasted into later rounds."""
    v = " ".join(str(value or "").split())
    if not v or len(v) > 30 or not re.fullmatch(r"[^\W\d_][^\W\d_ -]*(?:[ -][^\W\d_]+)*", v):
        return ""
    return v


def current_language() -> str:
    from . import session_state
    return clean_language(getattr(session_state.current(), "reply_language", None))


def bind_language(language: str | None) -> Any:
    from . import session_state
    return session_state.update(reply_language=clean_language(language) or None)


def reset_language(token: Any) -> None:
    from . import session_state
    session_state.reset_or(token, reply_language=None)


def budget_note(scope: str | None, used: int) -> str:
    """The shrinking tool budget of a narrow turn, stated after every round
    so the model plans its lookups instead of finding the cap by hitting it.
    Empty on a turn with no cap."""
    cap = max_tool_calls(scope)
    if cap is None:
        return ""
    left = max(cap - used, 0)
    if left == 0:
        return (f"[{scope} budget] all {cap} tool calls are spent. Answer now "
                "from what you have, and say what you could not find.")
    return (f"[{scope} budget] {used} of {cap} tool calls used, {left} left. "
            "A call that fails or finds nothing still counts. If a source came "
            "back empty, try a different kind of source rather than another "
            "guess at the same one, or answer with what is missing.")


def cap_refusal(scope: str | None) -> dict[str, Any]:
    """The dispatch refusal for a call past a narrow turn's cap. It says the
    budget is spent (the old text blamed the kind of tool)."""
    cap = max_tool_calls(scope)
    return {"ok": False, "code": "answer_scope", "error": (
        f"The {cap} tool calls this ask allows are spent, so this call did not "
        "run. Reply now with the answer in a few sentences from what you "
        "already have, naming the evidence, and say plainly what you could not "
        "find. If what you found shows an active compromise or a threat, say "
        "so and offer the full investigation; do not start one unasked.")}


_REFUSAL = (
    "This ask is a narrow question, so the turn answers it. Reply now with the "
    "answer in a few sentences, from what you have already read, naming the "
    "evidence. If what you found shows an active compromise or a threat, say "
    "that in the answer and offer to run the full investigation; do not start "
    "one unasked.")


_ACT_REFUSAL = (
    "The analyst asked for an action, so this turn stages it and stops. Do not "
    "investigate or enrich. Find the action with find(kind='action') for the "
    "target, then stage it with emit_card(card_type='action'). If the target "
    "is not named and is not on the record, ask the analyst for it.")


def answer_refusal(name: str, args: dict[str, Any] | None,
                   scope: str = ANSWER) -> dict[str, Any] | None:
    """The dispatch refusal for a narrow turn, or None when allowed. An answer
    turn withholds the whole hunt; a lookup keeps the log and endpoint
    lookups it was asked for and withholds only the prior-case sweep."""
    from .tools import READ_ONLY_WITHHELD_TOOLS
    args = args or {}
    if scope == ACT:
        if name == "emit_card":
            ct = str(args.get("card_type") or "").strip().lower()
            withheld = ct in _ACT_WITHHELD_CARDS
        else:
            withheld = name in _ACT_WITHHELD_TOOLS
        return ({"ok": False, "code": "answer_scope", "error": _ACT_REFUSAL}
                if withheld else None)
    hunt = _HUNT if scope != LOOKUP else frozenset({"prior_cases"})
    withheld = name in hunt or name in READ_ONLY_WITHHELD_TOOLS
    if name == "emit_card":
        ct = str(args.get("card_type") or "").strip().lower()
        withheld = ct in _DELIVERABLE_CARDS
    if not withheld:
        return None
    return {"ok": False, "code": "answer_scope", "error": _REFUSAL}


def current_scope() -> str | None:
    from . import session_state
    return getattr(session_state.current(), "ask_scope", None)


def bind_scope(scope: str | None) -> Any:
    """Install the turn's scope; returns a token for `reset_scope`."""
    from . import session_state
    return session_state.update(ask_scope=scope if scope in SCOPES else None)


def reset_scope(token: Any) -> None:
    from . import session_state
    session_state.reset_or(token, ask_scope=None)


_DECLARE_SYSTEM = (
    "You label the scope of one request made to a security operations "
    "assistant, so its effort matches the ask. The request may be written in "
    "any language. Reply with JSON only: "
    '{"scope": "<one of the five>", "reason": "<under 12 words>", '
    '"language": "<the language the request is written in, as its English '
    'name, e.g. English, French; English when the request is too short to '
    'show one, such as a bare command with an address>"}\n'
    "answer: the fact asked for is a field of the record in hand (its field "
    "names are listed), or a short explanation of what the record says. No "
    "tool is needed.\n"
    "  e.g. \"What severity is this?\" / \"Quelle est la gravite de cette "
    "alerte ?\"\n"
    "lookup: a focused question with ONE bounded answer about ONE entity or "
    "fact that is NOT in the record, which a tool or two settles: its "
    "reputation (even when worded as malicious, bad or suspicious), who owns "
    "it, whether it talked to X or to anything of some kind (a yes or no "
    "question, however broad the \"anything\" sounds), what a named intel "
    "source says.\n"
    "  e.g. \"What does VirusTotal say about this IP?\" / \"Ce serveur a-t-il "
    "contacte un domaine bloque cette semaine ?\"\n"
    "investigate: the subject is the whole alert or case (triage it, analyse "
    "it, give a verdict, find the cause), OR the analyst explicitly asks for "
    "everything: all the other activity, everything related, every place an "
    "entity shows up, which means searching several sources and following "
    "what turns up. A yes or no question is never an investigation, however "
    "broad its \"anything\" sounds; a request to list or find EVERYTHING "
    "about an entity is, because no one lookup can say it is complete.\n"
    "  e.g. \"Triage this alert\" / \"Find everything else this host did "
    "and who else was involved\" / \"Analyse cette alerte et trouve tout ce "
    "qui est lie a cet hote\"\n"
    "act: stage an action (block, isolate, update a record), including a "
    "bare command naming its target. Even on an alert page, a request to "
    "block or isolate is act, not investigate.\n"
    "  e.g. \"Block this IP\" / \"Isole cet hote\"\n"
    "A request that asks for triage, analysis or a verdict AND an action "
    "(\"triage it, then block the source\", \"if it is a false positive, "
    "close it\") is investigate: the verdict comes first and the action is "
    "staged at its end.\n"
    "  e.g. \"Triage this and stage a block of the source for my approval\" "
    "/ \"Analyse cette alerte et ferme-la si c'est un faux positif\"\n"
    "build: author or change a playbook or configuration.\n"
    "  e.g. \"Write a playbook that enriches new alerts\" / \"Cree un "
    "playbook qui enrichit les alertes\"\n"
    "The test is the shape of the answer, not how serious the entity sounds: "
    "one bounded fact is a lookup; a picture assembled from many places is an "
    "investigation. When unsure between lookup and investigate, say "
    "investigate.")


def _parse_declared(said: str) -> tuple[str | None, str, str]:
    """(scope, reason, language) from the declaration; language "" when the
    reply named none or an unusable one."""
    import json
    m = re.search(r"\{.*\}", said, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            sc = str(obj.get("scope") or "").strip().lower()
            if sc in SCOPES:
                return (sc, str(obj.get("reason") or "").strip()[:120],
                        clean_language(obj.get("language")))
        except Exception:  # noqa: BLE001
            pass
    bare = said.strip().strip(".\"' ").lower()   # a bare enum is our own protocol
    return (bare, "", "") if bare in SCOPES else (None, "", "")


async def declare_scope(provider: Any, text: str, *, intent: str = "triage",
                        record: str = "", timeout: float = 20.0
                        ) -> tuple[str | None, str]:
    """The model declares the scope of a typed ask: one cheap round, no tools.
    (None, "") on any failure or an unrecognised reply."""
    sc, reason, _lang = await declare_scope_and_language(
        provider, text, intent=intent, record=record, timeout=timeout)
    return sc, reason


async def declare_scope_and_language(provider: Any, text: str, *,
                                     intent: str = "triage", record: str = "",
                                     timeout: float = 20.0
                                     ) -> tuple[str | None, str, str]:
    """`declare_scope` plus the language the model says the ask is in, in the
    same round. (None, "", "") on any failure."""
    from .provider import Message, TextEvent

    async def _go() -> str:
        said = ""
        async for ev in provider.stream(
                system=_DECLARE_SYSTEM,
                messages=[Message(role="user", content=(
                    f"Page intent: {intent}\n"
                    + (f"Record in hand: {record}\n" if record else "")
                    + f"Request: {text}"))],
                tools=[], tags={"intent": "scope"}, max_tool_turns=1):
            if isinstance(ev, TextEvent):
                said += ev.text
        return said

    try:
        said = await asyncio.wait_for(_go(), timeout)
    except Exception:  # noqa: BLE001 - scope is an optimisation, never a failure
        return None, "", ""
    return _parse_declared(said)


async def resolve_scope(provider: Any, text: Any, *, intent: str = "triage",
                        quick_action: Any = None, record: str = ""
                        ) -> tuple[str | None, str, str]:
    """(scope, how, reason). No typed ask (empty text, a quick-action chip)
    is unscoped. Otherwise the model declares; if that call fails the turn is
    unscoped (never a guess from the words)."""
    sc, how, reason, _lang = await resolve_scope_and_language(
        provider, text, intent=intent, quick_action=quick_action, record=record)
    return sc, how, reason


async def resolve_scope_and_language(provider: Any, text: Any, *,
                                     intent: str = "triage",
                                     quick_action: Any = None, record: str = ""
                                     ) -> tuple[str | None, str, str, str]:
    """(scope, how, reason, language). The language is "" when nothing was
    declared (no typed ask, or the call failed); the round tail then falls
    back to quoting the analyst."""
    if quick_action or not isinstance(text, str) or not text.strip():
        return None, "default", "", ""
    sc, reason, lang = await declare_scope_and_language(
        provider, text.strip(), intent=intent, record=record)
    return (sc, "declared", reason, lang) if sc else (None, "default", "", "")


WRAPUP_DIRECTIVE = (
    "Answer the analyst's question now, in a few plain sentences, from what "
    "you have read. Name the evidence behind it. No tools. Quote exact "
    "values. " + REPLY_LANGUAGE_NOTE)

__all__ = ["ANSWER", "INVESTIGATE", "ACT", "BUILD", "SCOPES", "CAPPED",
           "ACT_MAX_TOOL_CALLS", "language_note", "clean_language",
           "current_language", "bind_language", "reset_language",
           "declare_scope_and_language", "resolve_scope_and_language",
           "ANSWER_MAX_TOOL_CALLS", "LOOKUP", "NARROW", "LOOKUP_MAX_TOOL_CALLS", "max_tool_calls", "answer_refusal",            "declare_scope", "resolve_scope", "current_scope", "bind_scope", "reset_scope",
           "WRAPUP_DIRECTIVE", "REPLY_LANGUAGE_NOTE", "language_note", "ESCALATION_OPTIONS", "escalation_directive", "budget_note", "cap_refusal"]
