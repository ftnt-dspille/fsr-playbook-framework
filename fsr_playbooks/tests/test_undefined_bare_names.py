"""Phase 0 (DYNAMIC_JINJA_RENDER_PLAN) — undefined bare-name detection via
Jinja AST.

The typed walker now parses each Jinja template and walks the AST for
``Name`` nodes with ``ctx='load'`` that aren't in the known set (Jinja2
builtins + FSR globals + locally-defined names).  This catches
``{{ items | length }}`` where ``items`` is never defined — the existing
``_check_undefined_vars`` only matches ``vars.<name>`` regex patterns.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.typed_walker import walk_playbook
from fsr_playbooks.compiler.jinja_render import find_undefined_bare_names

DB = default_db_path()


def _walk(text: str):
    cres = compile_yaml(text, DB)
    assert cres.ir is not None
    return walk_playbook(cres.ir)


# ---- unit: find_undefined_bare_names --------------------------------------

def test_undefined_bare_name_caught():
    """``{{ items | length }}`` where ``items`` is never defined."""
    result = find_undefined_bare_names("{{ items | length }}")
    assert len(result) == 1
    assert result[0][0] == "items"


def test_vars_reference_not_flagged():
    """``{{ vars.count | length }}`` — ``vars`` is always known."""
    result = find_undefined_bare_names("{{ vars.count | length }}")
    assert result == []


def test_known_global_not_flagged():
    """``{{ arrow.now() }}`` — ``arrow`` is an FSR global."""
    result = find_undefined_bare_names("{{ arrow.now() }}")
    assert result == []


def test_jinja2_builtin_not_flagged():
    """``{{ range(5) }}`` — ``range`` is a Jinja2 built-in."""
    result = find_undefined_bare_names("{{ range(5) }}")
    assert result == []


def test_loop_variable_not_flagged():
    """``{% for item in vars.steps.X.results %}{{ item }}{% endfor %}`` —
    ``item`` is a loop variable, not undefined."""
    tpl = "{% for item in vars.steps.X.results %}{{ item }}{% endfor %}"
    result = find_undefined_bare_names(tpl)
    assert result == []


def test_set_variable_not_flagged():
    """``{% set x = 42 %}{{ x }}`` — ``x`` is set-defined."""
    tpl = "{% set x = 42 %}{{ x }}"
    result = find_undefined_bare_names(tpl)
    assert result == []


def test_multiple_undefined_names():
    """``{{ a + b }}`` — both ``a`` and ``b`` are undefined."""
    result = find_undefined_bare_names("{{ a + b }}")
    names = [name for name, _ in result]
    assert "a" in names
    assert "b" in names


def test_dedup_same_name():
    """``{{ items | length }} {{ items | upper }}`` — ``items`` reported once."""
    tpl = "{{ items | length }} {{ items | upper }}"
    result = find_undefined_bare_names(tpl)
    assert len(result) == 1
    assert result[0][0] == "items"


def test_no_jinja_returns_empty():
    """Plain string (no ``{{ }}``) returns empty list."""
    assert find_undefined_bare_names("hello world") == []


def test_syntax_error_returns_empty():
    """A template with a syntax error returns empty (already caught by
    jinja_checks.check_jinja)."""
    assert find_undefined_bare_names("{% for %}") == []


# ---- integration: typed walker -------------------------------------------

_UNDEFINED_BARE = """
collection: t
playbooks:
  - name: Undefined
    steps:
      - name: start
        type: start
        next: Use It
      - name: Use It
        type: set_variable
        vars:
          count: "{{ items | length }}"
"""


def test_walker_flags_undefined_bare_name():
    w = _walk(_UNDEFINED_BARE)
    codes = [d.code for d in w.diagnostics]
    assert "jinja_undefined_variable" in codes
    diag = next(d for d in w.diagnostics if d.code == "jinja_undefined_variable")
    assert "items" in diag.message
    assert diag.severity == "warning"


_VARS_REF_NOT_FLAGGED = """
collection: t
playbooks:
  - name: VarsRef
    steps:
      - name: start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars:
          n: "123"
          next: Use
      - name: Use
        type: set_variable
        vars:
          doubled: "{{ vars.n | int }}"
"""


def test_walker_no_false_positive_on_vars_ref():
    w = _walk(_VARS_REF_NOT_FLAGGED)
    codes = [d.code for d in w.diagnostics]
    assert "jinja_undefined_variable" not in codes


_FOR_EACH_ITEM = """
collection: t
playbooks:
  - name: ForEach
    steps:
      - name: start
        type: start
        next: Loop
      - name: Loop
        type: set_variable
        for_each:
          item: "[1, 2, 3]"
        vars:
          val: "{{ vars.item }}"
"""


def test_walker_no_false_positive_on_for_each_item():
    w = _walk(_FOR_EACH_ITEM)
    codes = [d.code for d in w.diagnostics]
    assert "jinja_undefined_variable" not in codes


_FSR_GLOBAL = """
collection: t
playbooks:
  - name: Global
    steps:
      - name: start
        type: start
        next: Use
      - name: Use
        type: set_variable
        vars:
          now: "{{ get_current_date() }}"
"""


def test_walker_no_false_positive_on_fsr_global():
    w = _walk(_FSR_GLOBAL)
    codes = [d.code for d in w.diagnostics]
    assert "jinja_undefined_variable" not in codes


_LOOP_VAR_IN_TEMPLATE = """
collection: t
playbooks:
  - name: LoopVar
    steps:
      - name: start
        type: start
        next: Build
      - name: Build
        type: set_variable
        vars:
          result: "{% for x in vars.steps.start.input.records %}{{ x.id }}{% endfor %}"
"""


def test_walker_no_false_positive_on_jinja_loop_var():
    w = _walk(_LOOP_VAR_IN_TEMPLATE)
    codes = [d.code for d in w.diagnostics]
    assert "jinja_undefined_variable" not in codes


# ---- compile-path: reference_lint surfaces the warning -------------------

def test_compile_path_emits_jinja_undefined_variable():
    """The compile path (reference_lint) should surface the warning."""
    from fsr_playbooks.compiler.reference_lint import reference_lint
    cres = compile_yaml(_UNDEFINED_BARE, DB)
    assert cres.ir is not None
    warnings = reference_lint(cres.ir, db_path=str(DB))
    codes = [w.code.value for w in warnings]
    assert "jinja_undefined_variable" in codes
