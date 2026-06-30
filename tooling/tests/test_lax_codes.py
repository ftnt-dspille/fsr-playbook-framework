"""lax_codes demotion accepts every spelling of an ErrorCode.

Regression for a footgun: the demote pass compared only ``str(e.code)``
(``"ErrorCode.UNKNOWN_CONNECTOR"``), so a caller passing the friendly
``.value`` string (``"unknown_connector"``) was silently ignored and the
error still blocked. Demotion must accept the ``.value``, the ``.name``,
and the enum itself.
"""
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode

_YAML = """
collection: Lax Test
playbooks:
  - name: pb
    steps:
      - name: start
        type: start
        next: act
      - name: act
        type: connector
        arguments:
          connector: totally_not_a_real_connector
          operation: do_thing
"""


def test_unknown_connector_blocks_without_lax(db_path):
    r = compile_yaml(_YAML, db_path)
    assert not r.ok
    assert any(getattr(e.code, "value", None) == "unknown_connector" for e in r.errors)


def test_lax_codes_accepts_value_string(db_path):
    # The friendly `.value` string used to never match — now it demotes.
    r = compile_yaml(_YAML, db_path, lax_codes={"unknown_connector"})
    assert r.ok, r.errors


def test_lax_codes_accepts_enum_name(db_path):
    r = compile_yaml(_YAML, db_path, lax_codes={"UNKNOWN_CONNECTOR"})
    assert r.ok, r.errors


def test_lax_codes_accepts_enum(db_path):
    r = compile_yaml(_YAML, db_path, lax_codes={ErrorCode.UNKNOWN_CONNECTOR})
    assert r.ok, r.errors
