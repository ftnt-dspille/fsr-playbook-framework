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

Importable as `tooling.harness` (repo root on sys.path) or `harness`
(tooling/ on sys.path), like the other tooling packages.
"""
