"""Model-provider redaction: mask sensitive values before text leaves for the
LLM provider, restore them in everything the analyst and the tools see.

The one boundary is `agent_loop.run_loop` (every provider, the scope
declaration, the build loop and the wrap-ups all run through it). When a
`Redactor` is bound for the turn, the loop

  * masks the system prompt and the incoming messages before `open_turn`,
  * wraps the provider's `WireTurn` in `RedactingTurn`, which keeps the whole
    provider-side history masked (tool results, directives, replayed calls)
    and hands the loop UNMASKED text and tool-call arguments, so dispatch, the
    cards, the citations and the analyst's transcript only ever see real values.

Detection is structured first: a field is known to hold an address, a host, a
user, an email, a MAC or a secret from the identifier of the field it sits in
(or a registered FortiSOAR form type), never from the words of a sentence.
Free text is scanned only for language-independent VALUE formats: IPv4, IPv6,
email, MAC and key-shaped tokens. Hostnames and usernames are not guessed
from prose.

Placeholders are typed (`<IP_1>`, `<HOST_2>`) and stable: one value keeps one
placeholder for the life of the map, which the host persists per session
(`to_dict` / `from_dict`), so the model can still say "the same host as
before". With no redactor bound nothing here runs and the wire is unchanged.
"""
from __future__ import annotations

import contextvars
import dataclasses
import ipaddress
import json
import re
import threading
from collections.abc import AsyncIterator
from typing import Any

MODE_OFF = "off"
MODE_STANDARD = "standard"
MODE_STRICT = "strict"
MODES = (MODE_OFF, MODE_STANDARD, MODE_STRICT)

IP, HOST, USER, EMAIL, MAC, SECRET, TEXT = (
    "IP", "HOST", "USER", "EMAIL", "MAC", "SECRET", "TEXT")

#: Types compared without regard to case (the same host in two spellings is one
#: host). Secrets, addresses and free text are exact.
_CASE_INSENSITIVE = frozenset({HOST, USER, EMAIL, MAC})

#: What a placeholder stands in for when it cannot be resolved (a placeholder
#: the model invented). Never a placeholder-shaped string.
UNRESOLVED = "[redacted]"

#: Known values at least this long are replaced even inside a longer token.
_GLUED_MIN_LEN = 8
_PLACEHOLDER_RE = re.compile(r"<([A-Z]{2,8})_(\d{1,6})>")
#: A placeholder cut off by a streaming delta boundary.
_PARTIAL_PLACEHOLDER_RE = re.compile(r"<[A-Z]{0,8}(?:_\d{0,6})?$")

# ---------------------------------------------------------------- field typing

#: FortiSOAR `formType` (or an equivalent declared type) -> what the field holds.
FORM_TYPES: dict[str, str] = {
    "email": EMAIL, "password": SECRET, "encrypted": SECRET,
    "ipv4": IP, "ipv6": IP, "ipaddress": IP, "ip": IP,
    "domain": HOST, "hostname": HOST, "fqdn": HOST,
    "mac": MAC, "macaddress": MAC,
    "username": USER,
}
#: Form types whose values are free text; masked whole in strict mode.
FREE_TEXT_FORM_TYPES = frozenset({"textarea", "richtext", "html"})

# Identifier tokens (a field name split on case and separators). These are API
# identifiers, not prose: they say what a structured field holds.
_ID_TOKENS: dict[str, str] = {
    "ip": IP, "ips": IP, "ipv4": IP, "ipv6": IP, "ipaddr": IP, "ipaddress": IP,
    "ipaddresses": IP,
    "host": HOST, "hosts": HOST, "hostname": HOST, "hostnames": HOST,
    "fqdn": HOST, "computername": HOST, "machinename": HOST, "dnsname": HOST,
    "user": USER, "username": USER, "login": USER, "userid": USER,
    "samaccountname": USER, "upn": USER, "accountname": USER,
    "email": EMAIL, "emails": EMAIL, "emailaddress": EMAIL, "mail": EMAIL,
    "mac": MAC, "macaddress": MAC,
    "password": SECRET, "passwd": SECRET, "secret": SECRET, "token": SECRET,
    "apikey": SECRET, "credential": SECRET, "credentials": SECRET,
    "authorization": SECRET, "privatekey": SECRET, "accesskey": SECRET,
    "clientsecret": SECRET, "passphrase": SECRET,
}
# Longest-match order matters little: the first token that types the field wins,
# with secrets outranking the rest (a `password_user` is a password).
_TYPE_RANK = {SECRET: 0, EMAIL: 1, MAC: 2, IP: 3, HOST: 4, USER: 5}

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[^A-Za-z0-9]+")
_FIELD_TYPE_CACHE: dict[str, str | None] = {}


def field_type(name: str) -> str | None:
    """What a field called `name` holds, from its identifier alone."""
    if name in _FIELD_TYPE_CACHE:
        return _FIELD_TYPE_CACHE[name]
    tokens = [t.lower() for t in _CAMEL_RE.split(name) if t]
    whole = re.sub(r"[^a-z0-9]", "", name.lower())
    found: list[str] = []
    if whole in _ID_TOKENS:
        found.append(_ID_TOKENS[whole])
    # Adjacent tokens form compounds: api + key, private + key, ip + address.
    for i, tok in enumerate(tokens):
        if tok in _ID_TOKENS:
            found.append(_ID_TOKENS[tok])
        if i + 1 < len(tokens) and (tok + tokens[i + 1]) in _ID_TOKENS:
            found.append(_ID_TOKENS[tok + tokens[i + 1]])
    out = min(found, key=_TYPE_RANK.__getitem__) if found else None
    if len(_FIELD_TYPE_CACHE) < 5000:
        _FIELD_TYPE_CACHE[name] = out
    return out


# --------------------------------------------------------------- value formats

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w-])")
_MAC_RE = re.compile(
    r"(?<![0-9A-Fa-f:.-])(?:[0-9A-Fa-f]{2}([:-]))(?:[0-9A-Fa-f]{2}\1){4}"
    r"[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")
_IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w]|\.\d)")
_IPV6_RE = re.compile(
    r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
_JSON_PAIR_RE = re.compile(r'"([^"\\]{1,64})"\s*:\s*"((?:[^"\\]|\\.){1,512})"')
# Key-shaped tokens. Each is a published, fixed-format credential shape.
_SECRET_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
               re.DOTALL),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
)

#: Message / block keys whose values are structure, not content.
_STRUCTURAL_KEYS = frozenset({
    "role", "type", "id", "name", "tool_use_id", "tool_call_id", "signature",
    "cache_control", "finish_reason", "stop_reason", "is_error",
})


def _valid_ipv4(s: str) -> bool:
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


def _valid_ipv6(s: str) -> bool:
    if len(s) < 5:   # `::1`, `::`: loopback / unspecified, nothing to hide
        return False
    try:
        ipaddress.IPv6Address(s)
        return True
    except ValueError:
        return False


class Redactor:
    """The reversible map for one session, and the passes that use it."""

    def __init__(self, mode: str = MODE_STANDARD, *,
                 state: dict[str, Any] | None = None,
                 free_text_fields: frozenset[str] | set[str] | None = None) -> None:
        self.mode = mode if mode in (MODE_STANDARD, MODE_STRICT) else MODE_STANDARD
        self.free_text_fields = frozenset(free_text_fields or ())
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_placeholder: dict[str, str] = {}
        self._field_types: dict[str, str] = {}
        self._learned_re: dict[bool, re.Pattern[str] | None] = {True: None, False: None}
        self._dirty = False
        if state:
            self._load(state)

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {"v": 1, "items": [
                [ph.split("_", 1)[0][1:], val, ph]
                for ph, val in self._by_placeholder.items()]}

    def _load(self, state: dict[str, Any]) -> None:
        try:
            for typ, val, ph in state.get("items") or []:
                m = _PLACEHOLDER_RE.fullmatch(ph)
                if not m or not isinstance(val, str):
                    continue
                self._by_value[(typ, self._norm(typ, val))] = ph
                self._by_placeholder[ph] = val
                self._counters[m.group(1)] = max(
                    self._counters.get(m.group(1), 0), int(m.group(2)))
            self._dirty = False
        except (TypeError, ValueError):
            self._by_value.clear()
            self._by_placeholder.clear()
            self._counters.clear()

    @property
    def dirty(self) -> bool:
        return self._dirty

    # -- the map -----------------------------------------------------------

    @staticmethod
    def _norm(typ: str, value: str) -> str:
        return value.lower() if typ in _CASE_INSENSITIVE else value

    def placeholder(self, typ: str, value: str) -> str:
        with self._lock:
            key = (typ, self._norm(typ, value))
            ph = self._by_value.get(key)
            if ph is None:
                n = self._counters.get(typ, 0) + 1
                self._counters[typ] = n
                ph = f"<{typ}_{n}>"
                self._by_value[key] = ph
                self._by_placeholder[ph] = value
                self._learned_re = {True: None, False: None}
                self._dirty = True
            return ph

    def shareable(self) -> list[tuple[str, str]]:
        """Hosts, users and emails this map knows, as (type, value): the values
        that are the same entity in every session, so another map may adopt them."""
        with self._lock:
            return [(ph.split("_", 1)[0][1:], val)
                    for ph, val in self._by_placeholder.items()
                    if ph.split("_", 1)[0][1:] in (HOST, USER, EMAIL)]

    def adopt(self, pairs: list[tuple[str, str]]) -> None:
        """Learn (type, value) pairs from another map (see `shareable`)."""
        with self._lock:
            for typ, val in pairs:
                if typ in (HOST, USER, EMAIL) and isinstance(val, str):
                    self.placeholder(typ, val)

    def known_values(self) -> int:
        return len(self._by_placeholder)

    def register_field_types(self, types: dict[str, str]) -> None:
        """Declared form types for field names (FortiSOAR module metadata).
        `{"emailFrom": "email", "notes": "textarea"}`. Unknown types are ignored."""
        with self._lock:
            for fname, ftype in (types or {}).items():
                if isinstance(fname, str) and isinstance(ftype, str):
                    self._field_types[fname] = ftype.lower()

    def _typed(self, key: str) -> str | None:
        declared = self._field_types.get(key)
        if declared is not None:
            return FORM_TYPES.get(declared)
        return field_type(key)

    def _is_free_text(self, key: str) -> bool:
        if self.mode != MODE_STRICT:
            return False
        if key in self.free_text_fields:
            return True
        return self._field_types.get(key) in FREE_TEXT_FORM_TYPES and not self.free_text_fields

    # -- masking -----------------------------------------------------------

    def _mask_typed(self, typ: str, value: str) -> str:
        if (len(value) < 3 or value.startswith("/api/")
                or _PLACEHOLDER_RE.fullmatch(value)):
            return value
        return self.placeholder(typ, value)

    def _learned_pattern(self, ci: bool) -> re.Pattern[str] | None:
        pat = self._learned_re[ci]
        if pat is None:
            vals = sorted(
                (v for (t, _n), ph in self._by_value.items()
                 for v in [self._by_placeholder[ph]]
                 if (t in _CASE_INSENSITIVE) == ci and t not in (IP, MAC)),
                key=len, reverse=True)
            if not vals:
                return None
            uniq = list(dict.fromkeys(vals))
            # A long value is distinctive enough to be replaced even when glued
            # to other characters (a query such as `descriptionLIKE<host>^OR`);
            # a short one only as a whole token, so `admin` leaves `administrator`.
            longv = [v for v in uniq if len(v) >= _GLUED_MIN_LEN]
            shortv = [v for v in uniq if len(v) < _GLUED_MIN_LEN]
            parts = []
            if longv:
                parts.append("(?:" + "|".join(re.escape(v) for v in longv) + ")")
            if shortv:
                parts.append(r"(?<![A-Za-z0-9_])(?:" + "|".join(
                    re.escape(v) for v in shortv) + r")(?![A-Za-z0-9_])")
            pat = re.compile("|".join(parts), re.IGNORECASE if ci else 0)
            self._learned_re[ci] = pat
        return pat

    def _type_of_value(self, value: str, ci: bool) -> str | None:
        norm = value.lower() if ci else value
        for typ in ((USER, HOST, EMAIL) if ci else (SECRET, TEXT, IP)):
            if (typ, norm) in self._by_value:
                return typ
        return None

    def mask_text(self, text: str) -> str:
        """Mask every sensitive value in a string. Idempotent."""
        if not text or not isinstance(text, str):
            return text
        with self._lock:
            self._learn_from_text(text)
            out = text
            for rx in _SECRET_RES:
                out = rx.sub(lambda m: self.placeholder(SECRET, m.group(0)), out)
            out = _EMAIL_RE.sub(lambda m: self.placeholder(EMAIL, m.group(0)), out)
            out = _MAC_RE.sub(lambda m: self.placeholder(MAC, m.group(0)), out)
            for ci in (False, True):
                pat = self._learned_pattern(ci)
                if pat is not None:
                    out = pat.sub(self._learned_sub(ci), out)
            out = _IPV4_RE.sub(
                lambda m: self.placeholder(IP, m.group(0))
                if _valid_ipv4(m.group(0)) else m.group(0), out)
            out = _IPV6_RE.sub(
                lambda m: self.placeholder(IP, m.group(0))
                if _valid_ipv6(m.group(0)) else m.group(0), out)
            return out

    def _learned_sub(self, ci: bool):
        def sub(m: re.Match[str]) -> str:
            typ = self._type_of_value(m.group(0), ci)
            return self.placeholder(typ, m.group(0)) if typ else m.group(0)
        return sub

    def _learn(self, obj: Any, key: str | None = None, depth: int = 0) -> None:
        """Teach the map every typed value in a structure BEFORE anything is
        masked, so a known host or user is replaced wherever it sits in a longer
        string (a record name, a label), not only in the typed field itself, and
        whatever order the fields come in. Typing is by field identifier only."""
        if depth > 12:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._learn(v, k if isinstance(k, str) else None, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                self._learn(v, key, depth + 1)
        elif isinstance(obj, str) and obj:
            typ = self._typed(key) if key is not None else None
            if typ is not None:
                self._mask_typed(typ, obj)
            else:
                self._learn_from_text(obj, depth)

    def _learn_from_text(self, text: str, depth: int = 0) -> None:
        """A string that is itself a JSON document (a serialized tool result)
        is parsed, structurally, and its typed fields learned. Anything else is
        left alone: no value is guessed from prose."""
        head = text.lstrip()[:1]
        if head not in ("{", "[") or len(text) > 2_000_000:
            return
        try:
            doc = json.loads(text)
        except ValueError:
            # A truncated document (a stored result summary cut at a size cap):
            # read its complete `"key": "value"` pairs, still by key identifier.
            for m in _JSON_PAIR_RE.finditer(text):
                typ = self._typed(m.group(1))
                if typ is not None:
                    try:
                        val = json.loads('"' + m.group(2) + '"')
                    except ValueError:
                        continue
                    self._mask_typed(typ, val)
            return
        self._learn(doc, None, depth + 1)

    def mask_result(self, obj: Any, _key: str | None = None) -> Any:
        """Mask a structured value (a tool result, a record). Typed fields are
        masked by what the field IS, whatever the value looks like; the rest by
        value format. Typed values anywhere in `obj` are learned first."""
        with self._lock:
            self._learn(obj, _key)
            return self._mask_result(obj, _key)

    def _mask_result(self, obj: Any, _key: str | None = None) -> Any:
        if isinstance(obj, dict):
            return {k: self._mask_result(v, k if isinstance(k, str) else None)
                    for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._mask_result(v, _key) for v in obj]
        if isinstance(obj, str) and obj:
            if _key is not None:
                typ = self._typed(_key)
                if typ is not None:
                    return self._mask_typed(typ, obj)
                if self._is_free_text(_key) and 8 <= len(obj) <= 20000:
                    masked = self._mask_typed(TEXT, obj)
                    return masked
            return self.mask_text(obj)
        return obj

    def learn_record(self, fields: dict[str, Any] | None,
                     types: dict[str, str] | None = None) -> None:
        """Teach the map the typed values of a record in hand (the mounted
        record), so they are masked wherever they appear in text too."""
        if types:
            self.register_field_types(types)
        if isinstance(fields, dict):
            self.mask_result(fields)

    # -- message shapes ----------------------------------------------------

    def mask_block(self, block: Any) -> Any:
        """Mask one history entry, Anthropic block or OpenAI message, leaving
        its structure (roles, ids, tool names, thinking signatures) alone."""
        if isinstance(block, str):
            return self.mask_text(block)
        if isinstance(block, list):
            return [self.mask_block(b) for b in block]
        if not isinstance(block, dict):
            return block
        typ = block.get("type")
        if typ in ("thinking", "redacted_thinking", "image", "document"):
            return block
        out = dict(block)
        if typ == "text":
            out["text"] = self.mask_text(block.get("text", ""))
        elif typ == "tool_use":
            out["input"] = self.mask_result(block.get("input"))
        elif typ == "tool_result":
            out["content"] = self.mask_block(block.get("content"))
        else:
            for k, v in block.items():
                if k in _STRUCTURAL_KEYS:
                    continue
                if k == "tool_calls" and isinstance(v, list):
                    out[k] = [self._mask_call(c) for c in v]
                elif k in ("content", "text", "input", "arguments", "parts"):
                    out[k] = self.mask_block(v)
                elif isinstance(v, (str, list, dict)):
                    out[k] = self.mask_block(v)
        return out

    def _mask_call(self, call: Any) -> Any:
        if not isinstance(call, dict):
            return call
        out = dict(call)
        fn = call.get("function")
        if isinstance(fn, dict):
            fn = dict(fn)
            if isinstance(fn.get("arguments"), str):
                fn["arguments"] = self.mask_text(fn["arguments"])
            out["function"] = fn
        return out

    def mask_message(self, message: Any) -> Any:
        """A `provider.Message` with its content masked."""
        return dataclasses.replace(message, content=self.mask_block(message.content))

    # -- unmasking ---------------------------------------------------------

    def unmask_text(self, text: str, *, scrub: bool = True) -> str:
        """Restore real values. A placeholder this map never issued (the model
        invented one) becomes `UNRESOLVED` when `scrub`, so no placeholder-shaped
        token reaches an analyst or a tool."""
        if not text or not isinstance(text, str) or "<" not in text:
            return text

        def sub(m: re.Match[str]) -> str:
            val = self._by_placeholder.get(m.group(0))
            if val is not None:
                return val
            return UNRESOLVED if scrub else m.group(0)
        return _PLACEHOLDER_RE.sub(sub, text)

    def unmask_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.unmask_text(obj)
        if isinstance(obj, dict):
            return {k: self.unmask_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.unmask_obj(v) for v in obj]
        return obj


class StreamUnmasker:
    """Unmask a text stream delta by delta. A placeholder split across two
    deltas is held back until it completes, so no half placeholder escapes."""

    def __init__(self, redactor: Redactor) -> None:
        self._r = redactor
        self._held = ""

    def feed(self, delta: str) -> str:
        buf = self._held + (delta or "")
        self._held = ""
        cut = buf.rfind("<")
        if cut != -1 and _PARTIAL_PLACEHOLDER_RE.fullmatch(buf[cut:]):
            buf, self._held = buf[:cut], buf[cut:]
        return self._r.unmask_text(buf)

    def flush(self) -> str:
        tail, self._held = self._held, ""
        return self._r.unmask_text(tail)


# --------------------------------------------------------------- the binding

_REDACTOR: contextvars.ContextVar[Redactor | None] = contextvars.ContextVar(
    "fsr_playbooks_redactor", default=None)


def active() -> Redactor | None:
    """The redactor bound for this turn, or None (the default: no change)."""
    return _REDACTOR.get()


def bind(redactor: Redactor | None) -> contextvars.Token[Redactor | None]:
    return _REDACTOR.set(redactor)


def reset(token: contextvars.Token[Redactor | None]) -> None:
    _REDACTOR.reset(token)


# ------------------------------------------------------------ the wire wrapper


class RedactingTurn:
    """A provider `WireTurn` whose provider-side history is entirely masked.

    The loop talks to this object exactly as it does to a plain WireTurn: it
    gets unmasked text, unmasked tool-call arguments and unmasked reasoning,
    and everything it appends (tool results, directives, calls it makes itself)
    is masked on the way in. `Round.assistant`, the history entry the inner
    turn builds, stays masked and is appended untouched."""

    def __init__(self, inner: Any, redactor: Redactor) -> None:
        self._inner = inner
        self._r = redactor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    # reads
    @property
    def plain_tools(self) -> list[dict[str, Any]]:
        return self._inner.plain_tools

    @property
    def allowed_names(self) -> set[str]:
        return self._inner.allowed_names

    def _round(self, rnd: Any) -> Any:
        from .agent_loop import ToolCall
        r = self._r
        return dataclasses.replace(
            rnd,
            text=r.unmask_text(rnd.text),
            thinking=r.unmask_text(getattr(rnd, "thinking", "") or ""),
            tool_calls=[ToolCall(c.call_id, c.name, r.unmask_obj(c.args))
                        for c in rnd.tool_calls],
            dropped_calls=[dataclasses.replace(d, tail=r.unmask_text(d.tail))
                           for d in (rnd.dropped_calls or [])],
        )

    async def stream_round(self) -> AsyncIterator[tuple[str, Any]]:
        un = StreamUnmasker(self._r)
        async for kind, payload in self._inner.stream_round():
            if kind == "text":
                shown = un.feed(payload)
                if shown:
                    yield ("text", shown)
            elif kind == "final":
                tail = un.flush()
                if tail:
                    yield ("text", tail)
                yield ("final", self._round(payload))
            else:
                yield (kind, payload)

    async def wrapup_round(self, max_tokens: int) -> AsyncIterator[tuple[str, Any]]:
        un = StreamUnmasker(self._r)
        async for kind, payload in self._inner.wrapup_round(max_tokens):
            if kind == "text":
                shown = un.feed(payload)
                if shown:
                    yield ("text", shown)
            else:
                tail = un.flush()
                if tail:
                    yield ("text", tail)
                yield (kind, payload)

    async def forced_call(self, name: str) -> Any:
        from .agent_loop import ToolCall
        call = await self._inner.forced_call(name)
        if call is None:
            return None
        return ToolCall(call.call_id, call.name, self._r.unmask_obj(call.args))

    # writes
    def append_user(self, text: str) -> None:
        self._inner.append_user(self._r.mask_text(text))

    def append_tool_call(self, call: Any) -> None:
        from .agent_loop import ToolCall
        self._inner.append_tool_call(
            ToolCall(call.call_id, call.name, self._r.mask_result(call.args)))

    def _mask_outcome(self, o: Any) -> Any:
        return dataclasses.replace(o, content=self._r.mask_text(o.content))

    def append_tool_results(self, outcomes: list[Any], *, note: str | None = None) -> None:
        self._inner.append_tool_results(
            [self._mask_outcome(o) for o in outcomes],
            note=self._r.mask_text(note) if note else note)

    def result_wire(self, outcome: Any) -> Any:
        return self._inner.result_wire(self._mask_outcome(outcome))
