"""mcp_server.step_test — single-step variant of step_through_playbook.

Render-only path is tested offline (no live FSR). The execute path is
verified by stubbing run_op + _record_verification so we can assert the
verification side-effect without touching the live appliance.
"""
from __future__ import annotations

import textwrap

import pytest

pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp package not installed (pip install mcp)",
)

import fsr_core.mcp_server as mcp_server  # noqa: E402
import fsr_core.mcp_server.tools_execution  # noqa: E402, F401
import fsr_core.mcp_server._shared  # noqa: E402, F401


YAML = textwrap.dedent(
    """\
    playbooks:
      - name: Demo
        steps:
          - id: trigger
            type: start
            name: Trigger
            next: fetch
          - id: fetch
            type: connector
            name: Fetch Ticket
            arguments:
              connector: jira
              operation: get_ticket_details
              params:
                issue_key: JIR-1
            next: stop
          - id: stop
            type: stop
            name: Stop
    """
)


def test_step_not_found():
    r = mcp_server.step_test(YAML, step_id="nope")
    assert r["ok"] is False
    assert "not found" in r["error"]


def test_render_only_when_execute_disabled(monkeypatch):
    # Force the live-client out of the picture so render is a no-op.
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    r = mcp_server.step_test(YAML, step_id="fetch", execute_safe_ops=False)
    assert r["ok"] is True
    assert r["status"] == "rendered"
    assert r["rendered_args"]["connector"] == "jira"
    assert r["verification_recorded"] is False


def test_executes_safe_op_and_records_verification(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(
        mcp_server._shared, "_safe_op_category",
        lambda c, o: "investigation",
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        mcp_server.tools_execution, "run_op",
        lambda **kw: {"ok": True, "data": {"key": "JIR-1"},
                      "output_top_keys": ["key"]},
    )
    monkeypatch.setattr(
        mcp_server.tools_execution, "_record_verification",
        lambda c, o, s, n: calls.append((c, o, s)),
    )

    r = mcp_server.step_test(YAML, step_id="fetch")
    assert r["status"] == "executed"
    assert r["output"] == {"key": "JIR-1"}
    assert r["verification_recorded"] is True
    # Schema's CHECK constraint only allows 'tested_pass' / 'tested_fail' / 'seen';
    # step_test reuses the existing taxonomy so its writes don't violate it.
    assert calls == [("jira", "get_ticket_details", "tested_pass")]


def test_mock_result_on_step_overlays_into_render_context(monkeypatch):
    """A connector step's `arguments.mock_result` is overlaid into
    `vars.steps.<key>` so downstream steps' templates resolve against
    the saved mock without re-running. Mocks live on the step itself
    (not the sidecar) and win over samples on conflict."""
    yaml_with_mock = textwrap.dedent(
        """\
        playbooks:
          - name: Demo
            steps:
              - id: block
                type: connector
                name: Block IP on FortiGate
                arguments:
                  connector: fortigate-firewall
                  operation: block_ip_new
                  mock_result:
                    already_blocked: ["1.1.1.1"]
                    newly_blocked: []
              - id: fetch
                type: connector
                name: Fetch Ticket
                arguments:
                  connector: jira
                  operation: get_ticket_details
                  params:
                    issue_key: "{{ vars.steps.Block_IP_on_FortiGate.already_blocked[0] }}"
              - type: end
                name: Stop
        """
    )
    class _Stub:
        def post(self, _path, data):
            from jinja2 import Environment
            return {"result": Environment().from_string(data["template"]).render(**data["values"])}
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: _Stub())

    r = mcp_server.step_test(yaml_with_mock, step_id="fetch",
                             execute_safe_ops=False)
    assert r["ok"] is True, r
    assert r["rendered_args"]["params"]["issue_key"] == "1.1.1.1"


def test_run_op_receives_inner_params_not_envelope(monkeypatch):
    """Regression: step_test must pass just the inner `params:` dict to
    run_op, not the full rendered envelope. The connector matches its
    declared parameters at the top level — sending `{connector, operation,
    params: {...}}` makes every declared param look 'not provided'."""
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(mcp_server._shared, "_safe_op_category", lambda c, o: "investigation")
    captured: dict = {}
    def _run_op(**kw):
        captured.update(kw)
        return {"ok": True, "data": {}, "output_top_keys": []}
    monkeypatch.setattr(mcp_server.tools_execution, "run_op", _run_op)
    monkeypatch.setattr(mcp_server.tools_execution, "_record_verification",
                        lambda *a, **kw: None)
    r = mcp_server.step_test(YAML, step_id="fetch")
    assert r["ok"] is True
    # Only the inner params land at run_op — no envelope keys leak through.
    assert captured["params"] == {"issue_key": "JIR-1"}
    assert "connector" not in captured["params"]
    assert "operation" not in captured["params"]


def test_unsafe_op_returns_needs_confirm_without_executing(monkeypatch):
    """Op name without a safe prefix => `needs_confirm`, no run_op call.
    UI uses the risk + category payload to render its warning + confirm
    button before letting the user re-invoke with confirm=True."""
    bad_yaml = YAML.replace("get_ticket_details", "delete_ticket")
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(mcp_server._shared, "_safe_op_category", lambda c, o: "remediation")

    def _boom(**kw):
        raise AssertionError("run_op must not be called pre-confirm")
    monkeypatch.setattr(mcp_server.tools_execution, "run_op", _boom)

    r = mcp_server.step_test(bad_yaml, step_id="fetch")
    assert r["status"] == "needs_confirm"
    assert r["risk"] in {"destructive", "investigation"}  # not "safe"
    assert r["risk_category"] == "remediation"
    assert r["verification_recorded"] is False


def test_unsafe_op_executes_when_user_confirms(monkeypatch):
    """confirm=True acknowledges the risk and lets run_op fire. Forwards
    confirm=True to run_op so the destructive-op guardrail there also
    sees the explicit user approval."""
    bad_yaml = YAML.replace("get_ticket_details", "delete_ticket")
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    monkeypatch.setattr(mcp_server._shared, "_safe_op_category", lambda c, o: "remediation")

    captured: dict = {}
    def _run_op(**kw):
        captured.update(kw)
        return {"ok": True, "data": {"deleted": "JIR-1"}, "output_top_keys": ["deleted"]}
    monkeypatch.setattr(mcp_server.tools_execution, "run_op", _run_op)
    monkeypatch.setattr(mcp_server.tools_execution, "_record_verification",
                        lambda *a, **kw: None)

    r = mcp_server.step_test(bad_yaml, step_id="fetch", confirm=True)
    assert r["status"] == "executed", r
    assert r["output"] == {"deleted": "JIR-1"}
    assert captured.get("confirm") is True


def test_step_lookup_by_name_with_underscores(monkeypatch):
    """Slugified-name lookup matches the IR's id-synthesis algorithm
    (lowercase, non-alphanum → `_`) so visual-editor nodes whose ids were
    synthesized from `name:` resolve back to the right YAML step."""
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    r = mcp_server.step_test(YAML, step_id="fetch_ticket", execute_safe_ops=False)
    assert r["ok"] is True
    assert r["step_id"] == "fetch"


def test_samples_sidecar_overlays_into_render_context(monkeypatch):
    """`# fsrpb:samples` values get merged into vars.steps.<id> so a
    downstream step's Jinja templates resolve against the author's
    synthetic answers without a live FSR run."""
    yaml_with_sample = textwrap.dedent(
        """\
        playbooks:
          - name: Demo
            steps:
              - type: manual_input
                name: Get IP Address
                arguments:
                  inputs:
                    - name: ip_address
                      kind: ipv4
                options:
                  - display: Block
                    primary: true
                    next: Fetch Ticket
              - id: fetch
                type: connector
                name: Fetch Ticket
                arguments:
                  connector: jira
                  operation: get_ticket_details
                  params:
                    issue_key: "{{ vars.steps.Get_IP_Address.input.ip_address }}"
              - type: end
                name: Stop
        # fsrpb:samples
        # {
        #   "Demo": {
        #     "get_ip_address": { "input": { "ip_address": "1.2.3.4" } }
        #   }
        # }
        # fsrpb:samples-end
        """
    )
    # Stub the live client so _render goes through the rendering path
    # and returns the post() body as-is.
    class _Stub:
        def post(self, _path, data):
            tpl = data["template"]
            # Echo back what the FSR engine would resolve — we just need
            # to prove the sample reached the rendering context.
            from jinja2 import Environment
            return {"result": Environment().from_string(tpl).render(**data["values"])}
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: _Stub())

    r = mcp_server.step_test(yaml_with_sample, step_id="fetch",
                             execute_safe_ops=False)
    assert r["ok"] is True, r
    assert r["rendered_args"]["params"]["issue_key"] == "1.2.3.4"


def test_step_lookup_by_synthesized_id_when_yaml_omits_id(monkeypatch):
    """Real-world repro: drafts written by the visual editor have no
    `id:` on steps. Visual node carries the slugified name as id; lookup
    must find the step anyway."""
    yaml_no_ids = textwrap.dedent(
        """\
        playbooks:
          - name: Demo
            steps:
              - type: start
                name: Start
                next: Block IP on FortiGate
              - type: connector
                name: Block IP on FortiGate
                arguments:
                  connector: fortigate-firewall
                  operation: block_ip_new
        """
    )
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)
    r = mcp_server.step_test(yaml_no_ids,
                             step_id="block_ip_on_fortigate",
                             execute_safe_ops=False)
    assert r["ok"] is True, r
    assert r["step_id"] == "block_ip_on_fortigate"
