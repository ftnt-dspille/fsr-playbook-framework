"""The action finders' scoped healthcheck must reuse the warm health cache.

`_healthcheck_many` (used by find_containment_actions / find_enrichment_actions)
used to probe live on every call, so two finders in one turn each paid the full
live-probe latency. It now consults `_cached_health` first and stores misses, so
repeat probes are sqlite reads. These tests pin that contract by patching the
cache + live-probe seams the function imports at call time.
"""
from __future__ import annotations

from fsr_core.mcp_server import tools_execution as te
from fsr_core.mcp_server.tools_triage import _healthcheck_many


def test_cache_hit_skips_live_probe(monkeypatch):
    calls = {"live": 0}

    monkeypatch.setattr(te, "_cached_health",
                        lambda c, v, cfg="": {"status": "Available"})

    def _live(*a, **k):
        calls["live"] += 1
        return {"status": "Available"}

    monkeypatch.setattr(te, "_live_healthcheck", _live)
    monkeypatch.setattr(te, "_store_health", lambda *a, **k: None)

    out = _healthcheck_many(object(), [("virustotal", "1.0.0", "")])
    assert out == {"virustotal": "Available"}
    assert calls["live"] == 0  # cache hit → no live probe


def test_cache_miss_probes_once_and_stores(monkeypatch):
    calls = {"live": 0, "store": 0}

    monkeypatch.setattr(te, "_cached_health", lambda c, v, cfg="": None)

    def _live(*a, **k):
        calls["live"] += 1
        return {"status": "Available", "message": ""}

    monkeypatch.setattr(te, "_live_healthcheck", _live)
    monkeypatch.setattr(te, "_store_health",
                        lambda *a, **k: calls.__setitem__("store", calls["store"] + 1))

    out = _healthcheck_many(object(), [("shodan", "2.0.0", "")])
    assert out == {"shodan": "Available"}
    assert calls["live"] == 1
    assert calls["store"] == 1  # miss is cached for the next finder/turn


def test_timing_dict_is_populated(monkeypatch):
    monkeypatch.setattr(te, "_cached_health",
                        lambda c, v, cfg="": {"status": "Available"})
    monkeypatch.setattr(te, "_live_healthcheck", lambda *a, **k: {"status": "Available"})
    monkeypatch.setattr(te, "_store_health", lambda *a, **k: None)

    timing: dict = {}
    out = _healthcheck_many(object(),
                            [("virustotal", "1.0.0", ""), ("shodan", "2.0.0", "")],
                            timing=timing)
    assert set(out) == {"virustotal", "shodan"}
    assert timing["n"] == 2
    assert timing["cached"] == 2 and timing["live"] == 0
    assert timing["timed_out"] == []
    assert isinstance(timing["probe_ms"], (int, float))


def test_deadline_abandons_a_hung_probe(monkeypatch):
    import time as _t
    monkeypatch.setattr(te, "_cached_health", lambda c, v, cfg="": None)
    monkeypatch.setattr(te, "_store_health", lambda *a, **k: None)

    def _slow(client, name, version, **k):
        if name == "hung":
            _t.sleep(5)          # simulates the on-box probe that ignores timeout=8
        return {"status": "Available"}

    monkeypatch.setattr(te, "_live_healthcheck", _slow)

    timing: dict = {}
    t0 = _t.perf_counter()
    out = _healthcheck_many(object(),
                            [("fast", "1.0.0", ""), ("hung", "1.0.0", "")],
                            deadline_s=0.5, timing=timing)
    elapsed = _t.perf_counter() - t0
    assert out.get("fast") == "Available"   # fast probe landed
    assert "hung" not in out                # straggler abandoned → caller fails open
    assert "hung" in timing["timed_out"]
    assert elapsed < 2.0                    # bounded by the deadline, not the 5s sleep
