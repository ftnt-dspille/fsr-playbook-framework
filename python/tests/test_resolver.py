from compiler import compile_yaml
from compiler.errors import ErrorCode


def _yaml(steps_block: str) -> str:
    return f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: target
      - name: target
{steps_block}
"""


def test_unknown_step_type_suggests(db_path):
    text = _yaml("        type: connetor\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_STEP_TYPE)
    assert e.near == "connector"
    assert "did you mean" in (e.suggestion or "")


def test_unknown_connector_suggests(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortimanger\n"
        "          operation: get_devices\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    codes = {e.code for e in r.errors}
    assert ErrorCode.UNKNOWN_CONNECTOR in codes


def test_unknown_operation_suggests(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortinet-fortisiem\n"
        "          operation: get_org_name_by_org_idz\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_OPERATION)
    assert e.near == "get_org_name_by_org_id"


def test_unknown_param(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortinet-fortisiem\n"
        "          operation: get_org_name_by_org_id\n"
        "          params:\n"
        "            domain_id_typo: x\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.UNKNOWN_PARAM for e in r.errors)


def test_unknown_next_step(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: nowhere
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.UNKNOWN_NEXT_STEP for e in r.errors)


def test_connector_version_stamped(db_path, repo_root):
    text = (repo_root / "examples" / "hello_connector.yaml").read_text()
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # Resolver stamps version onto the connector step's arguments.
    lookup_step = next(s for s in r.ir.playbooks[0].steps if s.id == "get_organization")
    assert lookup_step.arguments.get("version")  # set from connectors.version
