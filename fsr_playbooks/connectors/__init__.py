"""Connector domain knowledge: static validation of a ConnectorsV2 connector.

The agent layer (fsr-agentic-toolkit) and the eval graders use these to tell a
sound connector from a broken one without a FortiSOAR box and without running the
connector's code. Packaging/deploy of a connector lives in pyfsr; the corpus
lookup/audit tooling is a separate dev utility.
"""
from fsr_playbooks.connectors.antipatterns import Finding, scan
from fsr_playbooks.connectors.lint.runner import (
    Dispatch,
    Issue,
    Severity,
    resolve_dispatch,
    validate_connector,
)

__all__ = [
    "scan", "Finding",
    "validate_connector", "Issue", "Severity", "resolve_dispatch", "Dispatch",
]
