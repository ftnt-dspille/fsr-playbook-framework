"""Locks in the line/col math for the source-level auto-fixers.

These guard against silent offset drift when the regexes get tweaked —
the editor relies on the ranges matching exactly so `executeEdits` lands
the patch where the user expects.
"""
from fsr_core.compiler.source_fixer import collect_fixes


def _by_code(text: str) -> dict:
    return {f.code: f for f in collect_fixes(text)}


def test_stop_to_end_range_covers_full_line():
    text = "playbooks:\n  - name: P\n    steps:\n      - name: bye\n        type: stop\n"
    fixes = _by_code(text)
    f = fixes["stop_to_end"]
    assert f.line == 5
    assert f.col == 1
    # The match consumes through the trailing newline → end on next line, col 1.
    assert (f.end_line, f.end_col) == (6, 1)
    assert "type: stop" in f.original
    assert "type: end" in f.replacement


def test_norway_dispatch_quotes_yes_no_and_pins_line():
    text = (
        "playbooks:\n  - name: P\n    steps:\n"
        "      - name: g\n        type: decision\n"
        "        conditions:\n"
        "          - display: yes\n"
        "            when: x\n"
        "          - display: NO\n"
        "            when: y\n"
    )
    fixes = [f for f in collect_fixes(text) if f.code == "norway_quote"]
    assert len(fixes) == 2
    assert {f.line for f in fixes} == {7, 9}
    assert all('"' in f.replacement for f in fixes)


def test_input_param_ref_only_fires_for_declared_params():
    text = (
        "playbooks:\n  - name: P\n    parameters: [severity]\n"
        "    steps:\n      - name: s\n        type: set_variable\n"
        "        set:\n"
        "          a: \"{{ vars.input.severity }}\"\n"   # rewrite
        "          b: \"{{ vars.input.host }}\"\n"        # NOT declared, leave alone
        "          c: \"{{ vars.input.params.severity }}\"\n"  # already correct
    )
    fixes = [f for f in collect_fixes(text) if f.code == "input_param_ref"]
    assert len(fixes) == 1
    assert "vars.input.severity" in fixes[0].original
    assert "vars.input.params.severity" in fixes[0].replacement
    assert fixes[0].line == 8


def test_step_name_charset_substitutes_disallowed_runs():
    text = "playbooks:\n  - name: P\n    steps:\n      - name: Find—Records (v2)\n        type: end\n"
    fixes = [f for f in collect_fixes(text) if f.code == "step_name_charset"]
    assert len(fixes) == 1
    f = fixes[0]
    assert f.line == 4
    assert "—" in f.original
    assert "—" not in f.replacement and "(" not in f.replacement
    # Disallowed runs collapse to `_`; the existing space before `(` is
    # preserved (the regex doesn't munge spaces, only chars outside the
    # designer charset).
    assert "Find_Records" in f.replacement
    assert "v2" in f.replacement


def test_set_var_reserved_key_renames_declaration_and_refs():
    text = (
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - type: set_variable\n"
        "        name: Set Variable\n"
        "        vars:\n"
        "          message: hi\n"
        "      - type: manual_input\n"
        "        name: Show\n"
        "        arguments:\n"
        '          description: "{{ vars.message }}"\n'
    )
    fixes = [f for f in collect_fixes(text) if f.code == "set_var_reserved_key"]
    # One declaration rename + one reference rewrite.
    assert len(fixes) == 2
    decl = next(f for f in fixes if f.original == "message")
    assert decl.line == 7
    assert decl.replacement == "message_var"
    ref = next(f for f in fixes if "vars.message" in f.original)
    assert ref.replacement == "vars.message_var"
    assert ref.line == 11


def test_set_var_reserved_key_arg_list_form():
    text = (
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - type: set_variable\n"
        "        name: SV\n"
        "        arguments:\n"
        "          arg_list:\n"
        "            - name: result\n"
        "              value: 1\n"
    )
    fixes = [f for f in collect_fixes(text) if f.code == "set_var_reserved_key"]
    assert any(f.original == "result" and f.replacement == "result_var"
               for f in fixes)


def test_set_var_step_namespace_rewrites_step_dot_key():
    text = (
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - type: set_variable\n"
        "        name: Set Variable\n"
        "        vars:\n"
        "          greeting: hi\n"
        "      - type: manual_input\n"
        "        name: Show\n"
        "        arguments:\n"
        '          description: "{{ vars.steps.Set_Variable.greeting }}"\n'
    )
    fixes = [f for f in collect_fixes(text) if f.code == "set_var_step_namespace"]
    assert len(fixes) == 1
    assert fixes[0].replacement == "vars.greeting"
    assert "vars.steps.Set_Variable.greeting" in fixes[0].original


def test_set_var_step_namespace_post_rename_uses_new_key():
    """When the key is also reserved, the namespace rewrite should land
    on the renamed `vars.<key>_var` so both fixers stay coherent."""
    text = (
        "playbooks:\n"
        "  - name: P\n"
        "    steps:\n"
        "      - type: set_variable\n"
        "        name: Set Variable\n"
        "        vars:\n"
        "          message: hi\n"
        "      - type: manual_input\n"
        "        name: Show\n"
        "        arguments:\n"
        '          description: "{{ vars.steps.Set_Variable.message }}"\n'
    )
    ns = [f for f in collect_fixes(text) if f.code == "set_var_step_namespace"]
    assert len(ns) == 1 and ns[0].replacement == "vars.message_var"


def test_collect_fixes_is_sorted_by_position():
    text = (
        "playbooks:\n  - name: P\n    parameters: [severity]\n"
        "    steps:\n"
        "      - name: Find—Records\n"   # L5 charset
        "        type: stop\n"             # L6 stop
        "        conditions:\n"
        "          - display: yes\n"     # L8 norway
        "            when: \"{{ vars.input.severity }}\"\n"  # L9 input_param
    )
    fixes = collect_fixes(text)
    lines = [f.line for f in fixes]
    assert lines == sorted(lines)
    codes = [f.code for f in fixes]
    assert codes[0] == "step_name_charset"
    assert "stop_to_end" in codes
    assert "norway_quote" in codes
    assert "input_param_ref" in codes
