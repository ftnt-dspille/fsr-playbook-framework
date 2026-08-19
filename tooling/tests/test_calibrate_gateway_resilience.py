"""A sweep must not be defeated -- or silently believed -- because of the gateway.

Run 20260817T020056Z spent ~35 minutes against the screening gateway, lost 4
of 15 repeats to `httpx.ConnectError`, lost all 3 repeats of one fixture, and
exited 0. Three separate defects, one bad afternoon:

  * nothing asked whether the gateway was up BEFORE committing the time (#144);
  * a transient drop lost the repeat outright instead of being re-driven (#142);
  * the contaminated result exited 0, so it could be banked as a baseline (#143).

These are pinned by behaviour where behaviour exists -- `probe_llm_gateway`
against a stubbed transport, `_aggregate` against real run records,
`contamination_exit_code` against its inputs -- rather than by grepping the
source for a flag name. A test that only greps passes just as happily when the
flag is parsed and ignored.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tooling"))

from evals.calibrate_investigation import (  # noqa: E402
    _aggregate,
    _is_transport_failure,
    contamination_exit_code,
)

from fsr_playbooks.doctor import check_llm_gateway, probe_llm_gateway  # noqa: E402


# --------------------------------------------------------------- #144 preflight
class _Resp:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _stub_get(monkeypatch, result):
    """Bind httpx.get to `result` -- a _Resp to return, or an Exception to raise."""
    import httpx

    def fake_get(url, **kw):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(httpx, "get", fake_get)


def test_preflight_reports_an_unreachable_gateway(monkeypatch) -> None:
    import httpx
    _stub_get(monkeypatch, httpx.ConnectError("All connection attempts failed"))
    ok, detail = probe_llm_gateway("https://gw.example.com/v1", "k", "some-model")
    assert ok is False
    assert "unreachable" in detail and "ConnectError" in detail


def test_preflight_rejects_a_bad_key(monkeypatch) -> None:
    _stub_get(monkeypatch, _Resp(401))
    ok, detail = probe_llm_gateway("https://gw.example.com/v1", "k", "some-model")
    assert ok is False
    assert "key is rejected" in detail


def test_preflight_fails_when_the_named_model_is_not_served(monkeypatch) -> None:
    """The exact 'measured a model nobody chose' failure, caught for free."""
    _stub_get(monkeypatch, _Resp(200, {"data": [{"id": "other-model"}]}))
    ok, detail = probe_llm_gateway("https://gw.example.com/v1", "k", "some-model")
    assert ok is False
    assert "does NOT serve" in detail and "other-model" in detail


def test_preflight_passes_when_the_model_is_served(monkeypatch) -> None:
    _stub_get(monkeypatch, _Resp(200, {"data": [{"id": "some-model"}]}))
    ok, _ = probe_llm_gateway("https://gw.example.com/v1", "k", "some-model")
    assert ok is True


def test_preflight_does_not_invent_an_outage_from_a_gated_listing(monkeypatch) -> None:
    """Some gateways refuse /models but complete fine. Up is up."""
    _stub_get(monkeypatch, _Resp(404))
    ok, detail = probe_llm_gateway("https://gw.example.com/v1", "k", "some-model")
    assert ok is True
    assert "unverified" in detail


def test_doctor_gateway_check_is_a_pass_when_none_is_configured(
        monkeypatch, tmp_path) -> None:
    """Most work here never touches the gateway; absence is not a fault.

    A check that failed on an unconfigured laptop would sit perma-red and get
    deleted, taking the configured-and-down case with it. chdir to an empty
    dir: the check falls back to a `.env` in the cwd, and this repo has one."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FRANK_BASE_URL", raising=False)
    monkeypatch.delenv("FRANK_API_KEY", raising=False)
    monkeypatch.delenv("FRANK_MODEL", raising=False)
    c = check_llm_gateway()
    assert c.ok is True
    assert "not set" in c.detail


def test_doctor_gateway_check_fails_on_a_configured_dead_gateway(monkeypatch) -> None:
    import httpx
    monkeypatch.setenv("FRANK_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("FRANK_API_KEY", "k")
    monkeypatch.setenv("FRANK_MODEL", "some-model")
    _stub_get(monkeypatch, httpx.ConnectError("All connection attempts failed"))
    c = check_llm_gateway()
    assert c.ok is False
    assert "BEFORE starting a sweep" in c.detail


# ------------------------------------------------------------------ #142 retry
@pytest.mark.parametrize("msg", [
    "httpx.ConnectError: All connection attempts failed",
    "ReadError",
    "502 Bad Gateway",
    "rate limit exceeded",
])
def test_transport_failures_are_retryable(msg: str) -> None:
    assert _is_transport_failure(msg) is True


@pytest.mark.parametrize("msg", [
    "400 invalid_request: tool schema rejected",
    "422 unprocessable",
    "maximum context length exceeded",
])
def test_a_provider_rejection_is_never_retried(msg: str) -> None:
    """The request reached the model. Re-sending buys the same refusal twice."""
    assert _is_transport_failure(msg) is False


def test_retries_are_counted_not_smoothed_away() -> None:
    """A fixture that only scores because it was re-driven is not healthy.

    The pass cell alone would read 2/2 and say nothing about the gateway."""
    runs = [
        {"recall": 1.0, "passed": True, "calls": 8, "quality": {}, "retries": 2},
        {"recall": 1.0, "passed": True, "calls": 9, "quality": {}, "retries": 1},
    ]
    spread = _aggregate(runs)["spread"]
    assert spread["retries"] == 3
    assert spread["lost"] == 0


def test_a_run_lost_after_its_retries_is_still_lost() -> None:
    """Retrying is bounded. Exhausting it must not quietly score the run 0.0."""
    runs = [
        {"recall": 1.0, "passed": True, "calls": 8, "quality": {}, "retries": 0},
        {"recall": None, "passed": False, "calls": 0, "quality": {},
         "lost": True, "retries": 1, "error": "ConnectError"},
    ]
    agg = _aggregate(runs)
    assert agg["spread"]["lost"] == 1
    assert agg["spread"]["repeats"] == 1, "the lost repeat must not be scored"
    assert agg["recall"] == 1.0, "the surviving run's recall must not be averaged down"


# ------------------------------------------------------------- #143 exit code
def test_a_clean_sweep_exits_zero() -> None:
    assert contamination_exit_code(0, allow_contaminated=False) == 0


def test_a_contaminated_sweep_exits_non_zero() -> None:
    """Anything reading the exit code -- CI, a Makefile, a shell && -- would
    otherwise bank partial numbers as a baseline."""
    assert contamination_exit_code(1, allow_contaminated=False) == 3


def test_the_contamination_gate_has_an_explicit_opt_out() -> None:
    """Without one, people delete the check instead of passing a flag."""
    assert contamination_exit_code(4, allow_contaminated=True) == 0


def test_doctor_gateway_check_reads_dotenv_when_the_shell_has_no_frank_vars(
        monkeypatch, tmp_path) -> None:
    """`make doctor` does not load `.env`; the eval entrypoints do.

    Without this fallback the preflight would report "not configured" on
    exactly the machine that is configured, which is worse than no preflight."""
    import httpx
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "FRANK_BASE_URL=https://gw.example.com/v1\n"
        "FRANK_API_KEY=k\n"
        "FRANK_MODEL=some-model\n")
    for k in ("FRANK_BASE_URL", "FRANK_API_KEY", "FRANK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    _stub_get(monkeypatch, httpx.ConnectError("All connection attempts failed"))
    c = check_llm_gateway()
    assert c.ok is False, "the .env-configured gateway was not preflighted"


def test_doctor_gateway_check_fills_a_partially_exported_env(
        monkeypatch, tmp_path) -> None:
    """A shell exporting only URL+key must still resolve the MODEL from .env.

    Caught live: the fallback returned early once those two were present, so
    the probe reported the endpoint "up" and never checked that it serves the
    model the sweep was about to name -- the exact check that makes the
    preflight worth running."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("FRANK_MODEL=some-model\n")
    monkeypatch.setenv("FRANK_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("FRANK_API_KEY", "k")
    monkeypatch.delenv("FRANK_MODEL", raising=False)
    _stub_get(monkeypatch, _Resp(200, {"data": [{"id": "a-different-model"}]}))
    c = check_llm_gateway()
    assert c.ok is False, "the model name was never resolved, so nothing checked it"
    assert "does NOT serve" in c.detail


@pytest.mark.parametrize("msg", [
    # openai_provider._friendly_error(APIConnectionError) -- what a dead
    # gateway ACTUALLY produces. None of the raw ConnectError words survive.
    "Could not reach the OpenAI endpoint at https://gw.example.com/v1 -- "
    "check network connectivity and the base URL.",
    "The request to OpenAI timed out. Try again, or shorten the prompt.",
    "You've hit OpenAI's rate limit. Wait a moment and try again.",
    "OpenAI returned HTTP 503.",
])
def test_the_providers_friendly_wrapper_is_still_a_transport_failure(msg: str) -> None:
    """The classifier never sees the raw exception.

    Matching only raw httpx text scored a dead gateway as a provider rejection
    -- recall 0.0, exit 0 -- which is precisely what the lost-run work was
    supposed to stop. Found by running calibrate against a closed port."""
    assert _is_transport_failure(msg) is True


@pytest.mark.parametrize("msg", [
    "OpenAI authentication failed -- check the API key.",
    "The OpenAI API key lacks permission for this model.",
    "OpenAI rejected the request: tool schema invalid",
])
def test_the_friendly_wrapper_still_distinguishes_a_real_rejection(msg: str) -> None:
    """A bad key or a rejected request is a RESULT. Retrying buys it twice."""
    assert _is_transport_failure(msg) is False
