"""The durable half of HARDEN-1: the model should not echo the playbook at all.

Repairing a corrupt 20 kB transcription (`sanitize_yaml_text`) and refusing a
lossy save (`prewrite`) both treat a *symptom*. The cause is that read-path
tools demanded the whole document as an argument, so the model re-emitted it
on every turn -- and a re-emission can arrive corrupted (a mangled `®` reached
us as a NUL byte and killed a turn) or quietly short a field.

The cure is that omitting `yaml_text` on a read-path tool means "the playbook
already open", which the appliance has authoritatively. The model then has no
opportunity to corrupt or drop anything, because it never transcribes it.

The line these tests defend is **which tools may do that**. A READ tool
grounding an empty argument is correct. An AUTHORING tool doing it would be a
far worse bug than the one being fixed: `validate_yaml("")` reporting a clean
compile of the OLD document would tell the model its unwritten draft is fine.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server._shared import (
    load_yaml_text,
    reset_grounded_yaml,
    set_grounded_yaml,
)

OPEN_PLAYBOOK = """\
collection: Live Collection
playbooks:
  - name: Hunt Indicators
    steps:
      - name: Start
        type: start
      - name: Enrich
        type: connector
"""


@pytest.fixture
def grounded():
    """Bind the appliance's copy for the turn, as the chat loop does."""
    token = set_grounded_yaml(OPEN_PLAYBOOK)
    try:
        yield OPEN_PLAYBOOK
    finally:
        reset_grounded_yaml(token)


# --------------------------------------------------------------------------- #
# The new behaviour.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("empty", ["", None, "   ", "\n\n"])
def test_omitted_yaml_text_reads_the_open_playbook(grounded, empty):
    doc, load = load_yaml_text(empty, ground_when_empty=True)
    assert doc["playbooks"][0]["name"] == "Hunt Indicators"
    assert load.used_grounding is True
    assert "no yaml_text supplied" in load.grounding_reason


def test_supplied_yaml_text_still_wins(grounded):
    """Grounding is a default, never an override. A real draft must not be
    silently replaced by the document already on the appliance."""
    draft = "collection: Draft\nplaybooks:\n  - name: Something New\n"
    doc, load = load_yaml_text(draft, ground_when_empty=True)
    assert doc["playbooks"][0]["name"] == "Something New"
    assert load.used_grounding is False


def test_empty_without_the_flag_is_still_an_empty_document(grounded):
    """Opt-in per caller: every pre-existing call site keeps its old
    behaviour, so this change cannot alter a tool nobody reviewed."""
    doc, load = load_yaml_text("", ground_when_empty=False)
    assert doc == {}
    assert load.used_grounding is False


def test_empty_with_nothing_bound_is_an_empty_document():
    """Off a playbook page there is no open document. Omitting yaml_text must
    yield empty, not raise -- the caller reports 'no playbooks' as it always
    did."""
    assert _shared.get_grounded_yaml() is None
    doc, load = load_yaml_text("", ground_when_empty=True)
    assert doc == {}
    assert load.used_grounding is False


def test_grounding_does_not_leak_across_turns():
    """The ContextVar is released in a finally; a leak would ground an
    unrelated session against another customer's playbook."""
    token = set_grounded_yaml(OPEN_PLAYBOOK)
    reset_grounded_yaml(token)
    doc, load = load_yaml_text("", ground_when_empty=True)
    assert doc == {}
    assert load.used_grounding is False


def test_corrupt_transcription_still_falls_back(grounded):
    """The repair path (the original fix) must survive this change."""
    doc, load = load_yaml_text("collection: x\n\x00broken: [", ground_when_empty=True)
    assert doc["playbooks"][0]["name"] == "Hunt Indicators"
    assert load.used_grounding is True
    assert "no yaml_text supplied" not in load.grounding_reason


# --------------------------------------------------------------------------- #
# The boundary: authoring tools must NOT ground.
# --------------------------------------------------------------------------- #

def test_only_read_path_modules_opt_into_empty_grounding():
    """`validate_yaml("")` must never report a clean compile of the OLD
    document -- that would tell the model its unwritten draft is fine, a worse
    failure than the corruption this feature fixes.

    Asserted by SOURCE, not by calling the tools: the authoring tools resolve a
    live client and would make this a box-dependent test. The invariant is
    structural anyway -- who passes the flag -- and a source guard states it
    where a future edit will trip over it.
    """
    import pathlib

    import fsr_playbooks.mcp_server as pkg

    # _shared.py DEFINES the flag; tools_analysis.py is the read-path caller.
    allowed = {"tools_analysis.py", "_shared.py"}
    offenders = []
    for path in pathlib.Path(pkg.__file__).parent.glob("*.py"):
        if "ground_when_empty=True" in path.read_text() and path.name not in allowed:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} opted an empty yaml_text into grounding. If any of these "
        "is an AUTHORING tool (validate/compile/resolve/push), it will now "
        "report on a document the model never wrote. Add it to `allowed` only "
        "if it genuinely READS the open playbook.")


def test_read_path_tools_declare_yaml_text_optional():
    """The affordance only exists if the signature allows omission -- a
    required arg means the model must still echo the document."""
    import inspect

    from fsr_playbooks.mcp_server import tools_analysis

    # step_test is deliberately NOT in this list: its `step_id` is a required
    # positional that follows `yaml_text`, so defaulting yaml_text would be a
    # syntax error, and reordering would break every positional caller. It
    # still grounds a corrupt copy; it just cannot offer the omission.
    for fn in (tools_analysis.step_through_playbook,
               tools_analysis.analyze_playbook):
        param = inspect.signature(fn).parameters["yaml_text"]
        assert param.default == "", (
            f"{fn.__name__}.yaml_text is still required, so the model has no "
            "way to avoid transcribing the open playbook")


def test_read_path_docstrings_tell_the_model_to_omit_it():
    """The docstring IS the tool description the model reads. An optional
    argument nobody is told about changes no behaviour."""
    from fsr_playbooks.mcp_server import tools_analysis

    for fn in (tools_analysis.step_through_playbook,
               tools_analysis.analyze_playbook):
        doc = (fn.__doc__ or "").lower()
        assert "omit" in doc and "open playbook" in doc, (
            f"{fn.__name__} accepts an omitted yaml_text but never says so")


def test_step_through_runs_on_the_open_playbook(grounded, monkeypatch):
    """End to end on the real tool: the call that died on the NUL byte is now
    expressible without sending the document at all.

    The live client is stubbed out rather than merely disabling live ops --
    step_through_playbook renders args through the appliance's Jinja engine
    regardless of `execute_safe_ops`, so it reaches for a client either way.
    """
    from fsr_playbooks.mcp_server import tools_analysis

    monkeypatch.setattr(_shared, "_live_client", lambda: None)

    out = tools_analysis.step_through_playbook(execute_safe_ops=False)
    assert out.get("used_open_playbook") is True
    assert "keep omitting yaml_text" in out.get("yaml_text_note", "")
    assert out.get("error") != "no playbooks in YAML"
    assert out.get("playbook") == "Hunt Indicators"


def test_live_client_returns_none_when_the_box_is_unreachable(monkeypatch):
    """`_live_client` is documented to return None without a live FSR, but
    get_client() AUTHENTICATES -- so a configured-but-DOWN box raised straight
    through it, and every caller documented to degrade gracefully exploded
    instead. Found while testing the grounding path against a down box."""
    monkeypatch.setattr(_shared, "_LIVE_CLIENT_CACHE", {})

    class _Cfg:
        def is_live(self): return True

    import probes._env as env
    monkeypatch.setattr(env, "get_config", lambda: _Cfg())

    def _boom():
        raise ConnectionError("box is down")

    monkeypatch.setattr(env, "get_client", _boom)
    assert _shared._live_client() is None


def test_unreachable_box_is_not_memoised_as_dead(monkeypatch):
    """A box that comes back must reconnect on the next call, not stay dead
    for the life of the process."""
    monkeypatch.setattr(_shared, "_LIVE_CLIENT_CACHE", {})

    class _Cfg:
        def is_live(self): return True

    import probes._env as env
    monkeypatch.setattr(env, "get_config", lambda: _Cfg())
    monkeypatch.setattr(env, "get_client",
                        lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert _shared._live_client() is None

    sentinel = object()
    monkeypatch.setattr(env, "get_client", lambda: sentinel)
    assert _shared._live_client() is sentinel
