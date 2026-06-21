"""verify_enhancement — diff-aware pre-submit gate for enhance mode.

Sibling of `verify_playbook`. Same shape check (delegates to it), plus a
structural diff against `before_yaml` to flag regressions the build-mode
gate cannot see — dropped steps, silently-renamed steps, stripped
annotations, behavior changes outside the user-requested edit.

Why this exists: a green compile is necessary but not sufficient in
enhance mode. A "tidy up" that drops an `annotations:` block or renames
a step (breaking external `vars.steps.<slug>.*` consumers) compiles
clean but is still a regression vs the prior YAML. See
`docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md` §C3.

Heuristic boundary: "the user didn't ask to touch this step" is fuzzy.
We start strict — only literal step-name mentions in `user_message`
mark a step as fair game — and rely on C4's enhance eval bucket to
tell us where to loosen.
"""
from __future__ import annotations

from typing import Any

from ._shared import mcp
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
# IR projection — what counts as "the same step" for regression purposes.
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
# "Did the user ask to touch this step?" — strict by design.
# ---------------------------------------------------------------------------

def _user_referenced_steps(user_message: str | None,
                           step_names: list[str]) -> set[str] | None:
    """Return the set of step names the user explicitly named, or None
    if `user_message` is absent (eval harness, agent calling without
    chat context). None means: skip the `behavior_changed_outside_diff`
    flag — we only emit the hard regressions."""
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

    # Playbook-level diffs first.
    for name in before_pbs.keys() - after_pbs.keys():
        regressions.append({
            "kind": "playbook_dropped",
            "step": None,
            "before": name,
            "after": None,
            "severity": "error",
            "message": f"playbook {name!r} was present before and is now missing",
        })
    for name in after_pbs.keys() - before_pbs.keys():
        # Adding a playbook isn't a regression; surface in diff_summary
        # but no regressions entry.
        pass

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
                        regressions.append({
                            "kind": "step_renamed_silently",
                            "step": dn,
                            "before": dn,
                            "after": an,
                            "severity": "error",
                            "message": (f"step renamed {dn!r} → {an!r}; "
                                        "breaks external vars.steps.<slug>.* "
                                        "consumers — confirm with the user"),
                        })
                        dropped.discard(dn)
                        added.discard(an)
                        break

        for n in dropped:
            steps_removed.append(n)
            regressions.append({
                "kind": "step_dropped",
                "step": n,
                "before": b_steps[n].type,
                "after": None,
                "severity": "error",
                "message": (f"step {n!r} (type={b_steps[n].type}) was present "
                            "before and is now missing"),
            })

        for n in added:
            steps_added.append(n)

        for n in common:
            b_proj = _step_projection(b_steps[n])
            a_proj = _step_projection(a_steps[n])
            if b_proj == a_proj:
                unchanged_count += 1
                continue
            steps_modified.append(n)
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
    }
    return regressions, diff_summary


# ---------------------------------------------------------------------------
# Tool entry point
# ---------------------------------------------------------------------------

@mcp.tool()
def verify_enhancement(
    before_yaml: str,
    after_yaml: str,
    user_message: str | None = None,
    live_probe: bool = False,
) -> dict[str, Any]:
    """Diff-aware pre-submit gate for enhance mode.

    Runs `verify_playbook(after_yaml)` for the shape check, then
    structurally diffs `before_yaml` vs `after_yaml` and reports
    regressions the build-mode gate cannot see.

    Args:
      before_yaml: the playbook YAML the user started with.
      after_yaml: the proposed edited YAML.
      user_message: the chat turn that asked for the edit. Used to mark
        which steps were "fair game" to touch — steps changed outside
        the user's named scope fire a `behavior_changed_outside_diff`
        warning. Pass None to skip that heuristic (still emits hard
        regressions: dropped steps, renamed steps, stripped annotations).
      live_probe: forwarded to verify_playbook.

    Returns the verify_playbook contract plus:
      - regressions: [{kind, step, before, after, severity, message}]
      - diff_summary: {steps_added, steps_removed, steps_modified, unchanged}

    `ready_to_push` is False if verify_playbook would block OR if any
    regression has severity='error'. Warning-severity regressions
    surface but do not block.

    Regression kinds:
      - playbook_dropped       (error)
      - step_dropped           (error)
      - step_renamed_silently  (error) — same shape, new name; breaks
                                          external vars.steps.<slug>.* refs
      - annotation_stripped    (warning)
      - annotation_modified    (warning)
      - ui_metadata_lost       (warning)
      - behavior_changed_outside_diff (warning) — only when user_message given
    """
    # 1. Shape check on the after YAML.
    after_result = verify_playbook(after_yaml, live_probe=live_probe)

    # 2. Parse both for the diff.
    before_coll, before_errs = _parse(before_yaml)
    after_coll, after_errs = _parse(after_yaml)

    if before_coll is None:
        # Before YAML is unparseable — we cannot diff. Surface this as
        # an evidence note, return the verify_playbook result unchanged
        # with empty diff fields. Better than refusing the call.
        out = dict(after_result)
        out["regressions"] = []
        out["diff_summary"] = {"steps_added": [], "steps_removed": [],
                               "steps_modified": [], "unchanged": 0}
        out.setdefault("evidence", {})["before_unparseable"] = {
            "errors": before_errs,
            "note": ("before_yaml did not parse — skipping regression diff; "
                     "treating this as a build-mode verify of after_yaml only"),
        }
        return out

    if after_coll is None:
        # After is broken at parse time. verify_playbook already captured
        # that in required_fixes; nothing to diff against.
        out = dict(after_result)
        out["regressions"] = []
        out["diff_summary"] = {"steps_added": [], "steps_removed": [],
                               "steps_modified": [], "unchanged": 0}
        return out

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

    return out
