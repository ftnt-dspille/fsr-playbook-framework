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
