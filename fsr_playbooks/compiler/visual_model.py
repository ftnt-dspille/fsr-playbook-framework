"""Visual editor model.

Bridges YAML <-> the flowchart-canvas graph used by the visual editor.
The YAML pipeline (parser → resolver → emitter) stays the source of
truth; this module is a thin view over it that adds two things:

1.  **Graph projection** — `to_visual(yaml_text)` walks the parsed IR
    and returns `{playbooks: [{name, nodes, edges}], collection,
    layout_present, errors}`. Each node carries id, type family,
    display name, raw step args, and an `(x, y)` position when one is
    recorded. Edges encode the linear `next` link, decision branches,
    and unlabeled fanout, matching the IR shape exactly so no info is
    lost on the way out.

2.  **Identity / structural-preserving write** — `from_visual(graph,
    original_yaml)` uses `ruamel.yaml` round-trip mode to mutate the
    original document in place: positions are persisted to a
    `# fsrpb:layout` block at the bottom of the file, and step-level
    edits write back through the same key paths the parser reads. When
    nothing changed, the output is byte-identical to the input — that
    invariant is what the VISUAL_EDITOR_PLAN Phase 0.3 CI test pins.

Edits beyond positions (add / remove / rewire steps, change args)
land in Phase 3; for now `from_visual` covers identity + position
updates only. That's enough to ship Phase 1's read-only canvas with a
working YAML toggle.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import ir
from .parser import parse_yaml
from .samples import (
    append_samples,
    extract_samples_block,
)


# ---------------------------------------------------------------------------
# Node type families — collapses the 43 step types into ~7 visual templates
# the canvas renders. Source of truth for icon + color in the frontend.
# ---------------------------------------------------------------------------

_FAMILY_BY_TYPE: dict[str, str] = {
    "start": "trigger",
    "start_on_create": "trigger",
    "start_on_update": "trigger",
    "manual_action": "trigger",
    "api_call": "trigger",
    "decision": "decision",
    "connector": "connector_op",
    "find_record": "record_crud",
    "create_record": "record_crud",
    "insert_record": "record_crud",
    "update_record": "record_crud",
    "delete_record": "record_crud",
    "set_variable": "utility",
    "code_snippet": "utility",
    "delay": "utility",
    "manual_input": "manual_input",
    "workflow_reference": "workflow_ref",
    "ingest_bulk_feed": "record_crud",
    "stop": "terminal",
    "end": "terminal",
}


def _family(step_type: str) -> str:
    return _FAMILY_BY_TYPE.get(step_type, "utility")


# ---------------------------------------------------------------------------
# Graph projection
# ---------------------------------------------------------------------------

@dataclass
class _Edge:
    source: str
    target: str
    label: str | None = None         # decision branch label, None for linear
    branch_kind: str = "next"        # 'next' | 'branch' | 'unlabeled'

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "branch_kind": self.branch_kind,
        }


def _step_edges(step: ir.Step) -> list[_Edge]:
    edges: list[_Edge] = []
    if step.next:
        edges.append(_Edge(step.id, step.next, None, "next"))
    for label, target in (step.branches or {}).items():
        edges.append(_Edge(step.id, target, label, "branch"))
    for target in (step.unlabeled_next or []):
        edges.append(_Edge(step.id, target, None, "unlabeled"))
    # Decision conditions + manual_input options carry inline `next:`
    # on each branch; the resolver promotes them later, but the parser
    # leaves them under `arguments.conditions/options`. Surface them as
    # graph edges so the canvas reflects the same routing the FSR
    # designer renders.
    args = step.arguments or {}
    for key in ("conditions", "options"):
        items = args.get(key)
        if isinstance(items, list):
            for c in items:
                if not isinstance(c, dict):
                    continue
                target = c.get("next")
                if not isinstance(target, str):
                    continue
                label = (c.get("option") or c.get("display") or c.get("label")
                         or ("default" if c.get("default") else None))
                edges.append(_Edge(step.id, target, label, "branch"))
    return edges


def _step_node(step: ir.Step, position: dict | None) -> dict[str, Any]:
    return {
        "id": step.id,
        "type": step.type,
        "family": _family(step.type),
        "name": step.name or step.id,
        "arguments": step.arguments or {},
        "for_each": step.for_each,
        "comment": step.comment,
        "position": position,        # {"x": int, "y": int} or None
    }


# ---------------------------------------------------------------------------
# Layout sidecar
# ---------------------------------------------------------------------------

# A single comment block at the very top of the YAML, like:
#
# # fsrpb:layout
# # {"Route By Severity": {"start": [60, 40], "Branch on severity": [60, 200]}}
#
# Storing as a header comment keeps the FSR-relevant body untouched and
# makes the round-trip CI test trivial (only one place to look).

_LAYOUT_HEAD_RE = re.compile(r"(?m)^\s*#\s*fsrpb:layout\s*\n")
_LAYOUT_END_RE = re.compile(r"#\s*fsrpb:layout-end\s*\n?")


def _extract_layout_block(text: str) -> tuple[dict[str, dict[str, list[int]]], str]:
    """Pull the layout block out of the YAML if present.

    The block opens with `# fsrpb:layout` and closes with
    `# fsrpb:layout-end`. Lines between are `# <json>` comments holding
    the serialized layout map (playbook name → step id → [x, y]). The
    block may live at the top or bottom of the file — we search for the
    first occurrence. Missing/malformed → empty map + original text.
    """
    head = _LAYOUT_HEAD_RE.search(text)
    if not head:
        return {}, text
    before = text[: head.start()]
    rest = text[head.end():]
    end = _LAYOUT_END_RE.search(rest)
    if not end:
        return {}, text
    block = rest[: end.start()]
    after = rest[end.end():]
    json_lines = []
    for ln in block.splitlines():
        s = ln.lstrip()
        if s.startswith("#"):
            json_lines.append(s[1:].lstrip())
        else:
            return {}, text  # non-comment line inside block → bail
    try:
        layout = json.loads("\n".join(json_lines))
        if not isinstance(layout, dict):
            return {}, text
    except Exception:
        return {}, text
    return layout, before + after


def _emit_layout_block(layout: dict[str, dict[str, list[int]]]) -> str:
    """Inverse of _extract_layout_block.

    Returns "" for an empty layout so identity round-trips of files
    that had no layout originally stay identical.
    """
    if not layout:
        return ""
    body = json.dumps(layout, indent=2, sort_keys=True)
    out = ["# fsrpb:layout"]
    for ln in body.splitlines():
        out.append(f"# {ln}" if ln else "#")
    out.append("# fsrpb:layout-end")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def to_visual(yaml_text: str) -> dict[str, Any]:
    """Project a YAML playbook source into the canvas graph shape.

    Returns:
        {
          collection: {name, description, visible},
          playbooks: [{name, description, parameters, trigger,
                       nodes: [...], edges: [...]}],
          layout_present: bool,    # was a layout block found
          errors: [...],           # parser errors as plain dicts
        }
    """
    # Both sidecar blocks live at the YAML footer. We strip them only to
    # recover the map — parser tolerates them (they're comments), but
    # callers also want the structured form.
    layout_map, _body = _extract_layout_block(yaml_text)
    samples_map, _body2 = extract_samples_block(yaml_text)
    coll, errs = parse_yaml(yaml_text)
    if coll is None:
        return {
            "collection": None,
            "playbooks": [],
            "layout_present": bool(layout_map),
            "samples": samples_map,
            "errors": [_err_to_dict(e) for e in errs],
        }

    pbs_out = []
    for pb in coll.playbooks:
        pb_layout = layout_map.get(pb.name, {})
        nodes = []
        for s in pb.steps:
            pos_pair = pb_layout.get(s.id) or pb_layout.get(s.name)
            position = (
                {"x": int(pos_pair[0]), "y": int(pos_pair[1])}
                if isinstance(pos_pair, (list, tuple)) and len(pos_pair) == 2
                else None
            )
            nodes.append(_step_node(s, position))

        edges = []
        for s in pb.steps:
            for e in _step_edges(s):
                edges.append(e.to_dict())

        pbs_out.append({
            "name": pb.name,
            "description": pb.description,
            "parameters": list(pb.parameters or []),
            "trigger": pb.trigger,
            "trigger_step_id": pb.trigger_step_id,
            # Surfaced for the frontend's "inactive playbook" guard.
            # Default in the IR is False; trigger playbooks need this
            # set to True (or a post-push PUT-activate) to actually
            # fire — confirmed by the round-trip live-fire probe.
            "is_active": bool(getattr(pb, "is_active", False)),
            # Verbose runtime tracing. New visual-editor drafts ship
            # with this set so authors see step-by-step output the
            # first time they run; production playbooks should flip
            # it off via the inspector header.
            "debug": bool(getattr(pb, "debug", False)),
            "nodes": nodes,
            "edges": edges,
        })

    return {
        "collection": {
            "name": coll.name,
            "description": coll.description,
            "visible": coll.visible,
        },
        "playbooks": pbs_out,
        "layout_present": bool(layout_map),
        # Per-step synthetic values for `manual_input` (and future step
        # types). Shape: `{playbook_name: {step_id: {<key>: <value>}}}`.
        # Empty dict when no samples block is present.
        "samples": samples_map,
        "errors": [_err_to_dict(e) for e in errs],
    }


def _err_to_dict(e: Any) -> dict[str, Any]:
    return {
        "code": getattr(e, "code", None),
        "message": getattr(e, "message", str(e)),
        "path": getattr(e, "path", None),
    }


def from_visual(graph: dict[str, Any], original_yaml: str) -> str:
    """Write a graph back to YAML, preserving the original document.

    Identity contract: when nothing changed (positions or otherwise),
    the returned string MUST equal `original_yaml` byte-for-byte.
    Phase 0.3 CI pins this.

    Position-only updates re-emit the `# fsrpb:layout` footer block
    and leave the body intact (pure-stdlib path).

    Structural edits — `arguments`, `name`, `comment`, `for_each`,
    and step add/remove — are routed through `ruamel.yaml` round-trip
    mode so the rest of the document keeps its comments, key order,
    and quoting style. Edge rewiring is currently rejected so the
    user has one place to look (Phase 3.5/3.6 will lift this).
    """
    new_layout = _collect_layout_from_graph(graph)
    existing_layout, body = _extract_layout_block(original_yaml)
    existing_samples, body = extract_samples_block(body)
    # `graph["samples"]` is authoritative when present (the writer just
    # edited them); fall back to whatever was already in the YAML so a
    # graph payload that omits the key doesn't accidentally erase them.
    new_samples = (
        graph["samples"] if isinstance(graph.get("samples"), dict)
        else existing_samples
    )
    diff = _diff_against_original(graph, original_yaml)

    if not diff.has_structural_edits:
        if new_layout == existing_layout and new_samples == existing_samples:
            return original_yaml
        return _append_sidecars(body, new_layout, new_samples)

    new_body = _apply_structural_edits(body, diff, graph)
    return _append_sidecars(new_body, new_layout, new_samples)


def _append_sidecars(body: str,
                      layout: dict[str, dict[str, list[int]]],
                      samples: dict[str, dict[str, Any]]) -> str:
    """Layout first, then samples — fixed order so round-trips are
    byte-stable. Each is a no-op on its empty map."""
    out = _append_layout(body, layout)
    out = append_samples(out, samples)
    return out


def _append_layout(body: str, layout: dict[str, dict[str, list[int]]]) -> str:
    """Tack the layout block onto the end of `body`. Empty layout → body
    unchanged so files that never had a layout stay byte-identical."""
    footer = _emit_layout_block(layout)
    if not footer:
        return body
    sep = "" if body.endswith("\n") or not body else "\n"
    return body + sep + footer


# ---------------------------------------------------------------------------
# Diff + edit helpers
# ---------------------------------------------------------------------------

@dataclass
class _NodeEdit:
    name: str | None = None
    arguments: dict | None = None
    comment: str | None = None
    for_each: dict | None = None


@dataclass
class _PlaybookDiff:
    name: str
    added: list[dict]            # graph nodes that weren't in the original
    removed: list[str]           # original ids that aren't in the graph
    edits: dict[str, _NodeEdit]  # id -> mutation
    edges_changed: bool
    new_edges: list[dict] = None  # edges introduced by this diff (touch added)

    def __post_init__(self):
        if self.new_edges is None:
            self.new_edges = []


@dataclass
class _GraphDiff:
    playbook_diffs: list[_PlaybookDiff]
    has_structural_edits: bool
    edges_changed: bool


def _diff_against_original(graph: dict[str, Any], original_yaml: str) -> _GraphDiff:
    parsed = to_visual(original_yaml)
    orig_pbs = {pb["name"]: pb for pb in parsed["playbooks"]}

    if {pb["name"] for pb in graph.get("playbooks", [])} != set(orig_pbs):
        raise NotImplementedError(
            "from_visual: playbook add/remove not yet supported"
        )

    diffs: list[_PlaybookDiff] = []
    has_struct = False
    edges_changed_any = False
    for pb in graph.get("playbooks", []):
        orig = orig_pbs[pb["name"]]
        new_by_id = {n["id"]: n for n in pb["nodes"]}
        old_by_id = {n["id"]: n for n in orig["nodes"]}

        added = [n for n in pb["nodes"] if n["id"] not in old_by_id]
        removed = [sid for sid in old_by_id if sid not in new_by_id]

        edits: dict[str, _NodeEdit] = {}
        for sid, new_n in new_by_id.items():
            if sid not in old_by_id:
                continue
            old = old_by_id[sid]
            ed = _NodeEdit()
            changed = False
            if new_n.get("name") != old.get("name"):
                ed.name = new_n.get("name") or sid
                changed = True
            if new_n.get("arguments") != old.get("arguments"):
                ed.arguments = new_n.get("arguments") or {}
                changed = True
            if new_n.get("comment") != old.get("comment"):
                ed.comment = new_n.get("comment")
                changed = True
            if new_n.get("for_each") != old.get("for_each"):
                ed.for_each = new_n.get("for_each")
                changed = True
            if changed:
                edits[sid] = ed

        # Edges that touch a newly-added or newly-removed node are
        # accounted for by the add/remove path; they don't count as
        # "rewiring" of existing wiring.
        added_ids = {n["id"] for n in added}
        removed_set = set(removed)
        def _stable(es):
            return {(e["source"], e["target"], e.get("label"),
                     e.get("branch_kind")) for e in es
                    if e["source"] not in added_ids
                    and e["target"] not in added_ids
                    and e["source"] not in removed_set
                    and e["target"] not in removed_set}
        edges_changed = _stable(pb.get("edges", [])) != _stable(orig["edges"])
        new_edges = [
            e for e in pb.get("edges", [])
            if e["source"] in added_ids or e["target"] in added_ids
        ]

        struct = bool(added or removed or edits or edges_changed)
        if struct:
            has_struct = True
        if edges_changed:
            edges_changed_any = True
        diffs.append(_PlaybookDiff(
            name=pb["name"], added=added, removed=removed,
            edits=edits, edges_changed=edges_changed,
            new_edges=new_edges,
        ))

    return _GraphDiff(diffs, has_struct, edges_changed_any)


def _slugify(s: str) -> str:
    """Match parser._slugify so we can resolve `id` ↔ original `name:`."""
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    while out and out[-1] == "_":
        out.pop()
    return "".join(out) or "step"


def _apply_structural_edits(body: str, diff: _GraphDiff, graph: dict[str, Any]) -> str:
    """Mutate the YAML body in-place using ruamel round-trip mode.

    Comments, blank lines, key order, and quote style on unchanged
    sections are preserved. Failure to load (truly malformed YAML)
    re-raises so the caller doesn't accidentally clobber on save.
    """
    from ruamel.yaml import YAML  # lazy: only required when editing

    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True
    yaml_rt.width = 4096
    yaml_rt.indent(mapping=2, sequence=4, offset=2)

    import io
    doc = yaml_rt.load(io.StringIO(body))
    if doc is None or "playbooks" not in doc:
        raise ValueError("from_visual: original YAML missing `playbooks:` root")

    pbs_by_name = {pb.get("name"): pb for pb in doc["playbooks"]}
    graph_pbs_by_name = {pb["name"]: pb for pb in graph.get("playbooks", [])}

    for pd in diff.playbook_diffs:
        pb_doc = pbs_by_name.get(pd.name)
        if pb_doc is None:
            raise ValueError(f"from_visual: playbook {pd.name!r} not in source")
        steps = pb_doc.setdefault("steps", [])

        # Index existing yaml steps by slugified name (the canvas `id`).
        def _step_id(s_doc) -> str:
            return _slugify(str(s_doc.get("name", "")))

        # 1) Remove steps the caller dropped from the graph.
        if pd.removed:
            keep = [s for s in steps if _step_id(s) not in set(pd.removed)]
            steps[:] = keep

        # 2) Apply per-step edits.
        for s_doc in steps:
            sid = _step_id(s_doc)
            if sid not in pd.edits:
                continue
            edit = pd.edits[sid]
            if edit.name is not None:
                s_doc["name"] = edit.name
            if edit.comment is not None:
                if edit.comment == "":
                    if "comment" in s_doc:
                        del s_doc["comment"]
                else:
                    s_doc["comment"] = edit.comment
            if edit.for_each is not None:
                if edit.for_each:
                    s_doc["for_each"] = edit.for_each
                elif "for_each" in s_doc:
                    del s_doc["for_each"]
            if edit.arguments is not None:
                _splice_arguments(s_doc, edit.arguments)

        # 3) Append newly added nodes with a minimal default body.
        new_node_by_id = {n["id"]: n for n in pd.added}
        for new_n in pd.added:
            steps.append(_default_step_doc(new_n))

        # 4) Wire the edges that touch the newly-added nodes.
        for e in pd.new_edges:
            src_id, tgt_id = e["source"], e["target"]
            if tgt_id in new_node_by_id:
                tgt_name = new_node_by_id[tgt_id].get("name") or tgt_id
            else:
                # Existing target — look up its display name
                tgt_doc = next((s for s in steps if _step_id(s) == tgt_id), None)
                tgt_name = str(tgt_doc.get("name")) if tgt_doc else tgt_id
            # Find source step doc
            if src_id in new_node_by_id:
                src_doc = next((s for s in steps if _step_id(s) == src_id), None)
            else:
                src_doc = next((s for s in steps if _step_id(s) == src_id), None)
            if src_doc is None:
                continue
            kind = e.get("branch_kind", "next")
            if kind == "branch":
                # Phase 3.6 will lift this; for now, dropping branch
                # edges into newly-added decisions is a no-op.
                continue
            if "next" not in src_doc or src_doc.get("next") in (None, "", "null"):
                src_doc["next"] = tgt_name

        # 5) Edge rewiring on existing nodes (Phase 3.5/3.6).
        if pd.edges_changed:
            graph_pb = graph_pbs_by_name.get(pd.name)
            if graph_pb:
                _apply_edge_rewiring(steps, graph_pb, pd, _step_id)

    out = io.StringIO()
    yaml_rt.dump(doc, out)
    return out.getvalue()


# Top-level YAML keys the parser hoists out of `arguments:` into
# step-level shortcuts. Keeping them at the top level when present
# matches the original document style and avoids gratuitous diffs.
_HOISTED_ARG_KEYS: tuple[str, ...] = (
    "vars", "conditions", "options", "connector", "operation",
    "operationTitle", "version", "params", "filter_criteria", "module",
    "collection", "fields", "code", "code_snippet", "delay",
    "duration", "manual_input_type", "context", "audience",
    "assignment", "form_data",
)


def _splice_arguments(s_doc: Any, new_args: dict) -> None:
    """Update a step's args in-place, respecting the hoisted-key style.

    The parser accepts both `step.arguments.X` and `step.X` for many
    keys (set_variable.vars, decision.conditions, connector.params,
    …). When the original used the hoisted form, we rewrite under the
    same name; otherwise we drop everything into a single
    `arguments:` block. This keeps diffs minimal.

    set_variable's `arg_list:` shape (post-parser normalization) is
    converted back to the friendlier top-level `vars:` mapping when
    that's the form the original used — otherwise downstream re-parses
    would error with "set_variable: write a top-level `vars:` mapping".
    """
    new_args = dict(new_args or {})

    # set_variable: arg_list[{name, value}] → vars: {name: value} when
    # the original used the friendlier top-level mapping.
    if "vars" in s_doc and "arg_list" in new_args and "vars" not in new_args:
        arg_list = new_args.pop("arg_list")
        if isinstance(arg_list, list):
            new_args["vars"] = {
                str(item.get("name")): item.get("value")
                for item in arg_list
                if isinstance(item, dict) and item.get("name")
            }

    # Preserve the original document's style: hoisted keys stay hoisted,
    # nested keys stay nested. A key that lived under `arguments:` should
    # NOT be promoted to the step level just because the IR re-emits it
    # via `new_args` (which always carries the union of both forms).
    existing_arg_doc = s_doc.get("arguments")
    nested_keys = (
        set(existing_arg_doc.keys()) if isinstance(existing_arg_doc, dict) else set()
    )

    for hoisted in _HOISTED_ARG_KEYS:
        if hoisted in s_doc and hoisted in new_args:
            s_doc[hoisted] = new_args.pop(hoisted)
        elif hoisted in s_doc and hoisted not in new_args:
            # The graph dropped this key — remove it from the doc too.
            del s_doc[hoisted]
        elif hoisted in nested_keys:
            # Was nested under `arguments:` originally; leave the
            # remaining-keys block below to write it back there.
            continue
        elif hoisted not in s_doc and hoisted in new_args:
            # New top-level shortcut requested by the edit.
            s_doc[hoisted] = new_args.pop(hoisted)

    # Remaining keys go into `arguments:` (creating it if needed).
    if new_args:
        s_doc["arguments"] = new_args
    elif "arguments" in s_doc:
        del s_doc["arguments"]


def _apply_edge_rewiring(steps: list, graph_pb: dict, pd: _PlaybookDiff,
                          step_id_fn) -> None:
    """Rewrite outgoing wiring (next / branches) for existing source steps.

    Scope (Phase 3.5/3.6):
      - linear `next:` retargeting and removal
      - decision branch `next:` retargeting
      - decision branch label edits (option/display rename)
    Adding/removing branches on a decision is best-effort: a missing
    label in the new graph deletes that condition row; a new label
    appends a row with `when:` left blank for the user to fill in.
    """
    added_ids = {n["id"] for n in pd.added}
    nodes_by_id = {n["id"]: n for n in graph_pb["nodes"]}
    name_for_id = {sid: (n.get("name") or sid) for sid, n in nodes_by_id.items()}

    # Bucket the new edges by source step id, skipping edges that
    # touch newly-added nodes — those are already wired by step 4.
    by_source: dict[str, list[dict]] = {}
    for e in graph_pb.get("edges", []):
        if e["source"] in added_ids or e["target"] in added_ids:
            continue
        by_source.setdefault(e["source"], []).append(e)

    for s_doc in steps:
        sid = step_id_fn(s_doc)
        if sid in added_ids:
            continue
        outbound = by_source.get(sid, [])
        stype = str(s_doc.get("type", "")).lower()

        # ---- Linear next: -------------------------------------------
        next_edges = [e for e in outbound if e.get("branch_kind") == "next"]
        if next_edges:
            tgt = next_edges[0]["target"]
            new_next = name_for_id.get(tgt, tgt)
            if s_doc.get("next") != new_next:
                s_doc["next"] = new_next
        else:
            # All outbound `next:` edges removed for this step.
            if "next" in s_doc and stype != "decision":
                # Decisions keep next:None as default fallthrough; for
                # plain steps, dropping next means the step becomes a
                # leaf. ruamel preserves the absence cleanly.
                del s_doc["next"]

        # ---- Decision / manual_input branches -----------------------
        if stype not in ("decision", "manual_input"):
            continue
        branch_edges = [e for e in outbound if e.get("branch_kind") == "branch"]
        key = "conditions" if stype == "decision" else "options"
        # Hoisted form takes precedence over `arguments.<key>`.
        if key in s_doc:
            container = s_doc
        elif "arguments" in s_doc and key in s_doc.get("arguments", {}):
            container = s_doc["arguments"]
        else:
            container = None
        if container is None or not isinstance(container.get(key), list):
            continue
        rows = container[key]

        # Build a label→target map from the new graph for easy lookup.
        new_by_label: dict[str | None, str] = {}
        for be in branch_edges:
            new_by_label[be.get("label")] = name_for_id.get(be["target"], be["target"])

        # Update existing rows in-place when their label still exists,
        # and remove rows whose label was dropped from the graph.
        kept = []
        consumed: set[str | None] = set()
        for row in rows:
            if not isinstance(row, dict):
                kept.append(row)
                continue
            label = (row.get("option") or row.get("display") or row.get("label")
                     or ("default" if row.get("default") else None))
            if label in new_by_label:
                row["next"] = new_by_label[label]
                consumed.add(label)
                kept.append(row)
            # else: row dropped (label no longer in graph)
        # Append fresh rows for new labels not in the original.
        for label, tgt_name in new_by_label.items():
            if label in consumed:
                continue
            new_row = {"next": tgt_name}
            if label and label != "default":
                new_row["option"] = label
            else:
                new_row["default"] = True
            kept.append(new_row)
        container[key] = kept


def _default_step_doc(node: dict) -> dict:
    """Synthesize a minimal YAML body for a freshly added canvas node.

    Mirrors `_splice_arguments` for set_variable's `arg_list` →
    top-level `vars:` translation so brand-new steps round-trip
    through the parser cleanly.
    """
    out: dict[str, Any] = {"name": node.get("name") or node["id"], "type": node["type"]}
    args = dict(node.get("arguments") or {})

    if node.get("type") == "set_variable" and "arg_list" in args and "vars" not in args:
        arg_list = args.pop("arg_list")
        if isinstance(arg_list, list):
            out["vars"] = {
                str(item.get("name")): item.get("value")
                for item in arg_list
                if isinstance(item, dict) and item.get("name")
            }

    for hoisted in _HOISTED_ARG_KEYS:
        if hoisted in args:
            out[hoisted] = args.pop(hoisted)
    if args:
        out["arguments"] = args
    if node.get("comment"):
        out["comment"] = node["comment"]
    if node.get("for_each"):
        out["for_each"] = node["for_each"]
    return out


def _collect_layout_from_graph(graph: dict[str, Any]) -> dict[str, dict[str, list[int]]]:
    out: dict[str, dict[str, list[int]]] = {}
    for pb in graph.get("playbooks", []):
        pos_map: dict[str, list[int]] = {}
        for n in pb.get("nodes", []):
            p = n.get("position")
            if isinstance(p, dict) and "x" in p and "y" in p:
                pos_map[n["id"]] = [int(p["x"]), int(p["y"])]
        if pos_map:
            out[pb["name"]] = pos_map
    return out


