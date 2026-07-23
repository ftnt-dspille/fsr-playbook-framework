"""Hermetic unit tests for the record-write / connector-op static checks.

These exercise the pure check functions with injected catalog facts (no DB),
so they're deterministic regardless of whether the reference DB is warmed.
The DB-backed wiring lives in `tools_verify`; these pin the *logic*.

Grounding: the facts injected here are the real .205-warmed values
(alerts requires `name`; virustotal:query_ip requires `ip`; smtp has a
`content_type` param but no `body_type`).
"""
from fsr_playbooks.compiler.record_op_checks import (
    check_connector_config,
    check_op_params,
    check_record_module,
    check_required_record_fields,
    check_unknown_record_fields,
)


# --- unknown module field (resource keys) --------------------------------

def test_unknown_record_field_is_warning():
    issues = check_unknown_record_fields(
        module="alerts", resource={"name": "x", "notarealfield": "y"},
        known_fields=["name", "severity", "description"],
        step_id="s", path="p",
    )
    assert len(issues) == 1
    assert issues[0]["code"] == "unknown_record_field"
    assert issues[0]["severity"] == "warning"
    assert "notarealfield" in issues[0]["message"]


def test_known_record_fields_pass():
    assert check_unknown_record_fields(
        module="alerts", resource={"name": "x", "severity": "High"},
        known_fields=["name", "severity", "description"],
    ) == []


def test_unknown_field_skipped_when_catalog_unwarmed():
    assert check_unknown_record_fields(
        module="alerts", resource={"anything": 1}, known_fields=[],
    ) == []


# --- module existence (record writes) ------------------------------------

def test_unknown_module_is_error_with_suggestion():
    issues = check_record_module(
        module="alertz", known_modules=["alerts", "incidents", "assets"],
        step_id="s", path="p",
    )
    assert len(issues) == 1
    assert issues[0]["code"] == "unknown_module"
    assert issues[0]["severity"] == "error"
    assert "alerts" in issues[0]["near"]


def test_known_module_passes():
    assert check_record_module(
        module="alerts", known_modules=["alerts", "incidents"],
    ) == []


def test_module_iri_form_is_resolved():
    assert check_record_module(
        module="/api/3/alerts", known_modules=["alerts"],
    ) == []


def test_dynamic_module_is_skipped():
    assert check_record_module(
        module="{{ vars.module }}", known_modules=["alerts"],
    ) == []


def test_unwarmed_module_catalog_skips():
    assert check_record_module(module="whatever", known_modules=[]) == []


# --- F: required record-field completeness -------------------------------

def test_required_field_absent_is_error():
    issues = check_required_record_fields(
        module="alerts", resource={"description": "hi"},
        required_fields=["name"], step_id="s1", path="playbooks[0].steps[1]",
    )
    assert len(issues) == 1
    assert issues[0]["code"] == "required_record_field_missing"
    assert issues[0]["severity"] == "error"
    assert "name" in issues[0]["message"]
    assert issues[0]["path"].endswith(".arguments.resource")


def test_required_field_present_passes():
    assert check_required_record_fields(
        module="alerts", resource={"name": "x", "description": "hi"},
        required_fields=["name"],
    ) == []


def test_unknown_module_no_facts_no_flag():
    # No required-field facts → never guess.
    assert check_required_record_fields(
        module="widgets", resource={}, required_fields=[],
    ) == []


def test_non_dict_resource_is_ignored():
    assert check_required_record_fields(
        module="alerts", resource="{{ vars.thing }}", required_fields=["name"],
    ) == []


# --- G: connector-op param validity --------------------------------------

def test_unknown_param_name_is_warning_with_suggestion():
    issues = check_op_params(
        connector="smtp", operation="send_email",
        params={"body_type": "html"},
        declared_params=["to_recipients", "body", "subject", "content_type"],
        required_params=[],
        step_id="s2", path="p",
    )
    assert len(issues) == 1
    assert issues[0]["code"] == "op_param_unknown_name"
    assert issues[0]["severity"] == "warning"
    # difflib suggests the closest declared name (here 'body').
    assert issues[0]["near"] and issues[0]["near"][0] in {"body", "content_type"}


def test_required_param_missing_is_error():
    issues = check_op_params(
        connector="virustotal", operation="query_ip",
        params={"relationships": "x"},
        declared_params=["ip", "relationships"],
        required_params=["ip"],
        step_id="s3", path="p",
    )
    codes = {i["code"] for i in issues}
    assert codes == {"required_op_param_missing"}
    assert issues[0]["severity"] == "error"


def test_valid_params_pass():
    assert check_op_params(
        connector="virustotal", operation="query_ip",
        params={"ip": "1.2.3.4"},
        declared_params=["ip", "relationships"],
        required_params=["ip"],
    ) == []


def test_unprobed_op_no_declared_params_no_flag():
    # Op not in the catalog → don't flag anything (would be all noise).
    assert check_op_params(
        connector="x", operation="y", params={"anything": 1},
        declared_params=[], required_params=[],
    ) == []


# --- connector config existence ------------------------------------------

def test_no_config_at_all_is_error():
    issues = check_connector_config(
        connector="splunk", config_value="", configs_known=True,
        config_names=[], has_default=False, step_id="s", path="p",
    )
    assert [i["code"] for i in issues] == ["connector_config_missing"]
    assert issues[0]["severity"] == "error"


def test_config_less_builtin_with_empty_config_passes():
    # cyops_utilities is config-less: empty `config:` binds fine and it carries
    # no saved config, so it must NOT flag connector_config_missing even when the
    # catalog knows configs exist for other connectors (configs_known=True).
    assert check_connector_config(
        connector="cyops_utilities", config_value="", configs_known=True,
        config_names=[], has_default=False, step_id="s", path="p",
    ) == []


def test_config_less_builtin_still_validates_a_named_pin():
    # A non-empty config *name* on a config-less connector still gets name-checked
    # (a typo'd pin is a real error), so the exemption is scoped to empty config.
    issues = check_connector_config(
        connector="cyops_utilities", config_value="bogus", configs_known=True,
        config_names=["real-cfg"], has_default=True, step_id="s", path="p",
    )
    assert [i["code"] for i in issues] == ["unknown_connector_config"]


def test_configs_but_no_default_is_warning():
    issues = check_connector_config(
        connector="smtp", config_value="", configs_known=True,
        config_names=["localhost", "fortimail"], has_default=False,
    )
    assert [i["code"] for i in issues] == ["connector_config_no_default"]
    assert issues[0]["severity"] == "warning"


def test_default_config_present_passes():
    assert check_connector_config(
        connector="smtp", config_value="", configs_known=True,
        config_names=["localhost-postfix"], has_default=True,
    ) == []


def test_explicit_known_config_pin_passes():
    assert check_connector_config(
        connector="smtp", config_value="localhost-postfix", configs_known=True,
        config_names=["localhost-postfix", "localhost"], has_default=False,
    ) == []


def test_unknown_named_config_is_error():
    issues = check_connector_config(
        connector="virustotal", config_value="bogus", configs_known=True,
        config_names=["vt"], has_default=True, step_id="s", path="p",
    )
    assert [i["code"] for i in issues] == ["unknown_connector_config"]
    assert issues[0]["severity"] == "error"
    assert "bogus" in issues[0]["message"]


def test_config_iri_pin_is_trusted():
    assert check_connector_config(
        connector="smtp", config_value="/api/3/connectors/abc", configs_known=True,
        config_names=["localhost"], has_default=False,
    ) == []


def test_dynamic_config_is_trusted():
    assert check_connector_config(
        connector="smtp", config_value="{{ vars.cfg }}", configs_known=True,
        config_names=["localhost"], has_default=False,
    ) == []


def test_unwarmed_catalog_skips_config_check():
    # configs_known=False → the table was never warmed; never false-flag.
    assert check_connector_config(
        connector="anything", config_value="", configs_known=False,
        config_names=[], has_default=False,
    ) == []
