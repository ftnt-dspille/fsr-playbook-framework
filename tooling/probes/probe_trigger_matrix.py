"""probe_trigger_matrix — battle-test FSR field-based-trigger operators.

The question this answers: for each trigger operator (and nested AND/OR
groups), does *creating a record that matches the condition actually fire
the playbook*, and does *a non-matching record correctly NOT fire it*?
And does the `/api/query/<module>` selection engine agree with the trigger
evaluator? (They are known to differ — `in_all`/`changed` 500 on /query
but work in triggers — so disagreement is itself a recorded finding.)

For each case we:
  1. compile a one-step `start_on_create` playbook, then OVERWRITE the
     trigger step's `arguments.fieldbasedtrigger` with the exact filter
     group under test (so we control operator/type/_operator/nesting
     precisely, bypassing the compiler's flat `when:` expander), and push.
  2. create a MATCHING alert  → poll executions → expect FIRED.
  3. create a NON-MATCHING alert → poll executions → expect NOT FIRED.
  4. POST the same filter group to /api/query/alerts → record whether it
     selects the match / the non-match (secondary, cross-check signal).
  5. delete both alerts + hard-purge the collection.

A case PASSES (trigger_ok) iff match fired AND non-match did not. The
report flags every operator where trigger behavior and query behavior
disagree, and every operator that silently never fires (the bug class
that motivated this probe: contains / notcontains / like-without-`%`).

Usage:
    python tooling/probes/probe_trigger_matrix.py            # full matrix
    python tooling/probes/probe_trigger_matrix.py --only like_nowild,contains
    python tooling/probes/probe_trigger_matrix.py --list     # list case ids
    python tooling/probes/probe_trigger_matrix.py --keep      # don't purge
    python tooling/probes/probe_trigger_matrix.py --match-timeout 60
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from probes._env import get_client  # noqa: E402
from fsr_playbooks.compiler import compile_yaml  # noqa: E402
from e2e.runner import (  # noqa: E402
    _push, _PushError, _resolve_wf, _poll_by_template, _hard_purge,
)

DB = ROOT / "data" / "fsr_reference.db"
MODULE = "alerts"
NS = "fsrpbmx"  # name prefix so probe records are trivially identifiable


# ── case matrix ────────────────────────────────────────────────────────
# Each case: filters under test (canonical FSR wire shape, on `name`), plus
# the `name` of a record that SHOULD match and one that should NOT. `{TOK}`
# is replaced per-run with a unique token so cases never cross-match.
def _leaf(field, operator, value, _operator=None, type_="primitive"):
    leaf = {"type": type_, "field": field, "operator": operator, "value": value}
    if _operator is not None:
        leaf["_operator"] = _operator
    return leaf


def _compile_when_group(logic: str, filters: list[dict]) -> dict:
    """Compile a friendly `when:` through the real compiler and return the
    emitted `fieldbasedtrigger` group — so a probe case exercises exactly
    what authors get from the `when:` authoring path (incl. auto-correct)."""
    import yaml as _yaml
    when = {"logic": logic, "filters": filters}
    y = ("collection: _cc_extract\nplaybooks:\n  - name: probe\n    steps:\n"
         "      - name: On Create\n        type: start_on_create\n"
         "        module: alerts\n        when:\n"
         + "\n".join("          " + ln
                     for ln in _yaml.safe_dump(when).splitlines())
         + "\n        next: noop\n      - name: noop\n"
         "        type: set_variable\n        vars: {ok: 1}\n")
    res = compile_yaml(y, DB)
    if not res.ok:
        raise RuntimeError("when-compile failed: "
                           + "; ".join(e.message for e in res.errors))
    for s in res.fsr_json["data"][0]["workflows"][0]["steps"]:
        fbt = s.get("arguments", {}).get("fieldbasedtrigger")
        if fbt is not None:
            return fbt
    raise RuntimeError("no fieldbasedtrigger in compiled output")


def build_cases(tok: str) -> list[dict]:
    mid = f"{NS}-{tok}-mid"          # contains the needle
    needle = f"{tok}-mid"            # substring needle
    other = f"{NS}-{tok}-other"      # no needle
    exact = f"{NS}-{tok}-exact"
    C = []

    def case(cid, desc, group, match_name, nomatch_name, **extra):
        d = {"id": cid, "desc": desc, "group": group,
             "match": {"name": match_name}, "nomatch": {"name": nomatch_name}}
        d.update(extra)
        C.append(d)

    g = lambda logic, *fs: {"sort": [], "limit": 30, "logic": logic,
                            "filters": list(fs)}

    # ---- scalar comparison ----
    case("eq", "exact equality",
         g("AND", _leaf("name", "eq", exact, "eq")), exact, other)
    case("neq", "not-equal",
         g("AND", _leaf("name", "neq", exact, "neq")), other, exact)

    # ---- pattern (the core finding) ----
    # like WITH wildcards — should substring-match.
    case("like_wild", "like %needle% (wildcarded — expected to work)",
         g("AND", _leaf("name", "like", f"%{needle}%", "like")), mid, other)
    # like WITHOUT wildcards — suspected to behave as exact, so the
    # substring record should NOT fire (demonstrates the bug).
    case("like_nowild", "like needle (no % — suspected exact-only)",
         g("AND", _leaf("name", "like", needle, "like")), mid, other,
         note="if match does NOT fire, confirms like needs % wildcards")
    # our emitter's actual output: _operator=like_pattern (unattested).
    case("like_pattern_shadow", "like %needle% with _operator=like_pattern",
         g("AND", _leaf("name", "like", f"%{needle}%", "like_pattern")),
         mid, other,
         note="tests whether the like_pattern _operator shadow breaks firing")
    case("notlike", "notlike %needle% (does not match pattern)",
         g("AND", _leaf("name", "notlike", f"%{needle}%", "notlike")),
         other, mid)

    # ---- contains / does-not-contain (UI exposes these; corpus never uses) ----
    case("contains", "contains needle (UI 'Contains')",
         g("AND", _leaf("name", "contains", needle, "contains")), mid, other,
         note="discover: does contains substring-match a scalar string field?")
    case("notcontains", "notcontains needle (UI 'Does Not Contain')",
         g("AND", _leaf("name", "notcontains", needle, "notcontains")),
         other, mid, note="discover wire token + firing for the inverse")

    # ---- list membership ----
    case("in", "name in [match] (UI 'Is In List')",
         g("AND", _leaf("name", "in", [exact], None, "array")), exact, other)
    case("nin", "name nin [exact] (UI 'Is Not In List')",
         g("AND", _leaf("name", "nin", [exact], None, "array")), other, exact)

    # ---- nested logic (compiler can't author this; FSR supports it) ----
    case("nested_or", "(name eq A) OR (name eq B)",
         g("OR",
           {"logic": "AND", "filters": [_leaf("name", "eq", exact, "eq")]},
           {"logic": "AND", "filters": [_leaf("name", "eq", mid, "eq")]}),
         mid, other)
    case("nested_and", "(name like %tok% AND name like %mid%)",
         g("AND",
           {"logic": "AND",
            "filters": [_leaf("name", "like", f"%{tok}%", "like")]},
           {"logic": "AND",
            "filters": [_leaf("name", "like", "%mid%", "like")]}),
         mid, other)
    # flat AND with two leaves both required.
    case("flat_and", "name like %tok% AND name like %mid% (flat)",
         g("AND", _leaf("name", "like", f"%{tok}%", "like"),
           _leaf("name", "like", "%mid%", "like")), mid, other)

    # ---- COMPILER-PATH cases: author via friendly `when:` and let the
    # compiler emit the wire shape. Proves the auto-correct produces a
    # FIRING trigger (vs the raw-shape cases above that prove the bug). ----
    case("cc_contains", "compiler: op=contains needle (→ like %needle%)",
         _compile_when_group("AND", [{"field": "name", "op": "contains",
                                      "value": needle}]),
         mid, other, note="auto-correct: contains→like %…% should now FIRE")
    case("cc_like_bare", "compiler: op=like needle (no % → auto-wrapped)",
         _compile_when_group("AND", [{"field": "name", "op": "like",
                                      "value": needle}]),
         mid, other, note="auto-correct: bare like → %…% should now FIRE")
    return C


# ── per-case driver ────────────────────────────────────────────────────
def _baseline_yaml(coll_name: str) -> str:
    return f"""
collection: "{coll_name}"
description: "fsrpb trigger-matrix probe — safe to delete"
playbooks:
  - name: probe
    is_active: true
    steps:
      - name: On Create
        type: start_on_create
        module: alerts
        when:
          logic: AND
          filters:
            - {{field: name, op: eq, value: __placeholder__}}
        next: noop
      - name: noop
        type: set_variable
        vars: {{ok: 1}}
""".lstrip()


def _compiled_entity(coll_name: str, group: dict):
    res = compile_yaml(_baseline_yaml(coll_name), DB)
    if not res.ok:
        raise RuntimeError("baseline compile failed: "
                           + "; ".join(e.message for e in res.errors))
    coll = res.fsr_json["data"][0]
    wf = coll["workflows"][0]
    for s in wf["steps"]:
        if s.get("arguments", {}).get("fieldbasedtrigger") is not None:
            s["arguments"]["fieldbasedtrigger"] = copy.deepcopy(group)
            break
    return coll


def _create_alert(client, fields: dict) -> str | None:
    body = {"source": "fsrpb-probe", **fields}
    try:
        r = client.post(f"/api/3/{MODULE}", body)
    except Exception as e:  # noqa: BLE001
        print(f"      ! create_alert failed: {e}")
        return None
    return (r.get("@id") or "").rstrip("/").rsplit("/", 1)[-1] or None


def _delete_record(client, uuid_: str) -> None:
    try:
        client.session.delete(f"{client.base_url}/api/3/{MODULE}/{uuid_}",
                              verify=client.verify_ssl, timeout=30)
    except Exception:  # noqa: BLE001
        pass


def _run_trigger_record(client, pk_url: str) -> str | None:
    """Fetch a run's env and return the uuid of the record that triggered
    it (env.input.records[0] → /api/3/alerts/<uuid>). None if unavailable."""
    try:
        r = client.session.get(client.base_url + "/api" + pk_url
                               + "?step_detail=true", verify=client.verify_ssl,
                               timeout=30)
        if r.status_code != 200:
            return None
        recs = (((r.json().get("env") or {}).get("input") or {})
                .get("records") or [])
        if not recs:
            return None
        rec0 = recs[0]
        # env.input.records[0] is usually the hydrated record dict
        # ({"@id": "/api/3/alerts/<uuid>", "uuid": ...}); older runs may
        # store the bare IRI string.
        iri = rec0.get("@id") if isinstance(rec0, dict) else rec0
        if isinstance(rec0, dict) and rec0.get("uuid"):
            return rec0["uuid"]
        if isinstance(iri, str):
            return iri.rstrip("/").rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        return None
    return None


def _fired_set(client, wf_uuid: str, targets: set[str]) -> set[str]:
    """One-shot: which of `targets` have a run of this template, matched by
    triggering-record id (env.input.records[0]). No waiting."""
    template_iri = f"/api/3/workflows/{wf_uuid}"
    url = (client.base_url + "/api/wf/api/workflows/?format=json&limit=25"
           f"&ordering=-created&parent_wf__isnull=True"
           f"&template_iri={template_iri}")
    try:
        r = client.session.get(url, verify=client.verify_ssl, timeout=30)
        members = (r.json().get("hydra:member") or []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        members = []
    fired: set[str] = set()
    for m in members:
        rec = _run_trigger_record(client, m.get("@id") or "")
        if rec in targets:
            fired.add(rec)
    return fired


def _await_fence(client, fence_wf: str, targets: set[str], cap: int,
                 poll: float = 2.0) -> set[str]:
    """Event-driven barrier: poll until the catch-all FENCE playbook has
    fired for every record in `targets` — proof the engine has dispatched
    each create event to all field-based triggers. Adaptive (returns the
    instant the fence is satisfied); `cap` is only a hang backstop, not a
    per-record wait. Returns the fence-fired subset."""
    start = time.time()
    fired: set[str] = set()
    while time.time() - start < cap:
        fired = _fired_set(client, fence_wf, targets)
        if fired == targets:
            break
        time.sleep(poll)
    return fired


def _query_select(client, group: dict, match_id, nomatch_id) -> dict:
    """POST the filter group to /api/query/alerts; report which of our two
    records it selects. Returns {status, match, nomatch} (match/nomatch may
    be None if the query errored)."""
    payload = {"logic": group.get("logic", "AND"),
               "filters": group.get("filters", []),
               "sort": [], "limit": 200}
    url = f"{client.base_url}/api/query/{MODULE}"
    try:
        r = client.session.post(url, json=payload, verify=client.verify_ssl,
                                timeout=30)
    except Exception as e:  # noqa: BLE001
        return {"status": f"err:{e}", "match": None, "nomatch": None}
    if r.status_code != 200:
        return {"status": str(r.status_code), "match": None, "nomatch": None}
    ids = set()
    for m in (r.json().get("hydra:member") or []):
        ids.add((m.get("@id") or "").rstrip("/").rsplit("/", 1)[-1])
    return {"status": "200", "match": match_id in ids,
            "nomatch": nomatch_id in ids}


def run_case(client, case: dict, tok: str, log_dir: Path, fence_wf: str,
             cap: int, keep: bool) -> dict:
    cid = case["id"]
    coll_name = f"_{NS}_{tok}_{cid}"
    out = {"id": cid, "desc": case["desc"], "fired_match": None,
           "fired_nomatch": None, "trigger_ok": None, "query": None,
           "agree": None, "fence_ok": None, "note": case.get("note", ""),
           "error": None}
    coll = None
    match_id = nomatch_id = None
    try:
        coll = _compiled_entity(coll_name, case["group"])
        _push(client, coll, log_dir)
        wf_uuid = _resolve_wf(client, coll["uuid"], "probe")
        if not wf_uuid:
            out["error"] = "could not resolve workflow uuid"
            return out

        # Create BOTH records. The catch-all FENCE playbook fires for every
        # create; once it has fired for both records, the engine has provably
        # dispatched both create events to all field-based triggers — so the
        # test playbook's verdict is final and we read it with no static wait.
        match_id = _create_alert(client, {**case["match"]})
        nomatch_id = _create_alert(client, {**case["nomatch"]})
        if not match_id or not nomatch_id:
            out["error"] = "alert create failed"
            return out
        targets = {match_id, nomatch_id}
        fence_fired = _await_fence(client, fence_wf, targets, cap)
        out["fence_ok"] = (fence_fired == targets)
        fired = _fired_set(client, wf_uuid, targets)
        out["fired_match"] = match_id in fired
        out["fired_nomatch"] = nomatch_id in fired
        out["trigger_ok"] = out["fired_match"] and not out["fired_nomatch"]

        # cross-check vs the query engine.
        if match_id and nomatch_id:
            out["query"] = _query_select(client, case["group"],
                                         match_id, nomatch_id)
            q = out["query"]
            if q["status"] == "200":
                query_ok = (q["match"] is True) and (q["nomatch"] is False)
                out["agree"] = (query_ok == out["trigger_ok"])
    except _PushError as e:
        out["error"] = f"push failed: {e}"
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        if match_id:
            _delete_record(client, match_id)
        if nomatch_id:
            _delete_record(client, nomatch_id)
        if coll and not keep:
            try:
                _hard_purge(client, coll["uuid"], coll)
            except Exception as e:  # noqa: BLE001 — cleanup must never lose results
                out.setdefault("error", None)
                print(f"      ! purge failed (collection {coll_name} left): {e}")
    return out


def _fmt(v):
    return {True: "yes", False: "NO", None: "?"}.get(v, str(v))


# An empty filter group fires on *every* create — the event-watermark fence.
_FENCE_GROUP = {"sort": [], "limit": 30, "logic": "AND", "filters": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated case ids to run")
    ap.add_argument("--list", action="store_true", help="list case ids + exit")
    ap.add_argument("--keep", action="store_true", help="don't purge collections")
    ap.add_argument("--cap", type=int, default=120,
                    help="hang backstop (s) for the fence watermark, not a "
                         "per-case static wait")
    ap.add_argument("--out", default="", help="write JSON results to this path")
    args = ap.parse_args()

    tok = str(int(time.time()))[-6:]
    cases = build_cases(tok)
    if args.list:
        for c in cases:
            print(f"  {c['id']:22} {c['desc']}")
        return 0
    if args.only:
        want = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in want]

    client = get_client()
    if client is None:
        print("ERROR: no FSR client configured (check .env)")
        return 1
    log_dir = ROOT / "logs" / f"trigger_matrix_{tok}"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Probing {client.base_url}  module={MODULE}  cases={len(cases)} "
          f"token={tok}\n")

    # Push the catch-all fence once for the whole run.
    fence_coll = _compiled_entity(f"_{NS}_{tok}_fence", _FENCE_GROUP)
    _push(client, fence_coll, log_dir)
    fence_wf = _resolve_wf(client, fence_coll["uuid"], "probe")
    if not fence_wf:
        print("ERROR: could not push/resolve fence playbook")
        return 1
    print(f"fence playbook up (wf {fence_wf[:8]}) — event watermark\n")

    results = []
    try:
        for c in cases:
            print(f"  · {c['id']:22} {c['desc']}")
            r = run_case(client, c, tok, log_dir, fence_wf, args.cap, args.keep)
            results.append(r)
            q = r["query"] or {}
            print(f"      match_fired={_fmt(r['fired_match'])}  "
                  f"nomatch_fired={_fmt(r['fired_nomatch'])}  "
                  f"trigger_ok={_fmt(r['trigger_ok'])}  fence={_fmt(r['fence_ok'])}  "
                  f"query[{q.get('status','-')}] m={_fmt(q.get('match'))} "
                  f"n={_fmt(q.get('nomatch'))}  agree={_fmt(r['agree'])}"
                  + (f"  ERROR={r['error']}" if r['error'] else ""))
    finally:
        if not args.keep:
            try:
                _hard_purge(client, fence_coll["uuid"], fence_coll)
            except Exception as e:  # noqa: BLE001
                print(f"! fence purge failed: {e}")

    # summary
    print("\n" + "=" * 72)
    print(f"{'case':22} {'trig':5} {'qry':5} {'agree':6} note")
    print("-" * 72)
    for r in results:
        q = r["query"] or {}
        qok = ("ok" if q.get("status") == "200" and q.get("match") and
               not q.get("nomatch") else (q.get("status") or "-"))
        print(f"{r['id']:22} {_fmt(r['trigger_ok']):5} {str(qok):5} "
              f"{_fmt(r['agree']):6} {r['note'] or r['error'] or ''}")
    broken = [r["id"] for r in results if r["trigger_ok"] is False]
    print("\nNEVER-FIRES / BROKEN:", ", ".join(broken) or "(none)")
    diverge = [r["id"] for r in results if r["agree"] is False]
    print("TRIGGER≠QUERY divergence:", ", ".join(diverge) or "(none)")
    unreliable = [r["id"] for r in results if r["fence_ok"] is False]
    if unreliable:
        print("UNRELIABLE (fence hit cap — verdict suspect):",
              ", ".join(unreliable))

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2, default=str))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
