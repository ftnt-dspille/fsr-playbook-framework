"""Model-supplied `yaml_text` must survive a corrupted verbatim copy.

Regression + parity guard for the NUL-byte class of failure found live on a
.159 box: `analyze_playbook` on a real 6-step playbook died with

    yaml parse failed: unacceptable character #x0000: special characters are
    not allowed in "<unicode string>", position 15305

The record on the appliance was clean (real (R) signs, zero NUL bytes) and so
was the `entity.playbook_yaml` the widget sent. Only the model's re-emitted
copy was damaged: it wrote the (R) as a malformed escape whose JSON decoding
yields NUL + "AE". One bad byte 15 kB into a 20 kB blob killed the entire turn
-- no diagnostics, no assistant text, `stop_reason: null`.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from fsr_playbooks.mcp_server._shared import (
    load_yaml_text,
    reset_grounded_yaml,
    sanitize_yaml_text,
    set_grounded_yaml,
)

# The exact corruption seen on the box: the (R) sign arriving as NUL + "AE".
CORRUPTED_FRAGMENT = "Product: Microsoft\x00AE Windows\x00AE Operating System"

MINIMAL_PB = """\
playbooks:
- name: Hunt Indicators
  steps:
  - name: Start
    type: start
    arguments:
      note: {note}
"""


class TestSanitizeYamlText:
    def test_strips_nul_and_reports_count(self):
        clean, removed = sanitize_yaml_text(CORRUPTED_FRAGMENT)
        assert removed == 2
        assert "\x00" not in clean
        # Only the illegal byte goes; the orphaned "AE" the model left behind
        # stays. We are making the document parseable, not guessing that the
        # author meant "(R)" -- a repair we cannot prove.
        assert clean == "Product: MicrosoftAE WindowsAE Operating System"

    def test_preserves_legal_whitespace(self):
        text = "a: 1\n\tb: 2\r\nc: 3\n"
        clean, removed = sanitize_yaml_text(text)
        assert removed == 0
        assert clean == text, "tab/LF/CR are legal YAML and must survive"

    def test_clean_input_is_returned_unchanged_identity(self):
        text = "playbooks: []\n"
        clean, removed = sanitize_yaml_text(text)
        assert removed == 0
        assert clean is text, "fast path should not copy a clean document"

    def test_real_non_ascii_is_preserved(self):
        """The (R) itself is legal -- only its corrupted form is not."""
        text = "note: Microsoft\u00ae Windows\u00ae\n"
        clean, removed = sanitize_yaml_text(text)
        assert removed == 0
        assert "\u00ae" in clean

    @pytest.mark.parametrize("ctrl", ["\x00", "\x01", "\x08", "\x0b", "\x0c", "\x1f", "\x7f"])
    def test_each_illegal_control_char_is_stripped(self, ctrl):
        clean, removed = sanitize_yaml_text(f"a: b{ctrl}c")
        assert removed == 1 and ctrl not in clean

    def test_non_string_input_is_tolerated(self):
        assert sanitize_yaml_text(None) == ("", 0)
        assert sanitize_yaml_text(123) == ("", 0)


class TestLoadYamlText:
    def test_corrupted_document_now_parses(self):
        """The regression: this raised before the sanitizer existed."""
        bad = MINIMAL_PB.format(note=CORRUPTED_FRAGMENT.replace(":", " -"))
        doc, load = load_yaml_text(bad)
        assert load.control_chars_removed == 2
        assert not load.used_grounding
        assert doc["playbooks"][0]["name"] == "Hunt Indicators"

    def test_pinning_the_old_behaviour_proves_the_test_bites(self):
        """Without the strip, PyYAML rejects the whole document.

        Guards against the sanitizer silently becoming a no-op: if this ever
        stops raising, PyYAML changed and the test above no longer proves
        anything.
        """
        import yaml

        bad = MINIMAL_PB.format(note=CORRUPTED_FRAGMENT.replace(":", " -"))
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(bad)

    def test_empty_document_yields_empty_dict(self):
        doc, load = load_yaml_text("")
        assert doc == {} and load.control_chars_removed == 0

    def test_parse_errors_still_propagate(self):
        """Callers own their error contract -- don't swallow real syntax errors."""
        import yaml

        with pytest.raises(yaml.YAMLError):
            load_yaml_text("a:\n  - [unclosed\n")


@pytest.fixture
def grounded():
    """Bind an open playbook for the turn, as the chat loop does."""
    tokens = []

    def _bind(text):
        tokens.append(set_grounded_yaml(text))

    yield _bind
    for t in reversed(tokens):
        reset_grounded_yaml(t)


GROUND_TRUTH = MINIMAL_PB.format(note="the appliance's own copy")

# Sanitizing cannot save this one: the model also emitted an invalid `\,`
# escape inside a double-quoted scalar. Taken from the same real .159 payload
# as CORRUPTED_FRAGMENT -- one model copy, corrupted two different ways, which
# is why stripping control chars alone is necessary but not sufficient.
UNSALVAGEABLE = 'playbooks:\n- name: X\n  steps:\n  - mock: "a\\,b"\n'


class TestGroundingFallback:
    def test_unparseable_copy_falls_back_to_the_open_playbook(self, grounded):
        grounded(GROUND_TRUTH)
        doc, load = load_yaml_text(UNSALVAGEABLE)
        assert load.used_grounding is True
        assert load.grounding_reason           # says why, for the tool note
        assert doc["playbooks"][0]["name"] == "Hunt Indicators"

    def test_no_grounding_bound_means_the_error_still_raises(self):
        """Fail loudly rather than invent a document out of nothing."""
        import yaml

        with pytest.raises(yaml.YAMLError):
            load_yaml_text(UNSALVAGEABLE)

    def test_a_parseable_copy_is_never_replaced(self, grounded):
        """Grounding is a repair path, not a silent override of good input."""
        grounded(GROUND_TRUTH)
        mine = MINIMAL_PB.format(note="the model's own valid edit")
        doc, load = load_yaml_text(mine)
        assert load.used_grounding is False
        assert doc["playbooks"][0]["steps"][0]["arguments"]["note"] == (
            "the model's own valid edit")

    def test_identical_text_does_not_pretend_to_recover(self, grounded):
        """If grounding IS the failing text, re-parsing it changes nothing."""
        import yaml

        grounded(UNSALVAGEABLE)
        with pytest.raises(yaml.YAMLError):
            load_yaml_text(UNSALVAGEABLE)

    def test_opt_out_disables_the_fallback(self, grounded):
        """`allow_grounding=False` means 'parse exactly this text'."""
        import yaml

        grounded(GROUND_TRUTH)
        with pytest.raises(yaml.YAMLError):
            load_yaml_text(UNSALVAGEABLE, allow_grounding=False)

    def test_grounding_does_not_leak_across_turns(self):
        """A ContextVar left set would silently ground an unrelated session."""
        token = set_grounded_yaml(GROUND_TRUTH)
        reset_grounded_yaml(token)
        import yaml

        with pytest.raises(yaml.YAMLError):
            load_yaml_text(UNSALVAGEABLE)


class TestCompilerWritePath:
    """The compile/validate/push family must survive the same corruption.

    These reach `compiler.parser.parse_yaml`, NOT the tool layer's
    `load_yaml_text` -- and `push_playbook` WRITES. A stray control char here
    fails a save, not merely a read.
    """

    #: Current step shape -- args hoisted to the step top level (the
    #: `arguments:` wrapper is rejected by the compiler).
    COMPILER_PB = (
        "collection: Hunt\n"
        "playbooks:\n"
        "- name: Hunt Indicators\n"
        "  steps:\n"
        "  - name: Start\n"
        "    type: start\n"
        "    note: {note}\n"
    )

    def test_compiler_parses_a_control_char_corrupted_document(self):
        from fsr_playbooks.compiler.parser import parse_yaml

        bad = self.COMPILER_PB.format(
            note=CORRUPTED_FRAGMENT.replace(":", " -"))
        coll, errors = parse_yaml(bad)
        parse_errs = [e for e in errors if "YAML parse error" in str(e.message)]
        assert not parse_errs, (
            f"control char still breaks the write path: {parse_errs}")
        assert coll is not None, [f"{e.code}: {e.message}" for e in errors]

    def test_the_write_path_test_bites(self):
        """Same document, unsanitized, must still break PyYAML."""
        import yaml

        bad = self.COMPILER_PB.format(
            note=CORRUPTED_FRAGMENT.replace(":", " -"))
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(bad)

    def test_compiler_does_not_ground(self):
        """`parse_yaml` doubles as a whole-doc-vs-snippet CLASSIFIER.

        apply_patch asks "does this compile?" to decide whether the model sent
        a whole document or a snippet. If a grounding fallback fired here, that
        question would always answer yes and every snippet would be
        mis-classified as a whole-doc patch.
        """
        from fsr_playbooks.compiler.parser import parse_yaml

        tok = set_grounded_yaml(GROUND_TRUTH)
        try:
            coll, errors = parse_yaml(UNSALVAGEABLE)
        finally:
            reset_grounded_yaml(tok)
        assert coll is None or errors, (
            "parse_yaml silently substituted the open playbook -- that breaks "
            "apply_patch's snippet classification")


class TestNoBareSafeLoadParityGuard:
    """Every `yaml_text` entry point must go through `load_yaml_text`.

    This is the guard the bug class needs: the fix is only as good as its
    coverage, and a NEW tool that hand-rolls `yaml.safe_load(yaml_text)`
    reintroduces the exact failure. Mirrors the house rule that a concept
    living in more than one place must have the relationship asserted.
    """

    #: The only places allowed to call yaml.safe_load directly. Everything
    #: else must come through load_yaml_text (tool layer) or parse_yaml
    #: (compiler), both of which sanitize first.
    SANCTIONED = {
        "_shared.py",     # implements load_yaml_text
        "parser.py",      # compiler entry; sanitizes inline (no grounding)
    }

    def test_no_module_hand_rolls_a_yaml_parse(self):
        """Catch `safe_load(<anything>)`, not just the name I happened to fix.

        The first version of this guard grepped for the literal
        `safe_load(yaml_text)` -- and therefore MISSED
        `compiler/parser.py`'s `safe_load(text)`, which is the entry for
        compile_yaml / validate_yaml / push_playbook: the write path, where a
        corrupted copy is most dangerous. Guarding the route I fixed rather
        than the concept is exactly how a fix inherits its own blind spot.
        """
        pkg = pathlib.Path(__file__).resolve().parents[1]
        pattern = re.compile(r"\byaml\.safe_load\s*\(|\b_yaml\.safe_load\s*\(")
        offenders = []
        for path in sorted(pkg.rglob("*.py")):
            if path.name in self.SANCTIONED or "/tests/" in path.as_posix():
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(pkg)))
        assert offenders == [], (
            "these modules parse YAML without the control-char strip, so a "
            "model copy corrupted the way the .159 payload was would fail "
            "there. Route them through _shared.load_yaml_text (tools) or "
            f"compiler.parser.parse_yaml: {offenders}"
        )
