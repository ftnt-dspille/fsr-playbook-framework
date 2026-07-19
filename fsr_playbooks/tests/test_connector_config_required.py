"""find_connector surfaces whether a connector needs a configuration (S3 residual).

The S3 build-persona eval's one remaining failure: the model called
`list_configured_connectors`, didn't see cyops_utilities (a config-LESS utility,
config_count=0), concluded "connector not available", and bailed to a skeleton
with an undefined input. cyops_utilities needs no config — its ops run with
`config: ''`. `find_connector` now returns a `config_required` bool per match and
a note that absence from the configured list is not unavailability.
"""
from fsr_playbooks.mcp_server.tools_discovery import (
    _connector_config_required as needs_config,
    find_connector,
)


def test_config_required_helper():
    # config-LESS → False
    for empty in (None, "", "{}", '{"fields": []}', "[]"):
        assert needs_config(empty) is False, f"{empty!r} should be config-less"
    # config-REQUIRING → True
    assert needs_config('{"fields": [{"name": "server_url"}]}') is True
    assert needs_config('[{"name": "host"}]') is True
    # malformed blob → treated as config-less (fail open, never crash)
    assert needs_config("not json{{") is False


def test_find_connector_marks_config_required_per_match():
    r = find_connector("utilities")
    matches = r.get("matches") or []
    assert matches, "expected at least one utilities-category match in the catalog"
    for m in matches:
        assert isinstance(m.get("config_required"), bool), \
            "every match must carry a config_required bool"
    # If any match is config-less, the note must steer away from the
    # 'absent-from-configured-list == unavailable' misread.
    if any(not m["config_required"] for m in matches):
        assert "config: ''" in (r.get("note") or ""), \
            "config-less matches must include the `config: ''` guidance note"
