"""
Unit tests for toolguard.tool_spec: the derived views pinned against literal
tool-name sets, payload-key resolution, and the registry's own integrity.
"""

import dataclasses
import unittest

from toolguard.config_validation import KNOWN_SUPPORTED_TOOLS
from toolguard.constants import BUILTIN_TOOLS as CONSTANTS_BUILTIN_TOOLS
from toolguard.constants import FILE_TOOLS
from toolguard.tool_spec import (
    _REGISTRY,
    _index_by_name,
    BUILTIN_TOOLS,
    DEFAULT_GOVERNED_TOOLS,
    FILE_KIND_TOOLS,
    KNOWN_TOOL_NAMES,
    ToolKind,
    ToolSpec,
    TOOLS_BY_NAME,
    payload_key,
)


class TestDerivedViewsPinnedToLiteralSets(unittest.TestCase):
    """Each derived view equals the literal tool-name set it is pinned to."""

    def test_builtin_tools_matches_prior_literal_set(self):
        """Given the registry, when derived, then BUILTIN_TOOLS is Bash/Read/Write/Edit."""
        self.assertEqual(BUILTIN_TOOLS, {"Bash", "Read", "Write", "Edit"})

    def test_file_kind_tools_matches_prior_literal_set(self):
        """Given the registry, when derived, then FILE_KIND_TOOLS is Read/Write/Edit."""
        self.assertEqual(FILE_KIND_TOOLS, {"Read", "Write", "Edit"})

    def test_known_tool_names_matches_prior_literal_set(self):
        """Given the registry, when derived, then KNOWN_TOOL_NAMES is the five known names."""
        self.assertEqual(
            KNOWN_TOOL_NAMES,
            {
                "Bash",
                "Read",
                "Write",
                "Edit",
                "mcp__jetbrains__execute_terminal_command",
            },
        )

    def test_constants_module_constants_are_the_same_frozensets(self):
        """
        Given constants.BUILTIN_TOOLS/FILE_TOOLS
        When compared to tool_spec's module-level frozensets
        Then they are the SAME object, not a second, independently-built copy
        """
        self.assertIs(CONSTANTS_BUILTIN_TOOLS, BUILTIN_TOOLS)
        self.assertIs(FILE_TOOLS, FILE_KIND_TOOLS)

    def test_config_validation_known_supported_tools_equals_derived_view(self):
        """``config_validation.KNOWN_SUPPORTED_TOOLS`` equals its derivation."""
        self.assertEqual(KNOWN_SUPPORTED_TOOLS, KNOWN_TOOL_NAMES)


class TestDefaultGovernedTools(unittest.TestCase):
    """DEFAULT_GOVERNED_TOOLS -- Configuration.governed_tools()'s fallback value."""

    def test_default_governed_tools_is_bash_read_write_edit_in_registry_order(self):
        """
        Given the real registry
        When DEFAULT_GOVERNED_TOOLS is derived
        Then it is exactly ('Bash', 'Read', 'Write', 'Edit'), in that order
        """
        self.assertEqual(DEFAULT_GOVERNED_TOOLS, ("Bash", "Read", "Write", "Edit"))

    def test_default_governed_tools_matches_builtin_tools_content(self):
        """Given BUILTIN_TOOLS, when compared as a set, then DEFAULT_GOVERNED_TOOLS agrees."""
        self.assertEqual(set(DEFAULT_GOVERNED_TOOLS), BUILTIN_TOOLS)


class TestPayloadKeyResolution(unittest.TestCase):
    """The payload key for each registered tool, driven from the registry."""

    def test_file_kind_tools_resolve_to_file_path_key(self):
        """Given each file-kind tool, when looked up, then its key is 'file_path'."""
        for name in ("Read", "Write", "Edit"):
            self.assertEqual(payload_key(name), "file_path")

    def test_bash_resolves_to_command_key(self):
        """Given 'Bash', when looked up, then its key is 'command'."""
        self.assertEqual(payload_key("Bash"), "command")

    def test_jetbrains_terminal_resolves_to_command_key(self):
        """Given the JetBrains MCP terminal tool, then its key is 'command'."""
        self.assertEqual(
            payload_key("mcp__jetbrains__execute_terminal_command"), "command"
        )

    def test_unknown_tool_raises_key_error(self):
        """Given an unregistered tool name, then payload_key raises KeyError."""
        with self.assertRaises(KeyError):
            payload_key("NotebookEdit")


class TestRegistryIntegrity(unittest.TestCase):
    """The registry itself: no duplicate names, every entry carrying a payload key."""

    def test_tools_by_name_has_one_entry_per_registry_entry(self):
        """
        Given the real _REGISTRY
        When indexed into TOOLS_BY_NAME
        Then the count matches exactly
        """
        self.assertEqual(len(TOOLS_BY_NAME), len(_REGISTRY))

    def test_every_registered_payload_key_is_non_empty(self):
        """Given every registered ToolSpec, then its payload_key is a non-empty string."""
        for spec in _REGISTRY:
            self.assertTrue(spec.payload_key)

    def test_duplicate_name_raises_at_index_time(self):
        """
        Given a registry with two entries sharing a name
        When indexed via _index_by_name
        Then it raises ValueError instead of silently keeping only the last one
        """
        duplicated = (
            ToolSpec(
                name="Bash",
                kind=ToolKind.COMMAND,
                payload_key="command",
                is_builtin=True,
            ),
            ToolSpec(
                name="Bash",
                kind=ToolKind.COMMAND,
                payload_key="command",
                is_builtin=False,
            ),
        )
        with self.assertRaises(ValueError):
            _index_by_name(duplicated)


class TestToolSpecShape(unittest.TestCase):
    """Basic shape checks on the ToolSpec type itself."""

    def test_tool_spec_is_frozen(self):
        """Given a ToolSpec instance, when mutated, then it raises FrozenInstanceError."""
        spec = ToolSpec(
            name="Bash",
            kind=ToolKind.COMMAND,
            payload_key="command",
            is_builtin=True,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.name = "Other"  # type: ignore[misc]

    def test_kind_is_an_enum(self):
        """Given ToolKind, then its members are COMMAND and FILE."""
        self.assertEqual({member.value for member in ToolKind}, {"command", "file"})


if __name__ == "__main__":
    unittest.main()
