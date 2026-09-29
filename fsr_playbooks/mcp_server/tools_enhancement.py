"""verify_enhancement -- diff-aware pre-submit gate for enhance mode.

Sibling of `verify_playbook`. Same shape check (delegates to it), plus a
structural diff against `before_yaml` to flag regressions the build-mode
gate cannot see -- dropped steps, silently-renamed steps, stripped
annotations, behavior changes outside the user-requested edit.

Why this exists: a green compile is necessary but not sufficient in
enhance mode. A "tidy up" that drops an `annotations:` block or renames
a step (breaking external `vars.steps.<slug>.*` consumers) compiles
clean but is still a regression vs the prior YAML. See
`docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md` §C3.

Heuristic boundary: "the user didn't ask to touch this step" is fuzzy.
We start strict -- only literal step-name mentions in `user_message`
mark a step as fair game -- and rely on C4's enhance eval bucket to
tell us where to loosen.
"""
from __future__ import annotations

from typing import Any

from . import _verified_yaml
from ._shared import _err, get_grounded_yaml, get_turn_user_message, mcp
from .tools_verify import verify_playbook


def _parse(yaml_text: str):
    """Parse → IR. Returns (Collection | None, errors). Wraps the sys.path
    setup the verify path also does so this module can be called from the
    MCP entry point or from web tests interchangeably."""
    try:
        from fsr_playbooks.compiler import parse_yaml
    except ImportError as exc:
        return None, [{"code": "compiler_unavailable", "message": str(exc)}]
    coll, errs = parse_yaml(yaml_text)
    return coll, errs


# ---------------------------------------------------------------------------
# IR projection -- what counts as "the same step" for regression purposes.
# Text-diffing YAML would flag whitespace + key ordering; IR-diffing won't.
# ---------------------------------------------------------------------------

def _step_projection(s) -> dict[str, Any]:
    """Stable projection of a Step for behavior comparison. Excludes
    resolver-filled fields (uuids, handler) since those are derived."""
    return {
        "type": s.type,
        "arguments": s.arguments or {},
        "next": s.next,
        "branches": dict(s.branches or {}),
        "unlabeled_next": list(s.unlabeled_next or []),
        "for_each": s.for_each,
        "comment": s.comment,
    }


def _annotation_projection(a) -> dict[str, Any]:
    """Annotation comparison projection. Excludes `uuid` (emitter-filled)
    and `auto_for_step` (derived from step.comment round-trip)."""
    return {
        "kind": a.kind,
        "title": a.title,
        "body": a.body,
        "top": a.top,
        "left": a.left,
        "height": a.height,
        "width": a.width,
        "collapsed": a.collapsed,
        "hide_in_logs": a.hide_in_logs,
        "contains": list(a.contains or []),
    }


# ---------------------------------------------------------------------------
# "Did the user ask to touch this step?" -- strict by design.
# ---------------------------------------------------------------------------

def _user_referenced_steps(user_message: str | None,
                           step_names: list[str]) -> set[str] | None:
    """Return the set of step names the user explicitly named, or None
    if `user_message` is absent (eval harness, agent calling without
    chat context). None means: skip the `behavior_changed_outside_diff`
    flag -- we only emit the hard regressions."""
    if user_message is None:
        return None
    msg = user_message.lower()
    referenced: set[str] = set()
    for name in step_names:
        ln = (name or "").lower()
        if not ln:
            continue
        if ln in msg or ln.replace(" ", "_") in msg or ln.replace(" ", "-") in msg:
            referenced.add(name)
    # Type-aware expansion ("rename all decision steps") happens in
    # `_expand_by_type`, which needs the name→type map the caller owns.
    return referenced


_RENAME_VERBS = ("rename", "renaming", "re-name", "call it", "change the name",
                 "change its name", "name it")


def _asked_to_rename(user_message: str | None) -> bool:
    """Did the analyst ask for a rename in so many words?

    Deliberately literal, for the same reason `_user_referenced_steps` is:
    the exemption this feeds REMOVES a blocking regression, so a loose match
    would let a gratuitous rename through by accident. A rename nobody asked
    for is the failure mode; missing an unusual phrasing only costs a warning
    that reads as an error.
    """
    if not user_message:
        return False
    msg = user_message.lower()
    return any(v in msg for v in _RENAME_VERBS)


_DELETE_VERBS = ("delete", "remove", "drop the", "drop step", "get rid of",
                 "take out", "eliminate", "strip out", "no longer need")


def _asked_to_delete(user_message: str | None) -> bool:
    """Did the analyst ask for a deletion in so many words?

    The deletion twin of `_asked_to_rename`, and literal for the same reason:
    the exemption it feeds REMOVES a blocking regression, so a loose match
    would wave through a step the model dropped by accident -- which is the
    failure mode `step_dropped` exists to catch. Missing an unusual phrasing
    only costs a warning that reads as an error.

    Like the rename exemption this is ANDed with the step actually being named
    by the user, so "remove the IP from the block list" cannot exempt dropping
    a step nobody mentioned.
    """
    if not user_message:
        return False
    msg = user_message.lower()
    return any(v in msg for v in _DELETE_VERBS)


def _expand_by_type(referenced: set[str], user_message: str,
                    name_to_type: dict[str, str]) -> set[str]:
    msg = (user_message or "").lower()
    type_phrases = {
        "decision": ("decision",),
        "manual_input": ("manual input", "manual_input", "approval"),
        "set_variable": ("set variable", "set_variable", "set var"),
        "connector": ("connector step", "api call"),
        "find_record": ("find record", "find_record", "lookup record"),
        "update_record": ("update record", "update_record"),
        "create_record": ("create record", "create_record"),
        "delay": ("delay step",),
        "code_snippet": ("code snippet", "code_snippet", "python step"),
        "workflow_reference": ("workflow reference", "workflow_reference",
                               "sub-playbook", "subplaybook"),
    }
    out = set(referenced)
    for t, phrases in type_phrases.items():
        if any(p in msg for p in phrases):
            for n, st in name_to_type.items():
                if st == t:
                    out.add(n)
    return out


# ---------------------------------------------------------------------------
# Structural diff
# ---------------------------------------------------------------------------

def _diff_collections(before, after, user_message: str | None
                      ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare two IR Collections. Returns (regressions, diff_summary)."""
    regressions: list[dict[str, Any]] = []

    # Pair playbooks by name (FSR's stable identifier within a collection).
    before_pbs = {pb.name: pb for pb in before.playbooks}
    after_pbs = {pb.name: pb for pb in after.playbooks}

    steps_added: list[str] = []
    steps_removed: list[str] = []
    steps_modified: list[str] = []
    unchanged_count = 0
    # Per-step before/after payloads. The name lists above are a good index
    # but a bad explanation -- the card can only render "what changed" if the
    # projections survive the flattening.
    changes: list[dict[str, Any]] = []

    # Playbook-level diffs first.
    for name in before_pbs.keys() - after_pbs.keys():
        changes.append({
            "playbook": name,
            "step": None,
            "kind": "playbook_removed",
            "type": None,
            "before": {"steps": [(s.name or s.id)
                                 for s in before_pbs[name].steps]},
            "after": None,
            "changed_fields": [],
        })
        regressions.append({
            "kind": "playbook_dropped",
            "step": None,
            "before": name,
            "after": None,
            "severity": "error",
            "message": f"playbook {name!r} was present before and is now missing",
        })
    for name in after_pbs.keys() - before_pbs.keys():
        # Adding a playbook isn't a regression, so no regressions entry --
        # but its steps are the whole change, so they belong in the diff.
        changes.append({
            "playbook": name,
            "step": None,
            "kind": "playbook_added",
            "type": None,
            "before": None,
            "after": {"steps": [(s.name or s.id) for s in after_pbs[name].steps]},
            "changed_fields": [],
        })

    for pb_name in before_pbs.keys() & after_pbs.keys():
        bpb = before_pbs[pb_name]
        apb = after_pbs[pb_name]

        # Build name maps. We key by display `name` (the FSR-stable
        # human identifier) rather than `id` (the parser's local refname,
        # which the resolver may regenerate).
        b_steps = {(s.name or s.id): s for s in bpb.steps}
        a_steps = {(s.name or s.id): s for s in apb.steps}

        b_names = set(b_steps.keys())
        a_names = set(a_steps.keys())

        # name_to_type for the type-aware reference heuristic
        name_to_type = {n: s.type for n, s in b_steps.items()}
        name_to_type.update({n: s.type for n, s in a_steps.items()})

        referenced = _user_referenced_steps(user_message, list(b_names | a_names))
        if referenced is not None and user_message is not None:
            referenced = _expand_by_type(referenced, user_message, name_to_type)

        dropped = set(b_names - a_names)
        added = set(a_names - b_names)
        common = b_names & a_names

        # Pair silent renames FIRST so we don't also flag the same pair
        # as drop+add. A rename = same projection, different name.
        if dropped and added:
            for dn in list(dropped):
                dproj = _step_projection(b_steps[dn])
                for an in list(added):
                    if _step_projection(a_steps[an]) == dproj:
                        # A rename the analyst asked for BY NAME is not
                        # silent, and blocking it told them their own
                        # request was a regression -- `ready_to_push` went
                        # false and the enhancement card said so. The
                        # consequence is still real and still surfaced; it
                        # just stops being a blocker. The exemption is the
                        # same `referenced` set `behavior_changed_outside_
                        # diff` already uses, narrowed by an explicit
                        # rename verb so an unrequested rename cannot
                        # inherit it from a step merely being mentioned.
                        requested = (referenced is not None
                                     and dn in referenced
                                     and _asked_to_rename(user_message))
                        regressions.append({
                            "kind": ("step_renamed_as_requested" if requested
                                     else "step_renamed_silently"),
                            "step": dn,
                            "before": dn,
                            "after": an,
                            "severity": "warning" if requested else "error",
                            "message": (
                                f"step renamed {dn!r} → {an!r} as requested; "
                                "external vars.steps.<slug>.* consumers that "
                                "referenced the old name will need updating"
                                if requested else
                                f"step renamed {dn!r} → {an!r}; "
                                "breaks external vars.steps.<slug>.* "
                                "consumers -- confirm with the user"),
                        })
                        changes.append({
                            "playbook": pb_name,
                            "step": dn,
                            "kind": "renamed",
                            "type": b_steps[dn].type,
                            "before": {"name": dn},
                            "after": {"name": an},
                            "changed_fields": ["name"],
                        })
                        dropped.discard(dn)
                        added.discard(an)
                        break

        for n in dropped:
            steps_removed.append(n)
            changes.append({
                "playbook": pb_name,
                "step": n,
                "kind": "removed",
                "type": b_steps[n].type,
                "before": _step_projection(b_steps[n]),
                "after": None,
                "changed_fields": [],
            })
            # A deletion the analyst asked for BY NAME is not a regression --
            # it is the edit. Blocking it told them their own request was an
            # error: live probe A3 ("delete the 'Dead End' step") came back
            # ok=False with EVERY check green (compile clean, typed_walk clean,
            # schema clean) and this the only finding, so the model narrated a
            # refusal and asked how to proceed instead of delivering. The edit
            # only reached the box because the connector's salvage fabricated a
            # patch_proposal around the failed verification.
            #
            # This is the same exemption `step_renamed_as_requested` already
            # had, and the same one the `behavior_changed_outside_diff` branch
            # below applies -- three sibling branches, two intent-aware and this
            # one left behind. The consequence is still surfaced (in
            # `diff_summary.steps_removed`, in `changes`, and as a warning
            # here); it just stops being a blocker.
            #
            # The write itself is still guarded: `prewrite.check_prewrite`
            # refuses a save that drops a step unless the caller acknowledges
            # it. That gate is fail-closed AND has an acknowledgement path.
            # This one had neither, so two fail-closed gates in series with no
            # way through made a deletion impossible to perform at all.
            requested = (referenced is not None
                         and n in referenced
                         and _asked_to_delete(user_message))
            regressions.append({
                "kind": ("step_deleted_as_requested" if requested
                         else "step_dropped"),
                "step": n,
                "before": b_steps[n].type,
                "after": None,
                "severity": "warning" if requested else "error",
                "message": (
                    f"step {n!r} (type={b_steps[n].type}) deleted as requested; "
                    "anything referencing vars.steps.<slug>.* from it will "
                    "need updating"
                    if requested else
                    f"step {n!r} (type={b_steps[n].type}) was present "
                    "before and is now missing"),
            })

        for n in added:
            steps_added.append(n)
            changes.append({
                "playbook": pb_name,
                "step": n,
                "kind": "added",
                "type": a_steps[n].type,
                "before": None,
                "after": _step_projection(a_steps[n]),
                "changed_fields": [],
            })

        for n in common:
            b_proj = _step_projection(b_steps[n])
            a_proj = _step_projection(a_steps[n])
            if b_proj == a_proj:
                unchanged_count += 1
                continue
            steps_modified.append(n)
            changes.append({
                "playbook": pb_name,
                "step": n,
                "kind": "modified",
                "type": a_steps[n].type,
                "before": b_proj,
                "after": a_proj,
                "changed_fields": sorted(
                    k for k in b_proj if b_proj[k] != a_proj.get(k)
                ),
            })
            # Only flag as a regression if the user didn't explicitly
            # name this step. When referenced is None we skip the flag
            # (no user_message context) but still report it in
            # diff_summary.
            if referenced is not None and n not in referenced:
                regressions.append({
                    "kind": "behavior_changed_outside_diff",
                    "step": n,
                    "before": b_proj,
                    "after": a_proj,
                    "severity": "warning",
                    "message": (f"step {n!r} changed but was not referenced "
                                "in the user's message; confirm this was "
                                "intended"),
                })

        # Annotation-level diffs. Key by Annotation.id (the slug).
        b_anns = {a.id: a for a in bpb.annotations}
        a_anns = {a.id: a for a in apb.annotations}
        for aid in b_anns.keys() - a_anns.keys():
            regressions.append({
                "kind": "annotation_stripped",
                "step": None,
                "before": _annotation_projection(b_anns[aid]),
                "after": None,
                "severity": "warning",
                "message": (f"annotation {aid!r} ({b_anns[aid].kind}) was "
                            "present before and is now missing"),
            })
        for aid in b_anns.keys() & a_anns.keys():
            bp = _annotation_projection(b_anns[aid])
            ap = _annotation_projection(a_anns[aid])
            if bp == ap:
                continue
            # UI-metadata-only diffs are a softer regression than full
            # body/title changes.
            ui_keys = {"top", "left", "height", "width", "collapsed"}
            differing = {k for k in bp if bp[k] != ap[k]}
            if differing and differing <= ui_keys:
                regressions.append({
                    "kind": "ui_metadata_lost",
                    "step": None,
                    "before": {k: bp[k] for k in differing},
                    "after": {k: ap[k] for k in differing},
                    "severity": "warning",
                    "message": (f"annotation {aid!r} UI metadata changed "
                                f"({sorted(differing)}); confirm this was "
                                "intended"),
                })
            else:
                regressions.append({
                    "kind": "annotation_modified",
                    "step": None,
                    "before": bp,
                    "after": ap,
                    "severity": "warning",
                    "message": f"annotation {aid!r} body/title changed",
                })

    diff_summary = {
        "steps_added": steps_added,
        "steps_removed": steps_removed,
        "steps_modified": steps_modified,
        "unchanged": unchanged_count,
        "changes": changes,
    }
    return regressions, diff_summary


# ---------------------------------------------------------------------------
# Tool entry point
# ---------------------------------------------------------------------------

@mcp.tool()
def verify_enhancement(
    before_yaml: str | None = None,
    after_yaml: str | None = None,
    user_message: str | None = None,
    live_probe: bool = False,
) -> dict[str, Any]:
    """The pre-submit gate for a WHOLESALE rewrite of the open playbook -- run
    this before `emit_card(card_type='enhancement_offer', ...)`. For a targeted
    edit (add/change/remove/re-route a few steps) use `edit_playbook` instead:
    it applies the change to the open playbook itself, so you never re-type the
    document. Authoring a NEW playbook from scratch has no open playbook: gate
    that with `verify_playbook` instead.

    Leave `before_yaml` out -- it defaults to the open playbook as read from
    FortiSOAR. Copying the open playbook into the call is how steps and links go
    missing. Pass only `after_yaml`, your complete revised playbook.

    Runs `verify_playbook(after_yaml)` for the shape check, then
    structurally diffs `before_yaml` vs `after_yaml` and reports
    regressions the build-mode gate cannot see.

    Args:
      before_yaml: omit it. Defaults to the open playbook; pass it only when
        verifying against some other baseline.
      after_yaml: the proposed edited YAML (required).
      user_message: the chat turn that asked for the edit. Used to mark
        which steps were "fair game" to touch -- steps changed outside
        the user's named scope fire a `behavior_changed_outside_diff`
        warning. Pass None to skip that heuristic (still emits hard
        regressions: dropped steps, renamed steps, stripped annotations).
      live_probe: forwarded to verify_playbook.

    Returns the verify_playbook contract plus:
      - regressions: [{kind, step, before, after, severity, message}]
      - diff_summary: {steps_added, steps_removed, steps_modified, unchanged,
                       changes}. The first four are name lists / a count --
                       an index. `changes` is the explanation: one entry per
                       changed step, {playbook, step, kind, type, before,
                       after, changed_fields}, where before/after are the IR
                       step projections. `kind` is one of added | removed |
                       modified | renamed | playbook_added | playbook_removed.

    `ready_to_push` is False if verify_playbook would block OR if any
    regression has severity='error'. Warning-severity regressions
    surface but do not block.

    Regression kinds:
      - playbook_dropped       (error)
      - step_dropped           (error) -- a step vanished and nobody asked
      - step_deleted_as_requested (warning) -- the same disappearance, when the
                                          analyst named that step AND used a
                                          delete verb. Their own request must
                                          not come back as a blocker. The save
                                          is still guarded: `check_prewrite`
                                          refuses a drop unless the caller
                                          acknowledges it, and unlike this gate
                                          it HAS an acknowledgement path.
      - step_renamed_silently  (error) -- same shape, new name; breaks
                                          external vars.steps.<slug>.* refs
      - step_renamed_as_requested (warning) -- the same rename, when the
                                          analyst named that step AND used a
                                          rename verb. Their own request must
                                          not come back as a blocker; the
                                          broken-consumer consequence still
                                          surfaces, it just does not stop
                                          `ready_to_push`.
      - annotation_stripped    (warning)
      - annotation_modified    (warning)
      - ui_metadata_lost       (warning)
      - behavior_changed_outside_diff (warning) -- only when user_message given

    When the verdict passes, the result also carries **`verified_id`** -- an
    opaque handle to the exact `after_yaml` bytes that just cleared the gate.
    Pass it to `emit_card(card_type='enhancement_offer', payload={verified_id: ..., summary: ...})` to apply the edit. That
    tool takes no YAML, so the document you verified is the document that
    lands; re-typing the playbook into chat instead is the one way to lose the
    edit (see `_verified_yaml` for the live failure this closes).
    """
    # DERIVE the intent when the model did not declare it. `user_message` is an
    # optional argument, and live on 8.0 the box model called this tool with
    # only `before_yaml` and `after_yaml` -- so `referenced` was None and EVERY
    # intent-aware exemption below (requested rename, requested deletion,
    # behavior_changed_outside_diff) was unreachable. The analyst had typed
    # "Delete the step named 'Dead End'"; the gate simply never saw it, called
    # their deletion an error, and the model dutifully refused its own edit.
    #
    # Same lesson as tracker #60 (`requested_by`: declared on 0 of 4 live
    # calls): derive intent from the analyst's own words, never depend on the
    # model to pass it along. The chat loop binds them for the turn; an
    # explicitly passed `user_message` still wins, so eval harnesses and direct
    # agent calls are unchanged.
    if user_message is None:
        user_message = get_turn_user_message()

    # The baseline is the open playbook, read from FortiSOAR -- never a copy the
    # model typed. Same pattern as analyze_playbook's empty `yaml_text`.
    if not (isinstance(before_yaml, str) and before_yaml.strip()):
        before_yaml = get_grounded_yaml()
        if not before_yaml:
            return _err(
                "no_open_playbook",
                "there is no open playbook to compare against. For a NEW "
                "playbook use verify_playbook; to verify against a specific "
                "baseline pass before_yaml.")
    if not (isinstance(after_yaml, str) and after_yaml.strip()):
        return _err("missing_field",
                    "after_yaml is required: the complete revised playbook. "
                    "For a targeted edit use edit_playbook(operations=[...]).")

    # 1. Shape check on the after YAML.
    after_result = _grandfather_orphans(
        verify_playbook(after_yaml, live_probe=live_probe), before_yaml)

    # 2. Parse both for the diff.
    before_coll, before_errs = _parse(before_yaml)
    after_coll, after_errs = _parse(after_yaml)

    if before_coll is None:
        # Before YAML is unparseable -- we cannot diff. Surface this as
        # an evidence note, return the verify_playbook result unchanged
        # with empty diff fields. Better than refusing the call.
        out = dict(after_result)
        out["regressions"] = []
        out["diff_summary"] = {"steps_added": [], "steps_removed": [],
                               "steps_modified": [], "unchanged": 0,
                               "changes": []}
        out.setdefault("evidence", {})["before_unparseable"] = {
            "errors": before_errs,
            "note": ("before_yaml did not parse -- skipping regression diff; "
                     "treating this as a build-mode verify of after_yaml only"),
        }
        return _issue_verified_id(out, after_yaml, before_yaml)

    if after_coll is None:
        # After is broken at parse time. verify_playbook already captured
        # that in required_fixes; nothing to diff against.
        out = dict(after_result)
        out["regressions"] = []
        out["diff_summary"] = {"steps_added": [], "steps_removed": [],
                               "steps_modified": [], "unchanged": 0,
                               "changes": []}
        return _issue_verified_id(out, after_yaml, before_yaml)

    # 3. Diff.
    regressions, diff_summary = _diff_collections(
        before_coll, after_coll, user_message
    )

    # 4. Merge into the verify_playbook envelope.
    out = dict(after_result)
    out["regressions"] = regressions
    out["diff_summary"] = diff_summary

    # ready_to_push downgrades only on error-severity regressions.
    if any(r.get("severity") == "error" for r in regressions):
        out["ready_to_push"] = False
        out["ok"] = False
        # Surface a next-action hint so the agent's first move is obvious.
        next_actions = list(out.get("next_actions") or [])
        first_err = next(r for r in regressions if r.get("severity") == "error")
        next_actions.insert(
            0, f"{first_err['kind']}: {first_err.get('message', '')[:120]}"
        )
        out["next_actions"] = next_actions[:5]

    return _issue_verified_id(out, after_yaml, before_yaml)


def _grandfather_orphans(result: dict[str, Any],
                         before_yaml: str) -> dict[str, Any]:
    """An orphan step the analyst's playbook ALREADY had is theirs, not the
    edit's: keep it visible as a warning instead of blocking an unrelated
    change. Only orphans the edit introduced stay required fixes -- that is the
    dropped-link failure `unreachable_step` exists to catch."""
    orphans = [f for f in result.get("required_fixes") or []
               if f.get("code") == "unreachable_step"]
    if not orphans:
        return result
    from fsr_playbooks.compiler import compile_yaml

    from ._shared import DB_PATH
    try:
        before = compile_yaml(before_yaml, DB_PATH)
    except Exception:  # noqa: BLE001 -- no baseline means nothing to excuse
        return result
    already = {e.message for e in before.errors
               if e.code.value == "unreachable_step"}
    keep = [f for f in result["required_fixes"]
            if f.get("code") != "unreachable_step" or f.get("message") not in already]
    if len(keep) == len(result["required_fixes"]):
        return result
    moved = [dict(f, severity="warning", pre_existing=True)
             for f in result["required_fixes"] if f not in keep]
    out = dict(result)
    out["required_fixes"] = keep
    out["warnings"] = list(result.get("warnings") or []) + moved
    out["ok"] = out["ready_to_push"] = not keep
    out["next_actions"] = [a for a in result.get("next_actions") or []
                           if not (a.startswith("unreachable_step:")
                                   and not any(f.get("code") == "unreachable_step"
                                               for f in keep))]
    return out


def _issue_verified_id(out: dict[str, Any], after_yaml: str,
                       before_yaml: str) -> dict[str, Any]:
    """Bind the verdict to the bytes it blessed, on the way out.

    Only a PASSING verdict gets a handle: `verified_id` is a claim that these
    exact bytes cleared the gate, so minting one for a failing verify would let
    `emit_card(card_type='enhancement_offer')` apply a document the gate rejected. On a failure we
    instead say -- in the envelope the model actually reads -- that the next move
    is to fix and re-verify, not to paste YAML into chat. The live regression
    was a model that treated a green verify as permission to free-hand the
    document; the symmetric risk is treating a red one as advisory.
    """
    if not out.get("ready_to_push"):
        out["verified_id"] = None
        out["how_to_apply"] = (
            "NOT ready. Fix the required_fixes/regressions above and call "
            "verify_enhancement again. Do not present this YAML as final and "
            "do not ask the analyst to apply it by hand."
        )
        return out

    # Deletions this gate judged INTENTIONAL, carried forward so the write can
    # acknowledge them. `check_prewrite` fails closed on a vanished step unless
    # the caller names it in `acknowledged_drops` -- correctly, that is the last
    # protection against a model silently eating a playbook. But the enhancement
    # -offer accept path had no way to name anything, so once verification
    # stopped blocking a requested deletion the write started blocking it
    # instead: live A3 came back "would_drop_fields ... steps[Dead End]".
    #
    # The acknowledgement is DERIVED from the verdict, never model-supplied.
    # `step_deleted_as_requested` is only emitted when the analyst named that
    # step AND used a delete verb, so this list is the set of drops a gate
    # already judged intentional -- the model cannot widen it by asking.
    out["acknowledged_drops"] = sorted(
        str(r.get("step")) for r in (out.get("regressions") or [])
        if r.get("kind") == "step_deleted_as_requested" and r.get("step")
    )

    out["verified_id"] = _verified_yaml.remember(
        after_yaml,
        before_fingerprint=_verified_yaml.fingerprint(before_yaml),
        diff_summary=out.get("diff_summary") or {},
        warnings=out.get("warnings") or [],
        acknowledged_drops=out["acknowledged_drops"],
    )
    # The COMPLETE payload, with the real id. This used to read
    # `payload={verified_id: ...}` -- no summary -- and models copied it
    # exactly: 4 of 10 refusals in one enhance-live run were `emit_card`
    # bouncing that very payload for a missing `summary`.
    out["how_to_apply"] = (
        "Call emit_card(card_type='enhancement_offer', payload={verified_id: "
        f"'{out['verified_id']}', summary: '<one or two plain-English lines on "
        "what this edit changes>'}) to apply this edit. That is the ONLY way "
        "the edit reaches the analyst's playbook. Do not re-type the YAML into "
        "your reply -- the offer card carries the exact text verified here."
    )
    return out


# ---------------------------------------------------------------------------
# edit_playbook -- targeted edits as OPERATIONS on the open playbook.
#
# Live: an agent re-typed a verified playbook to deliver an edit and dropped two
# `next:` links; the saved playbook ran only its first search. `verified_id`
# already stops a re-typed document from being DELIVERED, but every edit still
# made the model re-type the whole playbook to AUTHOR it (and, before
# `before_yaml` defaulted to the open playbook, re-type it twice). Here the
# model names only the change; the tool applies it to the open playbook with a
# round-trip YAML load, so every step it was not asked to touch -- links,
# uuids, layout, comments -- is carried over untouched by construction.
# ---------------------------------------------------------------------------

_EDIT_OPS = ("add_step", "update_step", "rename_step", "remove_step",
             "set_route", "remove_route")
# Step-level keys an update may not change: `name` has its own op because
# routes point at it; `uuid` ties the step to its live record.
_UPDATE_FORBIDDEN = frozenset({"name", "uuid"})
# Ops that reference an existing step by `name`.
_NAMED_OPS = frozenset({"update_step", "rename_step", "remove_step"})


class _EditError(Exception):
    pass


class _MissingStep(_EditError):
    """A reference to a step that is not in the playbook (yet) -- kept apart so
    an op naming a step a LATER op adds can wait for it (see edit_playbook)."""

    def __init__(self, ref: str, message: str):
        super().__init__(message)
        self.ref = ref


def _rt_yaml():
    from ruamel.yaml import YAML
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    return y


def _slug(name: str) -> str:
    from fsr_playbooks.compiler.parser import _slugify
    return _slugify(name)


def _refs(step) -> set[str]:
    """Every form a route may use to name this step (name or slug)."""
    name = str(step.get("name") or "")
    out = {name, _slug(name)}
    if step.get("id"):
        out.add(str(step["id"]))
    return {r for r in out if r}


def _route_slots(step):
    """(container, key) for every route out of a step: `next`, each
    decision condition / manual-input option `next`, and unlabeled fan-out."""
    slots = []
    if "next" in step:
        slots.append((step, "next"))
    for list_key in ("conditions", "options"):
        for entry in step.get(list_key) or []:
            if isinstance(entry, dict) and "next" in entry:
                slots.append((entry, "next"))
    fan = step.get("unlabeled_next")
    if isinstance(fan, list):
        slots.extend((fan, i) for i in range(len(fan)))
    return slots


def _find(steps, ref: Any):
    if not isinstance(ref, str) or not ref.strip():
        raise _EditError("a step reference must be the step's name")
    ref = ref.strip()
    for i, s in enumerate(steps):
        if ref in _refs(s):
            return i, s
    if not steps:
        # Live: every op anchored on "Start" in a playbook with no steps at all.
        raise _MissingStep(ref, (
            f"no step named {ref!r} -- the open playbook has no steps yet. Add "
            f"the start step first with no `after` "
            f"({{op: add_step, step: {{name: Start, type: start, ...}}}}), then "
            f"add each step `after` the one before it"))
    names = ", ".join(repr(str(s.get("name"))) for s in steps)
    raise _MissingStep(ref, f"no step named {ref!r} -- steps are: {names}")


def _branch_entry(step, option: str):
    for list_key in ("conditions", "options"):
        for entry in step.get(list_key) or []:
            if not isinstance(entry, dict):
                continue
            labels = {str(entry.get(k)) for k in ("display", "option", "label")
                      if entry.get(k) is not None}
            if option in labels or (option.lower() == "default" and entry.get("default")):
                return entry
    raise _EditError(f"step {step.get('name')!r} has no branch {option!r}")


# Canvas placement for added steps. A step with no `top`/`left` falls to the
# emitter's whole-graph auto-layout while every existing step keeps its saved
# spot, so the two grids collide (live: a spliced step landed off to the side
# and End sat above the steps now routed into it). Same strides as the emitter.
_ROW = 130


def _pos(step) -> tuple[int, int] | None:
    try:
        return int(step["top"]), int(step["left"])
    except (KeyError, TypeError, ValueError):
        return None


def _set_pos(step, top: int, left: int) -> None:
    step["top"], step["left"] = str(top), str(left)


def _downstream(steps, first) -> list:
    """Steps reachable from `first` (inclusive), following every route."""
    seen, out, todo = set(), [], [first]
    while todo:
        s = todo.pop()
        if id(s) in seen:
            continue
        seen.add(id(s))
        out.append(s)
        for box, key in _route_slots(s):
            ref = box[key]
            todo.extend(t for t in steps if isinstance(ref, str) and ref in _refs(t))
    return out


def _place_after(steps, prev, new) -> None:
    """Put `new` one row under `prev` and push what follows down a row, so the
    canvas reads in route order. No-op when `prev` has no saved position."""
    anchor = _pos(prev)
    if anchor is None or _pos(new) is not None:
        return
    top, left = anchor[0] + _ROW, anchor[1]
    below = [t for t in steps if t is not prev]
    nxt = new.get("next")
    first = next((t for t in below if isinstance(nxt, str) and nxt in _refs(t)), None)
    for t in _downstream(below, first) if first is not None else []:
        p = _pos(t)
        if p is not None and p[0] >= top:
            _set_pos(t, p[0] + _ROW, p[1])
    _set_pos(new, top, left)


def _place_below_all(steps, new) -> None:
    placed = [p for p in (_pos(s) for s in steps) if p is not None]
    if placed and _pos(new) is None:
        _set_pos(new, max(t for t, _ in placed) + _ROW, min(lf for _, lf in placed))


# Each op's shape, quoted in a refusal so the model can see which key it
# missed. Mirrors the edit_playbook docstring (the advertised contract).
_OP_SHAPES = {
    "add_step": "{op: add_step, step: {name, type, ...}, after: <step>, option: <branch>}",
    "update_step": "{op: update_step, name: <step>, set: {key or dotted.key: value}, unset: [key]}",
    "rename_step": "{op: rename_step, name: <current name>, to: <new name>}",
    "remove_step": "{op: remove_step, name: <step>, reconnect: true}",
    "set_route": "{op: set_route, from: <step>, to: <step>, option: <branch>}",
    "remove_route": "{op: remove_route, from: <step>, option: <branch>}",
}


def _normalize_op(op: dict) -> dict:
    """Canonical `{op: <kind>, ...}` from the two unambiguous shapes models
    send instead: the op name as the key (`{add_step: {...}}`, seen live), and
    add_step with the step's keys inline beside `after` rather than under
    `step`. Anything else passes through for `_apply_op` to refuse."""
    if "op" not in op and len(op) == 1:
        (kind, body), = op.items()
        if kind in _EDIT_OPS and isinstance(body, dict):
            op = {"op": kind, **body}
    if (op.get("op") in _NAMED_OPS and "name" not in op
            and isinstance(op.get("step"), str)):
        # `step: <name>` names the step as plainly as `name:` (live: A5's first
        # update_step was refused for it). add_step's `step` is the new step's
        # body, a mapping, so it never matches here.
        op = {**{k: v for k, v in op.items() if k != "step"}, "name": op["step"]}
    if (op.get("op") == "rename_step" and "name" not in op
            and isinstance(op.get("from"), str)):
        # `{from, to}` reads naturally for a rename and is unambiguous here
        # (live: 3 of 10 refusals in one enhance-live run, 2 of them stuck).
        op = {**{k: v for k, v in op.items() if k != "from"}, "name": op["from"]}
    if op.get("op") == "add_step" and "step" not in op and op.get("name"):
        step = {k: v for k, v in op.items() if k not in ("op", "after")}
        op = {"op": "add_step", "step": step,
              **({"after": op["after"]} if "after" in op else {})}
    return op


def _set_path(step, key: str, value) -> None:
    """`params.ip_addresses` sets ONE leaf inside `params`, keeping its
    siblings. Live (effect probe A5): the key was written literally, as a
    sibling `params.ip_addresses:` beside the untouched `params`, verify passed
    it, and the offer would have "applied" with the old IP still in place.
    No step or param key contains a dot, so the path is unambiguous."""
    from ruamel.yaml.comments import CommentedMap
    *parents, leaf = key.split(".")
    box = step
    for i, part in enumerate(parents):
        nxt = box.get(part)
        if nxt is None:
            nxt = box[part] = CommentedMap()
        elif not isinstance(nxt, dict):
            raise _EditError(f"set {key!r}: {'.'.join(parents[:i + 1])!r} is "
                             f"{type(nxt).__name__}, not a mapping")
        box = nxt
    box[leaf] = value


def _unset_path(step, key: str) -> None:
    *parents, leaf = key.split(".")
    box = step
    for part in parents:
        box = box.get(part) if isinstance(box, dict) else None
        if not isinstance(box, dict):
            return
    box.pop(leaf, None)


def _apply_op(steps, op: dict) -> str:
    op = _normalize_op(op)
    kind = op.get("op")
    if kind == "add_step":
        new = op.get("step")
        if not (isinstance(new, dict) and new.get("name") and new.get("type")):
            raise _EditError("add_step needs step={name, type, ...}")
        if any(str(new["name"]) in _refs(s) or _slug(str(new["name"])) in _refs(s)
               for s in steps):
            raise _EditError(f"a step named {new['name']!r} already exists")
        from ruamel.yaml.comments import CommentedMap
        new = CommentedMap(new)
        after = op.get("after")
        if after is None:
            _place_below_all(steps, new)
            steps.append(new)
            return f"added {new['name']!r} (unrouted -- route to it with set_route)"
        i, prev = _find(steps, after)
        if any(k in prev for k in ("conditions", "options")) and "next" not in prev:
            # A branching step (decision / manual_input): splice into ONE branch.
            # Live: `after` a manual_input with a single "Continue" button was
            # refused five times; with one branch there is nothing to choose.
            entries = [e for lk in ("conditions", "options")
                       for e in (prev.get(lk) or []) if isinstance(e, dict)]
            option = op.get("option")
            if option is not None:
                entry = _branch_entry(prev, str(option))
            elif len(entries) == 1:
                entry = entries[0]
            else:
                labels = [str(e.get("display") or e.get("option") or e.get("label")
                              or ("default" if e.get("default") else "?"))
                          for e in entries]
                raise _EditError(
                    f"{prev.get('name')!r} branches {labels}; name the branch to "
                    f"insert into with option=<label>")
            if entry.get("next") and "next" not in new:
                new["next"] = entry["next"]
            entry["next"] = str(new["name"])
            _place_after(steps, prev, new)
            steps.insert(i + 1, new)
            label = entry.get("display") or entry.get("option") or entry.get("label")
            return f"added {new['name']!r} after {prev.get('name')!r} [{label}]"
        # Splice into the chain: prev -> new -> whatever prev pointed at.
        if prev.get("next") and "next" not in new:
            new["next"] = prev["next"]
        prev["next"] = str(new["name"])
        _place_after(steps, prev, new)
        steps.insert(i + 1, new)
        return f"added {new['name']!r} after {prev.get('name')!r}"

    if kind == "update_step":
        _, step = _find(steps, op.get("name"))
        sets = op.get("set") or {}
        unset = op.get("unset") or []
        if not isinstance(sets, dict) or not isinstance(unset, list):
            raise _EditError("update_step takes set={key: value} and unset=[key]")
        bad = sorted(_UPDATE_FORBIDDEN & {str(k).split(".")[0]
                                          for k in (*sets, *unset)})
        if bad:
            raise _EditError(f"update_step cannot change {bad}; use rename_step "
                             f"to rename")
        if not sets and not unset:
            raise _EditError("update_step with nothing to set or unset")
        for k, v in sets.items():
            _set_path(step, str(k), v)
        for k in unset:
            _unset_path(step, str(k))
        return f"updated {step.get('name')!r}: {sorted(set(sets) | set(unset))}"

    if kind == "rename_step":
        _, step = _find(steps, op.get("name"))
        to = op.get("to")
        if not isinstance(to, str) or not to.strip():
            raise _EditError("rename_step needs to=<new name>")
        old_refs = _refs(step)
        step["name"] = to.strip()
        for s in steps:
            for box, key in _route_slots(s):
                if str(box[key]) in old_refs:
                    box[key] = to.strip()
        return f"renamed {sorted(old_refs)[0]!r} to {to.strip()!r} (routes updated)"

    if kind == "remove_step":
        i, step = _find(steps, op.get("name"))
        old_refs = _refs(step)
        successor = step.get("next") if op.get("reconnect", True) else None
        for s in steps:
            if s is step:
                continue
            fan = s.get("unlabeled_next")
            if isinstance(fan, list):
                kept = [successor if str(r) in old_refs else r for r in fan]
                fan[:] = [r for r in kept if r]
            for box, key in _route_slots(s):
                if isinstance(box, list) or str(box[key]) not in old_refs:
                    continue
                if successor:
                    box[key] = successor
                else:
                    box.pop(key)
        steps.pop(i)
        return (f"removed {step.get('name')!r}"
                + (f"; its predecessors now route to {successor!r}" if successor else ""))

    if kind == "set_route":
        _, src = _find(steps, op.get("from"))
        _, dst = _find(steps, op.get("to"))
        option = op.get("option")
        if option:
            _branch_entry(src, str(option))["next"] = str(dst["name"])
            return f"routed {src.get('name')!r} [{option}] -> {dst.get('name')!r}"
        if any(k in src for k in ("conditions", "options")):
            raise _EditError(f"{src.get('name')!r} branches; name the option= "
                             f"to route")
        src["next"] = str(dst["name"])
        return f"routed {src.get('name')!r} -> {dst.get('name')!r}"

    if kind == "remove_route":
        _, src = _find(steps, op.get("from"))
        option = op.get("option")
        box = _branch_entry(src, str(option)) if option else src
        if "next" not in box:
            raise _EditError(f"{src.get('name')!r} has no route to remove")
        box.pop("next")
        return f"removed route out of {src.get('name')!r}" + (f" [{option}]" if option else "")

    raise _EditError(f"unknown op {kind!r}; each operation is "
                     f"{{op: <kind>, ...}} with kind one of {list(_EDIT_OPS)}")


@mcp.tool()
def edit_playbook(
    operations: list[dict[str, Any]],
    playbook: str | None = None,
    user_message: str | None = None,
) -> dict[str, Any]:
    """EDIT the playbook the analyst has open -- the default way to change it.
    Name only the change; this applies it to the open playbook (read from
    FortiSOAR), verifies the result like `verify_enhancement`, and on a pass
    returns a `verified_id`. Deliver it with
    `emit_card(card_type='enhancement_offer', payload={verified_id: ..., summary: ...})`.
    You never re-type the playbook, so no step or link you did not name can go
    missing. Each call applies to the open playbook as it is, so on a failed
    verify fix the operations and send the WHOLE list again.

    `operations` is applied in order, all or nothing. Steps are named by their
    `name:`. An op may name a step a later op in the list adds. Each is an object with an `op`:
      - {op: add_step, step: {name, type, ...step keys}, after: <step>, option: <branch>}
          inserts after <step> and splices it into that step's `next` chain;
          after a decision / manual_input, `option` names the branch to splice
          into (not needed when it has one). Omit `after` to add it unrouted
          (then use set_route) -- the way to add the start step to an empty
          playbook.
      - {op: update_step, name: <step>, set: {key: value}, unset: [key]}
          changes step keys (params, vars, next, conditions, ...). A dotted
          key sets one leaf and keeps its siblings:
          set: {"params.ip_addresses": "1.2.3.4"} changes only that param;
          set: {params: {...}} REPLACES the whole params mapping.
      - {op: rename_step, name: <step>, to: <new name>}  -- routes follow.
      - {op: remove_step, name: <step>, reconnect: true}
          routes into it are re-pointed at its `next` (reconnect=false drops them).
      - {op: set_route, from: <step>, to: <step>, option: <branch label>}
          `option` for a decision condition / manual-input option; omit for `next`.
      - {op: remove_route, from: <step>, option: <branch label>}

    `playbook`: which playbook, when the open collection holds several.
    Returns the verify_enhancement envelope plus `applied` (one line per op) and
    `after_yaml`; on a bad operation, {ok: false, code: "bad_operation",
    operation_index, message} and nothing is applied.
    """
    import io
    import json

    before = get_grounded_yaml()
    if not before:
        return _err("no_open_playbook",
                    "no playbook is open to edit. For a NEW playbook author the "
                    "YAML and use verify_playbook.")
    if isinstance(operations, str):
        try:
            operations = json.loads(operations)
        except ValueError:
            return _err("bad_operation", "operations must be a list of objects")
    if isinstance(operations, dict):
        operations = [operations]
    if not isinstance(operations, list) or not operations:
        return _err("bad_operation", "operations must be a non-empty list")

    y = _rt_yaml()
    try:
        doc = y.load(before)
    except Exception as exc:  # noqa: BLE001
        return _err("open_playbook_unreadable", f"could not read the open playbook: {exc}")
    pbs = (doc or {}).get("playbooks") if isinstance(doc, dict) else None
    if not isinstance(pbs, list) or not pbs:
        return _err("open_playbook_unreadable", "the open playbook has no playbooks: list")
    if playbook:
        target = next((p for p in pbs if str(p.get("name")) == playbook), None)
        if target is None:
            return _err("bad_operation", f"no playbook named {playbook!r} is open",
                        suggestions=[str(p.get("name")) for p in pbs])
    elif len(pbs) == 1:
        target = pbs[0]
    else:
        return _err("bad_operation", "the open collection has several playbooks; "
                    "name one with playbook=",
                    suggestions=[str(p.get("name")) for p in pbs])
    steps = target.get("steps")
    if not isinstance(steps, list):
        return _err("open_playbook_unreadable", "the open playbook has no steps: list")

    def _added_name(o: Any) -> str | None:
        if not isinstance(o, dict):
            return None
        n = _normalize_op(o)
        st = n.get("step") if n.get("op") == "add_step" else None
        return str(st["name"]) if isinstance(st, dict) and st.get("name") else None

    def _refused(i: int, op: Any, exc: Exception) -> dict[str, Any]:
        kind = _normalize_op(op).get("op")
        shape = _OP_SHAPES.get(kind)
        sent = sorted(k for k in op if k != "op") if isinstance(op, dict) else []
        return _err("bad_operation",
                    f"operations[{i}] ({kind}): {exc}"
                    + (f" -- expected {shape}; got keys {sent}" if shape else ""),
                    operation_index=i,
                    suggestions=["nothing was applied -- fix this operation "
                                 "and send the whole list again"])

    # An op may name a step a LATER op in the same list adds (live: set_route to
    # "Create ServiceNow incident" listed before the add_step that creates it).
    # Such an op waits until the rest has run, then applies in order.
    applied: list[str] = []
    deferred: list[tuple[int, dict]] = []
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            return _err("bad_operation", f"operations[{i}] is not an object",
                        operation_index=i)
        try:
            applied.append(_apply_op(steps, op))
        except _MissingStep as exc:
            later = {_added_name(o) for o in operations[i + 1:]}
            if exc.ref in later or _slug(exc.ref) in {_slug(n) for n in later if n}:
                deferred.append((i, op))
                continue
            return _refused(i, op, exc)
        except _EditError as exc:
            return _refused(i, op, exc)
    for i, op in deferred:
        try:
            applied.append(_apply_op(steps, op))
        except _EditError as exc:
            return _refused(i, op, exc)

    buf = io.StringIO()
    y.dump(doc, buf)
    after = buf.getvalue()
    out = verify_enhancement(before_yaml=before, after_yaml=after,
                             user_message=user_message)
    out = dict(out)
    out["applied"] = applied
    out["after_yaml"] = after
    return out
