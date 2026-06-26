"""Unit tests for the static Jinja checks (jinja_syntax_error +
unknown_jinja_filter).

Pure — `check_jinja` walks an args dict and runs jinja2's parser, which IS the
FortiSOAR runtime parser, so these findings are zero-false-positive for syntax.
"""
from fsr_playbooks.compiler.jinja_checks import (
    check_jinja,
    _KNOWN_FILTERS,
    _KNOWN_TESTS,
)


# --- catalog load ---------------------------------------------------------

def test_catalog_unions_builtins_and_fortisoar():
    # jinja2 built-ins present...
    assert "upper" in _KNOWN_FILTERS
    assert "tojson" in _KNOWN_FILTERS
    # ...and at least one FortiSOAR custom filter from the widget catalog.
    assert "b64encode" in _KNOWN_FILTERS
    assert "defined" in _KNOWN_TESTS


# --- syntax (error) -------------------------------------------------------

def test_missing_endif_is_syntax_error():
    issues = check_jinja(
        {"x": "{% if vars.a %}hi"}, step_id="s", path="p")
    codes = [i["code"] for i in issues]
    assert "jinja_syntax_error" in codes
    err = next(i for i in issues if i["code"] == "jinja_syntax_error")
    assert err["severity"] == "error"
    assert err["location"] == "arguments.x"


def test_malformed_filter_in_balanced_braces_is_syntax_error():
    # `{{ x | }}` — pipe with no filter name — parses to a TemplateSyntaxError.
    issues = check_jinja({"v": "{{ vars.a | }}"}, step_id="s", path="p")
    assert any(i["code"] == "jinja_syntax_error" for i in issues)


def test_valid_template_passes():
    assert check_jinja(
        {"to": "{{ vars.inputs.recipients | upper }}",
         "n": "{% if vars.x %}y{% endif %}"},
        step_id="s", path="p") == []


def test_plain_string_no_jinja_ignored():
    assert check_jinja({"k": "just a literal value"},
                       step_id="s", path="p") == []


# --- unknown filter (warning) --------------------------------------------

def test_unknown_filter_with_did_you_mean():
    # `defualt` is a transposition typo of `default` and does NOT contain it as
    # a substring, so the assertion proves the did-you-mean actually fired
    # rather than matching the original name.
    issues = check_jinja(
        {"v": "{{ vars.a | defualt('x') }}"}, step_id="s", path="p")
    assert len(issues) == 1
    f = issues[0]
    assert f["code"] == "unknown_jinja_filter"
    assert f["severity"] == "warning"
    assert "defualt" in f["message"]
    assert "Did you mean 'default'?" in f["message"]
    assert f["suggestion"] == "replace with 'default'"


def test_did_you_mean_fires_for_real_typo_below_strict_cutoff():
    # Regression: `uppercasse` sits below a 0.7 cutoff but above 0.6 — it must
    # still get a suggestion (this is the case that motivated lowering it).
    f = check_jinja(
        {"v": "{{ x | uppercasse }}"}, step_id="s", path="p")[0]
    assert "Did you mean 'upper'?" in f["message"]


def test_known_fortisoar_filter_passes():
    assert check_jinja(
        {"v": "{{ vars.a | b64encode }}"}, step_id="s", path="p") == []


def test_unknown_test_flagged():
    issues = check_jinja(
        {"v": "{% if vars.a is definedd %}x{% endif %}"},
        step_id="s", path="p")
    assert any(i["code"] == "unknown_jinja_filter"
               and "test" in i["message"] for i in issues)


def test_syntax_error_skips_filter_check():
    # An un-parseable template yields only the syntax finding (no AST to walk).
    issues = check_jinja(
        {"v": "{{ vars.a | uppercasse "}, step_id="s", path="p")
    assert [i["code"] for i in issues] == ["jinja_syntax_error"]


def test_nested_args_locations():
    issues = check_jinja(
        {"params": {"items": ["{{ x | nope }}"]}},
        step_id="s", path="p")
    assert issues[0]["location"] == "arguments.params.items[0]"
