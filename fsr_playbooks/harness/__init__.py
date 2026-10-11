"""What every harness that drives a SOC-assistant chat turn shares.

There are about twenty such harnesses across the framework, the connector and
the widget repos (local_turn, conv/chat-sweep, analyst-sim, the live scripts,
chat_drive, the effect probes, calibrate, the eval matrix). Each grew its own
copy of the same three things, and the copies disagreed:

- `llm`: which model a run talks to. Seven copies, four different default
  Frank models, and one (`LLM ?= fake`) that silently ran the fake provider.
- `frames`: reading a turn's transcript. About twelve copies of "the
  assistant's text", "the tools it called", "what it is waiting on".
- `classify`: whether a turn answered at all. Six policies -- a dead gateway
  graded as a model failure in one harness and as an answer in another.
- `drive`: the conversation loop (transports, halts answered by policy, resume,
  history). The connector and the framework each had their own transport and
  loop; `drive.Executor` is now the one seam, so any object with
  `.execute(op, params, timeout=)` can drive a turn.

Lives in the shipped package (`fsr_playbooks.harness`) so the connector's CI,
which installs the wheel, can import it. Dependency-free by design: stdlib
only, no tooling/ imports. Connector-only pieces (LocalTransport, mount_entity)
stay in the connector.
"""
