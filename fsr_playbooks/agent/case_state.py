"""Case-state spine — persisted per-session state for grounding, investigation, and capabilities.

Owned by the framework (dataclass + serialization + mutation helpers); persisted by the connector.
Schema version=1; loader migrates or discards on mismatch (fail-open).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Grounding:
    """Grounding computed ONCE by preflight, then reused across turns."""

    scenario_id: str | None = None
    """e.g. "c2_exfil" / "device_down" / "generic"."""

    system_prompt: str | None = None
    """The full 3-layer prompt triage_preflight returned."""

    indicators: dict[str, Any] | None = None
    """Normalized indicator summary (ips/hosts/hashes/users)."""

    computed_at: float | None = None
    """Timestamp when grounding was computed."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "scenario_id": self.scenario_id,
            "system_prompt": self.system_prompt,
            "indicators": self.indicators,
            "computed_at": self.computed_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Grounding":
        """Deserialize from dict (fail-open: return fresh Grounding on error)."""
        if not isinstance(d, dict):
            return cls()
        try:
            return cls(
                scenario_id=d.get("scenario_id"),
                system_prompt=d.get("system_prompt"),
                indicators=d.get("indicators"),
                computed_at=d.get("computed_at"),
            )
        except (TypeError, ValueError, KeyError):
            return cls()


@dataclass
class Investigation:
    """Investigation progress (guards read/write; session-scoped)."""

    invest_attempts: int = 0
    """Lifetime count — TriageDiscipline hunt-floor reads THIS."""

    hunt_floor_met: bool = False
    """Sticky once true; a later turn never resets it."""

    called_once_sigs: list[str] = field(default_factory=list)
    """Call-once guard signatures (find_*_actions per target_type)."""

    searched: list[str] = field(default_factory=list)
    """Indicators already searched (dedupe hint, not a gate)."""

    enriched: list[str] = field(default_factory=list)
    """Indicators already enriched."""

    verdict: str | None = None
    """Model-stated verdict once triage concludes (free text, short)."""

    _FIFO_CAP = 200
    """Cap on called_once_sigs, searched, enriched to prevent unbounded growth."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict. Applies the FIFO cap first — serialization is
        the persistence chokepoint, so the stored blob can never grow
        unbounded even if no caller invoked ``cap_lists()`` explicitly."""
        self.cap_lists()
        return {
            "invest_attempts": self.invest_attempts,
            "hunt_floor_met": self.hunt_floor_met,
            "called_once_sigs": self.called_once_sigs,
            "searched": self.searched,
            "enriched": self.enriched,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Investigation":
        """Deserialize from dict (fail-open: return fresh Investigation on error)."""
        if not isinstance(d, dict):
            return cls()
        try:
            return cls(
                invest_attempts=int(d.get("invest_attempts", 0)),
                hunt_floor_met=bool(d.get("hunt_floor_met", False)),
                called_once_sigs=list(d.get("called_once_sigs", [])),
                searched=list(d.get("searched", [])),
                enriched=list(d.get("enriched", [])),
                verdict=d.get("verdict"),
            )
        except (TypeError, ValueError, KeyError):
            return cls()

    def _apply_fifo_cap(self, lst: list[str]) -> list[str]:
        """Apply FIFO cap: keep only the last N items."""
        if len(lst) > self._FIFO_CAP:
            return lst[-self._FIFO_CAP :]
        return lst

    def cap_lists(self) -> None:
        """Apply FIFO cap to called_once_sigs, searched, enriched."""
        self.called_once_sigs = self._apply_fifo_cap(self.called_once_sigs)
        self.searched = self._apply_fifo_cap(self.searched)
        self.enriched = self._apply_fifo_cap(self.enriched)


@dataclass
class Capabilities:
    """Capability facts (stop guessing / retrying dead connectors)."""

    unavailable: dict[str, str] = field(default_factory=dict)
    """Connector -> reason ("connector_not_configured", "unhealthy")."""

    confirmed: list[str] = field(default_factory=list)
    """Connectors seen healthy this session."""

    noted_at: float | None = None
    """Timestamp when capabilities were last updated."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "unavailable": self.unavailable,
            "confirmed": self.confirmed,
            "noted_at": self.noted_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Capabilities":
        """Deserialize from dict (fail-open: return fresh Capabilities on error)."""
        if not isinstance(d, dict):
            return cls()
        try:
            return cls(
                unavailable=dict(d.get("unavailable", {})),
                confirmed=list(d.get("confirmed", [])),
                noted_at=d.get("noted_at"),
            )
        except (TypeError, ValueError, KeyError):
            return cls()


@dataclass
class CaseState:
    """Per-session case state: grounding, investigation, capabilities, phase."""

    version: int = 1
    """Schema version; loader migrates or discards on mismatch."""

    record_key: str | None = None
    """'module:uuid' the case is about (None = no record / build-only)."""

    grounding: Grounding | None = None
    """Grounding computed ONCE by preflight, then reused."""

    investigation: Investigation = field(default_factory=Investigation)
    """Investigation progress (guards read/write; session-scoped)."""

    capabilities: Capabilities = field(default_factory=Capabilities)
    """Capability facts (stop guessing / retrying dead connectors)."""

    phase: str = "new"
    """Phase: new | investigating | awaiting_approval | contained | building | offered | pushed."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "version": self.version,
            "record_key": self.record_key,
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "investigation": self.investigation.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "phase": self.phase,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CaseState":
        """Deserialize from dict.

        Fail-open: wrong version, missing keys, wrong types => return fresh CaseState().
        Never raises.
        """
        if not isinstance(d, dict):
            return cls()

        try:
            version = d.get("version")
            if version != 1:
                # Version mismatch: discard and return fresh
                return cls()

            record_key = d.get("record_key")
            grounding_data = d.get("grounding")
            investigation_data = d.get("investigation")
            capabilities_data = d.get("capabilities")
            phase = d.get("phase", "new")

            # Deserialize sub-objects (each is fail-open internally)
            grounding = Grounding.from_dict(grounding_data) if grounding_data else None
            investigation = Investigation.from_dict(investigation_data)
            capabilities = Capabilities.from_dict(capabilities_data)

            return cls(
                version=version,
                record_key=record_key,
                grounding=grounding,
                investigation=investigation,
                capabilities=capabilities,
                phase=phase,
            )
        except (TypeError, ValueError, KeyError, AttributeError):
            # Catch-all for any deserialization error: return fresh
            return cls()

    def for_record(self, record_key: str | None) -> "CaseState":
        """Return self if record_key matches, else a fresh CaseState for the new key.

        A different record_key on the same session resets the case (new record = new case).
        """
        if self.record_key == record_key:
            return self
        return new_case(record_key)


def new_case(record_key: str | None) -> CaseState:
    """Create a fresh CaseState for a given record key."""
    return CaseState(record_key=record_key)
