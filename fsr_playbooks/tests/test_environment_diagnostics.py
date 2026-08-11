"""#107 -- an uninstalled connector is a fact about the BOX, not a defect.

Live on .159, "Explain what this playbook does, step by step" produced four
`verify_playbook` calls against connectors the box does not have
(`phishme-intelligence`, `placeholder-connector`) and delivered no explanation.
The agent read `unknown_connector` as something it could fix by editing, and
the repeated-error guard could not stop the loop because each attempt returned
a DIFFERENT error -- no two call signatures matched.

The wire now says so directly: the diagnostic carries `environment: True` and a
remediation that re-running will not change the answer.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_verify import (
    _ENVIRONMENT_CODES,
    _mark_environment_diagnostic,
)


def _diag(code):
    return {"code": code, "message": "m", "path": "p", "suggestion": None,
            "severity": "error", "check": "compile"}


def test_unknown_connector_is_marked_as_environment():
    d = _mark_environment_diagnostic(_diag("unknown_connector"))
    assert d["environment"] is True
    # The one thing the model has to learn is that retrying is pointless.
    assert "re-running" in d["remediation"]
    # ...and what to do instead when the ask was read-only.
    assert "EXPLAIN" in d["remediation"]


def test_severity_and_code_are_not_softened():
    """An uninstalled connector still blocks a push. The tag explains WHY the
    fix is not an edit; it does not downgrade the finding, which would let a
    playbook be offered against a connector the box cannot run."""
    d = _mark_environment_diagnostic(_diag("unknown_connector"))
    assert d["severity"] == "error"
    assert d["code"] == "unknown_connector"


def test_playbook_defects_are_left_alone():
    """Only install-scoped codes get the tag. A real defect must keep reading
    as fixable -- telling the model 'you cannot fix this' about a genuine typo
    would stop it correcting something it can."""
    for code in ("unknown_step_reference", "type_mismatch", "jinja_syntax_error"):
        d = _mark_environment_diagnostic(_diag(code))
        assert "environment" not in d, code
        assert "remediation" not in d, code


def test_every_environment_code_says_retrying_is_pointless():
    """The set is meant to grow. A future entry that forgets the one message
    that stops the loop would be tagged and still looped on."""
    for code, guidance in _ENVIRONMENT_CODES.items():
        assert "re-running" in guidance or "will return the same" in guidance, code


def test_end_to_end_through_verify_playbook():
    """The tag has to survive the promotion into `required_fixes`, not just
    exist on the helper -- that promotion is the only thing the model reads.
    Uses `placeholder-connector`, one of the two names from the live #107
    transcript."""
    from pathlib import Path

    from fsr_playbooks.mcp_server.tools_verify import verify_playbook

    src = Path(__file__).resolve().parents[2] / "examples" / "hello_connector.yaml"
    yaml_text = src.read_text().replace("fortinet-fortisiem", "placeholder-connector")

    res = verify_playbook(yaml_text)
    hits = [f for f in res["required_fixes"] if f["code"] == "unknown_connector"]
    assert hits, f"expected unknown_connector, got {[f['code'] for f in res['required_fixes']]}"
    assert hits[0].get("environment") is True
    assert "re-running" in hits[0].get("remediation", "")
    # Still blocking: an uninstalled connector must not become pushable.
    assert res["ready_to_push"] is False
