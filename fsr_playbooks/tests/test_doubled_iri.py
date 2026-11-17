"""A /api/3/<module>/ prefix in front of an @id doubles the IRI.

Measured on 8.0.1: ``record: "/api/3/alerts/{{ <an IRI> }}"`` renders
``/api/3/alerts//api/3/alerts/<uuid>`` and the step fails with "No route found";
``{{ <the IRI> }}`` alone succeeds.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

_YAML = """collection: C
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        module: alerts
        next: Find
      - name: Find
        type: find_record
        module: alerts
        next: Upd
      - name: Upd
        type: update_record
        module: alerts
        record: "{record}"
        fields:
          description: x
"""


def _doubled(record: str) -> list:
    r = compile_yaml(_YAML.format(record=record), default_db_path())
    return [e for e in r.errors if "/api/3/<module>/" in e.message]


def test_prefix_before_an_id_is_an_error():
    assert _doubled("/api/3/alerts/{{ vars.steps.Find[0]['@id'] }}")


def test_the_id_alone_is_fine():
    assert not _doubled("{{ vars.steps.Find[0]['@id'] }}")


def test_prefix_before_a_uuid_is_fine():
    assert not _doubled("/api/3/alerts/{{ vars.steps.Find[0].uuid }}")
