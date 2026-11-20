"""Build ``mock_result`` values for a playbook from a successful past run.

``fsrpb mock-from-run`` reads a finished run's per-step results from a box
(through pyfsr), maps each executed step back to its YAML step by name, and
writes the captured output into that step's ``mock_result:``. Mock mode then
returns the captured shape, so downstream ``vars.steps.<X>.data...`` refs
resolve instead of rendering empty.

Rules this module enforces:

* Only steps that executed and succeeded are mocked. The default targets are
  ``connector`` and ``code_snippet`` steps; record-mutating and logic steps are
  skipped unless named with ``--steps``.
* ``mock_result`` is the step's stored result VERBATIM. For connector and
  code_snippet steps that stored result is the ``{data, status, message}``
  envelope, which is the shape downstream refs read (``.data.code_output``).
* Nothing here sets ``useMockOutput`` on a step. Turning mock mode on is a
  deliberate, per-step choice; the generator never flips a live step to mock.
* Redaction and list capping are opt-in / bounded, and every truncation is
  reported and written as a YAML comment above the ``mock_result`` key.

The pyfsr client is passed in by the caller; this module never builds one and
never imports pyfsr at module import time.
"""
from __future__ import annotations

import copy
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Step types mocked by default: the two that call something outside the engine.
DEFAULT_TYPES = frozenset({"connector", "code_snippet"})

_FAILED_RESULT_STATUSES = frozenset({"failed", "failure", "error"})

# Env keys the engine injects; they are not authored data and are not shape
# evidence for downstream refs.
_SYSTEM_ENV_KEYS = frozenset({
    "__schedule", "audit_info", "auth_info", "currentUser", "debug",
    "func_name", "globalMock", "last_run_at", "mockPlaybookId", "request",
    "resources", "result", "task_id", "useMockOutput",
})

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_KEY_RE = re.compile(
    r"(?i)(pass(word|wd)?|secret|token|api[_-]?key|apikey|private[_-]?key"
    r"|authorization|cookie|credential|session[_-]?id)"
)


class MockFromRunError(ValueError):
    """A user-facing refusal: bad input, unknown step name, unusable run."""


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #

@dataclass
class RunRecord:
    """A finished run's identity plus its raw per-step records."""
    pk: str
    name: str
    status: str
    task_id: str | None
    env: dict[str, Any]
    steps: list[dict[str, Any]]


@dataclass
class Decision:
    step: str
    type: str
    action: str  # "mock" | "skip"
    reason: str


@dataclass
class MockValue:
    value: Any
    truncated: list[str] = field(default_factory=list)  # "path (N -> M items)"
    replaced_existing: bool = False


@dataclass
class Finding:
    step: str
    location: str
    template: str
    empty: list[str]
    unrendered: str | None = None


@dataclass
class MockPlan:
    playbook: str
    mocks: dict[str, MockValue]
    decisions: list[Decision]
    redacted: int = 0
    sensitive_seen: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# YAML side
# --------------------------------------------------------------------------- #

def playbook_docs(text: str) -> list[dict[str, Any]]:
    """Every playbook mapping in a YAML document (``playbooks:`` list, or a
    single top-level playbook with ``steps:``)."""
    import yaml

    doc = yaml.safe_load(text) or {}
    if not isinstance(doc, dict):
        raise MockFromRunError("YAML root must be a mapping")
    if isinstance(doc.get("playbooks"), list):
        return [p for p in doc["playbooks"] if isinstance(p, dict)]
    if "steps" in doc:
        return [doc]
    raise MockFromRunError("no `playbooks:` list (or top-level `steps:`) found in YAML")


def pick_playbook(text: str, requested: str | None) -> str:
    """Name of the playbook to mock. Required when the file holds several."""
    names = [str(p.get("name")) for p in playbook_docs(text)]
    if requested:
        if requested not in names:
            raise MockFromRunError(
                f"--playbook {requested!r} not in YAML; playbooks: {', '.join(names)}")
        return requested
    if len(names) != 1:
        raise MockFromRunError(
            f"YAML holds {len(names)} playbooks; pass --playbook NAME (one of: {', '.join(names)})")
    return names[0]


def _yaml_steps(text: str, playbook: str) -> list[dict[str, Any]]:
    for pb in playbook_docs(text):
        if str(pb.get("name")) == playbook:
            return [s for s in (pb.get("steps") or []) if isinstance(s, dict)]
    raise MockFromRunError(f"playbook {playbook!r} not in YAML")


# --------------------------------------------------------------------------- #
# Run side
# --------------------------------------------------------------------------- #

def _norm(name: Any) -> str:
    return " ".join(str(name or "").replace("_", " ").split())


def run_record_from_raw(raw: Any, *, pk: str) -> RunRecord:
    """Build a RunRecord from a pyfsr ``get_execution(pk, step_detail=True)``
    result (a RunSummary, or a plain dict with the same keys)."""
    steps = raw.get("steps") or []
    return RunRecord(
        pk=str(pk),
        name=str(raw.get("name") or ""),
        status=str(raw.get("status") or ""),
        task_id=raw.get("task_id"),
        env=dict(raw.get("env") or {}),
        steps=[s for s in steps if isinstance(s, dict)],
    )


def _check_run_matches(run: RunRecord, playbook: str) -> None:
    if run.status != "finished":
        raise MockFromRunError(
            f"run {run.pk} has status {run.status!r}; mock-from-run needs a finished run")
    if _norm(run.name) != _norm(playbook):
        raise MockFromRunError(
            f"run {run.pk} is playbook {run.name!r}, not {playbook!r}")


def fetch_run(client: Any, ref: str, playbook: str) -> RunRecord:
    """Fetch the run named by a task_id or pk through pyfsr."""
    node = client.playbooks.run_tree(ref, depth=0)
    if not node.pk:
        raise MockFromRunError(f"run {ref!r} not found on this instance")
    raw = client.playbooks.get_execution(str(node.pk), step_detail=True)
    run = run_record_from_raw(raw, pk=str(node.pk))
    if run.task_id is None and node.task_id:
        run.task_id = node.task_id
    _check_run_matches(run, playbook)
    return run


def fetch_latest(client: Any, playbook: str, usable: Callable[[RunRecord], bool],
                 limit: int = 25) -> RunRecord:
    """Newest finished run of ``playbook`` that ``usable`` accepts."""
    for summary in client.playbooks.execution_history(playbook=playbook, limit=limit):
        if (summary.status or "") != "finished" or not summary.pk:
            continue
        raw = client.playbooks.get_execution(str(summary.pk), step_detail=True)
        run = run_record_from_raw(raw, pk=str(summary.pk))
        if _norm(run.name) != _norm(playbook):
            continue
        if usable(run):
            return run
    raise MockFromRunError(
        f"no finished run of {playbook!r} in the newest {limit} with a successful "
        "connector or code_snippet step")


def success_reason(rec: dict[str, Any]) -> str | None:
    """None when the step succeeded, else why it did not."""
    status = str(rec.get("status") or "").lower()
    if status != "finished":
        return f"step status is {status or 'missing'}"
    result = rec.get("result")
    if result is None:
        return "no result recorded"
    if isinstance(result, dict):
        inner = result.get("status")
        if isinstance(inner, str) and inner.lower() in _FAILED_RESULT_STATUSES:
            return f"result status is {inner}"
    return None


def _latest_record_by_name(run: RunRecord) -> dict[str, list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for rec in run.steps:
        by_name.setdefault(_norm(rec.get("name")), []).append(rec)
    return by_name


def usable_for(yaml_steps: list[dict[str, Any]]) -> Callable[[RunRecord], bool]:
    """Predicate: the run has at least one default-target step that succeeded."""
    targets = {_norm(s.get("name")) for s in yaml_steps
               if s.get("type") in DEFAULT_TYPES}

    def _usable(run: RunRecord) -> bool:
        for rec in run.steps:
            if _norm(rec.get("name")) in targets and success_reason(rec) is None:
                return True
        return False

    return _usable


# --------------------------------------------------------------------------- #
# Shaping: caps, redaction
# --------------------------------------------------------------------------- #

def cap_lists(obj: Any, max_items: int, path: str = "") -> tuple[Any, list[str]]:
    """Truncate every list longer than ``max_items``. Returns the capped copy
    and one note per truncated list, naming the path."""
    notes: list[str] = []

    def walk(node: Any, where: str) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, f"{where}.{k}" if where else str(k)) for k, v in node.items()}
        if isinstance(node, list):
            kept = node
            if len(node) > max_items:
                kept = node[:max_items]
                notes.append(f"{where or '<root>'} ({len(node)} -> {max_items} items)")
            return [walk(v, f"{where}[{i}]") for i, v in enumerate(kept)]
        return node

    return walk(obj, path), notes


class Redactor:
    """Replace obvious secrets, e-mail addresses and IPv4 addresses.

    Addresses map to reserved documentation ranges (RFC 5737 for IPs,
    ``example.com`` for mail). Each distinct value maps to one placeholder for
    the whole mock, so equality checks and joins in the playbook still line up.
    """

    def __init__(self) -> None:
        self._emails: dict[str, str] = {}
        self._ips: dict[str, str] = {}
        self.count = 0

    def _email(self, value: str) -> str:
        if value not in self._emails:
            self._emails[value] = f"user{len(self._emails) + 1}@example.com"
        return self._emails[value]

    def _ip(self, value: str) -> str:
        if value not in self._ips:
            n = len(self._ips)
            self._ips[value] = f"198.51.{n // 254}.{n % 254 + 1}"
        return self._ips[value]

    def text(self, value: str) -> str:
        def repl_email(m: re.Match[str]) -> str:
            self.count += 1
            return self._email(m.group(0))

        def repl_ip(m: re.Match[str]) -> str:
            self.count += 1
            return self._ip(m.group(0))

        def repl_bearer(m: re.Match[str]) -> str:
            self.count += 1
            return f"{m.group(1)} <redacted>"

        out = _BEARER_RE.sub(repl_bearer, value)
        out = _EMAIL_RE.sub(repl_email, out)
        return _IPV4_RE.sub(repl_ip, out)

    def apply(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[Any, Any] = {}
            for k, v in obj.items():
                if isinstance(v, (str, int, float)) and not isinstance(v, bool) \
                        and _SECRET_KEY_RE.search(str(k)) and v not in ("", 0):
                    self.count += 1
                    out[k] = "<redacted>"
                else:
                    out[k] = self.apply(v)
            return out
        if isinstance(obj, list):
            return [self.apply(v) for v in obj]
        if isinstance(obj, str):
            return self.text(obj)
        return obj


def scan_sensitive(obj: Any) -> dict[str, int]:
    """Count e-mail and IPv4 hits without changing anything (for the hint
    printed when --redact is off)."""
    counts = {"email": 0, "ipv4": 0}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            counts["email"] += len(_EMAIL_RE.findall(node))
            counts["ipv4"] += len(_IPV4_RE.findall(node))

    walk(obj)
    return {k: v for k, v in counts.items() if v}


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #

def build_plan(text: str, playbook: str, run: RunRecord, *,
               only: set[str] | None = None, max_items: int = 20,
               redact: bool = False) -> MockPlan:
    """Decide which steps to mock and build their values.

    ``only`` (from ``--steps``) replaces the default type filter: every named
    step is eligible whatever its type, and an unknown name is an error.
    """
    yaml_steps = _yaml_steps(text, playbook)
    by_yaml_name = {_norm(s.get("name")): s for s in yaml_steps}
    if only is not None:
        unknown = sorted(n for n in only if _norm(n) not in by_yaml_name)
        if unknown:
            raise MockFromRunError(
                f"--steps names not in the YAML playbook: {', '.join(unknown)}")
    run_by_name = _latest_record_by_name(run)
    redactor = Redactor() if redact else None
    sensitive: dict[str, int] = {}
    plan = MockPlan(playbook=playbook, mocks={}, decisions=[])

    for s in yaml_steps:
        name = str(s.get("name") or "")
        stype = str(s.get("type") or "")
        key = _norm(name)
        if only is not None and key not in {_norm(n) for n in only}:
            continue
        if only is None and stype not in DEFAULT_TYPES:
            if key in run_by_name:
                plan.decisions.append(Decision(name, stype, "skip",
                                               "not a default mock target (name it with --steps)"))
            continue
        recs = run_by_name.get(key)
        if not recs:
            plan.decisions.append(Decision(name, stype, "skip", "did not execute in the run"))
            continue
        why = success_reason(recs[-1])
        if why:
            plan.decisions.append(Decision(name, stype, "skip", why))
            continue
        value = copy.deepcopy(recs[-1]["result"])
        if redactor is not None:
            value = redactor.apply(value)
        else:
            for k, v in scan_sensitive(value).items():
                sensitive[k] = sensitive.get(k, 0) + v
        value, truncated = cap_lists(value, max_items)
        note = f"ran {len(recs)} times; mocked the last execution" if len(recs) > 1 else ""
        plan.mocks[name] = MockValue(
            value=value,
            truncated=truncated,
            replaced_existing=any(
                s2.get("mock_result") is not None
                for s2 in yaml_steps if _norm(s2.get("name")) == key),
        )
        plan.decisions.append(Decision(name, stype, "mock", note or "succeeded in run"))

    if redactor is not None:
        plan.redacted = redactor.count
    plan.sensitive_seen = sensitive
    return plan


# --------------------------------------------------------------------------- #
# Writing the YAML (ruamel round-trip keeps comments and ordering)
# --------------------------------------------------------------------------- #

def write_mocks(text: str, playbook: str, mocks: dict[str, MockValue]) -> str:
    from ruamel.yaml import YAML

    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True
    yaml_rt.width = 4096
    yaml_rt.indent(mapping=2, sequence=4, offset=2)
    doc = yaml_rt.load(text)
    pbs = doc["playbooks"] if isinstance(doc.get("playbooks"), list) else [doc]
    pb = next(p for p in pbs if str(p.get("name")) == playbook)
    for step in pb.get("steps") or []:
        name = str(step.get("name") or "")
        if name not in mocks:
            continue
        mv = mocks[name]
        step["mock_result"] = mv.value
        if mv.truncated:
            step.yaml_set_comment_before_after_key(
                "mock_result",
                before="mock_result from a successful run (fsrpb mock-from-run); "
                       "truncated: " + "; ".join(mv.truncated),
                indent=8,
            )
    buf = io.StringIO()
    yaml_rt.dump(doc, buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Offline render check: do the downstream refs resolve against the mocks?
# --------------------------------------------------------------------------- #

def _walk_templates(node: Any, where: str, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("mock_result", "comment", "description"):
                continue
            _walk_templates(v, f"{where}.{k}" if where else str(k), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_templates(v, f"{where}[{i}]", out)
    elif isinstance(node, str) and ("{{" in node or "{%" in node):
        out.append((where, node))


def _known(obj: Any) -> Any:
    from fsr_playbooks.compiler.local_render import Known

    if isinstance(obj, dict):
        return Known({k: _known(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_known(v) for v in obj]
    return obj


def render_check(text: str, playbook: str, run: RunRecord,
                 mocks: dict[str, MockValue]) -> tuple[int, int, list[Finding]]:
    """Render every template in the playbook against the mocked outputs.

    Context: each executed step's output, with mocked steps replaced by their
    mock value (the value mock mode will return), plus the run's recorded env
    variables. A step that did not run in the source run is absent, so a ref to
    it renders empty and is reported. Returns (templates checked, opaque
    reads, findings).
    """
    from fsr_playbooks.compiler.local_render import Known, Opaque, render
    from fsr_playbooks.compiler.parser import parse_yaml

    coll, errs = parse_yaml(text)
    if coll is None:
        raise MockFromRunError("mocked YAML does not parse: " +
                               "; ".join(str(e.message) for e in errs[:3]))
    pb = next((p for p in coll.playbooks if p.name == playbook), None)
    if pb is None:
        raise MockFromRunError(f"playbook {playbook!r} missing after mocking")

    mocked = {_norm(k): v.value for k, v in mocks.items()}
    steps_ctx: dict[str, Any] = {}
    for rec in run.steps:
        name = _norm(rec.get("name"))
        if not name or success_reason(rec) is not None:
            continue
        value = mocked[name] if name in mocked else rec.get("result")
        steps_ctx[name.replace(" ", "_")] = _known(value)
    vars_ctx: dict[str, Any] = {
        "steps": Known(steps_ctx),
        "input": Opaque("trigger input"),
        "item": Opaque("loop item"),
    }
    for k, v in run.env.items():
        if k in _SYSTEM_ENV_KEYS or k in vars_ctx:
            continue
        vars_ctx[k] = v
    ctx = {"vars": vars_ctx}

    checked = 0
    opaque = 0
    findings: list[Finding] = []
    for step in pb.steps:
        templates: list[tuple[str, str]] = []
        _walk_templates(step.arguments or {}, "", templates)
        for where, tpl in templates:
            checked += 1
            res = render(tpl, ctx)
            opaque += 1 if res["opaque"] else 0
            if res["unrendered"]:
                findings.append(Finding(step.name or step.id, where, tpl[:160], [],
                                        unrendered=res["unrendered"]))
            elif res["empty"]:
                findings.append(Finding(step.name or step.id, where, tpl[:160], res["empty"]))
    return checked, opaque, findings
