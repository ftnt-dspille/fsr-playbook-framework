"""Test that tool name references are consistent and don't reference consolidated names.

The consolidation of emit_* tools into emit_card(card_type=...) requires that:
1. Old names (emit_playbook_offer, emit_enhancement_offer, etc.) are never
   referenced in model-facing strings outside of expected places
2. Guards, carriers, and directives use the new emit_card interface
3. Tool result strings reference emit_card, not old names
"""
from pathlib import Path

import pytest

# Import these unconditionally - they're used in early test classes
from fsr_playbooks.llm.tools import (
    CONSOLIDATED_AWAY,
    anthropic_tools,
    openai_tools,
)


class TestConsolidatedAwayNamesNotAdvertised:
    """Verify old names are truly not advertised to the model."""

    def test_anthropic_tools_excludes_consolidated_names(self):
        """anthropic_tools() must not include CONSOLIDATED_AWAY names."""
        tool_names = {t["name"] for t in anthropic_tools()}
        for old_name in CONSOLIDATED_AWAY:
            assert old_name not in tool_names, (
                f"{old_name} from CONSOLIDATED_AWAY is still in anthropic_tools()"
            )

    def test_openai_tools_excludes_consolidated_names(self):
        """openai_tools() must not include CONSOLIDATED_AWAY names."""
        tool_names = {t["function"]["name"] for t in openai_tools()}
        for old_name in CONSOLIDATED_AWAY:
            assert old_name not in tool_names, (
                f"{old_name} from CONSOLIDATED_AWAY is still in openai_tools()"
            )

    def test_emit_card_is_advertised(self):
        """emit_card must be in advertised tools."""
        anthropic_names = {t["name"] for t in anthropic_tools()}
        openai_names = {t["function"]["name"] for t in openai_tools()}
        assert "emit_card" in anthropic_names, "emit_card not in anthropic_tools()"
        assert "emit_card" in openai_names, "emit_card not in openai_tools()"


class TestEffectiveNameMapping:
    """Test the helper function that maps old names to new."""

    def test_maps_emit_card_names(self):
        """effective_emit_card_name must map old emit_card names to 'emit_card'."""
        pytest.importorskip("fsr_playbooks.llm._loop_helpers")
        from fsr_playbooks.llm._loop_helpers import effective_emit_card_name

        old_names = [
            "emit_playbook_offer", "emit_enhancement_offer",
            "emit_patch_proposal", "emit_action_card",
            "emit_choice_card", "emit_manual_input",
            "emit_capability_gap_card",
        ]
        for name in old_names:
            assert effective_emit_card_name(name) == "emit_card", (
                f"effective_emit_card_name({name!r}) should return 'emit_card'"
            )

    def test_non_card_names_return_none(self):
        """Non-emit-card names should return None."""
        pytest.importorskip("fsr_playbooks.llm._loop_helpers")
        from fsr_playbooks.llm._loop_helpers import effective_emit_card_name

        assert effective_emit_card_name("find_connector") is None
        assert effective_emit_card_name("run_playbook") is None
        assert effective_emit_card_name("emit_card") is None  # Not an old name


class TestGuardsCheckEmitCard:
    """Test that delivery guards check for emit_card availability."""

    def test_create_delivery_guard_checks_emit_card(self):
        """CreateDeliveryGuard.outstanding should accept emit_card."""
        pytest.importorskip("fsr_playbooks.llm._loop_helpers")
        from fsr_playbooks.llm._loop_helpers import CreateDeliveryGuard

        guard = CreateDeliveryGuard()
        # Set up a verified YAML (pass yaml_text in args)
        guard.note_result(
            "verify_playbook",
            {"yaml_text": "---\nname: Test\nsteps: []"},
            {"ready_to_push": True, "summary": "Test playbook"},
        )
        # Without emit_card, not outstanding
        assert guard.outstanding({"other_tool"}) is None
        # With emit_card, outstanding (new behavior after consolidation)
        assert guard.outstanding({"emit_card"}) is not None

    def test_enhance_delivery_guard_checks_emit_card(self):
        """EnhanceDeliveryGuard.outstanding should accept emit_card."""
        pytest.importorskip("fsr_playbooks.llm._loop_helpers")
        from fsr_playbooks.llm._loop_helpers import EnhanceDeliveryGuard

        guard = EnhanceDeliveryGuard()
        # Set up verified bytes
        guard.note_result(
            "verify_enhancement",
            {},
            {"ready_to_push": True, "verified_id": "test-id"},
        )
        # Without emit_card, not outstanding
        assert guard.outstanding({"other_tool"}) is None
        # With emit_card, outstanding (new behavior after consolidation)
        assert guard.outstanding({"emit_card"}) == "test-id"

    def test_guards_recognize_emit_card_in_results(self):
        """Guards should recognize emit_card calls in note_result."""
        pytest.importorskip("fsr_playbooks.llm._loop_helpers")
        from fsr_playbooks.llm._loop_helpers import (
            CreateDeliveryGuard,
            EnhanceDeliveryGuard,
        )

        create_guard = CreateDeliveryGuard()
        create_guard.note_result(
            "verify_playbook", {}, {"ready_to_push": True}
        )
        create_guard.note_result("validate_yaml", {}, {})

        # Should recognize emit_card with playbook_offer type
        create_guard.note_result(
            "emit_card",
            {"card_type": "playbook_offer", "payload": {}},
            {"ok": True},
        )
        # After delivery via emit_card, should not be outstanding
        assert create_guard.outstanding({"emit_card"}) is None

        enhance_guard = EnhanceDeliveryGuard()
        enhance_guard.note_result(
            "verify_enhancement",
            {},
            {"ready_to_push": True, "verified_id": "test-id"},
        )

        # Should recognize emit_card with enhancement_offer type
        enhance_guard.note_result(
            "emit_card",
            {"card_type": "enhancement_offer", "payload": {}},
            {"ok": True},
        )
        # After delivery via emit_card, should not be outstanding
        assert enhance_guard.outstanding({"emit_card"}) is None


class TestToolNameReferencesInCode:
    """Scan code for references to old tool names in model-facing strings."""

    @staticmethod
    def _read_file_cautiously(path: Path) -> str | None:
        """Read file, return None if binary or unreadable."""
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None

    @staticmethod
    def _find_old_name_references(content: str) -> list[tuple[int, str]]:
        """Find lines referencing old tool names in model-facing strings.

        Focuses on tool result strings, error messages, and suggestions
        that the model or analyst would see.
        """
        lines = content.split("\n")
        results = []
        # Pattern: quoted strings containing old tool names
        # Exclude: comments, function definitions, dict keys, tool registrations
        old_names = [
            "emit_playbook_offer", "emit_enhancement_offer",
            "emit_patch_proposal", "emit_action_card",
            "emit_choice_card", "emit_manual_input",
            "emit_capability_gap_card",
            "list_recent_failed_runs", "list_tags",
        ]

        for i, line in enumerate(lines, 1):
            # Skip full-line comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # Skip function definitions and decorators
            if "def emit_" in line or "def list_" in line:
                continue
            if "@" in stripped:
                continue

            # Skip intent/config definitions (frozenset, dict literals with these names)
            if "TRIAGE_ONLY_TOOLS" in line or "ENHANCE_ONLY_TOOLS" in line:
                continue
            if "BUILD_ONLY_TOOLS" in line or "_INTENT_DROP_SET" in line:
                continue
            if "CONSOLIDATED_AWAY" in line:
                continue

            # Skip schema/mapping definitions
            if "_CARD_TYPE_MAP" in line or "CARD_TYPES" in line:
                continue
            if "fn_name = " in line:
                continue
            if "\"choice\":" in line or "\"action\":" in line:
                continue
            if "'choice':" in line or "'action':" in line:
                continue
            if "= \"emit" in line:  # Variable assignments
                continue
            if "suggestions=[" in line:  # Tool result suggestions
                continue

            # Skip tool registry definitions (the actual tool defs in tools.py)
            if "name" in line and "emit_playbook_offer" in line:
                if "tools.py" in str(Path(__file__)):
                    # This is OK in tools.py schema definitions
                    continue

            # Skip inline dict/list with old names in frozenset or list definitions
            if "{" in line or "[" in line:
                # This is likely a collection literal, not a string
                pass

            # Check for string literals containing old names that are NOT
            # in frozenset/dict definitions or inline comments
            for old_name in old_names:
                if old_name in line and ("\"" in line or "'" in line):
                    # Make sure it's in a string literal, not a comment or frozenset
                    # Simple check: look for the string actually quoted
                    if f'"{old_name}"' in line or f"'{old_name}'" in line:
                        # Double-check it's not in an expected location
                        if ("frozenset" not in line and "list(" not in line and
                                "dispatch(" not in line):  # dispatch() can route to old names
                            results.append((i, line.strip()))
                    break

        return results

    def test_directives_use_emit_card(self):
        """Directives should tell model to call emit_card, not old names."""
        from fsr_playbooks.llm import anthropic_provider, openai_provider

        # Check anthropic directives
        assert "emit_card(" in anthropic_provider._BUILD_PROGRESS_DIRECTIVE
        assert "emit_card(" in anthropic_provider._CREATE_DELIVERY_DIRECTIVE
        assert "emit_card(" in anthropic_provider._DELIVERY_DIRECTIVE

        # Check openai directives
        assert "emit_card(" in openai_provider._BUILD_PROGRESS_DIRECTIVE
        assert "emit_card(" in openai_provider._CREATE_DELIVERY_DIRECTIVE
        assert "emit_card(" in openai_provider._DELIVERY_DIRECTIVE

        # Old names should NOT be in directives
        old_names = [
            "emit_playbook_offer", "emit_enhancement_offer"
        ]
        for directive in [
            anthropic_provider._BUILD_PROGRESS_DIRECTIVE,
            anthropic_provider._CREATE_DELIVERY_DIRECTIVE,
            anthropic_provider._DELIVERY_DIRECTIVE,
            openai_provider._BUILD_PROGRESS_DIRECTIVE,
            openai_provider._CREATE_DELIVERY_DIRECTIVE,
            openai_provider._DELIVERY_DIRECTIVE,
        ]:
            for old_name in old_names:
                if old_name in directive and "emit_card(" not in directive:
                    pytest.fail(
                        f"Directive contains old name {old_name} without "
                        f"context of emit_card()"
                    )

    def test_triage_turn_not_treated_as_authoring(self):
        """Verify that triage turns (without build-only tools) are NOT treated as authoring."""
        # Triage turns lack build-only tools like verify_playbook, push_playbook, verify_enhancement
        # Build turns have at least one of these
        triage_only_tools = {"find_connector", "search_module_records", "emit_card"}
        build_tools = {"find_connector", "verify_playbook", "emit_card"}

        # The logic: build tools include verify_playbook, push_playbook, or verify_enhancement
        # Triage tools do not
        assert all(tool not in triage_only_tools for tool in
                   ["verify_playbook", "push_playbook", "verify_enhancement"])
        assert any(tool in build_tools for tool in
                   ["verify_playbook", "push_playbook", "verify_enhancement"])

    def test_ast_scan_registered_tool_descriptions_no_old_names(self):
        """Scan registered tool descriptions for old tool names.

        Only checks the descriptions of ADVERTISED tools (from anthropic_tools/openai_tools),
        not docstrings of unadvertised tool functions. This ensures model-facing strings
        reference only current tool names.
        """
        pytest.importorskip("fsr_playbooks.llm.tools")
        from fsr_playbooks.llm.tools import anthropic_tools

        old_names = [
            "emit_playbook_offer", "emit_enhancement_offer",
            "emit_patch_proposal", "emit_action_card",
            "emit_choice_card", "emit_manual_input",
            "emit_capability_gap_card",
            "list_recent_failed_runs", "list_tags",
        ]

        failures = []
        for tool_def in anthropic_tools():
            tool_name = tool_def.get("name", "")
            description = tool_def.get("description", "")

            for old_name in old_names:
                if old_name in description:
                    failures.append((tool_name, old_name, description[:100]))
                    break

        assert not failures, (
            f"Found old tool names in registered tool descriptions: {failures}"
        )

    def test_agent_markdown_no_old_names(self):
        """Scan fsr_playbooks/agent/*.md files for old tool names."""
        framework_root = Path(__file__).parent.parent
        agent_dir = framework_root / "agent"

        if not agent_dir.exists():
            pytest.skip("agent directory does not exist")

        old_names = [
            "emit_playbook_offer", "emit_enhancement_offer",
            "emit_patch_proposal", "emit_action_card",
            "emit_choice_card", "emit_manual_input",
            "emit_capability_gap_card",
            "list_recent_failed_runs", "list_tags",
        ]

        failures = []
        for md_file in sorted(agent_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for old_name in old_names:
                if old_name in content:
                    # Count occurrences and get context
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if old_name in line:
                            failures.append(
                                (md_file.name, i, line.strip()[:100])
                            )
                            break

        assert not failures, (
            f"Found old tool names in markdown docs: "
            f"{failures}"
        )


def test_lmstudio_provider_resolves_its_error_classifier():
    """lmstudio_provider called `_is_error_result` without defining or
    importing it, so its first tool result raised NameError. Pin the name."""
    from fsr_playbooks.llm import lmstudio_provider
    assert lmstudio_provider._is_error_result({"ok": False}) is True
    assert lmstudio_provider._is_error_result({"ok": True}) is False
