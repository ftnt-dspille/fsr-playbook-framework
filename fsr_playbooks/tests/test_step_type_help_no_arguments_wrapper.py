"""The step-type help the author reads must never present the `arguments:`
wrapper as a valid place to put keys.

The compiler rejects the wrapper for EVERY step (`bad_value`: "the arguments:
wrapper is no longer used -- hoist all step arguments to the step level"), yet
the decision step-type help used to say `conditions:` "lives at the step level
(sugar) or under `arguments:` (wire form)" -- legitimizing a shape the compiler
rejects. A model reading that authored `arguments:` and failed the draft gate
(localized live on gpt-4.1-mini). A warning AGAINST the wrapper is fine; naming
it a valid alternative is the leak.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from fsr_playbooks.mcp_server.tools_discovery import get_step_type


def _md(step_type: str) -> str:
    out = get_step_type(step_type)
    return (out.get("markdown") or "").lower()


def test_decision_help_does_not_legitimize_the_arguments_wrapper():
    md = _md("decision")
    # The exact phrasing that taught the wrong shape must be gone.
    assert "wire form" not in md, (
        "decision help still presents an `arguments:` wire form as valid")
    assert "under `arguments:`" not in md and "under arguments:" not in md, (
        "decision help still routes conditions under the arguments wrapper")
    # And it should steer the author to the step level instead.
    assert "step level" in md


def test_decision_help_still_covers_conditions_and_default():
    # The fix must not drop the real guidance the help carries.
    md = _md("decision")
    assert "conditions:" in md
    assert "default" in md
