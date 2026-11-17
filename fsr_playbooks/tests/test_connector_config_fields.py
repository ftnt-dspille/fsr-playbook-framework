"""CFG001/CFG002: configuration fields the code never reads, and a hard-coded host."""
import json

from fsr_playbooks.connectors import validate_connector


def _connector(tmp_path, fields, code):
    (tmp_path / "info.json").write_text(json.dumps({"name": "c", "version": "1.0.0",
                                                    "configuration": {"fields": fields}, "operations": []}))
    (tmp_path / "operations.py").write_text(code)
    return {i.code for i in validate_connector(tmp_path)}


def test_an_unused_field_and_hardcoded_host_are_flagged(tmp_path):
    codes = _connector(tmp_path, [{"name": "api_key"}], "import requests\nrequests.get('https://x.example.com')\n")
    assert {"CFG001", "CFG002"} <= codes


def test_a_read_server_field_is_clean(tmp_path):
    codes = _connector(tmp_path, [{"name": "server"}],
                       "import requests\ndef op(config, params):\n    return requests.get(config.get('server'))\n")
    assert not {"CFG001", "CFG002"} & codes
