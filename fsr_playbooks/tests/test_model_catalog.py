"""The model field is a curated list with evidence, not a free-text box.

`gpt-4.1-mini` sat as the shipped default while scoring 3/5 on the pinned
routing slice -- it delivered a finished build through the wrong card and
stopped one call short of the approval gate, 0/3 on both, box-free and
reproducible. It "supports function calling", which is all the old connector
description asked of a model. These tests pin the three properties that stop
that from recurring.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsr_playbooks.llm.model_catalog import (
    CATALOG,
    allowed_models,
    check,
    lookup,
)

#: The connector, when it is checked out beside this repo. Absent in CI.
CONNECTOR_INFO = (Path(__file__).resolve().parents[3]
                  / "ConnectorsV2" / "fsr-playbook-builder"
                  / "connector-fsr-soc-assistant" / "info.json")


def test_a_measured_failure_is_refused_and_says_what_broke() -> None:
    v = check("gpt-4.1-mini")
    assert v.ok is False
    assert v.level == "discouraged"
    # The refusal must carry the evidence -- "not allowed" with no reason is
    # how a good model gets excluded next time by someone guessing.
    assert "3/5" in v.message
    assert "#155" in v.message or "#156" in v.message


def test_an_unknown_model_warns_but_is_never_silently_blessed() -> None:
    """Unknown is the common case and must not be refused -- customers run
    their own endpoints. It must also never come back as `tested`."""
    v = check("some-local-llama")
    assert v.ok is True
    assert v.level == "unknown"
    assert "not in the tested-model list" in v.message


def test_reachability_is_a_property_of_the_endpoint_not_the_model() -> None:
    """GLM-5.2 scores 5/5 and is a fine choice for a box. What an appliance
    cannot reach is the Fortilab gateway it is screened on -- so this is a
    warning about where to point it, not a refusal of the model."""
    v = check("glm-5.2")
    assert v.ok is True
    assert v.level == "tested"
    assert v.endpoint_warning
    assert "reach" in v.endpoint_warning


def test_every_entry_carries_evidence() -> None:
    for e in CATALOG:
        assert e.evidence.strip(), f"{e.model} claims tier {e.tier} with no evidence"
        if e.tier == "tested":
            # A tested claim must be re-readable: an archived run id, or a
            # named live acceptance.
            assert any(tok in e.evidence for tok in ("Z --", "live-acceptance")), (
                f"{e.model} is 'tested' but its evidence names no run: "
                f"{e.evidence!r}")


def test_offered_models_exclude_the_ones_we_measured_failing() -> None:
    for provider in {e.provider for e in CATALOG}:
        for model in allowed_models(provider):
            assert check(model, provider).ok, f"{model} offered but refused"
    assert "gpt-4.1-mini" not in allowed_models("openai")


def _shipped_model_fields() -> dict[str, dict]:
    """The connector's per-provider model fields.

    They are NOT top-level: `llm_provider` is a select whose `onchange` map
    carries a field list per provider, so a naive scan of
    `configuration.fields` finds no model field at all and a test written
    against it passes by finding nothing.
    """
    info = json.loads(CONNECTOR_INFO.read_text())
    out: dict[str, dict] = {}
    for field in info["configuration"]["fields"]:
        for provider, sub in (field.get("onchange") or {}).items():
            for f in sub:
                if "model" in str(f.get("name", "")):
                    out[provider] = f
    return out


@pytest.mark.skipif(not CONNECTOR_INFO.exists(),
                    reason="connector not checked out beside this repo")
def test_the_shipped_default_model_is_a_tested_one() -> None:
    """The gate that would have caught the original defect.

    A default is the model almost every install runs. Shipping one nobody
    measured is how 3/5 became production behaviour.
    """
    fields = _shipped_model_fields()
    assert fields, "no per-provider model field found in the connector info.json"
    for provider, f in fields.items():
        model = f.get("value")
        if not model:
            continue
        v = check(model, provider)
        assert v.level == "tested", (
            f"the shipped {provider} default {model!r} is {v.level}, not "
            f"tested: {v.message}")
        assert lookup(model, provider) is not None


@pytest.mark.skipif(not CONNECTOR_INFO.exists(),
                    reason="connector not checked out beside this repo")
def test_no_offered_dropdown_option_is_a_model_we_measured_failing() -> None:
    """A `select` puts its options one click away -- offering a model we
    measured failing is worse than letting someone type it deliberately."""
    for provider, f in _shipped_model_fields().items():
        for opt in (f.get("options") or []):
            model = opt if isinstance(opt, str) else opt.get("value")
            if not model:
                continue
            v = check(model, provider)
            assert v.ok, f"{provider} offers {model!r} in a dropdown: {v.message}"
            # Stronger than "not refused": a dropdown is a recommendation, so
            # every option must be a model somebody has taken a position on.
            assert v.level != "unknown", (
                f"{provider} offers {model!r} in a dropdown but the catalog "
                f"says nothing about it -- add an entry with evidence, or "
                f"remove the option.")


def test_the_frank_default_is_recognised_by_its_configured_id() -> None:
    """The eval harnesses default to `coding-b200/max` and every run warned
    "not in the tested-model list", because lookup() is exact and no row
    carried that id."""
    v = check("coding-b200/max")
    assert v.level == "tested"
    assert "20260926T184805Z" in v.message


def test_the_offline_tier_models_are_screened():
    """doctor graded the sweep (qwen) and loop-smoke (deepseek) models
    UNSCREENED; both passed the gate slice 5/5 x3 on 2026-09-28."""
    from fsr_playbooks.llm import model_catalog as mc
    for m in ("coding-b200/qwen3.8-27b-nvfp4", "coding-b200/deepseek-v4-flash-0731"):
        v = mc.check(m, "frank")
        assert v.level == "tested", m
        assert v.endpoint_warning, "gateway is not reachable from a box"
