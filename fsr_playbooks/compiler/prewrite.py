"""HARDEN-1: refuse a playbook save that silently deletes the customer's data.

The widget writes the model's last ```yaml fence back **over** the live
playbook. Field loss on that path is *silent*: it has happened twice
(`for_each`, then declared `parameters`), both found by accident, both
invisible to every test tier -- unit fixtures are synthesized so they inherit
the fixer's blind spots, mock e2e is hermetic, and the live sweep drives the UI
rather than the compiler. `corpus_gate` catches the *compiler* losing a field it
should have kept, but it can only ever run over fixtures we already thought of.

This module closes the gap from the other side: at the moment of writing, diff
what is about to be saved against what is currently on the appliance and refuse
the save when something present in the live playbook has vanished.

The comparison is the same **semantic** projection `roundtrip` uses
(`normalize_collection`: per-step type/arguments/for_each, the routing graph,
declared parameters), so appliance-only metadata -- timestamps, ownership,
layout, record IRIs -- never trips it.

Policy: **fail closed, and name the dropped path.** A drop is not always a bug --
"delete the notify step" is a perfectly good request -- so the guard does not try
to read intent, which it cannot do reliably. It refuses, reports exactly which
paths disappeared, and lets the caller re-issue the write with those paths named
in `acknowledged` (`acknowledged_drops` at the `push_playbook` boundary -- keep
the user-facing copy naming the parameter the caller actually passes). That
turns a silent deletion into a deliberate one.

    verdict = check_prewrite(live_json, outgoing_json, db_path)
    if not verdict.ok:
        return {"ok": False, "error": verdict.message, "dropped": verdict.dropped}

Additions and in-place value changes are never refused -- those are the edit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .roundtrip import normalize_collection
from .wire import UnexpandedRelationshipsError, require_expanded_collection


@dataclass
class PreWriteVerdict:
    """Outcome of the pre-write diff. `ok` False means: do not write."""

    ok: bool
    dropped: list[str] = field(default_factory=list)
    """Semantic paths present in the live playbook and absent from the write."""
    acknowledged: list[str] = field(default_factory=list)
    """Dropped paths the caller explicitly named, so they were allowed."""
    entailed: list[str] = field(default_factory=list)
    """Drops that follow necessarily from an acknowledged one.

    Routes incident to a deleted step. Kept OUT of `acknowledged` -- the caller
    never named these, and reporting them as things they signed off on would
    misstate what they agreed to. Surfaced so the effect of the save is still
    fully enumerable.
    """
    message: str = ""
    code: str = ""
    """Machine-readable refusal class. Empty when `ok`.

    Callers BRANCH on this, so the classes must not be conflated. In
    particular an unreadable live pull is NOT a field-loss refusal: it carries
    an empty `dropped`, so a caller that saw one code for both would read
    "nothing dropped" and retry with an empty acknowledgement forever -- a
    refusal that can never be satisfied by the remedy it appears to offer.

    `would_drop_fields`  -- named paths would be deleted; acknowledgeable.
    `live_unreadable`    -- we could not establish what is live; NOT
                            acknowledgeable, and never satisfiable by retrying
                            with acknowledgements.
    """

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dropped": list(self.dropped),
            "acknowledged": list(self.acknowledged),
            "entailed": list(self.entailed),
            "message": self.message,
            "code": self.code,
        }


_REDERIVED_ARGS = frozenset({"config"})
"""Step arguments the compiler re-derives, so their absence is not a deletion.

`config` is filled from the **per-appliance** `connector_configs` catalog
(`resolver/connector_args.py`: `if not a.get("config"): a["config"] =
resolve_config_id(connector) or ""`), and `""` is the documented "use the
connector's default configuration" sentinel. The same YAML therefore compiles
with a uuid on a host whose catalog is warmed and with `""` on one whose is
not -- a difference in the *environment*, not in the document.

The decompiler already classifies it that way (`decompiler.py`: it strips
`config: ""` so a round trip is byte-stable). The guard did not, and the two
disagreeing is what live probe A3 hit: deleting one step was refused partly
for `steps[Block IP].arguments.config`, a field nothing in the turn had
touched. A guard that fires on catalog warmth is noise, and noise on a
fail-closed path teaches callers to acknowledge paths they have not read.

Scoped to the `arguments` level on purpose: a top-level key that happens to be
named `config` is not this field.
"""


def _is_empty(value: Any) -> bool:
    """Did this field lose its content?

    `None`, `""`, `[]`, `{}` are all "gone" -- the wire is inconsistent about
    which one a cleared field becomes, and for a *loss* check they mean the
    same thing. `0` and `False` are real values and are NOT empty.
    """
    if value is None:
        return True
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) == 0
    return False


def _walk_losses(before: Any, after: Any, path: str, out: list[str]) -> None:
    """Collect paths where `before` had content and `after` does not.

    Deliberately one-directional: anything only in `after` is the requested
    edit, and a changed value is an edit too. Only disappearance is a loss.
    """
    if _is_empty(before):
        return  # nothing was there to lose
    if _is_empty(after):
        # Name what was lost, not just the container that held it. Clearing a
        # workflow's whole `parameters` list must report each parameter -- an
        # agent handed "collection.workflows[X].parameters" cannot tell which
        # inputs it just deleted, which is the whole point of the message.
        if isinstance(before, list):
            for value in before:
                out.append(f"{path}[{_identity(value)}]")
        elif isinstance(before, dict):
            for key in sorted(before):
                _walk_losses(before[key], None, f"{path}.{key}", out)
        else:
            out.append(path)
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for k in sorted(before):
            if k in _REDERIVED_ARGS and path.endswith(".arguments"):
                # Not the author's data -- see _REDERIVED_ARGS.
                continue
            _walk_losses(before[k], after.get(k), f"{path}.{k}", out)
        return
    if isinstance(before, list) and isinstance(after, list):
        # Lists here are already sorted by a stable identity key
        # (`normalize_collection` sorts steps by name+type, routes by
        # src/tgt/label, parameters alphabetically), so compare as SETS of
        # identity rather than by index -- otherwise deleting the first of
        # three steps reports every later step as changed instead of
        # reporting the one that actually vanished.
        before_by_id = {_identity(v): v for v in before}
        after_ids = {_identity(v) for v in after}
        for ident, value in before_by_id.items():
            if ident not in after_ids:
                out.append(f"{path}[{ident}]")
                continue
            # Same identity on both sides -- recurse to catch a step that
            # survived but lost an argument (the `for_each` / `parameters`
            # defect class).
            match = next(v for v in after if _identity(v) == ident)
            _walk_losses(value, match, f"{path}[{ident}]", out)
        return
    # Two non-empty scalars, or a type change between non-empty values:
    # that is a modification, not a loss.


def _identity(item: Any) -> str:
    """A stable, human-readable key for a list member.

    Steps are identified by name (that is what the analyst sees and what the
    routing graph references), routes by their endpoints, and anything else --
    notably the `parameters` string list -- by its own value.
    """
    if isinstance(item, dict):
        if "name" in item:
            return str(item.get("name"))
        if "src_name" in item or "tgt_name" in item:
            label = item.get("label")
            edge = f"{item.get('src_name')}->{item.get('tgt_name')}"
            return f"{edge}:{label}" if label else edge
    return str(item)


def diff_losses(live_json: dict[str, Any], outgoing_json: dict[str, Any]) -> list[str]:
    """Semantic paths present in `live_json` and gone from `outgoing_json`.

    Both arguments are FortiSOAR collection envelopes (`{"data": [ ... ]}`) --
    the live one as pulled from the appliance, the outgoing one as the compiler
    emitted it from the YAML about to be saved.
    """
    before = normalize_collection(live_json)
    after = normalize_collection(outgoing_json)
    losses: list[str] = []
    _walk_losses(before, after, "collection", losses)
    return losses


@dataclass(frozen=True)
class RouteEntailment:
    """Why a vanished route did not need a decision of its own."""

    kind: str
    """`deleted_step` -- forgiven only when that deletion is acknowledged.
    `rewired_by_insertion` -- forgiven outright; additions are the edit."""
    cause: str
    """The `steps[...]` path responsible."""


def entailed_route_drops(
    live_json: dict[str, Any], outgoing_json: dict[str, Any]
) -> dict[str, RouteEntailment]:
    """Map each vanished route to the step change that necessarily removed it.

    A route is an edge between two steps, so some route drops are not decisions
    the caller made -- they are arithmetic on a decision they did make. Two
    shapes, both found by live effect probes:

    `deleted_step` (probe A3). Delete a step and its edges cannot survive; FSR
    will not accept a route pointing at a step that is not there. Reporting
    those as independent losses is what made the escape hatch unusable: "delete
    the Dead End step" came back demanding acknowledgement of three paths, two
    of which the caller never authored.

    `rewired_by_insertion` (probe A2). Insert a step *between* two others and
    the direct edge they used to share is necessarily replaced by the path
    through the new step -- `Enrich IP->Block IP` becomes `Enrich IP->Stamp
    Verdict->Block IP`. The guard read the vanished direct edge as data loss and
    refused, so the single most common enhancement there is -- add a step in the
    middle -- could not be saved at all. These are forgiven OUTRIGHT rather than
    acknowledged: additions are never refused, so there is no refusal for the
    caller to acknowledge in the first place.

    The insertion rule is deliberately narrow. `A->B` is only forgiven when the
    outgoing document still connects A to B by a path whose every intermediate
    node is newly added -- i.e. the edge was rerouted, not severed. Dropping
    `A->B` while adding an unrelated step elsewhere gets no forgiveness, which
    keeps "silently reshapes execution" caught.
    """
    before = normalize_collection(live_json)
    after = normalize_collection(outgoing_json)
    after_wfs = {w.get("name"): w for w in after.get("workflows") or []}

    entailed: dict[str, RouteEntailment] = {}
    for wf in before.get("workflows") or []:
        name = wf.get("name")
        awf = after_wfs.get(name)
        if awf is None:
            # The whole workflow is gone; its own loss path already covers
            # everything inside it, routes included.
            continue
        prefix = f"collection.workflows[{name}]"
        live_names = {s.get("name") for s in wf.get("steps") or []}
        kept_names = {s.get("name") for s in awf.get("steps") or []}
        gone_steps = live_names - kept_names
        added_steps = kept_names - live_names

        # Outgoing adjacency, for the insertion walk below.
        out_edges: dict[Any, set[Any]] = {}
        for route in awf.get("routes") or []:
            out_edges.setdefault(route.get("src_name"), set()).add(
                route.get("tgt_name"))

        surviving = {_identity(r) for r in awf.get("routes") or []}
        for route in wf.get("routes") or []:
            ident = _identity(route)
            if ident in surviving:
                continue
            path = f"{prefix}.routes[{ident}]"
            src, tgt = route.get("src_name"), route.get("tgt_name")

            # Attribute to the deleted endpoint, so acknowledging a DIFFERENT
            # deletion cannot forgive this edge.
            deleted = next((e for e in (src, tgt) if e in gone_steps), None)
            if deleted is not None:
                entailed[path] = RouteEntailment(
                    "deleted_step", f"{prefix}.steps[{deleted}]")
                continue

            via = _rerouted_through_new_steps(src, tgt, out_edges, added_steps)
            if via is not None:
                entailed[path] = RouteEntailment(
                    "rewired_by_insertion", f"{prefix}.steps[{via}]")
    return entailed


def _rerouted_through_new_steps(
    src: Any, tgt: Any, out_edges: dict[Any, set[Any]], added: set[Any]
) -> Any | None:
    """The first new step on a path `src -> ... -> tgt` made only of new steps.

    None when no such path exists -- meaning the edge was genuinely severed
    rather than rerouted, and stays a loss. Bounded by `added`, which is small;
    `seen` keeps a cyclic outgoing graph from looping.
    """
    if src is None or tgt is None or not added:
        return None
    seen: set[Any] = set()
    # (node, first added step used to get here)
    queue: list[tuple[Any, Any]] = [(src, None)]
    while queue:
        node, first = queue.pop()
        for nxt in out_edges.get(node, ()):  # noqa: SIM118
            if nxt == tgt:
                if first is not None:
                    return first
                continue  # a direct src->tgt edge is not a reroute
            if nxt in added and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, first if first is not None else nxt))
    return None


def _ack_matches(token: str, path: str) -> bool:
    """Does the caller's acknowledgement name this loss path?

    Exact paths are accepted (that is the documented remedy: echo `dropped`
    back), and so is the tail of one -- most usefully a bare step name. The
    caller thinks in the vocabulary of the playbook they are editing, not in
    the guard's internal path grammar, and requiring the latter turned the
    escape hatch into a second obstacle.
    """
    token = token.strip()
    if not token:
        return False
    return (token == path
            or path.endswith(f".{token}")
            or path.endswith(f"[{token}]"))


def check_prewrite(
    live_json: dict[str, Any] | None,
    outgoing_json: dict[str, Any],
    acknowledged: list[str] | None = None,
) -> PreWriteVerdict:
    """Decide whether this write may proceed.

    `live_json` is the current appliance state; pass `None` when there is
    nothing to overwrite (a create), which always passes -- a create cannot
    destroy anything.

    Every path in `acknowledged` is a drop the caller has explicitly asked for.
    Anything else that disappears refuses the write.
    """
    if live_json is None:
        return PreWriteVerdict(ok=True, message="create -- nothing to overwrite")

    try:
        # An UNEXPANDED pull is uncomparable, not empty. Without
        # `?$relationships=true` the appliance omits `workflows` entirely, and
        # every comparison below would read that absence as "the live
        # collection had nothing" -- so a write that deletes every workflow
        # comes back `ok=True, "no field loss"`. Verified against a live box,
        # both transports. The check lives HERE, not only at the call site,
        # because this is the safety-critical function: it must not depend on
        # every caller remembering a query parameter.
        require_expanded_collection(live_json)
        losses = diff_losses(live_json, outgoing_json)
        entailed = entailed_route_drops(live_json, outgoing_json)
    except UnexpandedRelationshipsError as exc:
        return PreWriteVerdict(
            ok=False,
            code="live_unreadable",
            message=(
                f"{exc} Re-read the collection with `?$relationships=true` and "
                "retry; refusing to overwrite a live playbook we could not read. "
                "Acknowledgements cannot clear this -- there is nothing to "
                "acknowledge until the live document can be read."
            ),
        )
    except Exception as exc:
        # Fail CLOSED. If we cannot establish that the write is safe, we have
        # not established that it is safe. A malformed live pull is exactly the
        # situation in which a blind overwrite does the most damage.
        return PreWriteVerdict(
            ok=False,
            code="live_unreadable",
            message=(
                f"pre-write safety check could not run ({type(exc).__name__}: {exc}); "
                "refusing the save rather than overwriting the live playbook unchecked"
            ),
        )

    tokens = [t for t in (acknowledged or []) if isinstance(t, str)]

    def _is_acked(path: str) -> bool:
        if any(_ack_matches(t, path) for t in tokens):
            return True
        why = entailed.get(path)
        if why is None:
            return False
        if why.kind == "rewired_by_insertion":
            # Nothing to acknowledge: the cause is an ADDITION, and additions
            # are never refused. Requiring an ack here would demand the caller
            # sign off on a deletion they did not make.
            return True
        # A route removed BY a step deletion is covered by acknowledging that
        # step -- the caller decided the deletion, not its arithmetic.
        return any(_ack_matches(t, why.cause) for t in tokens)

    # Entailed routes are never REPORTED either: naming a consequence next to
    # its cause reads as three separate things being destroyed, which is how a
    # one-step deletion came back looking like a partial document.
    reportable = [p for p in losses if p not in entailed]
    acked = [p for p in reportable if _is_acked(p)]
    unacked = [p for p in reportable if not _is_acked(p)]
    followed = [p for p in losses if p in entailed and _is_acked(p)]

    if not unacked:
        note = "no field loss" if not acked else f"{len(acked)} acknowledged drop(s)"
        if followed:
            note += f" (+{len(followed)} entailed route(s))"
        return PreWriteVerdict(
            ok=True, acknowledged=acked, entailed=followed, message=note)

    listed = "\n  - ".join(unacked[:20])
    more = f"\n  ... and {len(unacked) - 20} more" if len(unacked) > 20 else ""
    return PreWriteVerdict(
        ok=False,
        dropped=unacked,
        acknowledged=acked,
        entailed=followed,
        code="would_drop_fields",
        message=(
            f"refusing to save: {len(unacked)} field(s) present in the live playbook "
            f"are missing from what you are about to write:\n  - {listed}{more}\n"
            "If a deletion IS what was asked for, re-issue the save with those paths "
            "in `acknowledged_drops` -- a bare step name works too. Routes removed by "
            "a step's deletion are covered by naming that step. Otherwise re-read the "
            "live playbook and re-apply your edit on top of it -- do not write a "
            "partial document."
        ),
    )
