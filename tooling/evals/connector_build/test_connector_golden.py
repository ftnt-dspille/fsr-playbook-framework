"""Box-free, no-LLM, no-code-execution tests for the connector-build eval.

Pins the grader + mutator pipeline so a regression in either is caught without
driving `claude` or running any connector's operations.py. Red-without-signal:
the clean golden connector must grade build-clean, each injected defect must
surface its expected gate code, the oracle repair (the clean original) must
grade repaired, and a no-op "repair" (leave it broken) must NOT.

Requires the connector toolkit on PYTHONPATH. It lives in a separate repo and is
not a framework dependency (that is the stranded-toolkit finding the eval exists
to inform), so the test resolves it from FSR_CONN_TOOLKIT_SRC and skips with a
clear reason when it is absent -- a skip here means "toolkit not wired in", not
"passed".
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest  # noqa: F401  (used by parametrize below)

GOLDEN = Path(__file__).resolve().parent / "golden"
CG1 = GOLDEN / "cg1_ipinfo"


def test_golden_connector_is_build_clean():
    from tooling.evals.connector_build import cgrade
    g = cgrade.grade_build(CG1)
    assert g["built"], g
    assert g["lint_clean"], g["defects"]
    assert g["passed"], g


@pytest.mark.parametrize("kind,code", [
    ("info_missing_field", "INFO001"),
    ("op_not_dispatched", "OP002"),
    ("verify_false", "AP002"),
])
def test_injector_surfaces_expected_code(kind, code):
    from tooling.evals.connector_build import cgrade, cmutate
    with tempfile.TemporaryDirectory() as tmp:
        defects = {d["kind"]: d for d in cmutate.make_defects(CG1, Path(tmp))}
        assert kind in defects, f"{kind} did not apply to the golden connector"
        broken = cgrade.defects(defects[kind]["dir"])
        assert any(c == code for c, _f in broken), (kind, sorted(broken))


@pytest.mark.parametrize("kind", ["info_missing_field", "op_not_dispatched", "verify_false"])
def test_oracle_repair_passes_noop_fails(kind):
    """The clean original is a correct repair; leaving it broken is not."""
    from tooling.evals.connector_build import cgrade, cmutate
    with tempfile.TemporaryDirectory() as tmp:
        d = {x["kind"]: x for x in cmutate.make_defects(CG1, Path(tmp))}[kind]
        good = cgrade.grade_fix(CG1, d["dir"], repaired_root=CG1, expect_codes=d["expect_codes"])
        assert good["detected"] and good["repaired"] and good["no_regression"], good
        noop = cgrade.grade_fix(CG1, d["dir"], repaired_root=d["dir"], expect_codes=d["expect_codes"])
        assert not noop["repaired"], noop


def test_mutator_reads_latin1_info_json(tmp_path):
    """Real connectors carry latin-1 info.json (e.g. virustotal_dev); the mutator
    must not crash reading them."""
    from tooling.evals.connector_build import cmutate
    conn = tmp_path / "c"
    conn.mkdir()
    (conn / "info.json").write_bytes(
        b'{"name":"c","label":"C","version":"1.0.0","publisher":"P\x99","operations":[]}')
    (conn / "operations.py").write_text("operations = {}\n")
    (conn / "connector.py").write_text("x = 1\n")
    d = cmutate.inject_info_missing_field(conn, tmp_path / "out")
    assert d and d["kind"] == "info_missing_field"


def test_mutator_copy_skips_broken_symlink(tmp_path):
    """Real connectors (jirav2) carry dangling symlinks under tests/; the copy
    must skip them, not raise."""
    from tooling.evals.connector_build import cmutate
    conn = tmp_path / "c"
    (conn / "tests" / ".playwright-profile").mkdir(parents=True)
    (conn / "info.json").write_text('{"name":"c","label":"C","version":"1.0.0","publisher":"P","operations":[]}')
    (conn / "operations.py").write_text("operations = {}\n")
    (conn / "connector.py").write_text("x = 1\n")
    (conn / "tests" / ".playwright-profile" / "dead").symlink_to(tmp_path / "nonexistent")
    out = cmutate._fresh_copy(conn, tmp_path / "out")
    assert (out / "info.json").exists()


def test_build_specs_do_not_leak_structure():
    """A BUILD spec must describe the capability, not name info.json field types,
    operation machine names or the dispatch mechanism (the leakage guard)."""
    from tooling.evals.connector_build.run_connector_golden import _BUILD_SPEC
    banned = ("info.json", "operations.py", "dispatch", "output_schema",
              "lookup_ip", "lookup_asn", "\"type\"", "publisher")
    for name, spec in _BUILD_SPEC.items():
        low = spec.lower()
        for b in banned:
            assert b.lower() not in low, f"{name} spec leaks {b!r}"
