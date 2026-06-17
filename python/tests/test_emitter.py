from fsr_playbooks.compiler import compile_yaml


def _hello(repo_root):
    return (repo_root / "examples" / "hello_connector.yaml").read_text()


def _strip_volatile(obj):
    """Recursively drop wall-clock fields so determinism checks don't flake
    when two compiles straddle a second boundary. `lastModifyDate` is stamped
    with the real time on purpose (wf-engine staleness diagnostics); it is not
    part of what "deterministic" means here — UUIDs and structure are."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in ("lastModifyDate", "createDate", "modifyDate")}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def test_deterministic_uuids(db_path, repo_root):
    text = _hello(repo_root)
    a = compile_yaml(text, db_path)
    b = compile_yaml(text, db_path)
    assert a.ok and b.ok
    # Two compiles of identical input produce byte-equal JSON, modulo the
    # intentionally wall-clock `lastModifyDate` stamp.
    import json
    assert (json.dumps(_strip_volatile(a.fsr_json), sort_keys=True)
            == json.dumps(_strip_volatile(b.fsr_json), sort_keys=True))


def test_routes_synthesized(db_path, repo_root):
    r = compile_yaml(_hello(repo_root), db_path)
    wf = r.fsr_json["data"][0]["workflows"][0]
    assert wf["triggerStep"]
    assert len(wf["routes"]) == 2  # start->prep, prep->lookup
    pairs = {(rt["sourceStep"], rt["targetStep"]) for rt in wf["routes"]}
    assert len(pairs) == 2


def test_workflow_collection_link_is_stamped(db_path, repo_root):
    """Regression: the recycle-bin-restore + bulkupsert path used to leave
    a workflow's `collection` field null, which orphaned the playbook in
    the FSR UI (empty breadcrumbs, `?collection=<uuid>` filter found 0
    results). Workflows must carry the parent collection IRI in the
    emitted payload so bulkupsert preserves the relation across a restore.
    """
    r = compile_yaml(_hello(repo_root), db_path)
    coll = r.fsr_json["data"][0]
    coll_uuid = coll["uuid"]
    expected_iri = f"/api/3/workflow_collections/{coll_uuid}"
    for wf in coll["workflows"]:
        assert wf["collection"] == expected_iri, (
            f"workflow {wf['name']!r} missing collection IRI: "
            f"{wf['collection']!r}"
        )


def test_step_type_iri_format(db_path, repo_root):
    r = compile_yaml(_hello(repo_root), db_path)
    for step in r.fsr_json["data"][0]["workflows"][0]["steps"]:
        assert step["stepType"].startswith("/api/3/workflow_step_types/")
        assert len(step["uuid"]) == 36  # UUID4-shaped


def test_decision_bare_next_synthesizes_else_default(db_path):
    """Decision with `next:` and no `default: true` row gets an
    auto-synthesized Else default condition so the FSR designer renders
    a labeled fall-through edge instead of a broken edge."""
    yaml_text = """
collection: TestDecisionElse
playbooks:
  - name: t
    steps:
      - name: start
        type: start
        next: gate
      - name: gate
        type: decision
        conditions:
          - display: hot
            when: "{{ vars.input.severity == 'high' }}"
            next: hot_path
        next: cool_path
      - name: hot_path
        type: set_variable
        set: {note: hot}
      - name: cool_path
        type: set_variable
        set: {note: cool}
"""
    r = compile_yaml(yaml_text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    steps = r.fsr_json["data"][0]["workflows"][0]["steps"]
    gate = next(s for s in steps if s["name"] == "gate")
    conds = gate["arguments"]["conditions"]
    defaults = [c for c in conds if c.get("default")]
    assert len(defaults) == 1
    assert defaults[0]["option"].startswith("Else")


def test_debug_flag_round_trips_through_emitter(db_path):
    """`debug:` on a playbook reaches the FSR JSON. Default is False;
    explicit True must flow through parser → IR → emitter."""
    yaml_text = (
        'collection: "_test_debug"\n'
        'description: ""\n'
        'playbooks:\n'
        '  - name: "with_debug"\n'
        '    description: ""\n'
        '    debug: true\n'
        '    is_active: true\n'
        '    steps:\n'
        '      - name: start\n'
        '        type: start\n'
    )
    r = compile_yaml(yaml_text, db_path)
    assert r.ok, r.errors
    wf = r.fsr_json["data"][0]["workflows"][0]
    assert wf["debug"] is True
    assert wf["isActive"] is True


def test_debug_flag_defaults_to_false(db_path):
    """Legacy YAML without `debug:` keeps emitting `debug: false`."""
    yaml_text = (
        'collection: "_test_debug_default"\n'
        'description: ""\n'
        'playbooks:\n'
        '  - name: "no_debug"\n'
        '    description: ""\n'
        '    steps:\n'
        '      - name: start\n'
        '        type: start\n'
    )
    r = compile_yaml(yaml_text, db_path)
    assert r.ok, r.errors
    wf = r.fsr_json["data"][0]["workflows"][0]
    assert wf["debug"] is False


def _priority_iri(db_path, value):
    import sqlite3
    from fsr_playbooks.compiler.ir import PRIORITY_LIST_NAME
    c = sqlite3.connect(db_path)
    row = c.execute(
        "SELECT item_iri FROM picklists WHERE list_name=? AND item_value=?",
        (PRIORITY_LIST_NAME, value)).fetchone()
    c.close()
    return row[0] if row else None


def test_priority_high_emits_synced_iri(db_path):
    yaml_text = """
collection: TestPriority
playbooks:
  - name: P
    priority: High
    steps:
      - name: s
        type: start
"""
    r = compile_yaml(yaml_text, db_path)
    assert r.ok
    wf = r.fsr_json["data"][0]["workflows"][0]
    expected = _priority_iri(db_path, "High")
    assert expected and expected.startswith("/api/3/picklists/")
    assert wf["priority"] == expected


def test_priority_medium_resolves_from_store(db_path):
    yaml_text = """
collection: TestPriorityMed
playbooks:
  - name: P
    priority: Medium
    steps:
      - name: s
        type: start
"""
    r = compile_yaml(yaml_text, db_path)
    assert r.ok
    assert r.fsr_json["data"][0]["workflows"][0]["priority"] == _priority_iri(db_path, "Medium")


def test_priority_unset_defaults_to_high(db_path):
    # Authoring default: no `priority:` → High (the field is optional).
    yaml_text = """
collection: TestPriorityNone
playbooks:
  - name: P
    steps:
      - name: s
        type: start
"""
    r = compile_yaml(yaml_text, db_path)
    assert r.ok
    assert r.fsr_json["data"][0]["workflows"][0]["priority"] == _priority_iri(db_path, "High")


def test_priority_unknown_warns_and_unsets(db_path):
    from fsr_playbooks.compiler.errors import ErrorCode
    yaml_text = """
collection: TestPriorityBad
playbooks:
  - name: P
    priority: Bogus
    steps:
      - name: s
        type: start
"""
    r = compile_yaml(yaml_text, db_path)
    assert r.ok  # warning does not block
    assert r.fsr_json["data"][0]["workflows"][0]["priority"] is None
    assert any(e.code is ErrorCode.BAD_VALUE and "priority" in (e.path or "")
               for e in r.warnings)
