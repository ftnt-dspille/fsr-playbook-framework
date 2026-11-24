"""Typed connector output models, keyed per connector.

Provenance doctrine (m365-trial-test-plan 8.2): every model cites its source
-- ``source-derived (operations.py), live-capture pending`` until a capture
lands -- and normalizes the connector's REAL wire quirks, not idealized
shapes. Sanitized mock fixtures live beside the models under ``mocks/``.

Current modules: ``microsoft_365_defender`` (the microsoft-365-defender
connector). The microsoft-graph security pair lands as ``graph_common`` +
its own module.
"""
from fsr_playbooks.connectors.typed.microsoft_365_defender import (
    OP_OUTPUT_MODELS,
    OP_PARAM_MODELS,
    AdvancedHuntingParams,
    AdvancedHuntingResponse,
    DefenderConnectorConfig,
    GetIncidentParams,
    GetIncidentResponse,
    Incident,
    IncidentAlert,
    IncidentComment,
    IncidentListResponse,
    ListIncidentsParams,
    UpdateIncidentParams,
    UpdateIncidentResponse,
    UpdateIncidentResult,
)

__all__ = [
    "OP_OUTPUT_MODELS",
    "OP_PARAM_MODELS",
    "AdvancedHuntingParams",
    "AdvancedHuntingResponse",
    "DefenderConnectorConfig",
    "GetIncidentParams",
    "GetIncidentResponse",
    "Incident",
    "IncidentAlert",
    "IncidentComment",
    "IncidentListResponse",
    "ListIncidentsParams",
    "UpdateIncidentParams",
    "UpdateIncidentResponse",
    "UpdateIncidentResult",
]
