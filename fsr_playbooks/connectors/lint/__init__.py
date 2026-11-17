"""Rung-1 static validator for FortiSOAR custom connectors.

Pure AST + info.json checks. No FSR runtime, no network, no agent.

Usage:
    from connector_building.validator import validate_connector
    issues = validate_connector(Path("path/to/connector_dir"))

CLI:
    python -m connector_building.validator <connector_dir> [...]
"""
from .runner import Issue, Severity, validate_connector  # noqa: F401
