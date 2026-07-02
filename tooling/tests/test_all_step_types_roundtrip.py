"""All-step-types validation playbook -- the capstone round-trip test.

Proves the three loops (author / discover / read) for every friendly step type
in one artifact: ``examples/all_step_types_validation.yaml`` -- a single
friendly-YAML collection that uses all 26 friendly step types (24 typed +
the ``stop``/``end`` one-way sugars).

Two halves:

* **OFFLINE (runs in CI, no marker).** The author loop -- the friendly YAML
  compiles clean for all 26 types -- plus the offline *semantic* round-trip
  (decompile our compiled canonical -> reemit -> assert semantic equivalence).
  The offline round-trip proves the decompiler branch exists and is
  self-consistent for every type, and pins the coverage matrix's ``read`` flags
  against actual decompiler behavior. It does NOT prove the read loop against
  the box: it feeds our own clean compiled output back through the decompiler,
  so it cannot see wire-shape drift the box introduces.

* **LIVE (``@pytest.mark.live``; deselected offline).** The FULL read loop --
  compile -> push -> pull -> decompile -> recompile -- against a live box.
  THIS is the gap-catcher: it feeds the BOX's canonical back through, surfacing
  the open read-loop gaps the offline loop structurally cannot (the
  ``delete_record`` envelope asymmetry, ``manual_input``'s ~14-key surface,
  ``connector``/``CyopsUtilices`` boilerplate -- G10 Tier 1/2). A live failure
  is a real gap to feed back into the type's ``read`` flag.

The live half needs ``.env`` (``FSR_BASE_URL``/``FSR_PASSWORD``) at the repo
root; it is skipped otherwise. Run it with ``pytest -m live``.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile
from fsr_playbooks.compiler.resolver import SHORT_TYPE_TO_FSR
from fsr_playbooks.compiler.roundtrip import roundtrip

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"
YAML_PATH = EXAMPLES / "all_step_types_validation.yaml"

COLLECTION_NAME = "FSRPB All Step Types Validation"
ORCHESTRATOR = "Orchestrator - Threat Feed Ingest"

# The 26 friendly step types this playbook must exercise (24 typed + the
# stop/end one-way sugars). Author-loop coverage is asserted against this set.
ALL_STEP_TYPES: list[str] = [
    # triggers (one per playbook; 6 variants)
    "start", "start_on_create", "start_on_update", "start_on_delete",
    "api_endpoint",
    # record family
    "create_record", "insert_record", "update_record", "delete_record",
    "find_record",
    # control / data
    "set_variable", "decision", "delay", "code_snippet", "manual_input",
    "ingest_bulk_feed",
    # the connector family
    "connector", "utilities",
    # action / notify
    "send_email", "create_task", "set_api_keys", "approval",
    "workflow_reference", "trigger_tenant_playbook",
    # one-way authoring sugars (compile down to Connectors / cyops_utilities.no_op)
    "stop", "end",
]

# Types whose friendly sugar compiles down to a shared canonical (``Connectors``)
# and so is one-way -- a pulled step of these types round-trips as ``connector``.
# Correct-by-design (coverage ``read=sugar-not-recovered``), NOT a gap.
SUGAR_NOT_RECOVERED: frozenset[str] = frozenset(
    {"stop", "end", "delete_record", "utilities"}
)

# Per friendly type, the set of type-name spellings that count as "this type
# survived" when grepping a decompiled YAML. Built from SHORT_TYPE_TO_FSR (the
# friendly->canonical map) plus the editor-palette canonicals the box may store
# (ApprovalManualInput, CyopsUtilices, SendMail) and the Manual-trigger start
# variant (cybersponse.action). Grounded in ``tooling/step_type_coverage.py``
# EDITOR_PALETTE + CONNECTOR_FAMILY.
#
# Alias-aware: where multiple friendly types share one canonical (create_record
# & insert_record both -> InsertData; stop/end/utilities/delete_record/connector
# all -> Connectors), the decompiler is last-wins, so an authored type may
# round-trip as its alias. Accept any friendly sharing the same canonical.
from collections import defaultdict

_CANON_TO_FRIENDLIES: dict[str, set[str]] = defaultdict(set)
for _f, _c in SHORT_TYPE_TO_FSR.items():
    _CANON_TO_FRIENDLIES[_c].add(_f)

_FRIENDLY_TO_ACCEPT: dict[str, set[str]] = {}
for _t in ALL_STEP_TYPES:
    _accept = {_t}
    _canon = SHORT_TYPE_TO_FSR.get(_t)
    if _canon:
        _accept.add(_canon)
        _accept.update(_CANON_TO_FRIENDLIES[_canon])  # aliases (last-wins)
    _FRIENDLY_TO_ACCEPT[_t] = _accept
_FRIENDLY_TO_ACCEPT["approval"].update({"ApprovalManualInput"})
_FRIENDLY_TO_ACCEPT["utilities"].update({"CyopsUtilices", "CyopsUtilities"})
_FRIENDLY_TO_ACCEPT["send_email"].update({"SendEmail", "SendMail"})
_FRIENDLY_TO_ACCEPT["start"].update({"cybersponse.action"})  # Manual variant
# Sugar types decompile back as `connector` -- accept that too.
for _t in SUGAR_NOT_RECOVERED:
    _FRIENDLY_TO_ACCEPT[_t].update({"connector", "Connectors"})


def _authored_step_types(text: str) -> set[str]:
    """The ``type:`` values at step level in a playbook YAML.

    Walks the parsed document (``playbooks[].steps[].type``) rather than
    regexing the text: the decompiler emits step list items as
    ``  - type: X`` (dash + key on one line), so a naive ``^\\s+type:`` regex
    misses every step-level type and only catches *nested* ``type:`` keys
    (``arguments.type``, input ``kind``/``schema.type``, …). Works on the
    authored YAML and on the decompiler's output alike.
    """
    import yaml

    doc = yaml.safe_load(text) or {}
    out: set[str] = set()
    for pb in doc.get("playbooks", []):
        for s in pb.get("steps") or []:
            t = s.get("type") if isinstance(s, dict) else None
            if t:
                out.add(str(t))
    return out


# ---------------------------------------------------------------------------
# OFFLINE -- the author loop + offline semantic round-trip. Runs in CI.
# ---------------------------------------------------------------------------

def test_authors_every_step_type():
    """AUTHOR loop: every one of the 26 friendly types is authored at least once."""
    authored = _authored_step_types(YAML_PATH.read_text())
    missing = set(ALL_STEP_TYPES) - authored
    assert not missing, f"step types not exercised in the playbook: {sorted(missing)}"


def test_compiles_clean_offline(db_path):
    """AUTHOR loop: the whole collection compiles with zero blocking errors."""
    res = compile_yaml(YAML_PATH.read_text(), db_path)
    assert res.ok, [
        e.to_dict() for e in res.errors if e.severity == "error"
    ]
    assert res.fsr_json is not None


def test_offline_semantic_roundtrip_clean(db_path):
    """Offline decompile -> reemit -> semantic-equal is clean for all 26 types.

    Proves the decompiler branch exists + is self-consistent for every type.
    Does NOT prove the read loop against the box's wire shape -- the live test
    does that.
    """
    res = compile_yaml(YAML_PATH.read_text(), db_path)
    assert res.fsr_json is not None
    ok, diffs = roundtrip(res.fsr_json, db_path)
    assert ok, f"offline roundtrip diffs:\n  " + "\n  ".join(diffs[:20])


def test_offline_decompile_read_flags_match_matrix(db_path):
    """The offline decompiler recovers each type exactly as the coverage matrix
    claims: sugar-not-recovered types (stop/end/delete_record/utilities) round-
    trip as ``connector``; every other type recovers its friendly name.

    Pins the ``read`` flags in ``tooling/step_type_coverage.py`` against actual
    decompiler behavior on our compiled output.
    """
    res = compile_yaml(YAML_PATH.read_text(), db_path)
    assert res.fsr_json is not None
    col = decompile(res.fsr_json, db_path)
    recovered = {s.type for wf in col.playbooks for s in wf.steps}
    # Every non-sugar type we authored must be recovered as a friendly name --
    # itself or an alias sharing its canonical (create_record <-> insert_record
    # both -> InsertData; the decompiler is last-wins).
    expected = set(ALL_STEP_TYPES) - SUGAR_NOT_RECOVERED
    missing = [t for t in expected if not (recovered & _FRIENDLY_TO_ACCEPT[t])]
    assert not missing, (
        f"types not recovered as friendly on offline decompile: {sorted(missing)}\n"
        f"recovered: {sorted(recovered)}"
    )
    # The sugar types (stop/end/delete_record/utilities) round-trip as
    # `connector` (sugar-not-recovered) -- that is correct-by-design.
    assert "connector" in recovered, (
        f"sugar types should round-trip as `connector`; recovered: {sorted(recovered)}"
    )


# ---------------------------------------------------------------------------
# LIVE -- the real read loop. Compile -> push -> pull -> decompile -> recompile.
# Marked `live`; skipped unless .env credentials are present.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def env_configured():
    """Skip the live tests if credentials are absent.

    Honors ``FSR_ENV_FILE`` (an absolute or repo-relative path) so a run can
    target a specific box without clobbering the repo's ``.env`` -- e.g.
    ``FSR_ENV_FILE=../pyfsr/.env.fsr-ga pytest -m live``. Defaults to the
    framework repo's ``.env``.
    """
    env = Path(os.environ.get("FSR_ENV_FILE") or (REPO / ".env"))
    if not env.is_absolute():
        env = REPO / env
    if not env.exists():
        pytest.skip(f"env file missing: {env}")
    text = env.read_text()
    if "FSR_BASE_URL" not in text or "FSR_PASSWORD" not in text:
        pytest.skip(f"{env} does not contain FSR_BASE_URL / FSR_PASSWORD")
    return env


@pytest.fixture(scope="module")
def live_client(env_configured):
    from pyfsr import FortiSOAR

    # The live read-loop needs the push/pull/decompile wrappers + from_env_file,
    # which live in the editable ../pyfsr (>=0.6.4), not the slim PyPI build the
    # framework venv may carry. Skip gracefully (don't error) when it's absent.
    if not hasattr(FortiSOAR, "from_env_file"):
        pytest.skip(
            "installed pyfsr lacks FortiSOAR.from_env_file; install the editable "
            "../pyfsr to run the live read-loop test: `uv pip install -e ../pyfsr`"
        )
    return FortiSOAR.from_env_file(str(env_configured))


def _delete_collection_if_exists(client, name: str) -> None:
    """Hard-delete any existing collection with this name (replace matches by
    uuid, and the YAML carries none, so stale same-named collections would
    otherwise accumulate across runs)."""
    for c in client.workflow_collections.list():
        if (c.get("name") if isinstance(c, dict) else getattr(c, "name", None)) == name:
            uuid = c.get("uuid") if isinstance(c, dict) else getattr(c, "uuid")
            client.workflow_collections.delete(uuid, hard=True)
            return


@pytest.mark.live
def test_live_full_decompile_roundtrip(live_client, db_path):
    """READ loop (the gap-catcher): compile -> push -> pull -> decompile ->
    recompile, asserting each type's friendly shape survives the box.

    The hard assertions:

    * the pulled friendly YAML **recompiles clean** -- this is the round-trip
      that catches extra keys the box added that the decompiler didn't strip
      (``unknown_param`` / ``unknown_connector`` on recompile). This is where
      the ``manual_input`` ~14-key surface and ``connector`` boilerplate gaps
      surface.
    * each of the 26 types **survives** the box, as its friendly name, its
      canonical name, or (for the one-way sugars) as ``connector``. A type
      that vanishes entirely is a real read-loop gap.

    The ``delete_record`` envelope asymmetry (G10 Tier 1) is expected to pass
    here: delete_record is sugar-not-recovered, so it round-trips as
    ``connector`` and recompiles clean. If it instead breaks recompile (extra
    ``step_variables``/``version`` keys), THAT is the gap surfacing -- feed it
    back into the type's ``read`` flag.
    """
    from pyfsr.authoring import compile_playbook_yaml

    yaml_text = YAML_PATH.read_text()

    # 1. Clean up any stale same-named collection, then compile + push.
    _delete_collection_if_exists(live_client, COLLECTION_NAME)
    live_client.workflow_collections.import_from_yaml(
        yaml_text, replace=True, refresh_catalog=True,
    )

    # 2. Pull the collection back as the BOX stores it, decompiled to friendly
    #    YAML (seamless catalog warming from the live client).
    pulled_yaml = live_client.workflow_collections.export_to_yaml(COLLECTION_NAME)
    assert pulled_yaml and "playbooks:" in pulled_yaml, (
        f"export_to_yaml returned no playbook body:\n{pulled_yaml!r}"
    )

    pulled_types = _authored_step_types(pulled_yaml)

    # 3. The pulled friendly YAML must recompile clean -- the core gap-catcher.
    cp = compile_playbook_yaml(pulled_yaml, client=live_client)
    assert cp.ok, (
        "pulled YAML did NOT recompile clean -- read-loop gap (extra keys the "
        "box added that the decompiler didn't strip):\n  "
        + "\n  ".join(
            f"[{e.get('code')}] {e.get('path')}: {e.get('message')}"
            for e in cp.blocking
        )
    )

    # 4. Per-type survival: each of the 26 types must survive the box in some
    #    spelling (friendly / canonical / connector-for-sugars). A type that
    #    vanishes is a real gap.
    missing = [
        t for t in ALL_STEP_TYPES
        if not (pulled_types & _FRIENDLY_TO_ACCEPT[t])
    ]
    assert not missing, (
        f"step types that lost their shape across the live box: {sorted(missing)}\n"
        f"pulled types: {sorted(pulled_types)}"
    )

    # 5. Offline semantic round-trip on the pulled canonical too (the recompiled
    #    envelope must be self-consistent under decompile->reemit).
    ok, diffs = roundtrip(cp.fsr_json, db_path)
    assert ok, f"pulled-canonical roundtrip diffs:\n  " + "\n  ".join(diffs[:20])


# ---------------------------------------------------------------------------
# LIVE -- the RUN loop. The orchestrator actually EXECUTES on a live box to a
# terminal `finished` state, with its manual_input gate answered programmatically.
# Marked `live`; skipped unless .env credentials are present.
# ---------------------------------------------------------------------------

# FortiSOAR run statuses we treat as terminal (the run is done, for better or
# worse). `awaiting` is the manual_input/approval PAUSE -- not terminal; the
# test answers it mid-run via pb.approval.
_LIVE_TERMINAL = frozenset(
    {"finished", "failed", "error", "cancelled", "aborted"}
)


def _run_pk(run: dict) -> str | None:
    """Run pk = trailing segment of its ``@id`` path."""
    return ((run.get("@id") or "").rstrip("/").rsplit("/", 1)[-1] or None)


# The 3 active post-write trigger playbooks the orchestrator fires by
# creating/updating/deleting its marker-tagged audit alert. Each is `start_on_*`
# on `alerts` with a `description contains fsrpb_all_step_types_` filter, so it
# fires ONLY on the orchestrator's audit alert -- never on unrelated box noise.
_TRIGGER_PLAYBOOKS = (
    "On Create - Audit Alert",
    "On Update - Audit Alert",
    "On Delete - Audit Alert",
)


def _wait_for_new_trigger_run(pb, name: str, baseline: set, *, timeout: float = 60,
                              interval: float = 2) -> dict | None:
    """Poll a trigger playbook's execution history for a NEW terminal run.

    Returns the run (a RunSummary-shaped dict) once one appears whose pk is not
    in ``baseline`` and whose status is terminal, or ``None`` on timeout. The
    baseline (captured before the orchestrator fired) makes the check robust to
    pre-existing trigger runs and avoids the fragile `since`-timestamp string
    comparison.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runs = pb.execution_history(playbook=name, limit=10)
        for r in runs or []:
            pk = r.get("pk") if isinstance(r, dict) else getattr(r, "pk", None)
            if pk in baseline:
                continue
            status = (r.get("status") if isinstance(r, dict)
                      else getattr(r, "status", "")) or ""
            if status.lower() in _LIVE_TERMINAL:
                return r if isinstance(r, dict) else {"pk": pk, "status": status}
        time.sleep(interval)
    return None


def _cleanup_run_artifacts(client) -> None:
    """Delete any records tagged with the run marker + the collection.

    Records queries use ``operator`` (the ``op`` spelling is for playbook
    triggers). Best-effort -- a flaky module must not block the rest of
    teardown, so per-module errors are swallowed.
    """
    for module, field in (("alerts", "description"), ("comments", "content")):
        try:
            client.records(module).delete_by_query(
                {"logic": "AND",
                 "filters": [{"field": field, "operator": "like",
                              "value": "fsrpb_all_step_types_"}]},
                hard=True,
            )
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass
    _delete_collection_if_exists(client, COLLECTION_NAME)


def _ensure_debug_logging(client) -> bool:
    """Turn ON global playbook debug logging for this run + return the prior state.

    Step ``result`` payloads and the run ``env`` dict are only captured when
    FortiSOAR's global *Playbook debug logging* is on (System Settings ->>
    Playbooks ->> Logs; ``publicValues.workflow_log_config.debug``). With it off
    (the default) every step result is ``{}`` and ``env`` is empty, so the
    logical checks below (branch taken / create produced a record / find
    returned it / variable populated) are *not observable*. The caller restores
    the prior state in its ``finally`` so the box is left as it was found.
    """
    prior = bool(
        (client.system_settings.get_public_values().get("workflow_log_config") or {})
        .get("debug")
    )
    if not prior:
        client.system_settings.set_playbook_debug_logging(
            enabled=True, allow_playbook_override=False)
    return prior


def _step(steps: dict, name: str) -> dict:
    """One step's raw record by display name (the run's ``steps[]`` list)."""
    return steps.get(name) or {}


@pytest.mark.live
def test_live_runs_to_finished(live_client):
    """RUN loop: the orchestrator actually EXECUTES on a live box to a terminal
    ``finished`` state, with its manual_input gate answered programmatically --
    PLUS logical checks that the run *did the right thing*, not just that it
    finished (branch taken; create_record produced a real record; find_record
    returned it; set_variable vars populated; delete closed the lifecycle).

    The round-trip test proves the playbook compiles + survives the box's wire
    shape; THIS test proves it is *runnable and correct*. It:

    * turns on global playbook debug logging (so step results + env are captured;
      restored in ``finally``);
    * pushes the collection, then triggers the orchestrator;
    * polls the run; when it pauses on the ``Pause for approval`` manual_input
      step (status ``awaiting``), it answers **approve** via
      :meth:`pb.approval <pyfsr.api.playbooks.PlaybooksAPI.approval>`;
    * asserts the run reaches a ``finished``-family status with no non-ignored
      step hard-failing (``why_failed.failing_step is None``);
    * LOGICAL checks (need debug on):
        - the decision took the *data* branch, not Else (``Raise no data`` /
          ``Stop here`` skipped, ``Pause for approval`` finished);
        - ``create_record`` produced a real record (step result carries an
          ``@id`` IRI into ``/api/3/alerts/``);
        - ``find_record`` returned that same record (result list non-empty,
          ``[0]['@id']`` == the create step's ``@id``);
        - the ``set_variable`` vars are populated in ``env`` (``marker`` tagged,
          ``indicators`` non-empty, ``ingestedData`` mirrors it);
        - the manual_input gate recorded the resume (result carries ``userid``);
        - ``delete_record`` closed the lifecycle cleanly (status ``finished``,
          not ``finished with error`` -- the ``record:`` vs ``record_id:`` fix).
    * tears down tagged records + the collection (``finally``), and restores
      the prior debug-logging state.

    The remaining ``ignore_errors`` steps (``send_email`` SMTP,
    ``trigger_tenant_playbook`` peer tenant) still error gracefully -- step
    status ``finished with error`` -- which is why the run reaches ``finished``
    despite box-config gaps.
    """
    pb = live_client.playbooks
    _delete_collection_if_exists(live_client, COLLECTION_NAME)
    live_client.workflow_collections.import_from_yaml(
        YAML_PATH.read_text(), replace=True, refresh_catalog=True,
    )
    prior_debug = _ensure_debug_logging(live_client)
    try:
        # Baseline each trigger's existing run pks BEFORE the orchestrator fires,
        # so the post-run fire-check can spot the NEW runs the orchestrator's
        # create/update/delete of the audit alert kicks off.
        trigger_baseline = {
            name: {r.get("pk") for r in (pb.execution_history(playbook=name, limit=10) or [])}
            for name in _TRIGGER_PLAYBOOKS
        }

        resp = pb.trigger(
            ORCHESTRATOR,
            inputs={
                "feed_url": "https://demo.example/feed",
                "lastPullTime": "2026-01-01T00:00:00Z",
            },
        )
        task_id = resp.task_id if hasattr(resp, "task_id") else resp.get("task_id")
        assert task_id, f"trigger returned no task_id: {resp!r}"

        # Poll to terminal; answer the manual_input gate when the run pauses on it.
        answered: set[int] = set()
        status = ""
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            members = (pb.log_list(task_id=task_id, limit=1) or {}).get("hydra:member") or []
            run = members[0] if members else {}
            status = (run.get("status") or "").lower()
            if status == "awaiting":
                rpk = _run_pk(run)
                pending = live_client.manual_input.pending_for_run(task_id)
                fresh = [p for p in pending if p.id not in answered]
                if fresh and rpk:
                    pb.approval(rpk, decision="approve")
                    answered.add(fresh[0].id)
            elif status in _LIVE_TERMINAL:
                break
            time.sleep(2)
        assert status in _LIVE_TERMINAL, (
            f"orchestrator did not reach a terminal status within 180s (last={status!r})"
        )

        # The run's true terminal status + (absence of) a hard failure.
        why = pb.why_failed(playbook=ORCHESTRATOR)
        assert why is not None, "orchestrator produced no run record"
        assert why.status.lower().startswith("finished"), (
            f"orchestrator did not reach a finished-family status: {why.status!r}"
        )
        assert why.failing_step is None, (
            f"a non-ignored step hard-failed: {why.failing_step!r}: {why.error_message!r}"
        )

        # The full run record (step_detail=True). With debug logging on, each
        # step's `result` and the run `env` are populated; without it they're {}
        # / empty and the logical checks below can't run.
        full = pb.get_execution(str(why.pk), step_detail=True)
        step_list = [s for s in full.get("steps") or [] if isinstance(s, dict)]
        steps = {s["name"]: s for s in step_list if s.get("name")}
        statuses = {nm: (s.get("status") or "") for nm, s in steps.items()}

        # --- runtime-behavior checks (the two types a round-trip can't exercise) ---
        assert statuses.get("Pause for approval") == "finished", (
            f"manual_input gate did not finish -- pb.approval resume failed? "
            f"status={statuses.get('Pause for approval')!r}"
        )
        assert statuses.get("Call normalize child") == "finished", (
            f"workflow_reference step did not finish: "
            f"status={statuses.get('Call normalize child')!r}"
        )
        tree = pb.run_tree(str(why.pk), depth=1)
        assert any(
            c.name == "Normalize Indicator"
            and (c.status or "").lower().startswith("finished")
            for c in tree.children
        ), f"workflow_reference child did not run to finished: {tree.children}"

        # --- LOGICAL checks (need debug logging on) ---

        # 1. Branch taken: the decision picked the *data* branch (Pause for
        #    approval), not Else (Raise no data -> Stop here).
        assert statuses.get("Raise no data") == "skipped", (
            f"decision took the Else branch (data was empty?): "
            f"Raise no data={statuses.get('Raise no data')!r}"
        )
        assert statuses.get("Stop here") == "skipped", (
            f"Else branch ran: Stop here={statuses.get('Stop here')!r}"
        )

        # 2. create_record produced a real record: its result carries the
        #    created alert's @id IRI into /api/3/alerts/.
        create_res = _step(steps, "Create audit alert").get("result")
        assert isinstance(create_res, dict) and create_res.get("@id", "").startswith(
            "/api/3/alerts/"
        ), f"create_record did not produce an alert record: result={create_res!r}"
        created_iri = create_res["@id"]

        # 3. find_record returned that SAME record (the lifecycle is wired right):
        #    non-empty list whose [0]['@id'] == the create step's @id.
        find_res = _step(steps, "Find audit alert").get("result")
        assert isinstance(find_res, list) and find_res, (
            f"find_record returned no records: result={find_res!r}"
        )
        assert find_res[0].get("@id") == created_iri, (
            f"find_record did not return the record create_record made: "
            f"create={created_iri!r} find[0]={find_res[0].get('@id')!r}"
        )

        # 4. delete_record closed the lifecycle cleanly (the `record:` IRI fix --
        #    feeding the @id via `record_id:` doubled the path -> 404). With
        #    ignore_errors still on, a regression shows as `finished with error`.
        assert statuses.get("Delete audit alert") == "finished", (
            f"delete_record did not finish cleanly (record: vs record_id: regression?): "
            f"status={statuses.get('Delete audit alert')!r}, "
            f"result={_step(steps, 'Delete audit alert').get('result')!r}"
        )

        # 5. set_variable vars are populated in the run env.
        env = full.get("env") or {}
        assert isinstance(env, dict) and env, (
            "run env is empty -- global debug logging is off (step results/vars "
            "are only captured with it on); this is a test-env problem, not a "
            "playbook failure"
        )
        marker = env.get("marker") or ""
        assert isinstance(marker, str) and marker.startswith("fsrpb_all_step_types_"), (
            f"set_variable 'marker' not populated: {marker!r}"
        )
        indicators = env.get("indicators")
        assert isinstance(indicators, list) and indicators, (
            f"set_variable 'indicators' not populated: {indicators!r}"
        )
        assert env.get("ingestedData") == indicators, (
            "Map ingested data did not mirror the Configure indicators list"
        )

        # 6. The manual_input gate recorded the resume (a userid/timestamp).
        pause_res = _step(steps, "Pause for approval").get("result")
        assert isinstance(pause_res, dict) and pause_res.get("userid"), (
            f"manual_input resume was not recorded on the step: result={pause_res!r}"
        )

        # 7. The 3 post-write triggers FIRED -- proving start_on_create/_update/
        #    _delete actually RUN (not just compile). The orchestrator's own
        #    create/update/delete of the marker-tagged audit alert fires each
        #    (they are alert-scoped + marker-filtered, so only our alert trips
        #    them). Assert a NEW terminal run appeared for each. This is the one
        #    piece a round-trip + status-only run check can't reach: the trigger
        #    TYPE executing in response to a record event. Needs the compiler's
        #    `contains`->`like %..%` wrap (regression: underscored values used to
        #    skip the wrap and silently never fire).
        for name in _TRIGGER_PLAYBOOKS:
            trun = _wait_for_new_trigger_run(
                pb, name, trigger_baseline[name], timeout=60)
            assert trun is not None, (
                f"post-write trigger {name!r} did not fire (no new run after the "
                f"orchestrator created/updated/deleted the audit alert) -- the "
                f"start_on_* trigger TYPE did not execute"
            )
            assert (trun.get("status") or "").lower().startswith("finished"), (
                f"trigger {name!r} fired but did not finish cleanly: "
                f"status={trun.get('status')!r}"
            )
    finally:
        # Always leave the box as it was found: restore debug-logging state +
        # clean up tagged records + the collection.
        if not prior_debug:
            try:
                live_client.system_settings.set_playbook_debug_logging(
                    enabled=False, allow_playbook_override=True)
            except Exception:  # noqa: BLE001 - best-effort restore
                pass
        _cleanup_run_artifacts(live_client)


@pytest.mark.live
def test_live_cleanup(live_client):
    """Tear down the validation collection after the live run (leave the box clean)."""
    _delete_collection_if_exists(live_client, COLLECTION_NAME)
