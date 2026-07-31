"""The decompiler's step-id slug must equal the parser's.

These two functions are a contract, not two conveniences. The decompiler
writes `next: <slug>` into YAML; the parser re-derives a step's id from its
`name:` when the author omitted `id:`. Any disagreement emits a reference that
points at an id no step will ever have.

They disagreed for the whole life of the corpus: the decompiler stripped
`[^a-z0-9_]+`, treating `_` as a keepable character, so "Create Domain
Indicator _ Deduplicated" slugged to `create_domain_indicator___deduplicated`
(space + kept underscore + space) where the parser collapsed the run to one
`_`. Seven names in the shipped-pack corpus hit it and 42 references broke.
"""
import pytest

from fsr_playbooks.compiler.decompiler import _slugify as decompiler_slugify
from fsr_playbooks.compiler.parser import _slugify as parser_slugify

# The corpus names that actually broke, plus the general shapes around them.
NAMES = [
    "Create Domain Indicator _ Deduplicated",
    "Create File MD5 Indicator  _ Deduplicated",   # double space, too
    "Create Host Indicator _ Deduplicated",
    "Create IP Indicator _ Deduplicated",
    "Create URL Indicator _ Deduplicated",
    "Show info _ get results",
    "Block Domain",
    "already_snake_case",
    "Mixed_Case _ With  Spaces",
    "trailing _ ",
    " _ leading",
    "Punctuation! (parens) & symbols",
    "hyphen-separated-name",
]


@pytest.mark.parametrize("name", NAMES)
def test_decompiler_slug_matches_parser_slug(name):
    assert decompiler_slugify(name, set()) == parser_slugify(name)


def test_the_exact_regression_case():
    """Pinned literally -- this is the string that broke 42 references."""
    name = "Create Domain Indicator _ Deduplicated"
    assert decompiler_slugify(name, set()) == "create_domain_indicator_deduplicated"
    assert "___" not in decompiler_slugify(name, set())


def test_collision_suffixing_survives_the_shared_rule():
    """The decompiler must still disambiguate; only the base rule is shared.

    The parser reports duplicate ids as an error. The decompiler cannot -- it is
    handed whatever FSR contains -- so it appends a counter instead.
    """
    taken: set[str] = set()
    assert decompiler_slugify("Block Domain", taken) == "block_domain"
    assert decompiler_slugify("Block Domain", taken) == "block_domain_2"
    assert decompiler_slugify("Block Domain", taken) == "block_domain_3"


def test_empty_name_falls_back_to_step():
    assert decompiler_slugify("", set()) == "step"
    assert parser_slugify("") == "step"
