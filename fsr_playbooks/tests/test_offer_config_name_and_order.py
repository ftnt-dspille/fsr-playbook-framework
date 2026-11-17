"""Both offer cards refuse a `config:` name the box does not have, and the
new-playbook card lists steps in flow order.

Live (classroom): the box's FortiAIGate config was named one way, the model
wrote 'student19 FortiAIGate', and the card offered it. verify checks config
names only under live_probe, and neither offer gate checked them, so the step
would fail on its first run.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server import tools_emit
from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

YAML = """\
playbooks:
  - name: Suspend AI Access
    parameters: []
    steps:
      - name: Revoke Key
        type: connector
        connector: fortigate-firewall
        operation: block_ip
        config: {cfg}
      - name: Read Key Id
        type: set_variable
        next: Revoke Key
        vars:
          key_id: abc
      - name: Start
        type: start
        module: alerts
        next: Read Key Id
"""


@pytest.fixture
def box(monkeypatch):
    monkeypatch.setattr(tcd, "list_configured_connectors",
                        lambda **kw: {"configured": [{"name": "fortigate-firewall"}]})
    names = {"fortigate-firewall": ["Student19 FortiAIGate", "Lab Gate",
                                    "student04 FortiAIGate", "student10 FortiAIGate",
                                    "sutdent09 FortiAIGate"]}
    monkeypatch.setattr(tools_emit, "_box_config_names", lambda: names)
    return names


def _offer(cfg):
    return _offer_from_yaml("c1", "save it", YAML.format(cfg=cfg),
                            title_suggestion=None, editable_title=True)


@pytest.mark.parametrize("cfg", ["student19 FortiAIGate", "Student19FortiAIGate",
                                 "Student19 FortiAIGate ", "nope"])
def test_unknown_config_name_is_refused(box, cfg):
    res = _offer(repr(cfg))
    if cfg.strip() == "Student19 FortiAIGate":
        assert res["ok"] is True       # surrounding spaces are not a new name
        return
    assert res["ok"] is False
    assert res["code"] == "offer_uses_unknown_config"
    [bad] = res["unknown_configs"]
    assert bad["step"] == "Revoke Key"
    assert bad["config"] == cfg.strip()
    if cfg != "nope":
        assert bad["near"] == ["Student19 FortiAIGate"]
    else:
        assert bad["near"] == []


@pytest.mark.parametrize("cfg", ["'Student19 FortiAIGate'", "'Lab Gate'",
                                 "'{{ vars.cfg }}'", "''"])
def test_exact_templated_or_empty_config_is_offered(box, cfg):
    assert _offer(cfg)["ok"] is True


def test_fails_open_when_the_box_cannot_be_asked(box, monkeypatch):
    monkeypatch.setattr(tools_emit, "_box_config_names", lambda: None)
    assert _offer("'whatever'")["ok"] is True


def test_new_playbook_card_lists_steps_in_flow_order(box):
    res = _offer("'Lab Gate'")
    assert [o["label"] for o in res["card"]["ops_summary"]] == \
        ["Start", "Read Key Id", "Revoke Key"]


@pytest.mark.parametrize("cfg,near", [
    # The box's own config is misspelled; the model wrote it correctly.
    ("student09 FortiAIGate", ["sutdent09 FortiAIGate"]),
    # No config for this student: never suggest a different student's.
    ("student05 FortiAIGate", []),
    ("student04 fortiaigate", ["student04 FortiAIGate"]),
])
def test_suggests_only_an_unambiguous_match(box, cfg, near):
    res = _offer(repr(cfg))
    assert res["code"] == "offer_uses_unknown_config"
    assert res["unknown_configs"][0]["near"] == near
    if not near:
        assert "ask the analyst" in res["message"]
        assert res["suggestions"] == []
