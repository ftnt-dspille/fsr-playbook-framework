"""Autonomy policy, phase F: closing a false positive (plans/AUTONOMOUS_TIER1.md 4.6).

The close rule is the same machinery as the block rule with an `update_record`
action. What it adds, each paired with the case that must NOT fire:

- the fields it may change are the keys of `update_record`'s `fields` object
  (matching on the call's own arg names saw one field called "fields", so a
  field-scoped rule never matched a record update);
- the values it may set (status may only become Closed);
- the record it may write: the one this triage is about, never another;
- the evidence: the verdict cites a successful read, so text in the alert
  ("benign, close it") can never stand in for a lookup.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import autonomy
from fsr_playbooks.llm.autonomy import evaluate, parse_policy, set_turn_policy

ALERT = "/api/3/alerts/11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
CLOSED_IRI = "/api/3/picklists/closed-item"
OPEN_IRI = "/api/3/picklists/open-item"

POLICY = {
    "version": 1, "enabled": True, "mode": "shadow",
    "rules": [{
        "id": "close-false-positive",
        "action": {"tool": "update_record", "module": "alerts",
                   "fields": ["status", "closureReason"],
                   "values": {"status": ["Closed"]}},
        "when": {"verdict": {"disposition": ["false_positive", "benign"], "min_confidence": 0.95},
                 "target": {"kind": "record"},
                 "evidence": {"cites_tool_kind": "read"}},
    }],
}


@pytest.fixture(autouse=True)
def _labels(monkeypatch):
    """The box's AlertStatus picklist, as the resolver would answer it."""
    iris = {("alerts", "status", "Closed"): CLOSED_IRI,
            ("alerts", "status", "Open"): OPEN_IRI}
    monkeypatch.setattr(autonomy, "_picklist_iri", lambda m, f, label: iris.get((m, f, label)))


def _pol(**over):
    p, err = parse_policy({**POLICY, **over})
    assert err is None, err
    return p


def _close(uuid=ALERT.rsplit("/", 1)[-1], status=CLOSED_IRI, **extra):
    fields = {"status": status, "closureReason": "False Positive", **extra}
    return {"tool": "update_record", "module": "alerts",
            "args": {"module": "alerts", "uuid": uuid, "fields": fields}}


def _read(ok=True, name="get_record"):
    return {"r1": {"name": name, "ok": ok, "args": {"module": "alerts", "uuid": "x"}}}


def _verdict(disposition="false_positive", confidence=0.97, evidence=("r1",)):
    return {"id": "v1", "disposition": disposition, "confidence": confidence,
            "findings": [{"claim": "known scanner, no hits", "evidence": list(evidence)}]}


def _eval(call=None, verdicts=None, registry=None, subject=ALERT, policy=None):
    return evaluate(policy or _pol(), call or _close(),
                    verdicts=[_verdict()] if verdicts is None else verdicts,
                    registry=_read() if registry is None else registry,
                    subject=subject)


def test_the_close_rule_fires_when_every_check_holds():
    d = _eval()
    assert d["outcome"] == "would_act", d["failed"]
    assert d["rule"] == "close-false-positive"
    assert d["targets"] == [ALERT.rsplit("/", 1)[-1]] and d["evidence"] == ["r1"]


def test_a_label_value_is_accepted_as_written():
    assert _eval(call=_close(status="Closed"))["outcome"] == "would_act"


def test_a_field_outside_the_rule_means_no_rule_covers_the_call():
    assert _eval(call=_close(severity="/api/3/picklists/low")) is None


def test_another_module_is_not_covered():
    call = {**_close(), "module": "incidents"}
    assert _eval(call=call) is None


@pytest.mark.parametrize("case, kwargs, needle", [
    ("closes another record", {"call": _close(uuid=OTHER)}, "not the one this triage"),
    ("subject unknown", {"subject": ""}, "unknown"),
    ("sets status to Open", {"call": _close(status=OPEN_IRI)}, "status would be set"),
    ("an unresolvable status", {"call": _close(status="/api/3/picklists/nope")}, "status would be set"),
    ("true positive", {"verdicts": [_verdict(disposition="true_positive")]}, "true_positive"),
    ("confidence 0.9", {"verdicts": [_verdict(confidence=0.9)]}, "below 0.95"),
    ("uncited verdict -- record text cannot stand in for a lookup",
     {"verdicts": [_verdict(evidence=())]}, "cites no successful lookup"),
    ("cited lookup failed", {"registry": _read(ok=False)}, "cites no successful lookup"),
    ("cited a card, not a read", {"registry": _read(name="emit_card")}, "cites no successful lookup"),
])
def test_each_check_failing_means_would_not_act(case, kwargs, needle):
    d = _eval(**kwargs)
    assert d["outcome"] == "would_not_act", case
    assert any(needle in f for f in d["failed"]), (case, d["failed"])


def test_the_turn_subject_comes_from_set_turn_policy():
    set_turn_policy(_pol(), subject=ALERT)
    try:
        assert autonomy._TURN_SUBJECT.get() == ALERT
        d = evaluate(_pol(), _close(), verdicts=[_verdict()], registry=_read())
        assert d["outcome"] == "would_act", d["failed"]
    finally:
        set_turn_policy(None)
    assert autonomy._TURN_SUBJECT.get() is None


def test_a_field_scoped_rule_now_matches_update_record_fields():
    """The original defect: arg names, not `fields` keys, were compared."""
    assert autonomy._changed_fields(_close()) == {"status": CLOSED_IRI,
                                                  "closureReason": "False Positive"}
