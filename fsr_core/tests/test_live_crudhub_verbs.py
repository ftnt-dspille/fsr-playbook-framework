"""The crudhub client/session shims must expose every HTTP verb the push path
uses. e2e.runner._push does PUT-then-POST and _hard_purge does DELETE; the
agent run_op wrap does PUT (debug) + DELETE (cleanup). Missing verbs used to
AttributeError on the agent box and break push_playbook / dry_run_playbook.
"""
from __future__ import annotations

from fsr_core.mcp_server import _live_crudhub as lc


def _recorder():
    calls = []

    def mr(url, method, body=None):
        calls.append((method, url, body))
        return {"ok": True}

    return mr, calls


def test_client_exposes_all_verbs():
    mr, calls = _recorder()
    client = lc.CrudhubLiveClient(mr)
    for verb in ("get", "post", "put", "delete"):
        assert callable(getattr(client, verb)), f"client missing {verb}"
    for verb in ("get", "post", "put", "delete"):
        assert callable(getattr(client.session, verb)), f"session missing {verb}"


def test_session_put_and_delete_route_through_make_request():
    mr, calls = _recorder()
    client = lc.CrudhubLiveClient(mr)
    client.session.put("/api/3/workflows/abc", json={"debug": True})
    client.session.delete("/api/3/delete/workflow_collections?$hardDelete=true",
                          json={"ids": ["c1"]})
    methods = {c[0] for c in calls}
    assert methods == {"PUT", "DELETE"}
    assert ("PUT", "/api/3/workflows/abc", {"debug": True}) in calls


def test_client_put_routes_through_make_request():
    mr, calls = _recorder()
    client = lc.CrudhubLiveClient(mr)
    client.put("/api/3/workflow_collections/u1", data={"name": "x"})
    assert calls == [("PUT", "/api/3/workflow_collections/u1", {"name": "x"})]


def test_bodyless_delete_sends_no_body():
    """Single-row `?$hardDelete=true` deletes must NOT carry a body. Passing an
    empty `{}` body makes make_request issue a no-op that leaves the row in
    place (the scratch-collection leak fixed in 0.3.64). Both the session and
    the client must forward body=None, not {}, when no body is supplied."""
    mr, calls = _recorder()
    client = lc.CrudhubLiveClient(mr)
    url = "/api/3/workflow_collections/u1?$hardDelete=true&$showDeleted=true"
    client.session.delete(url)
    client.delete(url)
    assert calls == [("DELETE", url, None), ("DELETE", url, None)], calls
