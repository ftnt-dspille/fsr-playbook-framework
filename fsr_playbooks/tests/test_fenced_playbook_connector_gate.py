"""A playbook in the reply text must pass the same connector check as an offer.

The widget saves the LAST ```yaml fence in the reply over the open record, so a
fence is a delivery. The offer gate (`offer_uses_unconfigured_connector`) only
ever saw offer-card YAML, so a turn that ended on a capability gap and then put
a complete playbook calling an unconfigured connector in its reply was handed to
the analyst unchecked. The terminal-round self-repair now runs the same check
and sends the model back with the connector named.

Each test drives the real provider loop and checks the requests it sent.
"""
from __future__ import annotations

from unittest.mock import patch

from test_openai_build_progress_forced import _BUILD_TOOLS, _delta_chunk, _usage_chunk
from test_unexecuted_tool_calls_not_replayed import _close_round, _run_openai_like

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.mcp_server import tools_connector_discovery as _tcd

_LISTING_NO_FALCON = {"configured": [{"name": "fortinet-fortiedr", "status": "Completed"}]}

_FALCON_REPLY = """The CrowdStrike Falcon connector is not configured, so here is the playbook.

```yaml
playbooks:
  - name: Isolate host
    parameters: []
    steps:
      - name: Start
        type: start
        module: alerts
        next: Lookup
      - name: Lookup
        type: connector
        connector: crowd-strike-falcon
        operation: list_endpoint
        params:
          filter_str: "ip: 10.0.0.1"
        next: End
      - name: End
        type: end
```
"""

_FORTIEDR_REPLY = """Isolating through FortiEDR, which is configured.

```yaml
playbooks:
  - name: Isolate host
    parameters: []
    steps:
      - name: Start
        type: start
        module: alerts
        next: Isolate
      - name: Isolate
        type: connector
        connector: fortinet-fortiedr
        operation: isolate_collector
        next: End
      - name: End
        type: end
```
"""


def _reply_round(text):
    return [_delta_chunk(content=text), _delta_chunk(finish="stop"), _usage_chunk()]


def _with_listing(listing):
    """Patch the box's connector list and the catalog's config question, so the
    test does not depend on a reference database being present."""
    if isinstance(listing, Exception):
        def _raise(*_a, **_kw):
            raise listing
        lister = patch.object(_tcd, "list_configured_connectors", side_effect=_raise)
    else:
        lister = patch.object(_tcd, "list_configured_connectors", return_value=listing)
    return lister


def _user_texts(messages):
    return [str(m.get("content")) for m in messages if m.get("role") == "user"]


def test_a_reply_fence_calling_an_unconfigured_connector_is_sent_back():
    """Red before the fix: the fence compiles and nothing asks about its
    connector, so the loop ends after one request."""
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.llm.agent_loop.compile_errors", return_value=None), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        requests, _, _ = _run_openai_like(
            OpenAIProvider, [_reply_round(_FALCON_REPLY), _close_round()], _BUILD_TOOLS)
    assert len(requests) >= 2, "a playbook calling an unconfigured connector was delivered"
    follow_up = _user_texts(requests[1])
    assert any("crowd-strike-falcon" in t and "not configured" in t for t in follow_up), (
        f"the repair round did not name the connector: {follow_up[-1:]}")


def test_a_reply_fence_calling_a_configured_connector_is_delivered_unchanged():
    """Control: the same loop with a configured connector sends no repair."""
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.llm.agent_loop.compile_errors", return_value=None), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        requests, _, _ = _run_openai_like(
            OpenAIProvider, [_reply_round(_FORTIEDR_REPLY), _close_round()], _BUILD_TOOLS)
    for msgs in requests:
        assert not any("not configured" in t for t in _user_texts(msgs))


def test_unconfigured_connector_is_named_by_the_check():
    from fsr_playbooks.mcp_server.tools_emit import fenced_connector_errors
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        err = fenced_connector_errors(_FALCON_REPLY.split("```yaml")[1].split("```")[0])
    assert err and "crowd-strike-falcon" in err and "not configured" in err


def test_configured_connector_passes_the_check():
    from fsr_playbooks.mcp_server.tools_emit import fenced_connector_errors
    with _with_listing(_LISTING_NO_FALCON):
        err = fenced_connector_errors(_FORTIEDR_REPLY.split("```yaml")[1].split("```")[0])
    assert err is None


def test_undecidable_listing_refuses_with_a_retry_message():
    from fsr_playbooks.mcp_server.tools_emit import fenced_connector_errors
    """A listing that raises cannot decide. The check refuses and says so,
    rather than letting the playbook through."""
    with _with_listing(RuntimeError("connection refused")):
        err = fenced_connector_errors(_FALCON_REPLY.split("```yaml")[1].split("```")[0])
    assert err and "could not verify connectors" in err


def test_no_connector_steps_never_asks_the_listing():
    from fsr_playbooks.mcp_server.tools_emit import fenced_connector_errors
    """Nothing to decide: a playbook that calls no connector is not gated on
    the listing at all."""
    yaml_text = "playbooks:\n  - name: x\n    steps:\n      - name: S\n        type: start\n"
    with _with_listing(RuntimeError("must not be called")):
        assert fenced_connector_errors(yaml_text) is None
