"""WIRE_SHAPE_GAP_PLAN Phase 3 — the universal step envelope.

`when`, `ignore_errors`, `do_until`, `message`, `agent`, `apply_async`,
`pickFromTenant` are valid on (nearly) every step type. Authors may write them
as top-level step keys (instead of burying them under `arguments:`), plus three
friendly sugars: `retry` → `do_until`, `on_remote` → `agent`/`pickFromTenant`,
`post_comment` → `message`. The parser hoists/expands; the resolver+emitter only
ever see the canonical wire keys.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks._db import PACKAGED_SLIM_DB


def _emit(yaml_text: str):
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    steps: dict[str, dict] = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("@type") == "WorkflowStep":
                steps[o.get("name")] = o.get("arguments") or {}
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(res.fsr_json)
    return res, steps


def _upd(body: str) -> str:
    return f"""
collection: T
playbooks:
  - name: P
    steps:
      - {{name: Start, type: start, next: Upd}}
      - name: Upd
        type: update_record
{body}
        arguments:
          module: incidents
          resource: {{status: Closed}}
"""


def _errs(res):
    return [e.message for e in res.errors if e.severity != "warning"]


# ---- top-level hoist -------------------------------------------------------

def test_top_level_envelope_keys_hoisted():
    res, steps = _emit(_upd(
        '        ignore_errors: true\n'
        '        apply_async: true\n'
        '        do_until: {condition: "{{ vars.done }}", retries: 3, delay: 5}\n'
        '        agent: "lab-collector"\n'
    ))
    assert res.ok, _errs(res)
    a = steps["Upd"]
    assert a["ignore_errors"] is True
    assert a["apply_async"] is True
    assert a["do_until"] == {"condition": "{{ vars.done }}", "retries": 3, "delay": 5}
    assert a["agent"] == "lab-collector"


def test_top_level_and_arguments_conflict_errors():
    res, _ = _emit("""
collection: T
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, next: Upd}
      - name: Upd
        type: update_record
        ignore_errors: true
        arguments:
          module: incidents
          ignore_errors: false
          resource: {status: Closed}
""")
    assert not res.ok
    assert any("ignore_errors" in m and "pick one" in m for m in _errs(res))


# ---- retry sugar -----------------------------------------------------------

def test_retry_sugar_maps_to_do_until():
    res, steps = _emit(_upd(
        '        retry: {times: 3, delay: 5, until: "{{ vars.done }}"}\n'
    ))
    assert res.ok, _errs(res)
    assert steps["Upd"]["do_until"] == {
        "condition": "{{ vars.done }}", "retries": 3, "delay": 5,
    }


def test_retry_conflicts_with_do_until():
    res, _ = _emit(_upd(
        '        retry: {times: 3}\n'
        '        do_until: {condition: "{{ x }}", retries: 1}\n'
    ))
    assert not res.ok
    assert any("retry" in m and "pick one" in m for m in _errs(res))


def test_retry_rejects_unknown_keys():
    res, _ = _emit(_upd('        retry: {times: 3, wait: 5}\n'))
    assert not res.ok
    assert any("unknown keys" in m for m in _errs(res))


# ---- on_remote sugar -------------------------------------------------------

def test_on_remote_pick_from_record():
    res, steps = _emit(_upd('        on_remote: pick_from_record\n'))
    assert res.ok, _errs(res)
    a = steps["Upd"]
    assert a["agent"] == "Pick From Record Ownership"
    assert a["pickFromTenant"] is True


def test_on_remote_named_agent():
    res, steps = _emit(_upd('        on_remote: lab-collector\n'))
    assert res.ok, _errs(res)
    a = steps["Upd"]
    assert a["agent"] == "lab-collector"
    assert a["pickFromTenant"] is False


def test_on_remote_conflicts_with_agent():
    res, _ = _emit(_upd(
        '        on_remote: lab-collector\n'
        '        agent: other\n'
    ))
    assert not res.ok
    assert any("on_remote" in m and "pick one" in m for m in _errs(res))


# ---- post_comment sugar ----------------------------------------------------

def test_post_comment_expands_to_message_block():
    res, steps = _emit(_upd('        post_comment: "auto-added by triage"\n'))
    assert res.ok, _errs(res)
    msg = steps["Upd"]["message"]
    assert isinstance(msg, dict)
    assert "auto-added by triage" in msg["content"]


def test_post_comment_conflicts_with_message():
    res, _ = _emit(_upd(
        '        post_comment: "hi"\n'
        '        message: {content: "there"}\n'
    ))
    assert not res.ok
    assert any("post_comment" in m and "pick one" in m for m in _errs(res))


# ---- message block: `tenant` (MSSP content) --------------------------------

def test_message_block_accepts_tenant():
    """Shipped Fortinet content addresses a comment at a tenant.

    The allowlist rejected `tenant` outright, so MSSP-aware stock playbooks
    could not compile at all — and an agent asked to edit one could not return
    a compiling result no matter how good its edit was. Confirmed against 400
    stock playbooks pulled from a live appliance: `tenant` is the ONLY message
    key real content uses outside the original allowlist, and it appears in 9
    of them. Widened on that evidence, not on a remembered error string.
    """
    res, steps = _emit(_upd(
        '        message: {content: "escalated", '
        'tenant: "/api/3/tenants/abc-123"}\n'
    ))
    assert res.ok, _errs(res)
    # Accepting the key but dropping it on the way out would trade a loud
    # error for silent data loss, which is the worse of the two.
    assert steps["Upd"]["message"]["tenant"] == "/api/3/tenants/abc-123"


def test_message_block_omits_tenant_when_absent():
    """The wire shape must not grow a key the product did not send."""
    res, steps = _emit(_upd('        message: {content: "plain"}\n'))
    assert res.ok, _errs(res)
    assert "tenant" not in steps["Upd"]["message"]


def test_message_block_still_rejects_a_genuinely_unknown_key():
    """Widening for `tenant` must not turn the allowlist into a free-for-all."""
    res, _ = _emit(_upd(
        '        message: {content: "x", bogusKey: "y"}\n'))
    assert not res.ok
    assert any("bogusKey" in m for m in _errs(res))
