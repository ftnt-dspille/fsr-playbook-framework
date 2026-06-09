"""`_infer_shape` collapses large homogeneous maps.

VirusTotal query_ip echoes ~90 AV engines under last_analysis_results, every
value the same {method,engine_name,category,result} shape. Echoing all 90 keys
bloated the run_op tool result (export sess-ei6esw96) with no added signal. The
shaper now keeps one representative entry + a count sentinel.
"""
from __future__ import annotations

from fsr_core.mcp_server._shared import _infer_shape


def test_large_homogeneous_map_collapses():
    engines = {f"Engine{i}": {"method": "blacklist", "engine_name": "X",
                              "category": "harmless", "result": "clean"}
               for i in range(90)}
    shape = _infer_shape({"last_analysis_results": engines})
    inner = shape["last_analysis_results"]
    assert inner["__repeated__"] == {"keys": 90, "all_same_shape": True}
    # exactly one representative engine entry survives + the sentinel
    assert len([k for k in inner if k != "__repeated__"]) == 1
    sample = next(v for k, v in inner.items() if k != "__repeated__")
    assert sample == {"method": "str", "engine_name": "str",
                      "category": "str", "result": "str"}


def test_small_or_heterogeneous_map_is_untouched():
    # Small map: keep every key.
    small = _infer_shape({"a": 1, "b": "x", "c": True})
    assert small == {"a": "int", "b": "str", "c": "bool"}

    # Large but NOT homogeneous: don't collapse (keys carry distinct shapes).
    mixed = {f"k{i}": ({"x": "str"} if i % 2 else "int") for i in range(20)}
    shaped = _infer_shape(mixed)
    assert "__repeated__" not in shaped
    assert len(shaped) == 20
