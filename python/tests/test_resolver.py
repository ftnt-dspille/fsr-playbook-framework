from fsr_core.compiler import compile_yaml
from fsr_core.compiler.errors import ErrorCode


def _yaml(steps_block: str) -> str:
    return f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: target
      - name: target
{steps_block}
"""


def test_unknown_step_type_suggests(db_path):
    text = _yaml("        type: connetor\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_STEP_TYPE)
    assert e.near == "connector"
    assert "did you mean" in (e.suggestion or "")


def test_type_for_each_emits_modifier_not_type_hint(db_path):
    """Regression: agents commonly write `type: for_each` thinking it's
    a step type. The diagnostic must explicitly say it's a modifier so
    the agent fixes the structural mistake on the first iteration
    instead of guessing alternative step names."""
    text = _yaml(
        "        type: for_each\n"
        "        arguments:\n"
        "          list: '{{ vars.x }}'\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_STEP_TYPE)
    assert "modifier" in e.message.lower()
    assert "sibling to `arguments" in (e.message or "")


def test_for_each_on_decision_step_rejected(db_path):
    """Parser allowlist: for_each on a control-flow host is rejected
    with a clear diagnostic instead of compiling clean."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: gate
      - name: gate
        type: decision
        for_each:
          item: "{{ vars.xs }}"
        conditions:
          - display: yes
            when: "{{ true }}"
            next: gate
          - display: else
            default: true
            next: gate
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    msgs = " ".join(e.message for e in r.errors)
    assert "for_each is not supported" in msgs


def test_unknown_connector_suggests(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortimanger\n"
        "          operation: get_devices\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    codes = {e.code for e in r.errors}
    assert ErrorCode.UNKNOWN_CONNECTOR in codes


def test_unknown_operation_suggests(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortinet-fortisiem\n"
        "          operation: get_org_name_by_org_idz\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_OPERATION)
    assert e.near == "get_org_name_by_org_id"


def test_unknown_param(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: fortinet-fortisiem\n"
        "          operation: get_org_name_by_org_id\n"
        "          params:\n"
        "            domain_id_typo: x\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.UNKNOWN_PARAM for e in r.errors)


def test_picklist_enum_rejected_with_did_you_mean(db_path):
    """apivoid.dnspropagation.dns_record_type accepts ['A','AAAA','NS',
    'MX','TXT','SRV','SOA','CNAME','SPF','CAA']. A near-miss value
    should be rejected with a fuzzy suggestion."""
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: apivoid\n"
        "          operation: dnspropagation\n"
        "          params:\n"
        "            dns_record_type: AAA\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "dns_record_type" in (e.message or "")]
    assert bad, [e.to_dict() for e in r.errors]
    assert "'AAAA'" in bad[0].message


def test_picklist_enum_case_mismatch_emits_case_hint(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: apivoid\n"
        "          operation: dnspropagation\n"
        "          params:\n"
        "            dns_record_type: aaaa\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "dns_record_type" in (e.message or "")]
    assert bad
    assert "case-sensitive" in bad[0].message
    assert "'AAAA'" in bad[0].message


def test_picklist_jinja_value_skipped(db_path):
    """Jinja-templated values are deferred to runtime — no static
    enum complaint, since we can't resolve the expression."""
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: apivoid\n"
        "          operation: dnspropagation\n"
        "          params:\n"
        "            dns_record_type: \"{{ vars.input.params.t }}\"\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "dns_record_type" in (e.message or "")
           and "not in enum" in (e.message or "")]
    assert not bad


def test_integer_param_rejects_non_numeric_literal(db_path):
    """aws-access-analyzer.list_analyzers.size is type=integer.
    A non-numeric literal should be rejected at compile time."""
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: aws-access-analyzer\n"
        "          operation: list_analyzers\n"
        "          params:\n"
        "            type: ACCOUNT\n"
        "            size: many\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "size" in (e.message or "")
           and "integer" in (e.message or "")]
    assert bad, [e.to_dict() for e in r.errors]


def test_integer_param_accepts_numeric_string(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: aws-access-analyzer\n"
        "          operation: list_analyzers\n"
        "          params:\n"
        "            type: ACCOUNT\n"
        "            size: \"25\"\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "size" in (e.message or "")
           and "integer" in (e.message or "")]
    assert not bad


def test_checkbox_param_rejects_arbitrary_string(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: aws-access-analyzer\n"
        "          operation: list_analyzers\n"
        "          params:\n"
        "            type: ACCOUNT\n"
        "            assume_role: maybe\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "assume_role" in (e.message or "")
           and "boolean" in (e.message or "")]
    assert bad


def test_checkbox_param_accepts_native_bool_and_truthy_string(db_path):
    for val in ("true", "false", "True", "yes", "1"):
        text = _yaml(
            "        type: connector\n"
            "        arguments:\n"
            "          connector: aws-access-analyzer\n"
            "          operation: list_analyzers\n"
            "          params:\n"
            "            type: ACCOUNT\n"
            f"            assume_role: {val}\n"
        )
        r = compile_yaml(text, db_path)
        bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
               and "assume_role" in (e.message or "")
               and "boolean" in (e.message or "")]
        assert not bad, f"value {val!r} should be accepted"


def test_decimal_param_rejects_non_numeric(db_path):
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: claroty-xdome\n"
        "          operation: get_vulnerabilities\n"
        "          params:\n"
        "            cvss_v3_score: critical\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and "cvss_v3_score" in (e.message or "")
           and "number" in (e.message or "")]
    assert bad


def test_typed_param_skips_jinja(db_path):
    """Jinja templates defer to runtime; no static type complaint."""
    text = _yaml(
        "        type: connector\n"
        "        arguments:\n"
        "          connector: aws-access-analyzer\n"
        "          operation: list_analyzers\n"
        "          params:\n"
        "            type: ACCOUNT\n"
        "            size: \"{{ vars.input.params.n }}\"\n"
        "            assume_role: \"{{ vars.input.params.role }}\"\n"
    )
    r = compile_yaml(text, db_path)
    bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
           and (e.path or "").endswith((".size", ".assume_role"))]
    assert not bad, [e.to_dict() for e in bad]


def test_tier23_ipv4_validator_unit():
    """Pure-function tests for the new observed_type validators. These
    don't need the DB — they catch validator regressions cheaply."""
    from fsr_core.compiler.resolver.connector_args import (
        _is_ipv4, _is_url, _is_email, _is_iso8601,
        _is_json_object, _is_json_array,
    )
    assert _is_ipv4("10.0.0.1")
    assert _is_ipv4("0.0.0.0")
    assert not _is_ipv4("999.0.0.1")
    assert not _is_ipv4("hostname.example.com")
    assert not _is_ipv4("::1")          # ipv6 — distinct observed_type
    assert not _is_ipv4(12345)

    assert _is_url("https://example.com/path?x=1")
    assert _is_url("ftp://host")
    assert not _is_url("example.com")    # no scheme
    assert not _is_url("not a url")

    assert _is_email("user@example.com")
    assert _is_email("a.b+tag@host.tld")
    assert not _is_email("no-at-sign")
    assert not _is_email("user@host")    # no TLD-style suffix

    assert _is_iso8601("2026-05-20T12:00:00")
    assert _is_iso8601("2026-05-20")
    assert not _is_iso8601("yesterday")
    assert not _is_iso8601(1717200000)   # epoch — not iso

    assert _is_json_object({"a": 1})
    assert _is_json_object('{"a":1}')
    assert not _is_json_object("[1,2]")  # array, not object
    assert not _is_json_object("not json")

    assert _is_json_array([1, 2])
    assert _is_json_array("[1,2]")
    assert not _is_json_array('{"a":1}')


def test_tier23_ipv4_observed_type_fires(db_path):
    """Integration: when observed_type='ipv4' is set on a text-widget
    param, a non-IPv4 literal triggers the new diagnostic.

    We mutate the DB in-process so the test is self-contained — the
    Tier 2.2 live probe is what populates observed_type in production.
    """
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path)
    # Snapshot the previous value so we can restore — db_path is shared
    # across tests via the session fixture.
    cur = conn.execute(
        "SELECT observed_type FROM operation_params "
        "WHERE connector_name='abuseipdb' AND op_name='ip_lookup' "
        "  AND param_name='ip'")
    row = cur.fetchone()
    prev = row[0] if row else None
    conn.execute(
        "UPDATE operation_params SET observed_type='ipv4' "
        "WHERE connector_name='abuseipdb' AND op_name='ip_lookup' "
        "  AND param_name='ip'")
    conn.commit()
    try:
        text = _yaml(
            "        type: connector\n"
            "        arguments:\n"
            "          connector: abuseipdb\n"
            "          operation: ip_lookup\n"
            "          params:\n"
            "            ip: not-an-ip\n"
            "            days: 30\n"
        )
        r = compile_yaml(text, db_path)
        bad = [e for e in r.errors if e.code is ErrorCode.BAD_VALUE
               and (e.path or "").endswith(".ip")
               and "IPv4" in (e.message or "")]
        assert bad, [e.to_dict() for e in r.errors]

        # Jinja-templated value: no diagnostic.
        text2 = _yaml(
            "        type: connector\n"
            "        arguments:\n"
            "          connector: abuseipdb\n"
            "          operation: ip_lookup\n"
            "          params:\n"
            "            ip: \"{{ vars.input.records.source_ip }}\"\n"
            "            days: 30\n"
        )
        r2 = compile_yaml(text2, db_path)
        bad2 = [e for e in r2.errors if (e.path or "").endswith(".ip")
                and "IPv4" in (e.message or "")]
        assert not bad2
    finally:
        conn.execute(
            "UPDATE operation_params SET observed_type=? "
            "WHERE connector_name='abuseipdb' AND op_name='ip_lookup' "
            "  AND param_name='ip'", (prev,))
        conn.commit()
        conn.close()


def test_unknown_next_step(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: nowhere
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.UNKNOWN_NEXT_STEP for e in r.errors)


def test_connector_version_stamped(db_path, repo_root):
    text = (repo_root / "examples" / "hello_connector.yaml").read_text()
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # Resolver stamps version onto the connector step's arguments.
    lookup_step = next(s for s in r.ir.playbooks[0].steps if s.id == "get_organization")
    assert lookup_step.arguments.get("version")  # set from connectors.version
