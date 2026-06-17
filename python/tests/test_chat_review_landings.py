"""Regression tests for the resolver fixes landed after session c44c6e36.

Each fix corresponds to a gap surfaced by the deep review of the
"Confirm Before Block" thumbs-down. See
`memory/project_fsrpb_chat_review_landings_2026_05_07.md` and the
top-of-TODO.md follow-up block for the change context.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml


# ---- Trigger defaults (Issue 1) ----------------------------------

def test_record_action_trigger_defaults_module_and_button_label(db_path):
    """`start` with `module:` switches into cybersponse.action; missing
    `module:`/`button_label:` should become warnings (not errors) and
    default to [alerts, incidents] + the playbook name."""
    text = """
collection: T
playbooks:
  - name: My Action Playbook
    steps:
      - type: start
        name: Start
        arguments:
          module: alerts
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    msgs = " | ".join(w.message for w in r.warnings)
    assert "button_label" in msgs
    assert "My Action Playbook" in msgs
    # Find the resolved start step args
    start = r.ir.playbooks[0].steps[0]
    assert start.arguments.get("title") == "My Action Playbook"


def test_post_create_trigger_defaults_module_to_alerts_and_incidents(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start_on_create
        name: Start
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    msgs = " | ".join(w.message for w in r.warnings)
    assert "[alerts, incidents]" in msgs
    start = r.ir.playbooks[0].steps[0]
    assert start.arguments.get("resources") == ["alerts", "incidents"]


# ---- ipv4/email/url kind hint (Issue 2) --------------------------

def test_text_kind_on_ip_address_field_warns_to_use_ipv4(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Ask
      - type: manual_input
        name: Ask
        arguments:
          title: Enter IP
          inputs:
            - {name: ip_address, kind: text, label: IP Address, required: true}
        options:
          - display: ok
            next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    msg = " | ".join(w.message for w in r.warnings)
    assert "'ipv4'" in msg and "ip_address" in msg


def test_text_kind_on_email_field_warns_to_use_email(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Ask
      - type: manual_input
        name: Ask
        arguments:
          title: Email me
          inputs:
            - {name: contact_email, kind: text}
        options:
          - display: ok
            next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msg = " | ".join(w.message for w in r.warnings)
    assert "'email'" in msg


def test_specific_kind_no_warning(db_path):
    """ipv4 already on the field -> no nag."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Ask
      - type: manual_input
        name: Ask
        arguments:
          title: Enter IP
          inputs:
            - {name: ip_address, kind: ipv4}
        options:
          - display: ok
            next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ok
    assert not any("ipv4" in w.message and "switch to" in w.message
                   for w in r.warnings)


# ---- Connector flat-arg auto-lift (Issue 4 prerequisite) ---------

def test_connector_flat_args_lift_into_params(db_path):
    """Top-level keys matching known op params get hoisted into
    arguments.params:, with a warning, so the agent's most common
    connector-step mistake still produces a usable playbook."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: B
      - type: connector
        name: B
        arguments:
          connector: fortigate-firewall
          operation: block_ip_new
          method: "Quarantine Based"
          ip_addresses: "1.2.3.4"
          time_to_live: "12 Hour"
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ir is not None
    step = r.ir.playbooks[0].steps[1]
    params = step.arguments.get("params") or {}
    assert "method" in params and "ip_addresses" in params and "time_to_live" in params
    msgs = " | ".join(w.message for w in r.warnings)
    assert "lifted into" in msgs


# ---- Conditional-visibility checker (Issue 4) --------------------

def test_visibility_warns_on_inactive_branch_param(db_path):
    """block_ip_new.ip_block_policy is only valid when method='Policy
    Based'. Setting it under method='Quarantine Based' should warn."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: B
      - type: connector
        name: B
        arguments:
          connector: fortigate-firewall
          operation: block_ip_new
          params:
            method: "Quarantine Based"
            ip_block_policy: "WrongBranch"
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msgs = " | ".join(w.message for w in r.warnings)
    assert "ip_block_policy" in msgs and "Policy Based" in msgs


def test_visibility_silent_when_branch_matches(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: B
      - type: connector
        name: B
        arguments:
          connector: fortigate-firewall
          operation: block_ip_new
          params:
            method: "Policy Based"
            ip_block_policy: "MyPolicy"
            ip_type: "IPv4"
            ip: "1.2.3.4"
            ngfw_mode: "profile-based"
            vdom: "root"
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msgs = " | ".join(w.message for w in r.warnings)
    assert "ip_block_policy" not in msgs or "only valid" not in msgs


# ---- set_variable message: sugar (Issue 3) -----------------------

def test_message_sugar_wraps_plain_text_and_resolves_tags(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars:
          status: approved
        message:
          content: hello world
          tags: [auto_block]
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ir is not None
    args = r.ir.playbooks[0].steps[1].arguments
    assert args.get("status") == "approved"  # user var preserved
    msg = args.get("message")
    assert isinstance(msg, dict)
    assert msg["content"] == "<p>hello world</p>"  # auto-wrap
    assert msg["tags"] == ["/api/3/tags/auto_block"]
    assert msg["type"].startswith("/api/3/picklists/")
    assert msg["thread"] is False
    assert "records" not in msg  # omitted -> FSR auto-attaches


def test_message_sugar_record_override(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars:
          x: 1
        message:
          content: "<p>already html</p>"
          record: "{{ vars.alert_iri }}"
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msg = r.ir.playbooks[0].steps[1].arguments["message"]
    assert msg["content"] == "<p>already html</p>"  # not double-wrapped
    assert msg["records"] == "{{ vars.alert_iri }}"


def test_message_sugar_does_not_collide_with_reserved_var_rewriter(db_path):
    """`message` is in _RESERVED_VARS_KEYS — when it's a dict (the
    record-message sugar) the auto-rewriter must leave it alone."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars: {}
        message:
          content: hi
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    args = r.ir.playbooks[0].steps[1].arguments
    assert "message" in args and isinstance(args["message"], dict)
    assert "message_var" not in args  # rewriter did NOT rename


def test_message_type_friendly_names_resolve_to_comment_type_picklist(db_path):
    """`type: Comment` and `type: ActionLog` map to the Comment Type
    picklist's stock IRIs. Case-insensitive."""
    for friendly, expected_uuid in [
        ("Comment",   "ff599189-3eeb-4c86-acb0-a7915e85ac3b"),
        ("comment",   "ff599189-3eeb-4c86-acb0-a7915e85ac3b"),
        ("ActionLog", "1165899b-7091-4291-aafc-487c4309e8ff"),
        ("actionlog", "1165899b-7091-4291-aafc-487c4309e8ff"),
    ]:
        text = f"""
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars: {{x: 1}}
        message:
          content: hi
          type: {friendly}
        next: End
      - type: end
        name: End
"""
        r = compile_yaml(text, db_path)
        msg = r.ir.playbooks[0].steps[1].arguments["message"]
        assert msg["type"] == f"/api/3/picklists/{expected_uuid}", friendly


def test_message_type_unknown_friendly_warns_and_defaults(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars: {x: 1}
        message:
          content: hi
          type: Whatever
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msgs = " | ".join(w.message for w in r.warnings)
    assert "Whatever" in msgs and "Comment" in msgs
    msg = r.ir.playbooks[0].steps[1].arguments["message"]
    assert msg["type"].endswith("ff599189-3eeb-4c86-acb0-a7915e85ac3b")


def test_message_tags_accept_any_name_and_full_iris(db_path):
    """Tags are free-form: any name synthesizes /api/3/tags/<name>;
    a full IRI passes through unchanged."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars: {x: 1}
        message:
          content: hi
          tags:
            - brand_new_unseen_tag
            - "/api/3/tags/already-an-iri"
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    msg = r.ir.playbooks[0].steps[1].arguments["message"]
    assert msg["tags"] == [
        "/api/3/tags/brand_new_unseen_tag",
        "/api/3/tags/already-an-iri",
    ]


def test_message_sugar_requires_content(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: R
      - type: set_variable
        name: R
        vars: {x: 1}
        message:
          tags: [foo]
        next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("content" in e.message for e in r.errors)
