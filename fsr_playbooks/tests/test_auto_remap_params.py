"""run_op auto-remap: a single semantic-alias param miss (ip→value) is
recovered without a round-trip. Export sess-vtd15c5v wasted ~8 calls guessing
`ip`/`srcIP`/`host` when the real param was `value`."""
from fsr_playbooks.mcp_server._shared import _auto_remap_params


def test_single_unknown_to_single_missing_remaps():
    issues = [
        {"param": "ip", "problem": "unknown"},
        {"param": "value", "problem": "missing_required"},
    ]
    out = _auto_remap_params({"ip": "1.2.3.4"}, issues)
    assert out == {"params": {"value": "1.2.3.4"}, "from": "ip", "to": "value"}


def test_no_remap_when_ambiguous():
    # two unknowns → can't tell which maps where
    issues = [
        {"param": "ip", "problem": "unknown"},
        {"param": "srcIP", "problem": "unknown"},
        {"param": "value", "problem": "missing_required"},
    ]
    assert _auto_remap_params({"ip": "1.2.3.4", "srcIP": "5.6.7.8"}, issues) is None


def test_no_remap_for_nonscalar_value():
    issues = [
        {"param": "filter", "problem": "unknown"},
        {"param": "value", "problem": "missing_required"},
    ]
    assert _auto_remap_params({"filter": {"a": 1}}, issues) is None


def test_no_remap_without_missing_required():
    issues = [{"param": "ip", "problem": "unknown"}]
    assert _auto_remap_params({"ip": "1.2.3.4"}, issues) is None
