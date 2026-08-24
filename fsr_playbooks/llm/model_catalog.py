"""Which models this assistant is known to work on -- and which it refuses.

The connector's model field used to end with "Any model on the configured
endpoint that supports function calling will work." That is not true, and we
have the measurements to prove it: on the five pinned routing fixtures at three
repeats each, `gpt-5.4-mini` scores 5/5 while `gpt-4.1-mini` -- the previous
default, still selectable -- scores 3/5, failing to offer a playbook it just
built and stopping one call short of the approval gate. Both models "support
function calling". One of them cannot run this agent.

So the field is a curated list with evidence, not a free-text box:

  TESTED       measured on the gate slice, >=3 repeats, every fixture green.
               The run id is recorded so the claim can be re-read.
  SUPPORTED    expected to work -- same family and reasoning class as a tested
               model -- but not measured here. Allowed, and honest about it.
  DISCOURAGED  measured and it failed, or structurally unsuited (no reasoning:
               the agent runs a multi-step tool loop and plans badly without
               it). Allowed only deliberately, and it says what breaks.
Reachability is tracked SEPARATELY from the tier, because it is a property of
the endpoint, not of the model. GLM-5.2 scores 5/5 and would serve this agent
well; the Fortilab gateway it is screened on simply does not answer from a
FortiSOAR appliance. That is a "point it at a reachable endpoint" warning, not
a reason to refuse the model.

`check()` never raises and never silently passes an unknown id: an id nobody
has measured returns `unknown`, which the caller surfaces as a warning. Silence
is what let a 3/5 model sit as the default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["tested", "supported", "discouraged"]

#: The eval that earns a `tested` row: `make matrix LANE=attribute MODE=gate
#: REPEAT=3` (or LANE=screen for a free model). Anything less is `supported`.
GATE_SLICE = "matrix MODE=gate REPEAT=3"


@dataclass(frozen=True)
class ModelEntry:
    model: str
    provider: str
    tier: Tier
    #: Whether the model does native reasoning. The agent runs a multi-step
    #: tool loop; the non-reasoning minis plan badly in it, which is the whole
    #: reason the default moved off `gpt-4.1-mini`.
    reasoning: bool
    #: What backs the tier. For `tested`, an archived run id.
    evidence: str
    note: str = ""
    #: Where the measurement was taken. Kept because a green score says
    #: nothing about whether a FortiSOAR appliance can dial that host.
    endpoint: str = ""
    #: False when the endpoint above is NOT reachable from an appliance. The
    #: model is still fine -- it needs a different endpoint.
    endpoint_reachable_from_box: bool = True


CATALOG: tuple[ModelEntry, ...] = (
    # -- OpenAI ------------------------------------------------------------
    ModelEntry(
        "gpt-5.4-mini", "openai", "tested", True,
        "attribute lane 20260823T213343Z -- 5/5, 3 repeats, verdict consistent",
        "The default. A reasoning mini: cheap enough for volume, and the only "
        "OpenAI model measured green on every gate fixture.",
    ),
    ModelEntry(
        "o4-mini", "openai", "discouraged", True,
        "attribute lane 20260824T020457Z -- 4/5, 3 repeats, verdict flaky",
        "Measured, as the row above asked for, and it is genuinely better "
        "than gpt-4.1-mini: it fixes #156 outright (3/3 on the neutral run "
        "request, where 4.1-mini never reaches the approval gate). But "
        "select_build_offer is 1/3 -- it passed once and dropped two gates "
        "the other two times. That is the flaky case, not the failing one, "
        "and it is demoted for exactly the reason the screen prints: a flaky "
        "model is not a cheaper consistent one, because the analyst gets one "
        "attempt. Re-measured at the corrected turn budget (the harness had "
        "been capping at 12 while production allows 16) and the result did "
        "not move: 1/3 either way. Two of the three runs spend the whole "
        "budget and end with no final text at all -- it builds a playbook "
        "that verifies ready_to_push, then never offers it. Worth "
        "re-measuring if that fixture's gates move.",
    ),
    ModelEntry(
        "gpt-4.1-mini", "openai", "discouraged", False,
        "attribute lane 20260823T203404Z -- 3/5, 3 repeats, verdict failing",
        "The previous default. Two reproducible failures, box-free: it "
        "delivers a finished build through the wrong card (tracker #155), and "
        "on a run request it lists playbooks and stops without ever reaching "
        "the approval gate (#156). Both are 0/3 -- not flakiness.",
    ),
    # -- Anthropic ---------------------------------------------------------
    ModelEntry(
        "claude-sonnet-5", "anthropic", "tested", True,
        "row 7 live-acceptance: adaptive thinking + task budgets accepted on "
        "the live endpoint",
        "The volume default. Serves reasoning depth, task budgets and context "
        "editing natively rather than by host emulation.",
    ),
    ModelEntry(
        "claude-opus-5", "anthropic", "supported", True,
        "same API surface as the tested Sonnet 5; not measured on the gate "
        "slice",
        "The quality option.",
    ),
    ModelEntry(
        "claude-opus-4-7", "anthropic", "supported", True,
        "documented supported set (row 5); not measured on the gate slice",
        "Supported, not default.",
    ),
    ModelEntry(
        "claude-sonnet-4-6", "anthropic", "supported", True,
        "documented supported set (row 5); not measured on the gate slice",
        "Supported, not default. Takes adaptive thinking; `budget_tokens` is "
        "deprecated on it.",
    ),
    ModelEntry(
        "claude-sonnet-4-5-20250929", "anthropic", "supported", True,
        "documented supported set (row 5); not measured on the gate slice",
        "Pre-4.6: uses `budget_tokens`, not adaptive thinking.",
    ),
    ModelEntry(
        "claude-haiku-4-5-20251001", "anthropic", "discouraged", True,
        "gate slice on the attribute substrate, 20260824T013356Z -- 4/5, "
        "3 repeats, verdict failing",
        "Screened, as the row above asked for. Fast -- 3-12s a fixture, "
        "several times quicker than any OpenAI model here -- and green on "
        "four of five. It fails select_build_offer 0/3, dropping three of "
        "four gates every single time: a consistent defect on the build "
        "hand-off, not variance, which is the same fixture #155 names for "
        "gpt-4.1-mini. Cheap and fast does not survive handing a finished "
        "build to the wrong card. Re-measure if that hand-off changes.",
    ),
    # -- Fortilab gateway: laptop-only -------------------------------------
    ModelEntry(
        "glm-5.2", "frank", "tested", True,
        "screen lane 20260823T163129Z -- 5/5, 3 repeats",
        "Free, green, and the lane everything is screened on. The model is a "
        "fine choice for a box; what is not reachable from an appliance is "
        "the Fortilab gateway it is measured on -- serve it from an endpoint "
        "the box can dial.",
        endpoint="Fortilab AI gateway",
        endpoint_reachable_from_box=False,
    ),
    ModelEntry(
        "qwen3.6", "frank", "supported", False,
        "never measured on the gate slice",
        "The gateway's lower-end model. No reasoning, and unmeasured here -- "
        "screen it before putting an analyst behind it.",
        endpoint="Fortilab AI gateway",
        endpoint_reachable_from_box=False,
    ),
)

_BY_ID = {(e.provider, e.model): e for e in CATALOG}
#: Same id, any provider -- the connector's field is free text, so a model can
#: arrive labelled with the wrong provider.
_BY_MODEL = {e.model: e for e in CATALOG}


@dataclass(frozen=True)
class Verdict:
    """`ok` is "may run", not "is good" -- read `level` for that."""

    ok: bool
    level: Literal["tested", "supported", "discouraged", "unknown"]
    message: str
    entry: ModelEntry | None = None
    #: Set when the model is fine but the endpoint it was measured on is not
    #: reachable from an appliance. A warning to surface, never a refusal.
    endpoint_warning: str = ""


def lookup(model: str, provider: str | None = None) -> ModelEntry | None:
    key = (model or "").strip()
    if not key:
        return None
    if provider:
        hit = _BY_ID.get((provider.strip().lower(), key))
        if hit:
            return hit
    return _BY_MODEL.get(key)


def check(model: str, provider: str | None = None) -> Verdict:
    """Classify a configured model. Never raises."""
    key = (model or "").strip()
    if not key:
        return Verdict(False, "unknown", "no model id configured")
    e = lookup(key, provider)
    if e is None:
        return Verdict(
            True, "unknown",
            f"{key!r} is not in the tested-model list. It may work -- any "
            f"function-calling model will answer -- but nothing here has "
            f"measured whether it can run a multi-step tool loop. Screen it "
            f"with `{GATE_SLICE}` before relying on it.")
    warn = ""
    if not e.endpoint_reachable_from_box:
        warn = (f"measured on the {e.endpoint or 'screening endpoint'}, which "
                f"a FortiSOAR appliance cannot reach -- point this at an "
                f"endpoint the box can dial")
    if e.tier == "discouraged":
        return Verdict(
            False, "discouraged",
            f"{key!r} is known NOT to run this agent reliably: {e.evidence}. "
            f"{e.note}", e, warn)
    if e.tier == "supported":
        return Verdict(
            True, "supported",
            f"{key!r} is expected to work ({e.evidence}) but has not been "
            f"measured on the gate slice.", e, warn)
    return Verdict(True, "tested",
                   f"{key!r} is tested: {e.evidence}.", e, warn)


def allowed_models(provider: str) -> list[str]:
    """Ids worth offering for `provider`, best-evidenced first."""
    order = {"tested": 0, "supported": 1, "discouraged": 2}
    got = [e for e in CATALOG
           if e.provider == (provider or "").strip().lower()
           and e.tier in ("tested", "supported")]
    return [e.model for e in sorted(got, key=lambda e: (order[e.tier], e.model))]
