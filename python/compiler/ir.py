"""Intermediate representation for FSR playbooks.

The IR is what the parser produces and the emitter consumes. It is
deliberately thin — closer to the YAML the human authored than the FSR
JSON we emit. The emitter is responsible for synthesizing UUIDs, IRI
references, layout coordinates, and other FSR-internal noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Step:
    id: str                          # short refname unique within a playbook
    type: str                        # 'connector' | 'set_variable' | 'decision' | 'start' | ...
    name: str = ""                   # display name (defaults to id)
    arguments: dict[str, Any] = field(default_factory=dict)
    next: Optional[str] = None       # id of next step (linear flow)
    branches: dict[str, str] = field(default_factory=dict)  # decision: option -> step id
    # Unlabeled fanout: multiple outgoing routes from the same source where
    # no labels were attached. Rare in practice (~0.5% of playbooks) but the
    # round-trip needs to preserve `label=None` distinctly from a labeled branch.
    unlabeled_next: list[str] = field(default_factory=list)

    # Filled by the resolver:
    step_type_uuid: Optional[str] = None
    step_type_name: Optional[str] = None  # canonical FSR name e.g. 'Connectors'
    handler: Optional[str] = None         # FUNCTION_MAP key


@dataclass
class Playbook:
    name: str
    description: str = ""
    tag: str = ""
    is_active: bool = False
    trigger: str = "start"           # short-name short-cut for the trigger step type
    # Explicit trigger step id. If unset, emitter falls back to "first step
    # whose type is 'start'". Decompiled playbooks always set this — they
    # might trigger on cybersponse.post_create, cybersponse.action, etc.
    trigger_step_id: Optional[str] = None
    # Input parameter names for this playbook. Callers pass values in
    # via `arguments={name: value}` on a workflow_reference step;
    # inside the playbook, values are read as `{{vars.input.params.<name>}}`.
    parameters: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)


@dataclass
class Collection:
    name: str
    description: str = ""
    visible: bool = True
    playbooks: list[Playbook] = field(default_factory=list)
