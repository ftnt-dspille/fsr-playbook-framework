"""Sample-data sidecar (`# fsrpb:samples`) — extract/emit roundtrip,
coexistence with the layout block, and overlay into Jinja vars."""
from __future__ import annotations

import textwrap


from fsr_playbooks.compiler.samples import (
    append_samples,
    extract_samples_block,
    overlay_into_vars,
)
from fsr_playbooks.compiler.visual_model import to_visual, from_visual


YAML_PLAIN = textwrap.dedent(
    """\
    playbooks:
      - name: Demo
        steps:
          - type: manual_input
            name: Get IP Address
            arguments:
              inputs:
                - name: ip_address
                  kind: ipv4
                - name: reason
                  kind: text
            options:
              - display: Block
                primary: true
                next: Stop
          - type: end
            name: Stop
    """
)


def test_empty_samples_roundtrip_is_byte_identical():
    m, body = extract_samples_block(YAML_PLAIN)
    assert m == {}
    assert body == YAML_PLAIN
    assert append_samples(YAML_PLAIN, {}) == YAML_PLAIN


def test_emit_and_extract_roundtrip():
    samples = {"Demo": {"get_ip_address": {"input": {"ip_address": "1.2.3.4",
                                                       "reason": "test"}}}}
    text = append_samples(YAML_PLAIN, samples)
    assert "# fsrpb:samples" in text
    assert text.rstrip().endswith("# fsrpb:samples-end")
    m, body = extract_samples_block(text)
    assert m == samples
    # Stripping the block recovers the original body exactly.
    assert body == YAML_PLAIN


def test_malformed_block_returns_original_text():
    bad = YAML_PLAIN + "# fsrpb:samples\n# not-json-at-all\n# fsrpb:samples-end\n"
    m, body = extract_samples_block(bad)
    assert m == {}
    assert body == bad


def test_overlay_into_vars_seeds_steps_input():
    vars_ctx = {"input": {"params": {}}, "steps": {}}
    overlay_into_vars({"get_ip_address": {"input": {"ip_address": "1.2.3.4"}}},
                      vars_ctx)
    assert vars_ctx["steps"]["get_ip_address"]["input"]["ip_address"] == "1.2.3.4"


def test_overlay_does_not_clobber_existing_step():
    vars_ctx = {"input": {"params": {}},
                "steps": {"get_ip_address": {"input": {"ip_address": "real"}}}}
    overlay_into_vars({"get_ip_address": {"input": {"ip_address": "sample",
                                                     "reason": "test"}}},
                      vars_ctx)
    # Existing real key wins; missing reason gets filled.
    assert vars_ctx["steps"]["get_ip_address"]["input"]["ip_address"] == "real"
    assert vars_ctx["steps"]["get_ip_address"]["input"]["reason"] == "test"


def test_visual_model_surfaces_samples():
    samples = {"Demo": {"get_ip_address": {"input": {"ip_address": "1.2.3.4"}}}}
    text = append_samples(YAML_PLAIN, samples)
    g = to_visual(text)
    assert g["samples"] == samples


def test_visual_model_roundtrips_samples_via_from_visual():
    samples = {"Demo": {"get_ip_address": {"input": {"ip_address": "1.2.3.4"}}}}
    text = append_samples(YAML_PLAIN, samples)
    g = to_visual(text)
    out = from_visual(g, text)
    # No edits → byte-identical, including the samples block.
    assert out == text


def test_from_visual_rewrites_samples_when_graph_overrides():
    g = to_visual(YAML_PLAIN)
    g["samples"] = {"Demo": {"get_ip_address": {"input": {"ip_address": "9.9.9.9"}}}}
    out = from_visual(g, YAML_PLAIN)
    m, _ = extract_samples_block(out)
    assert m["Demo"]["get_ip_address"]["input"]["ip_address"] == "9.9.9.9"


def test_samples_and_layout_coexist_at_footer():
    g = to_visual(YAML_PLAIN)
    # Force a layout block.
    g["playbooks"][0]["nodes"][0]["position"] = {"x": 10, "y": 20}
    g["samples"] = {"Demo": {"get_ip_address": {"input": {"ip_address": "1.1.1.1"}}}}
    out = from_visual(g, YAML_PLAIN)
    assert "# fsrpb:layout" in out
    assert "# fsrpb:samples" in out
    # Footer order is layout then samples — stable across re-saves.
    assert out.find("# fsrpb:layout") < out.find("# fsrpb:samples")
    # Re-round-trip is stable.
    g2 = to_visual(out)
    assert from_visual(g2, out) == out


def test_samples_block_does_not_break_parsing():
    """The compiler must continue to parse the YAML cleanly — samples
    live in comments and never reach the FSR push payload."""
    samples = {"Demo": {"get_ip_address": {"input": {"ip_address": "1.2.3.4"}}}}
    text = append_samples(YAML_PLAIN, samples)
    g = to_visual(text)
    assert g["errors"] == []
    assert g["playbooks"][0]["nodes"][0]["id"] == "get_ip_address"
