"""Discovery must not lie: stale-catalog detection + honest near-matches.

Both behaviours here exist because of one live session set (box 159,
2026-07-22) where the agent looked incompetent while reasoning correctly on
what its tools told it:

  * FortiAnalyzer was installed at 09:18; the last warmup ran at 07:08. The
    catalog is a snapshot with an emptiness-only staleness check, so for the
    rest of the day every ``faz_*`` call got "connector
    'fortinet-fortianalyzer' not found in store" — indistinguishable from
    "that connector doesn't exist".
  * ``find_connector`` then compounded it: difflib at cutoff 0.45 with no
    token evidence answered "siem" with ['smtp', 'imap'], "crowdstrike" with
    ['cyops_utilities'] and "fortianalyzer" with ['fortinet-fortiedr'] — all
    phrased as "did you mean…?", which the model relayed as a real finding.

A wrong suggestion is worse than none: it redirects the whole turn.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server.tools_discovery import _plausible_name_matches

NAMES = [
    "cyops_utilities", "exchange", "fortigate-cloud", "fortigate-firewall",
    "fortinet-fortiai-proxy", "fortinet-forticlient-ems", "fortinet-fortiedr",
    "fortinet-fortiguard-ioc", "fortinet-fortimanager-json-rpc",
    "fortisoar-ml-engine", "http", "imap", "servicenow", "smtp", "smtp_ng",
    "tenable-io", "virustotal", "whois-rdap",
]


# ── near-match honesty ──────────────────────────────────────────────────────

@pytest.mark.parametrize("q", ["siem", "crowdstrike", "fortisiem",
                               "fortianalyzer", "xyzzy"])
def test_absent_products_get_no_suggestion(q):
    """The exact queries that produced confident nonsense on the live box.

    None of these products is in NAMES, so the only correct answer is silence.
    """
    assert _plausible_name_matches(q, NAMES) == [], (
        f"{q!r} produced a spelling suggestion for a product that is simply "
        f"not installed — this is the failure mode that sent the model to the "
        f"wrong vendor"
    )


def test_vendor_stem_alone_is_not_a_match():
    """"forti" is shared by a whole family and must not make them near-matches."""
    for q in ("fortianalyzer", "fortisiem"):
        for got in _plausible_name_matches(q, NAMES):
            assert "forti" != got[:5] or got.startswith(q[:8]), (
                f"{q!r} matched {got!r} on the shared vendor stem alone"
            )


@pytest.mark.parametrize("q,expected", [
    ("fortiedr", "fortinet-fortiedr"),        # product name, vendor-prefixed row
    ("virustotl", "virustotal"),              # single-char typo
    ("fortgate", "fortigate-firewall"),       # transposition/omission typo
])
def test_real_typos_still_resolve(q, expected):
    """Tightening must not cost us the cases suggestions are FOR."""
    assert expected in _plausible_name_matches(q, NAMES)


def test_present_connector_is_found_once_catalogued():
    """The FortiAnalyzer case, after a warmup picks it up."""
    names = NAMES + ["fortinet-fortianalyzer"]
    assert _plausible_name_matches("fortianalyzer", names) == [
        "fortinet-fortianalyzer"]


def test_very_short_queries_are_not_guessed_at():
    assert _plausible_name_matches("ip", NAMES) == []


# ── stale-catalog detection ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_probe():
    original = _shared._LIVE_CATALOG_PROBE
    yield
    _shared.set_live_catalog_probe(original)


def test_no_probe_means_unknown_not_absent():
    """Bare library (no connector): behaviour is exactly as before."""
    _shared.set_live_catalog_probe(None)
    assert _shared.box_has_connector("fortinet-fortianalyzer") is None
    assert _shared.stale_catalog_hint("fortinet-fortianalyzer") is None


def test_hint_fires_when_the_box_has_it_but_the_catalog_does_not():
    _shared.set_live_catalog_probe(lambda: {"fortinet-fortianalyzer", "smtp"})
    hint = _shared.stale_catalog_hint("fortinet-fortianalyzer")
    assert hint is not None
    assert hint["code"] == "stale_catalog"
    # The message must say the connector EXISTS — that is the whole point.
    assert "IS installed" in hint["message"]
    assert any("warm" in s.lower() for s in hint["suggestions"])


def test_no_hint_for_a_connector_the_box_really_lacks():
    _shared.set_live_catalog_probe(lambda: {"smtp"})
    assert _shared.box_has_connector("fortinet-fortisiem") is False
    assert _shared.stale_catalog_hint("fortinet-fortisiem") is None


def test_probe_failure_is_unknown_never_absent():
    """A failing/None probe must not be read as 'the box has nothing'.

    Treating "couldn't ask" as "isn't there" would flip every lookup into a
    false stale-catalog claim — a new confident falsehood replacing the old.
    """
    def _boom():
        raise RuntimeError("loopback down")

    for probe in (_boom, lambda: None):
        _shared.set_live_catalog_probe(probe)
        assert _shared.box_has_connector("smtp") is None
        assert _shared.stale_catalog_hint("smtp") is None


def test_probe_returning_a_bad_shape_is_tolerated():
    _shared.set_live_catalog_probe(lambda: 42)
    assert _shared.box_has_connector("smtp") is None
