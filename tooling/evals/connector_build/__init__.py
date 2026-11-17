"""Connector-build eval: can an agent BUILD or FIX a FortiSOAR connector?

Mirrors tooling/evals/corpus_authoring but grades against the connector
toolkit's own STATIC gates (fsr_connector_toolkit.lint + antipatterns) instead
of the playbook compiler, so it never drifts from that tool's definition of a
sound connector and needs no FortiSOAR box.
"""
