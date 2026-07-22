# Enhance-mode scenarios

Edits to a playbook the analyst already has OPEN — the request type that
generated the most live failures and had, until recently, no test coverage at
all (`grep -r enhance` matched no test file).

Each scenario mounts `before_yaml` as the `OPEN PLAYBOOK` block and issues
`prompt` as the analyst's message. Grading is `score_enhance_delivery`: did the
edit actually reach the playbook, or did the agent print YAML at the analyst?

The failure these were written from: asked to add a `manual_input` step, the
agent verified one document and then re-typed three different ones into chat.
Nothing was written, every tool call returned ok, and the analyst asked three
times. `expect` names the specific way each scenario can fail that way.

Deterministic gate (no LLM, runs in CI):
    pytest tooling/tests/test_evals_enhance_delivery.py
Live behavioural run (needs a configured model):
    the harness reads these fixtures the same way it reads `tasks/`.
