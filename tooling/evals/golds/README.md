# Eval golds

Hand-authored **correct answers** to the behavioral fixtures in
`tooling/evals/tasks/`. They exist to calibrate the graders, not to demo
features: an assertion no correct playbook can satisfy is indistinguishable
from an agent that keeps getting it wrong, and it is the first thing to suspect
when a row never scores (`docs/AGENT_INTELLIGENCE_PLAN.md`, rule 1).

They live here rather than in `examples/` because `examples/` is a smoke set
that must compile against the installed-connector view -- these deliberately
reach for connectors (okta, pagerduty) a stock offline install does not carry.

`test_evals_ir_assertions.py` proves every gold passes its own fixture's
assertions, and names the fixtures that still have no gold at all.
