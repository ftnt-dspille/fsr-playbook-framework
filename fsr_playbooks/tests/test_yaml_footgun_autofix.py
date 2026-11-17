"""Two YAML foot-guns a model emits verbatim, fixed mechanically at the compile
entry so one typo does not fail the whole compile and bounce the agent loop back
to re-author.

Foot-gun 1 (parse recovery): an unquoted mapping value whose inner `: ` makes
YAML read a second mapping key -- `description: scores above 50: {{ x }}` breaks
at the colon. Foot-gun 2 (Norway): `display: Yes` is read as a YAML 1.1 boolean,
so a branch label keys off `True` instead of the literal string.

Localized live on soc_phish: both appeared in one delivered playbook and blocked
the compile. The fix runs at the `compile_yaml` entry so the corrected text flows
to BOTH the parser and the raw-text linter -- doing it only inside `parse_yaml`
left the linter reading the original text and still flagging Norway. Each fix is
surfaced as a warning, never silent.

RED without the fix: `_autofix_yaml_footguns` does not exist / is not wired, so
the text stays unparseable (colon) and the Norway lint still blocks.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.parser import _autofix_yaml_footguns
from fsr_playbooks.compiler.pipeline import compile_yaml

_DB = Path(__file__).resolve().parents[1] / "_data" / "fsr_reference.db"

_COLON = ("            description: The following IPs have reputation scores "
          "above 50: {{ vars.high_score_ips }}. Choose action.")
_NORWAY = "            display: Yes"

_BOTH = f"""playbooks:
  - name: Probe
    trigger: {{type: manual}}
    steps:
      - name: note
        type: set_variable
        arguments:
{_COLON}
{_NORWAY}
"""


def test_autofix_quotes_a_colon_scalar_and_a_norway_boolean():
    errors: list[CompileError] = []
    fixed = _autofix_yaml_footguns(_BOTH, errors)
    # The colon value is now parseable YAML (foot-gun 1 recovered).
    yaml.safe_load(fixed)
    # `Yes` is quoted so it stays the literal string, not True (foot-gun 2).
    assert 'display: "Yes"' in fixed or "display: 'Yes'" in fixed
    assert '"The following IPs have reputation scores above 50:' in fixed
    # Every fix is surfaced -- never silent.
    assert len(errors) == 2
    assert all(e.severity == "warning" for e in errors)
    assert all(e.code == ErrorCode.BAD_VALUE for e in errors)


def test_clean_yaml_is_untouched():
    clean = ("playbooks:\n  - name: Probe\n    trigger: {type: manual}\n"
             "    steps:\n      - name: note\n        type: set_variable\n")
    errors: list[CompileError] = []
    assert _autofix_yaml_footguns(clean, errors) == clean
    assert errors == []


def test_compile_entry_clears_both_blockers():
    # Through the real compile entry: the corrected text must reach both the
    # parser (no PARSE_ERROR from the colon) and the raw-text linter (no Norway
    # boolean BAD_VALUE). The fix is at the entry so the linter sees it too --
    # doing it only inside parse_yaml left the linter reading the original text.
    # (Warning-surfacing is proved directly in the unit test above; a later
    # schema block can drop warnings, but the foot-guns never reach it.)
    result = compile_yaml(_BOTH, _DB)
    blockers = [e for e in result.errors if e.severity != "warning"]
    assert not any(e.code == ErrorCode.PARSE_ERROR for e in blockers), \
        "colon scalar still unparseable at the compile entry"
    assert not any("boolean" in e.message for e in blockers), \
        "Norway boolean still blocks because the linter saw the original text"
