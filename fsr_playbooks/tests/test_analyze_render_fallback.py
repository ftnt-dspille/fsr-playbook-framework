"""When the box's Jinja renderer cannot be reached, the walk renders locally.

Analyst sim: offline, every `analyze_playbook` on a playbook with a connector
step came back ok:false "params.ip: '_CassetteClient' object has no attribute
'post'" -- with no top-level `error`, so session reports showed a blank
failure. The model chased a defect that was not in the playbook. A renderer
that could not be reached is not a broken template; a broken template still
fails, because it fails the local renderer too.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import _shared, tools_analysis

_PB = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Note}
      - {name: Note, type: set_variable, vars: {x: "__TPL__"}}
"""


class _NoRender:
    """A client the walk can see but cannot render through."""


class _Refuses:
    def post(self, *_a, **_k):
        raise ConnectionError("render endpoint unreachable")


def _walk(monkeypatch, client, tpl):
    monkeypatch.setattr(_shared, "_live_client", lambda: client)
    return tools_analysis.step_through_playbook(yaml_text=_PB.replace("__TPL__", tpl))


def test_a_client_without_a_render_endpoint_falls_back_to_local(monkeypatch):
    out = _walk(monkeypatch, _NoRender(), "{{ 1 + 1 }}")
    assert out["ok"], out.get("error")
    note = next(t for t in out["trace"] if t["name"] == "Note")
    assert note.get("rendered_locally")


def test_an_unreachable_renderer_falls_back_to_local(monkeypatch):
    out = _walk(monkeypatch, _Refuses(), "{{ 'a' | upper }}")
    assert out["ok"], out.get("error")


def test_a_broken_template_is_still_an_error_and_says_why(monkeypatch):
    out = _walk(monkeypatch, _Refuses(), "{{ 'a' | upper ")
    assert not out["ok"]
    assert out["error"] and "Note" in out["error"]


def test_analyze_names_the_failure(monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: _Refuses())
    out = tools_analysis.analyze_playbook(yaml_text=_PB.replace("__TPL__", "{{ 'a' | upper "))
    assert out["ok"] is False and out.get("error")


def test_an_empty_playbook_is_not_reported_as_malformed(monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: None)
    out = tools_analysis.step_through_playbook(
        yaml_text="collection: C\nplaybooks:\n  - name: P\n    steps: []\n")
    assert out.get("code") == "empty_playbook", out
    assert "no steps yet" in out["error"]
