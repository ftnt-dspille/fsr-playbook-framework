"""Registry binding a verification verdict to the exact bytes it blessed.

Why this exists — a live failure, reproduced end to end on a real appliance.
The analyst asked the agent to add a `manual_input` step to the playbook they
had open. The agent called `verify_enhancement`, got back
`ready_to_push: True`, and then **re-typed the playbook into chat three times**,
each rendering different from the verified one and from each other:

    verified after_yaml   ip: '{{ vars.steps.Prompt_Block_IP.input.ip_to_block }}'
                          ip_type: 'IPv4'
    chat fence #2         ip: '{{ vars.steps.Prompt Block IP.input.ip_to_block }}'
    chat fence #3         ip: "{{ vars.steps['Prompt Block IP'].input.ip_to_block }}"

The enhance path's only delivery channel is a regex in the widget that scrapes
the LAST ```yaml fence out of the model's prose. So the analyst's Save applied
fence #3 — YAML that no gate had ever seen — while the transcript recorded a
green verification of something else entirely. From the analyst's seat the step
simply never landed.

The fix is structural, not a prompt plea: `verify_enhancement` stashes the
blessed text HERE and hands back an opaque `verified_id`. `emit_enhancement_offer`
takes that id and *cannot* take YAML. The model never gets a chance to re-type
the document, so verified and delivered are the same bytes by construction.

Process-local and bounded. A verified id is only meaningful inside the turn
that produced it — the connector runs the tool loop in-process, same as
`agent.skill_trace`'s active-trace scope. A cold worker (or a connector
upgrade, which recycles workers) simply misses, and a miss is a loud, typed
`unknown_verified_id` telling the caller to re-verify — never a silent
fallback to unverified text, which is the whole failure mode being closed.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any

# Bounded MRU. A turn issues at most a handful of verifications; the cap only
# exists so a long-lived worker can't accumulate playbook bodies forever.
_MAX_ENTRIES = 32
_REGISTRY: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def fingerprint(yaml_text: str) -> str:
    """Stable id for a YAML body. Content-addressed on purpose: verifying the
    same text twice yields the same id, so a re-verify after a no-op edit
    doesn't strand the offer against a dead handle."""
    return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()[:16]


def remember(after_yaml: str, **meta: Any) -> str:
    """Stash a verified body, return its `verified_id`.

    `meta` rides along for the offer card to display (diff_summary, the
    before-fingerprint, warnings the analyst should still see). Callers should
    only call this when the verdict actually passed — an id is a claim that
    these exact bytes cleared the gate.
    """
    vid = fingerprint(after_yaml)
    _REGISTRY[vid] = {"yaml": after_yaml, **meta}
    _REGISTRY.move_to_end(vid)
    while len(_REGISTRY) > _MAX_ENTRIES:
        _REGISTRY.popitem(last=False)
    return vid


def lookup(verified_id: str) -> dict[str, Any] | None:
    """Fetch a stashed body, or None if the id is unknown/evicted/cross-worker.

    None is a real answer the caller must handle by asking for a re-verify.
    Do NOT paper over it with model-supplied text.
    """
    if not isinstance(verified_id, str) or not verified_id:
        return None
    entry = _REGISTRY.get(verified_id)
    if entry is not None:
        _REGISTRY.move_to_end(verified_id)
    return entry


def clear() -> None:
    """Drop everything. For tests, and for a session boundary if one is ever
    threaded through here."""
    _REGISTRY.clear()
