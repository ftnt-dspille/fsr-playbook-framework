"""Tests for case_state.py: round-trip, fail-open, FIFO cap, record-key reset."""

from fsr_playbooks.agent.case_state import (
    CaseState,
    Capabilities,
    Grounding,
    Investigation,
    new_case,
)


class TestGrounding:
    """Tests for Grounding dataclass."""

    def test_grounding_to_dict(self):
        """to_dict() serializes all fields."""
        g = Grounding(
            scenario_id="c2_exfil",
            system_prompt="You are a triage agent",
            indicators={"ips": ["1.1.1.1"]},
            computed_at=1234567890.5,
        )
        d = g.to_dict()
        assert d["scenario_id"] == "c2_exfil"
        assert d["system_prompt"] == "You are a triage agent"
        assert d["indicators"] == {"ips": ["1.1.1.1"]}
        assert d["computed_at"] == 1234567890.5

    def test_grounding_from_dict_valid(self):
        """from_dict() reconstructs from valid dict."""
        d = {
            "scenario_id": "device_down",
            "system_prompt": "Prompt text",
            "indicators": {"hosts": ["example.com"]},
            "computed_at": 1234567890.0,
        }
        g = Grounding.from_dict(d)
        assert g.scenario_id == "device_down"
        assert g.system_prompt == "Prompt text"
        assert g.indicators == {"hosts": ["example.com"]}
        assert g.computed_at == 1234567890.0

    def test_grounding_from_dict_missing_keys(self):
        """from_dict() fail-open on missing keys: return fresh Grounding."""
        d = {"scenario_id": "c2_exfil"}
        g = Grounding.from_dict(d)
        # Should succeed and fill in None for missing fields
        assert g.scenario_id == "c2_exfil"
        assert g.system_prompt is None
        assert g.indicators is None
        assert g.computed_at is None

    def test_grounding_from_dict_none(self):
        """from_dict(None) returns fresh Grounding."""
        g = Grounding.from_dict(None)
        assert g.scenario_id is None
        assert g.system_prompt is None
        assert g.indicators is None
        assert g.computed_at is None

    def test_grounding_from_dict_not_dict(self):
        """from_dict() fail-open on non-dict input: return fresh Grounding."""
        g = Grounding.from_dict("not a dict")
        assert g.scenario_id is None
        assert g.system_prompt is None

    def test_grounding_roundtrip(self):
        """to_dict() and from_dict() round-trip successfully."""
        g_orig = Grounding(
            scenario_id="generic",
            system_prompt="Triage this",
            indicators={"users": ["admin"]},
            computed_at=9999999.99,
        )
        d = g_orig.to_dict()
        g_restored = Grounding.from_dict(d)
        assert g_restored.scenario_id == g_orig.scenario_id
        assert g_restored.system_prompt == g_orig.system_prompt
        assert g_restored.indicators == g_orig.indicators
        assert g_restored.computed_at == g_orig.computed_at


class TestInvestigation:
    """Tests for Investigation dataclass."""

    def test_investigation_defaults(self):
        """Investigation() has sensible defaults."""
        inv = Investigation()
        assert inv.invest_attempts == 0
        assert inv.hunt_floor_met is False
        assert inv.called_once_sigs == []
        assert inv.searched == []
        assert inv.enriched == []
        assert inv.verdict is None

    def test_investigation_to_dict(self):
        """to_dict() serializes all fields."""
        inv = Investigation(
            invest_attempts=5,
            hunt_floor_met=True,
            called_once_sigs=["sig1", "sig2"],
            searched=["ip1", "ip2"],
            enriched=["enriched1"],
            verdict="malicious",
        )
        d = inv.to_dict()
        assert d["invest_attempts"] == 5
        assert d["hunt_floor_met"] is True
        assert d["called_once_sigs"] == ["sig1", "sig2"]
        assert d["searched"] == ["ip1", "ip2"]
        assert d["enriched"] == ["enriched1"]
        assert d["verdict"] == "malicious"

    def test_investigation_from_dict_valid(self):
        """from_dict() reconstructs from valid dict."""
        d = {
            "invest_attempts": 10,
            "hunt_floor_met": False,
            "called_once_sigs": ["a", "b", "c"],
            "searched": ["x", "y"],
            "enriched": ["z"],
            "verdict": "benign",
        }
        inv = Investigation.from_dict(d)
        assert inv.invest_attempts == 10
        assert inv.hunt_floor_met is False
        assert inv.called_once_sigs == ["a", "b", "c"]
        assert inv.searched == ["x", "y"]
        assert inv.enriched == ["z"]
        assert inv.verdict == "benign"

    def test_investigation_from_dict_type_coercion(self):
        """from_dict() with compatible types works; incompatible type in one field fails all."""
        # Compatible types that can be coerced
        d = {
            "invest_attempts": "5",  # string -> int works
            "hunt_floor_met": 1,  # int (truthy) -> bool works
            "called_once_sigs": ("sig1", "sig2"),  # tuple -> list works
            "searched": ["x", "y"],  # list -> list works
        }
        inv = Investigation.from_dict(d)
        assert inv.invest_attempts == 5
        assert inv.hunt_floor_met is True
        assert inv.called_once_sigs == ["sig1", "sig2"]
        assert inv.searched == ["x", "y"]

    def test_investigation_from_dict_incompatible_type_fails_open(self):
        """from_dict() fails open when one field has incompatible type (e.g., None for list)."""
        d = {
            "invest_attempts": 5,  # Good
            "hunt_floor_met": False,  # Good
            "called_once_sigs": ("sig1",),  # Good (tuple -> list)
            "searched": None,  # BAD: list(None) raises TypeError
        }
        inv = Investigation.from_dict(d)
        # Should fail open and return fresh Investigation, not the partial one
        assert inv.invest_attempts == 0
        assert inv.called_once_sigs == []

    def test_investigation_from_dict_fail_open(self):
        """from_dict() fail-open on garbage: return fresh Investigation."""
        inv = Investigation.from_dict("garbage")
        assert inv.invest_attempts == 0
        assert inv.hunt_floor_met is False
        assert inv.called_once_sigs == []

    def test_investigation_fifo_cap_called_once_sigs(self):
        """cap_lists() caps called_once_sigs at 200."""
        inv = Investigation()
        inv.called_once_sigs = [f"sig_{i}" for i in range(250)]
        inv.cap_lists()
        assert len(inv.called_once_sigs) == 200
        # Should keep the last 200
        assert inv.called_once_sigs[0] == "sig_50"
        assert inv.called_once_sigs[-1] == "sig_249"

    def test_investigation_fifo_cap_searched(self):
        """cap_lists() caps searched at 200."""
        inv = Investigation()
        inv.searched = [f"ip_{i}" for i in range(300)]
        inv.cap_lists()
        assert len(inv.searched) == 200
        # Should keep the last 200
        assert inv.searched[0] == "ip_100"
        assert inv.searched[-1] == "ip_299"

    def test_investigation_fifo_cap_enriched(self):
        """cap_lists() caps enriched at 200."""
        inv = Investigation()
        inv.enriched = [f"enriched_{i}" for i in range(250)]
        inv.cap_lists()
        assert len(inv.enriched) == 200
        assert inv.enriched[0] == "enriched_50"
        assert inv.enriched[-1] == "enriched_249"

    def test_investigation_fifo_cap_all_three(self):
        """cap_lists() caps all three lists independently."""
        inv = Investigation()
        inv.called_once_sigs = [f"sig_{i}" for i in range(250)]
        inv.searched = [f"ip_{i}" for i in range(300)]
        inv.enriched = [f"e_{i}" for i in range(150)]
        inv.cap_lists()
        assert len(inv.called_once_sigs) == 200
        assert len(inv.searched) == 200
        assert len(inv.enriched) == 150  # Under cap, unchanged

    def test_investigation_fifo_cap_under_limit(self):
        """cap_lists() leaves lists under 200 unchanged."""
        inv = Investigation()
        inv.called_once_sigs = ["a", "b", "c"]
        inv.searched = [f"ip_{i}" for i in range(100)]
        inv.enriched = []
        inv.cap_lists()
        assert inv.called_once_sigs == ["a", "b", "c"]
        assert len(inv.searched) == 100
        assert inv.enriched == []

    def test_investigation_roundtrip(self):
        """to_dict() and from_dict() round-trip successfully."""
        inv_orig = Investigation(
            invest_attempts=3,
            hunt_floor_met=True,
            called_once_sigs=["sig1"],
            searched=["ip1", "ip2"],
            enriched=["enriched1"],
            verdict="contained",
        )
        d = inv_orig.to_dict()
        inv_restored = Investigation.from_dict(d)
        assert inv_restored.invest_attempts == inv_orig.invest_attempts
        assert inv_restored.hunt_floor_met == inv_orig.hunt_floor_met
        assert inv_restored.called_once_sigs == inv_orig.called_once_sigs
        assert inv_restored.searched == inv_orig.searched
        assert inv_restored.enriched == inv_orig.enriched
        assert inv_restored.verdict == inv_orig.verdict


class TestCapabilities:
    """Tests for Capabilities dataclass."""

    def test_capabilities_defaults(self):
        """Capabilities() has sensible defaults."""
        cap = Capabilities()
        assert cap.unavailable == {}
        assert cap.confirmed == []
        assert cap.noted_at is None

    def test_capabilities_to_dict(self):
        """to_dict() serializes all fields."""
        cap = Capabilities(
            unavailable={"whois-rdap": "connector_not_configured"},
            confirmed=["nmap", "ip-reputation"],
            noted_at=1234567890.5,
        )
        d = cap.to_dict()
        assert d["unavailable"] == {"whois-rdap": "connector_not_configured"}
        assert d["confirmed"] == ["nmap", "ip-reputation"]
        assert d["noted_at"] == 1234567890.5

    def test_capabilities_from_dict_valid(self):
        """from_dict() reconstructs from valid dict."""
        d = {
            "unavailable": {"connector_a": "unhealthy"},
            "confirmed": ["connector_b"],
            "noted_at": 9999999.0,
        }
        cap = Capabilities.from_dict(d)
        assert cap.unavailable == {"connector_a": "unhealthy"}
        assert cap.confirmed == ["connector_b"]
        assert cap.noted_at == 9999999.0

    def test_capabilities_from_dict_fail_open(self):
        """from_dict() fail-open on garbage: return fresh Capabilities."""
        cap = Capabilities.from_dict([1, 2, 3])
        assert cap.unavailable == {}
        assert cap.confirmed == []
        assert cap.noted_at is None

    def test_capabilities_roundtrip(self):
        """to_dict() and from_dict() round-trip successfully."""
        cap_orig = Capabilities(
            unavailable={"dead_connector": "connection_timeout"},
            confirmed=["alive_1", "alive_2"],
            noted_at=555555.555,
        )
        d = cap_orig.to_dict()
        cap_restored = Capabilities.from_dict(d)
        assert cap_restored.unavailable == cap_orig.unavailable
        assert cap_restored.confirmed == cap_orig.confirmed
        assert cap_restored.noted_at == cap_orig.noted_at


class TestCaseState:
    """Tests for CaseState dataclass."""

    def test_casestate_defaults(self):
        """CaseState() has sensible defaults."""
        state = CaseState()
        assert state.version == 1
        assert state.record_key is None
        assert state.grounding is None
        assert isinstance(state.investigation, Investigation)
        assert isinstance(state.capabilities, Capabilities)
        assert state.phase == "new"

    def test_casestate_to_dict(self):
        """to_dict() serializes all fields including nested objects."""
        state = CaseState(
            version=1,
            record_key="alerts:uuid123",
            grounding=Grounding(
                scenario_id="c2_exfil",
                system_prompt="Triage",
                indicators={"ips": ["1.1.1.1"]},
                computed_at=1000.0,
            ),
            investigation=Investigation(invest_attempts=3, hunt_floor_met=True),
            capabilities=Capabilities(
                unavailable={"whois": "not_configured"}, noted_at=2000.0
            ),
            phase="investigating",
        )
        d = state.to_dict()
        assert d["version"] == 1
        assert d["record_key"] == "alerts:uuid123"
        assert d["grounding"]["scenario_id"] == "c2_exfil"
        assert d["investigation"]["invest_attempts"] == 3
        assert d["capabilities"]["unavailable"]["whois"] == "not_configured"
        assert d["phase"] == "investigating"

    def test_casestate_to_dict_no_grounding(self):
        """to_dict() handles None grounding."""
        state = CaseState(grounding=None)
        d = state.to_dict()
        assert d["grounding"] is None

    def test_casestate_from_dict_valid(self):
        """from_dict() reconstructs from valid dict."""
        d = {
            "version": 1,
            "record_key": "alerts:uuid456",
            "grounding": {
                "scenario_id": "device_down",
                "system_prompt": "Check device",
                "indicators": {"hosts": ["example.com"]},
                "computed_at": 3000.0,
            },
            "investigation": {
                "invest_attempts": 5,
                "hunt_floor_met": False,
                "called_once_sigs": ["sig1"],
                "searched": ["ip1"],
                "enriched": ["e1"],
                "verdict": "benign",
            },
            "capabilities": {
                "unavailable": {},
                "confirmed": ["nmap"],
                "noted_at": 4000.0,
            },
            "phase": "building",
        }
        state = CaseState.from_dict(d)
        assert state.version == 1
        assert state.record_key == "alerts:uuid456"
        assert state.grounding.scenario_id == "device_down"
        assert state.investigation.invest_attempts == 5
        assert state.capabilities.confirmed == ["nmap"]
        assert state.phase == "building"

    def test_casestate_from_dict_version_mismatch(self):
        """from_dict() fail-open on version mismatch: return fresh CaseState."""
        d = {
            "version": 2,  # Wrong version
            "record_key": "alerts:uuid789",
            "grounding": {"scenario_id": "c2_exfil"},
        }
        state = CaseState.from_dict(d)
        # Should return a fresh state, ignoring the dict contents
        assert state.version == 1
        assert state.record_key is None
        assert state.grounding is None
        assert state.phase == "new"

    def test_casestate_from_dict_garbage(self):
        """from_dict() fail-open on garbage input: return fresh CaseState."""
        state = CaseState.from_dict("not a dict")
        assert state.version == 1
        assert state.record_key is None
        assert state.phase == "new"

    def test_casestate_from_dict_empty_dict(self):
        """from_dict({}) returns fresh CaseState (missing version)."""
        state = CaseState.from_dict({})
        # Empty dict has no version key, so it should fail-open
        assert state.version == 1
        assert state.record_key is None

    def test_casestate_from_dict_missing_version(self):
        """from_dict() fails open when version is missing."""
        d = {
            "record_key": "alerts:uuid",
            "grounding": {"scenario_id": "c2_exfil"},
        }
        state = CaseState.from_dict(d)
        # Missing version key: should fail-open and return fresh
        assert state.record_key is None

    def test_casestate_roundtrip(self):
        """to_dict() and from_dict() round-trip successfully."""
        state_orig = CaseState(
            version=1,
            record_key="alerts:xyz",
            grounding=Grounding(
                scenario_id="generic",
                system_prompt="Go",
                indicators={"hashes": ["abc123"]},
                computed_at=5555.5,
            ),
            investigation=Investigation(
                invest_attempts=2,
                hunt_floor_met=False,
                called_once_sigs=["s1", "s2"],
                searched=["i1"],
                enriched=["e1"],
                verdict="unknown",
            ),
            capabilities=Capabilities(
                unavailable={"bad": "timeout"},
                confirmed=["good"],
                noted_at=6666.6,
            ),
            phase="awaiting_approval",
        )
        d = state_orig.to_dict()
        state_restored = CaseState.from_dict(d)
        assert state_restored.version == state_orig.version
        assert state_restored.record_key == state_orig.record_key
        assert state_restored.grounding.scenario_id == state_orig.grounding.scenario_id
        assert (
            state_restored.investigation.invest_attempts
            == state_orig.investigation.invest_attempts
        )
        assert (
            state_restored.capabilities.unavailable
            == state_orig.capabilities.unavailable
        )
        assert state_restored.phase == state_orig.phase

    def test_casestate_for_record_same_key(self):
        """for_record(same_key) returns self."""
        state = CaseState(record_key="alerts:uuid1")
        state.investigation.invest_attempts = 5  # Mutate it
        result = state.for_record("alerts:uuid1")
        assert result is state  # Same object
        assert result.investigation.invest_attempts == 5  # Mutation preserved

    def test_casestate_for_record_different_key(self):
        """for_record(different_key) returns fresh CaseState."""
        state = CaseState(record_key="alerts:uuid1")
        state.investigation.invest_attempts = 5
        result = state.for_record("alerts:uuid2")
        assert result is not state  # Different object
        assert result.record_key == "alerts:uuid2"
        assert result.investigation.invest_attempts == 0  # Fresh

    def test_casestate_for_record_none_to_key(self):
        """for_record(None) from a keyed state returns fresh."""
        state = CaseState(record_key="alerts:uuid1")
        result = state.for_record(None)
        assert result is not state
        assert result.record_key is None

    def test_casestate_for_record_key_to_none(self):
        """for_record(key) from None state returns fresh."""
        state = CaseState(record_key=None)
        result = state.for_record("alerts:uuid1")
        assert result is not state
        assert result.record_key == "alerts:uuid1"

    def test_casestate_for_record_chain(self):
        """Chaining for_record() calls works as expected."""
        state = CaseState(record_key="a")
        state.investigation.invest_attempts = 1

        state2 = state.for_record("b")
        assert state2.record_key == "b"
        assert state2.investigation.invest_attempts == 0

        state3 = state2.for_record("b")
        assert state3 is state2  # Same key, so same object

        state4 = state3.for_record("c")
        assert state4.record_key == "c"
        assert state4.investigation.invest_attempts == 0


class TestNewCaseHelper:
    """Tests for new_case() helper function."""

    def test_new_case_with_key(self):
        """new_case(key) creates a fresh CaseState with that key."""
        case = new_case("alerts:uuid999")
        assert case.record_key == "alerts:uuid999"
        assert case.version == 1
        assert case.grounding is None
        assert case.investigation.invest_attempts == 0
        assert case.phase == "new"

    def test_new_case_with_none(self):
        """new_case(None) creates a fresh CaseState with None key."""
        case = new_case(None)
        assert case.record_key is None
        assert case.version == 1
        assert case.phase == "new"

    def test_new_case_is_independent(self):
        """Multiple new_case() calls return independent objects."""
        case1 = new_case("a")
        case2 = new_case("a")
        assert case1 is not case2
        # Both have the same key, but are different objects
        case1.investigation.invest_attempts = 5
        assert case2.investigation.invest_attempts == 0


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_nested_from_dict_corruption_investigation(self):
        """from_dict() with corrupt investigation sub-object fails open gracefully."""
        d = {
            "version": 1,
            "record_key": "alerts:xyz",
            "investigation": {
                "invest_attempts": "not_an_int_but_coerced",
                "hunt_floor_met": "yes",  # Will be truthy
                "called_once_sigs": 123,  # Not a list, will fail list()
            },
        }
        state = CaseState.from_dict(d)
        # Should still succeed and have default investigation
        assert isinstance(state.investigation, Investigation)

    def test_nested_from_dict_corruption_capabilities(self):
        """from_dict() with corrupt capabilities sub-object fails open gracefully."""
        d = {
            "version": 1,
            "capabilities": {
                "unavailable": "not a dict",  # Will fail dict()
                "confirmed": 456,  # Not a list
            },
        }
        state = CaseState.from_dict(d)
        assert isinstance(state.capabilities, Capabilities)

    def test_fifo_cap_exact_boundary(self):
        """FIFO cap at exactly 200 items stays as-is."""
        inv = Investigation()
        inv.called_once_sigs = [f"sig_{i}" for i in range(200)]
        inv.cap_lists()
        assert len(inv.called_once_sigs) == 200

    def test_fifo_cap_201_items(self):
        """FIFO cap at 201 items drops to 200."""
        inv = Investigation()
        inv.called_once_sigs = [f"sig_{i}" for i in range(201)]
        inv.cap_lists()
        assert len(inv.called_once_sigs) == 200
        assert inv.called_once_sigs[0] == "sig_1"
        assert inv.called_once_sigs[-1] == "sig_200"

    def test_casestate_multiple_phases(self):
        """CaseState can transition through all valid phases."""
        state = CaseState(record_key="alerts:xyz")
        for phase in ["new", "investigating", "awaiting_approval", "contained", "building", "offered", "pushed"]:
            state.phase = phase
            assert state.phase == phase
            d = state.to_dict()
            restored = CaseState.from_dict(d)
            assert restored.phase == phase


def test_to_dict_applies_fifo_cap():
    # Serialization is the persistence chokepoint: even when no caller invokes
    # cap_lists() explicitly, the stored blob must never exceed the cap.
    inv = Investigation()
    inv.called_once_sigs = [f"sig-{i}" for i in range(250)]
    inv.searched = [f"ip-{i}" for i in range(250)]
    d = inv.to_dict()
    assert len(d["called_once_sigs"]) == 200
    assert len(d["searched"]) == 200
    # FIFO: oldest entries dropped, newest kept.
    assert d["called_once_sigs"][-1] == "sig-249"
    assert d["called_once_sigs"][0] == "sig-50"
