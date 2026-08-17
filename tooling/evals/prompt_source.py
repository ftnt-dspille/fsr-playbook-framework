"""Resolve the triage system prompt the eval is supposed to be measuring.

Why this module exists: `fsr_playbooks.llm.intents.load_intent_prompt` looks
for `fsr_playbooks/agent/system_prompt_triage.md`, which does not exist in this
repo -- the triage prompt lives in the CONNECTOR, assembled at runtime from
`prompt_fragments/triage/`. So every investigation calibrate run silently fed
the model `_FALLBACK_TRIAGE_PROMPT`: a 583-character stub with no budget
section, no hunting instincts, no anti-patterns.

That made the investigation eval structurally unable to measure a triage-prompt
change. An A/B over any prompt edit returned pure run-to-run variance, because
both arms were served the same stub -- the "gate that selects zero files"
shape, which looks exactly like a gate that is working.

The rule here: a prompt this harness cannot resolve is a HARD ERROR, never a
quiet fallback. A run that cannot say which prompt it measured is not a
measurement.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

# The stub is ~583 chars. The real assembled triage prompt is tens of KB. Any
# "prompt" below this is the fallback (or a truncated read) wearing the real
# one's name -- refuse it rather than score against it.
MIN_CREDIBLE_PROMPT_CHARS = 2000


class PromptSource(NamedTuple):
    """The prompt plus provenance, so a run can state what it measured."""

    text: str
    origin: str          # human-readable: where this came from
    fingerprint: str     # short content hash, for run-to-run comparison

    @property
    def summary(self) -> str:
        return f"{self.origin} ({len(self.text)} chars, sha {self.fingerprint})"


def _fingerprint(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class PromptUnresolvable(RuntimeError):
    """No real triage prompt could be found. Never fall back -- say so."""


def _connector_on_path() -> None:
    """Mirror harness._register_connector_tools' path handling.

    `FSR_CONNECTOR_REPO` may name the repo root or the package dir; accept
    either, and let an already-importable connector win.
    """
    repo = os.environ.get("FSR_CONNECTOR_REPO", "").strip()
    if not repo:
        return
    for cand in (Path(repo) / "connector-fsr-soc-assistant", Path(repo)):
        if (cand / "fsr_soc_triage").is_dir() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
            return


def resolve_triage_prompt(*, mode: str | None = None,
                          allow_stub: bool = False) -> PromptSource:
    """The triage prompt as the RUNTIME assembles it, or a loud failure.

    Resolution order, most-faithful first:

    1. The connector's `assemble_triage_prompt()` -- what actually reaches the
       model on a box. Fragments are the source of truth; the shipped monolith
       `system_prompt_triage.md` is a second copy that can drift from them.
    2. A framework-vendored `fsr_playbooks/agent/system_prompt_triage.md`, if a
       future checkout ever carries one.
    3. Raise. `allow_stub=True` opts into the 583-char fallback, for callers
       that genuinely want to measure the framework in isolation -- but it
       returns an origin that SAYS so, so no summary can imply otherwise.
    """
    _connector_on_path()

    try:
        from fsr_soc_triage.prompt_assembly import (  # type: ignore[import-not-found]
            assemble_triage_prompt,
        )
    except ImportError:
        pass
    else:
        text = assemble_triage_prompt(mode=mode).strip()
        if len(text) >= MIN_CREDIBLE_PROMPT_CHARS:
            origin = "connector fragments (assemble_triage_prompt"
            origin += f", mode={mode})" if mode else ")"
            return PromptSource(text, origin, _fingerprint(text))
        raise PromptUnresolvable(
            f"assemble_triage_prompt() returned {len(text)} chars -- below the "
            f"{MIN_CREDIBLE_PROMPT_CHARS}-char credibility floor. The fragment "
            "dir is probably empty or partially checked out."
        )

    try:
        import fsr_playbooks
        p = (Path(fsr_playbooks.__file__).resolve().parent / "agent"
             / "system_prompt_triage.md")
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if len(text) >= MIN_CREDIBLE_PROMPT_CHARS:
                return PromptSource(text, f"framework file {p.name}",
                                    _fingerprint(text))
    except Exception:  # noqa: BLE001
        pass

    if allow_stub:
        from fsr_playbooks.llm.intents import load_intent_prompt
        text = load_intent_prompt("triage")
        return PromptSource(text, "FALLBACK STUB (not the shipped prompt)",
                            _fingerprint(text))

    raise PromptUnresolvable(
        "No real triage prompt found. The shipped prompt lives in the "
        "connector; point FSR_CONNECTOR_REPO at the checkout, e.g.\n"
        "  FSR_CONNECTOR_REPO=/path/to/fsr-playbook-builder\n"
        "Without it this run would have scored a 583-char fallback stub and "
        "reported the result as if it measured the real prompt."
    )
