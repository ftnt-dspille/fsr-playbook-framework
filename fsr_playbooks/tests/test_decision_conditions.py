"""Decision-route boolean gate (NON_BOOLEAN_CONDITION).

FSR's decision engine checks each route condition's rendered value with
isinstance(bool) (live-verified on 8.0.x). ``non_boolean_condition`` judges a
single expression's AST; ``linter._check_decision_conditions`` walks every
decision route with it. The flagged templates below are the live failure
shapes -- bare references whose runtime values were strings, which crashed
their child playbooks mid-run while the compiled build stayed green -- and the
passing ones include the ingestion chain's live-proven guards, so the gate
never false-fires on working playbooks.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.jinja_checks import non_boolean_condition

DB = default_db_path()

# ---- unit: non_boolean_condition -------------------------------------------

# Live-caught failure shapes: each rendered a non-bool and crashed the step.
_FLAGGED = [
    "{{ vars.steps.Enrich.data.matched }}",        # bare cross-step read
    "{{ vars.bag_file_path }}",                    # bare local
    "{{ vars.event_title | string }}",             # unguarded chain
    "{{ vars.flag and vars.steps.X.data.gold }}",  # and/or over non-bools
]

_DEFAULT_GUARD = "{{ vars.event_id | default('', true) | string | length > 0 }}"
_BOOL_GUARD = "{{ vars.request.env_setup | default(false) | bool }}"


def test_flagged_shapes():
    for text in _FLAGGED:
        assert non_boolean_condition(text) is not None, text


def test_live_proven_guards_pass():
    # The presence guard is the form the live fixes converged to; the `| bool`
    # chain is the ingestion chain's own request check, live-proven on the
    # appliance's decision engine.
    assert non_boolean_condition(_DEFAULT_GUARD) is None
    assert non_boolean_condition(_BOOL_GUARD) is None


def test_comparison_and_test_forms_pass():
    assert non_boolean_condition("{{ vars.a == 'true' }}") is None
    assert non_boolean_condition("{{ vars.a is defined }}") is None
    assert non_boolean_condition("{{ not vars.flag }}") is None
    assert non_boolean_condition("{{ true }}") is None
    # and/or whose both sides render bools
    assert non_boolean_condition(
        "{{ vars.a is defined and vars.b is boolean }}") is None


def test_undecidable_stays_silent():
    # Never false-fire: literals, multi-expression templates, statement
    # blocks, and unparsable text (the syntax check owns that) are not
    # verdicts a warning can ride on.
    assert non_boolean_condition("plain literal route") is None
    assert non_boolean_condition("{{ x }} and {{ y }}") is None
    assert non_boolean_condition("{% if x %}{{ y }}{% endif %}") is None
    assert non_boolean_condition("{{ x | }}") is None


# ---- compile-level: the linter walks decision routes ----------------------

_BARE = """
collection: t
playbooks:
  - name: d
    steps:
      - name: Start
        type: start
        next: Route
      - name: Route
        type: decision
        conditions:
          - display: Hit
            when: "{{ vars.events_found }}"
            next: Set
          - display: Miss
            default: true
            next: Set
      - name: Set
        type: set_variable
        vars: {ok: "1"}
"""

_FIXED = _BARE.replace(
    '"{{ vars.events_found }}"',
    "{{ (vars.events_found | default('', true) | string) "
    "| length > 0 }}")


def _errs(yaml_text):
    return compile_yaml(yaml_text, DB).errors


def test_bare_condition_warns_at_compile():
    errs = _errs(_BARE)
    hits = [e for e in errs if e.code.value == "non_boolean_condition"]
    assert hits, [e.message for e in errs]
    assert all(e.severity == "warning" for e in hits)
    assert hits[0].path.endswith("arguments.conditions[0].condition")


def test_fixed_condition_compiles_clean():
    errs = _errs(_FIXED)
    assert not [e for e in errs if e.code.value == "non_boolean_condition"]
