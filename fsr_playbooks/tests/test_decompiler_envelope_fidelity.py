"""Phase 4 — decompiler fidelity for the universal step envelope.

On pull (FSR JSON → friendly YAML) the decompiler must surface the envelope
wire keys back out of `arguments:` to the step surface — otherwise a
connector's `when`/`do_until`/`agent` round-trips as raw `arguments.when`,
a shape the editor never compiles. Also covers per-step `description`
round-trip and the `message: {content}` → `post_comment:` fold.
"""
from __future__ import annotations

import yaml

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml, _decompile_step
from fsr_playbooks.compiler.ir import Step
from fsr_playbooks._db import PACKAGED_SLIM_DB


def _roundtrip_steps(yaml_text: str):
    """Compile → decompile → parse, returning {step name: step dict}."""
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    doc = yaml.safe_load(decompile_to_yaml(res.fsr_json, PACKAGED_SLIM_DB))
    steps = doc["playbooks"][0]["steps"]
    return {s["name"]: s for s in steps}


def test_envelope_keys_hoisted_back_to_step_level():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set
      - name: Set
        type: set_variable
        when: "{{ vars.score > 70 }}"
        ignore_errors: true
        vars:
          foo: bar
"""
    )
    s = by_name["Set"]
    assert s["when"] == "{{ vars.score > 70 }}"
    assert s["ignore_errors"] is True
    # The envelope keys must NOT linger inside arguments.
    assert "when" not in (s.get("arguments") or {})
    assert "ignore_errors" not in (s.get("arguments") or {})


def test_step_description_round_trips():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set
      - name: Set
        type: set_variable
        description: "explains this step"
        vars:
          foo: bar
"""
    )
    assert by_name["Set"]["description"] == "explains this step"


def test_message_block_lifted_out_of_arguments():
    by_name = _roundtrip_steps(
        """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Comment
      - name: Comment
        type: set_variable
        post_comment: "auto note"
        vars:
          foo: bar
"""
    )
    s = by_name["Comment"]
    # message surfaces at the step level, never buried in arguments.
    assert "message" not in (s.get("arguments") or {})
    assert "message" in s or "post_comment" in s


def test_pure_message_content_folds_to_post_comment():
    """A bare `message: {content: str}` (e.g. from a hand-authored pull)
    reverses to the friendlier `post_comment:` sugar."""
    step = Step(id="c", type="set_variable", name="Comment",
                arguments={"message": {"content": "hello"}, "foo": "bar"})
    out = _decompile_step(step)
    assert out["post_comment"] == "hello"
    assert "message" not in out
    assert "message" not in (out.get("arguments") or {})


def test_enriched_message_kept_as_block():
    """An enriched message (more than `content`) stays a full block — folding
    to post_comment would drop tags/type/thread."""
    step = Step(id="c", type="set_variable", name="Comment",
                arguments={"message": {"content": "<p>hi</p>", "tags": [],
                                       "thread": False}})
    out = _decompile_step(step)
    assert "post_comment" not in out
    assert out["message"]["content"] == "<p>hi</p>"
