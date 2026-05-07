from compiler import compile_yaml


def _hello(repo_root):
    return (repo_root / "examples" / "hello_connector.yaml").read_text()


def test_deterministic_uuids(db_path, repo_root):
    text = _hello(repo_root)
    a = compile_yaml(text, db_path)
    b = compile_yaml(text, db_path)
    assert a.ok and b.ok
    # Two compiles of identical input produce byte-equal JSON.
    import json
    assert json.dumps(a.fsr_json, sort_keys=True) == json.dumps(b.fsr_json, sort_keys=True)


def test_routes_synthesized(db_path, repo_root):
    r = compile_yaml(_hello(repo_root), db_path)
    wf = r.fsr_json["data"][0]["workflows"][0]
    assert wf["triggerStep"]
    assert len(wf["routes"]) == 2  # start->prep, prep->lookup
    pairs = {(rt["sourceStep"], rt["targetStep"]) for rt in wf["routes"]}
    assert len(pairs) == 2


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
