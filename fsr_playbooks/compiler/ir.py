"""Intermediate representation for FSR playbooks.

The IR is what the parser produces and the emitter consumes. It is
deliberately thin — closer to the YAML the human authored than the FSR
JSON we emit. The emitter is responsible for synthesizing UUIDs, IRI
references, layout coordinates, and other FSR-internal noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# FSR system picklist that backs a workflow's execution priority. The resolver
# maps a playbook's `priority:` name (High/Medium/Low) to the live IRI by
# querying the synced `picklists` table for this listName — so the emitted IRI
# is always the running instance's own system value (probe_modules.py re-mines
# the picklists table from /api/3/picklist_names), never a baked constant.
PRIORITY_LIST_NAME = "WorkflowPriority"


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
    # Free-form explanation rendered as a sticky-note next to the step on
    # the FSR canvas. Authors set this to leave human-readable rationale
    # for AI-modified steps; the emitter auto-creates a 'note' annotation
    # positioned to the right of the step. Mutually compatible with
    # explicit `playbook.annotations` entries.
    comment: Optional[str] = None

    # FSR's per-step `description` field (distinct from `comment`, which is a
    # canvas sticky-note). Free-form text shown in the step's detail pane.
    # Round-tripped verbatim by the decompiler so a pulled playbook keeps it.
    description: str = ""

    # Per-iteration loop config. Wire shape is a dict at the step level
    # (sibling of `arguments`). When set, the step body executes once per
    # element of `item` (a Jinja list expression), with the current element
    # bound as `{{ vars.item }}` (and `vars.item.<field>` for object items).
    # Accepted keys: item (required), parallel, condition, __bulk,
    # batch_size, break_loop. None means no looping.
    for_each: Optional[dict] = None

    # Filled by the resolver:
    step_type_uuid: Optional[str] = None
    step_type_name: Optional[str] = None  # canonical FSR name e.g. 'Connectors'
    handler: Optional[str] = None         # FUNCTION_MAP key


@dataclass
class Annotation:
    """A sticky-note or visual block on the playbook canvas.

    Maps 1:1 to FSR's `WorkflowGroup` entity (table `workflow_groups`).
    `kind` is the FSR `type` field — `note` (sticky comment), `block`
    (bordered grouping that wraps steps), or `custom`.
    """
    id: str                          # local slug, unique within a playbook
    kind: str = "note"               # 'note' | 'block' | 'custom'
    title: str = "Note"              # FSR `name`; defaults to "Note" when blank
    body: str = ""                   # FSR `description`; markdown for notes
    top: Optional[int] = None        # canvas Y; emitter fills in if None
    left: Optional[int] = None       # canvas X; emitter fills in if None
    height: int = 0                  # 0 means auto-grow (FSR convention for notes)
    width: int = 300
    collapsed: bool = False
    hide_in_logs: bool = True        # default true for notes per real playbooks
    contains: list[str] = field(default_factory=list)  # block: step ids inside
    # Marker for auto-generated notes (from step.comment). Not user-set.
    # Lets the decompiler collapse the round-trip back into step.comment.
    auto_for_step: Optional[str] = None
    uuid: Optional[str] = None       # filled by emitter


@dataclass
class Playbook:
    name: str
    description: str = ""
    tag: str = ""
    # Defaults to active (matches FSR's UI + author intent: you don't usually
    # deploy a playbook you want disabled). Set is_active=False for a draft.
    is_active: bool = True
    # Verbose runtime tracing. FSR's workflow engine writes one log
    # line per step + a payload dump when this is true; keep off for
    # production but on for new visual-editor drafts so authors see
    # their step output without flipping a knob.
    debug: bool = False
    # Playbook visibility. FSR's `isPrivate` flag: when true the playbook is
    # hidden from the UI catalog and — per the documented ownership model —
    # only executable by users/API keys whose owner teams intersect the
    # playbook's `owners`. Authored as `is_private: true` in YAML.
    is_private: bool = False
    # Owner teams as authored — team NAMES (e.g. "TeamA") or IRIs
    # (`/api/3/teams/<uuid>`). Names resolve to IRIs via the resolver's
    # `teams` table (when the reference catalog carries one); IRIs pass
    # through unchanged. An empty list (default) leaves the playbook
    # unowned — FSR requires private playbooks to declare owners.
    owners: list[str] = field(default_factory=list)
    # Resolver-filled: owners as IRI strings (`/api/3/teams/<uuid>`). When
    # the `teams` table is unsynced, this stays empty and `owners` is
    # emitted verbatim so a deploy layer with a live client can resolve.
    owners_iris: list[str] = field(default_factory=list)
    # Execution priority NAME as authored (e.g. "High"). None = engine default.
    # The agent-routed run_op wrap sets this to "High" so containment ops jump
    # the queue. Resolved to a picklist IRI by the resolver (see priority_iri).
    priority: Optional[str] = None
    # Resolver-filled: the picklist IRI for `priority`, looked up live-synced
    # from the store's `picklists` table (listName WorkflowPriority).
    priority_iri: Optional[str] = None
    trigger: str = "start"           # short-name short-cut for the trigger step type
    # Explicit trigger step id. If unset, emitter falls back to "first step
    # whose type is 'start'". Decompiled playbooks always set this — they
    # might trigger on cybersponse.post_create, cybersponse.action, etc.
    trigger_step_id: Optional[str] = None
    # Input parameter names for this playbook. Callers pass values in
    # via `arguments={name: value}` on a workflow_reference step;
    # inside the playbook, values are read as `{{vars.input.params.<name>}}`.
    parameters: list[str] = field(default_factory=list)
    # Optional declared type per parameter (STATIC_TYPE_FLOW Phase 3). Set
    # only when `parameters:` is authored as a mapping {name: type}; a bare
    # list leaves this empty and each param stays `any`. Seeds
    # `vars.input.params.<name>` shapes in the typed walker.
    parameter_types: dict[str, str] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    annotations: list["Annotation"] = field(default_factory=list)


@dataclass
class Collection:
    name: str
    description: str = ""
    visible: bool = True
    playbooks: list[Playbook] = field(default_factory=list)
    # Push mode — toggled by which top-level YAML key was used:
    #   "wrap"        — YAML used `collection: <name>`. The push replaces
    #                   the whole collection (cascade-removes foreigns
    #                   unless --allow-foreign-loss is set). Default.
    #   "per_playbook"— YAML used `into_collection: <name>` (or omitted
    #                   both and inherited the default target). The push
    #                   touches ONLY the listed playbooks inside the
    #                   target collection; siblings are preserved.
    target_mode: str = "wrap"
