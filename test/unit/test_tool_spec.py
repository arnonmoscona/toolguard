"""
Unit tests for toolguard.tool_spec: the registry that decides what a governed
tool IS.

The registry's content is pinned here, but a name in a set proves nothing on
its own -- what each entry buys is asserted through the consumers that read
it: :func:`toolguard.api.decide` (kind routing), ``hook._resolve_event``
(governed-tool gate and payload key), ``Configuration.governed_tools`` (the
default set) and ``validate_permissions`` (recognised names).
"""

import dataclasses
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import toolguard.api as api_module
import toolguard.hook as hook_module
from test.unit._real_log_dir_guard import get_leak_events
from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_validation import KNOWN_SUPPORTED_TOOLS, validate_permissions
from toolguard.constants import BUILTIN_TOOLS as CONSTANTS_BUILTIN_TOOLS
from toolguard.constants import FILE_TOOLS
from toolguard.hook import _resolve_event
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

#: The registered MCP terminal tool: described by the registry, governed only
#: when the user's config asks for it.
MCP_TERMINAL = "mcp__jetbrains__execute_terminal_command"

#: A real Claude Code tool that is deliberately NOT in the registry.
UNREGISTERED_TOOL = "NotebookEdit"

#: Absolute, outside any project root, so file matching needs no anchoring.
FILE_TARGET = "/tmp/toolguard-tool-spec-probe/target.txt"
FILE_GLOB = "[glob]/tmp/toolguard-tool-spec-probe/**"

COMMAND_TARGET = "rm -rf /nonexistent-tool-spec-probe"
COMMAND_RULE_BODY = "rm -rf:*"

#: The names the behaviour tests drive, written out rather than read from the
#: derived views: a loop over the table under test cannot notice the table
#: losing an entry.
BUILTIN_NAMES = ("Bash", "Read", "Write", "Edit")
FILE_KIND_NAMES = ("Read", "Write", "Edit")
COMMAND_KIND_NAMES = ("Bash", MCP_TERMINAL)

#: One probe per registered tool: tool -> (tool_input key, target, the deny
#: rule that must decide it).
PROBES = {
    "Bash": ("command", COMMAND_TARGET, COMMAND_RULE_BODY),
    "Read": ("file_path", FILE_TARGET, FILE_GLOB),
    "Write": ("file_path", FILE_TARGET, FILE_GLOB),
    "Edit": ("file_path", FILE_TARGET, FILE_GLOB),
    MCP_TERMINAL: ("command", COMMAND_TARGET, COMMAND_RULE_BODY),
}


def _config(content):
    """A single-layer project Configuration over *content* (a raw config dict)."""
    provenance = Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/project/toolguard_hook.toml"),
        specificity=0,
    )
    layer = ConfigLayer(provenance=provenance, content=MappingProxyType(content))
    return Configuration(layers=(layer,), start_dir=None)


def _deny_config(extra=None):
    """A config denying COMMAND_TARGET for Bash and FILE_TARGET for every file tool."""
    content = {
        "permissions": {
            "allow": [],
            "deny": [f"Bash({COMMAND_RULE_BODY})"]
            + [f"{tool}({FILE_GLOB})" for tool in ("Read", "Write", "Edit")],
        }
    }
    if extra:
        content.update(extra)
    return _config(content)


def _payload_for(tool):
    """The tool_input a hook event for *tool* carries, per PROBES."""
    key, target, _ = PROBES[tool]
    return {key: target}


def _expected_rule_body(tool):
    """The wrapper-free deny rule that must decide *tool*'s probe target."""
    return PROBES[tool][2]


class TestRegistryContent(unittest.TestCase):
    """The registry's entries, field for field, in order."""

    EXPECTED = (
        ("Bash", ToolKind.COMMAND, "command", True),
        ("Read", ToolKind.FILE, "file_path", True),
        ("Write", ToolKind.FILE, "file_path", True),
        ("Edit", ToolKind.FILE, "file_path", True),
        (MCP_TERMINAL, ToolKind.COMMAND, "command", False),
    )

    def test_registry_entries_are_exactly_the_five_described_tools(self):
        """
        Given the real registry
        When each entry is read as (name, kind, payload_key, is_builtin)
        Then the whole tuple equals the five expected entries, in order
        """
        self.assertEqual(
            self.EXPECTED,
            tuple(
                (spec.name, spec.kind, spec.payload_key, spec.is_builtin)
                for spec in _REGISTRY
            ),
        )

    def test_every_registered_entry_carries_a_name_and_a_payload_key(self):
        """Given every registered ToolSpec, then name and payload_key are non-empty strings."""
        for spec in _REGISTRY:
            with self.subTest(tool=spec.name):
                self.assertIsInstance(spec.name, str)
                self.assertNotEqual("", spec.name)
                self.assertIsInstance(spec.payload_key, str)
                self.assertNotEqual("", spec.payload_key)
                self.assertIsInstance(spec.kind, ToolKind)


class TestDerivedViews(unittest.TestCase):
    """Each derived view equals the literal tool-name set it must produce."""

    def test_builtin_tools_is_bash_read_write_edit(self):
        """Given the registry, when derived, then BUILTIN_TOOLS is Bash/Read/Write/Edit."""
        self.assertEqual({"Bash", "Read", "Write", "Edit"}, BUILTIN_TOOLS)

    def test_file_kind_tools_is_read_write_edit(self):
        """Given the registry, when derived, then FILE_KIND_TOOLS is Read/Write/Edit."""
        self.assertEqual({"Read", "Write", "Edit"}, FILE_KIND_TOOLS)

    def test_known_tool_names_is_the_five_registered_names(self):
        """Given the registry, when derived, then KNOWN_TOOL_NAMES is the five names."""
        self.assertEqual(
            {"Bash", "Read", "Write", "Edit", MCP_TERMINAL}, KNOWN_TOOL_NAMES
        )

    def test_default_governed_tools_is_the_builtins_in_registry_order(self):
        """
        Given the real registry
        When DEFAULT_GOVERNED_TOOLS is derived
        Then it is exactly ('Bash', 'Read', 'Write', 'Edit'), in that order
        """
        self.assertEqual(("Bash", "Read", "Write", "Edit"), DEFAULT_GOVERNED_TOOLS)

    def test_command_kind_tools_are_bash_and_the_mcp_terminal(self):
        """
        Given the registry
        When the file-kind names are removed from the known names
        Then what remains is exactly Bash and the JetBrains MCP terminal --
            the tools routed through Bash matching
        """
        self.assertEqual({"Bash", MCP_TERMINAL}, KNOWN_TOOL_NAMES - FILE_KIND_TOOLS)


class TestDerivedViewsAreTheSameObjectsEverywhere(unittest.TestCase):
    """Every module-level mirror of a derived view is that view, not a copy.

    ``assertIs`` is the right instrument here: frozensets and tuples are never
    interned, so a module re-declaring the same literal set fails it.
    """

    def test_constants_module_re_exports_the_registry_frozensets(self):
        """Given constants.BUILTIN_TOOLS/FILE_TOOLS, then each IS the tool_spec frozenset."""
        self.assertIs(BUILTIN_TOOLS, CONSTANTS_BUILTIN_TOOLS)
        self.assertIs(FILE_KIND_TOOLS, FILE_TOOLS)

    def test_config_validation_known_supported_tools_is_known_tool_names(self):
        """Given config_validation.KNOWN_SUPPORTED_TOOLS, then it IS KNOWN_TOOL_NAMES."""
        self.assertIs(KNOWN_TOOL_NAMES, KNOWN_SUPPORTED_TOOLS)

    def test_the_two_routing_names_are_one_object(self):
        """
        Given hook.FILE_PATH_TOOLS and api's FILE_TOOLS -- two names for the
            one routing decision the hook/api seam exists to keep in agreement
        When compared to FILE_KIND_TOOLS
        Then all three are the same object
        """
        self.assertIs(FILE_KIND_TOOLS, hook_module.FILE_PATH_TOOLS)
        self.assertIs(FILE_KIND_TOOLS, api_module.FILE_TOOLS)


class TestKindDrivesRouting(unittest.TestCase):
    """decide() routes on the registered kind: file tools to file-path
    matching, everything else to Bash matching."""

    def test_each_file_kind_tool_is_matched_against_file_path_rules(self):
        """
        Given a config whose only rules are file-path denies
        When decide() is called for each file-kind tool with the denied path
        Then each is denied by that tool's own rule, named on the verdict
        """
        config = _deny_config()
        for tool in FILE_KIND_NAMES:
            with self.subTest(tool=tool):
                verdict = decide(config, tool, FILE_TARGET)
                self.assertEqual("deny", verdict.decision)
                self.assertEqual(FILE_GLOB, verdict.matched_rule)
                self.assertEqual(tool, verdict.tool)

    def test_a_file_path_reaching_bash_matching_is_not_denied_by_the_file_rules(self):
        """
        Given the same config
        When the denied PATH is evaluated as a Bash command instead
        Then the verdict is 'ask' with no matched rule -- so the file-kind
            results above are evidence of file-path routing, not of any
            rule matching the string on either route
        """
        verdict = decide(_deny_config(), "Bash", FILE_TARGET)
        self.assertEqual("ask", verdict.decision)
        self.assertIsNone(verdict.matched_rule)

    def test_each_command_kind_tool_is_matched_against_bash_rules(self):
        """
        Given a config whose only command rule is a Bash deny
        When decide() is called for Bash and for the MCP terminal tool
        Then both are denied by the Bash rule, and each verdict echoes its
            own tool name
        """
        config = _deny_config()
        for tool in COMMAND_KIND_NAMES:
            with self.subTest(tool=tool):
                verdict = decide(config, tool, COMMAND_TARGET)
                self.assertEqual("deny", verdict.decision)
                self.assertEqual(COMMAND_RULE_BODY, verdict.matched_rule)
                self.assertEqual(tool, verdict.tool)

    def test_a_command_reaching_file_path_matching_is_not_denied_by_the_bash_rule(self):
        """
        Given the same config
        When the denied COMMAND is evaluated as a Read file path instead
        Then the verdict is 'ask' with no matched rule -- the control for the
            command-kind results above
        """
        verdict = decide(_deny_config(), "Read", COMMAND_TARGET)
        self.assertEqual("ask", verdict.decision)
        self.assertIsNone(verdict.matched_rule)


class TestRegistryDrivesGovernance(unittest.TestCase):
    """The governed-tool gate in hook._resolve_event, fed by the registry's
    DEFAULT_GOVERNED_TOOLS."""

    def test_every_default_governed_tool_is_actually_governed(self):
        """
        Given a config that configures no governed_tools at all
        When a denied event is resolved for Bash, Read, Write and Edit
        Then each is denied by its own rule -- not waved through as ungoverned
        """
        config = _deny_config()
        for tool in BUILTIN_NAMES:
            with self.subTest(tool=tool):
                verdict = _resolve_event(tool, _payload_for(tool), config, True)
                self.assertEqual("deny", verdict.decision)
                self.assertEqual(_expected_rule_body(tool), verdict.matched_rule)

    def test_an_unregistered_tool_is_not_governed_by_default(self):
        """
        Given the same config and a tool with no registry entry
        When its event carries the very command Bash is denied for
        Then it is allowed, because it is not in the governed set -- the
            contrast that makes the denies above attributable to governance
        """
        verdict = _resolve_event(
            UNREGISTERED_TOOL, {"command": COMMAND_TARGET}, _deny_config(), True
        )
        self.assertEqual("allow", verdict.decision)
        self.assertIsNone(verdict.matched_rule)

    def test_the_registered_mcp_terminal_is_described_but_not_governed_by_default(self):
        """
        Given a config configuring no governed_tools
        When the MCP terminal tool's event is resolved
        Then it is allowed as ungoverned, while Bash's identical command is
            denied -- is_builtin=False is what separates the two
        """
        config = _deny_config()
        mcp = _resolve_event(MCP_TERMINAL, {"command": COMMAND_TARGET}, config, True)
        self.assertEqual("allow", mcp.decision)
        self.assertIsNone(mcp.matched_rule)

        bash = _resolve_event("Bash", {"command": COMMAND_TARGET}, config, True)
        self.assertEqual("deny", bash.decision)

    def test_configuring_the_mcp_terminal_governs_it_under_the_bash_rules(self):
        """
        Given the same config with governed_tools naming the MCP terminal tool
        When its event is resolved
        Then it is denied by the Bash deny rule: recognition comes from the
            registry, governance from the config
        """
        config = _deny_config({"governed_tools": [MCP_TERMINAL]})
        verdict = _resolve_event(
            MCP_TERMINAL, {"command": COMMAND_TARGET}, config, True
        )
        self.assertEqual("deny", verdict.decision)
        self.assertEqual(COMMAND_RULE_BODY, verdict.matched_rule)
        self.assertEqual(MCP_TERMINAL, verdict.tool)


class TestPayloadKeyIsWhatConsumersRead(unittest.TestCase):
    """payload_key() names the tool_input key the hook actually reads."""

    def test_unknown_tool_raises_key_error(self):
        """Given an unregistered tool name, then payload_key raises KeyError."""
        with self.assertRaises(KeyError):
            payload_key(UNREGISTERED_TOOL)

    def test_the_hook_reads_a_file_tools_target_from_the_registered_key(self):
        """
        Given the registry rebound so every file tool's payload key is
            'target_path'
        When an allowed event is resolved for each file tool with its target
            under that key
        Then each is allowed by the file rule -- so the key came from the
            registry and not from a hardcoded 'file_path'
        """
        rebound = {
            name: dataclasses.replace(TOOLS_BY_NAME[name], payload_key="target_path")
            for name in FILE_KIND_NAMES
        }
        config = _config(
            {
                "permissions": {
                    "allow": [
                        f"{tool}({FILE_GLOB})" for tool in ("Read", "Write", "Edit")
                    ],
                    "deny": [],
                }
            }
        )
        with patch.dict("toolguard.tool_spec.TOOLS_BY_NAME", rebound):
            for tool in FILE_KIND_NAMES:
                with self.subTest(tool=tool):
                    self.assertEqual("target_path", payload_key(tool))
                    verdict = _resolve_event(
                        tool, {"target_path": FILE_TARGET}, config, True
                    )
                    self.assertEqual("allow", verdict.decision)
                    self.assertEqual(FILE_GLOB, verdict.matched_rule)

    def test_the_unpatched_registry_reads_a_file_tools_target_from_file_path(self):
        """
        Given the real registry
        When a Read event carries its path under 'target_path' instead
        Then it is refused for a missing file_path -- the falsification that
            makes the patched test above evidence of anything
        """
        config = _config({"permissions": {"allow": [f"Read({FILE_GLOB})"], "deny": []}})
        self.assertEqual("file_path", payload_key("Read"))
        verdict = _resolve_event("Read", {"target_path": FILE_TARGET}, config, True)
        self.assertEqual("deny", verdict.decision)

    def test_the_hook_reads_a_command_tools_target_from_the_registered_key(self):
        """
        Given the registry rebound so Bash's payload key is 'shell_input'
        When an allowed event carries its command under that key
        Then it is allowed -- the registry is the single description of where
            a tool's subject lives, for command tools as much as file tools
        """
        rebound = {
            "Bash": dataclasses.replace(
                TOOLS_BY_NAME["Bash"], payload_key="shell_input"
            )
        }
        config = _config({"permissions": {"allow": ["Bash(ls:*)"], "deny": []}})
        with patch.dict("toolguard.tool_spec.TOOLS_BY_NAME", rebound):
            self.assertEqual("shell_input", payload_key("Bash"))
            verdict = _resolve_event("Bash", {"shell_input": "ls -la"}, config, True)
        self.assertEqual("allow", verdict.decision)
        self.assertEqual("ls:*", verdict.matched_rule)


class TestKnownNamesDriveValidation(unittest.TestCase):
    """KNOWN_TOOL_NAMES is what validate_permissions accepts without a warning."""

    def test_a_permission_for_every_registered_tool_validates_clean(self):
        """
        Given a config governing one probed tool and one permission for it
        When the permissions are validated
        Then no issue is reported, for each of the five names in PROBES
        """
        for tool in sorted(PROBES):
            with self.subTest(tool=tool):
                issues = validate_permissions(
                    {
                        "governed_tools": [tool],
                        "permissions": {"allow": [f"{tool}(probe)"], "deny": []},
                    }
                )
                self.assertEqual((), issues)

    def test_a_permission_for_an_unregistered_tool_is_reported(self):
        """
        Given a permission naming a tool with no registry entry
        When the permissions are validated
        Then exactly one issue reports it as not a known supported tool
        """
        issues = validate_permissions(
            {
                "governed_tools": [UNREGISTERED_TOOL],
                "permissions": {"allow": [f"{UNREGISTERED_TOOL}(probe)"], "deny": []},
            }
        )
        self.assertEqual(1, len(issues))
        self.assertEqual(
            f'Tool "{UNREGISTERED_TOOL}" is not a known supported tool',
            issues[0].message,
        )


class TestPopulationAndTheEmptyRegistry(unittest.TestCase):
    """An empty registry is not a configuration with nothing to govern -- it
    is a broken installation, and the hook fails closed rather than
    governing nothing. Both halves are asserted."""

    def test_every_derived_view_is_populated(self):
        """
        Given the real registry
        When each derived view's size is read
        Then the registry has five entries and no view is empty
        """
        self.assertEqual(5, len(_REGISTRY))
        self.assertEqual(5, len(TOOLS_BY_NAME))
        self.assertEqual(5, len(KNOWN_TOOL_NAMES))
        self.assertEqual(4, len(BUILTIN_TOOLS))
        self.assertEqual(4, len(DEFAULT_GOVERNED_TOOLS))
        self.assertEqual(3, len(FILE_KIND_TOOLS))

    def test_this_module_probes_every_registered_tool(self):
        """
        Given PROBES, the hand-written fixture the behaviour tests drive
        When its keys are compared to the registered names
        Then they are the same set: a tool added to the registry without a
            probe here would otherwise be governed by nothing this file checks
        """
        self.assertEqual(KNOWN_TOOL_NAMES, frozenset(PROBES))

    def test_an_unconfigured_config_governs_exactly_the_registry_default(self):
        """
        Given a config that configures no governed_tools
        When governed_tools() is resolved
        Then it IS the DEFAULT_GOVERNED_TOOLS object -- the default is used,
            not merely declared
        """
        self.assertIs(DEFAULT_GOVERNED_TOOLS, _deny_config().governed_tools())

    def test_an_explicitly_empty_governed_tools_list_falls_back_to_the_default(self):
        """
        Given a config setting governed_tools = []
        When governed_tools() is resolved
        Then the registry default is used, and Bash is still governed --
            an empty list reads as 'unset', not as 'govern nothing'
        """
        config = _deny_config({"governed_tools": []})
        self.assertIs(DEFAULT_GOVERNED_TOOLS, config.governed_tools())
        verdict = _resolve_event("Bash", {"command": COMMAND_TARGET}, config, True)
        self.assertEqual("deny", verdict.decision)

    def test_an_empty_default_governed_tools_fails_closed_not_open(self):
        """
        Given DEFAULT_GOVERNED_TOOLS rebound to empty at config.py's holder
        When a hard-denied command is resolved for Bash
        Then it is denied both before and after the rebind, but by different
            mechanisms -- before, hard_deny matches the command directly;
            after, the empty registry itself is treated as a corrupted
            configuration and refused before any rule is consulted, so
            hard_deny never runs, and no rule is left standing in for it
        """
        config = _deny_config(
            {"hard_deny": {"deny": [f"Bash({COMMAND_RULE_BODY})"], "allow": []}}
        )
        before = _resolve_event("Bash", _payload_for("Bash"), config, True)
        self.assertEqual("deny", before.decision)
        self.assertEqual(COMMAND_RULE_BODY, before.matched_rule)

        with patch("toolguard.config.DEFAULT_GOVERNED_TOOLS", ()):
            self.assertEqual((), config.governed_tools())
            verdict = _resolve_event("Bash", _payload_for("Bash"), config, True)
        self.assertEqual("deny", verdict.decision)
        self.assertIsNone(verdict.matched_rule)
        self.assertIn("no built-in tools are registered", verdict.reason)


class TestRegistryIntegrity(unittest.TestCase):
    """_index_by_name: every entry kept, keyed by its own name, duplicates loud."""

    DISTINCT = (
        ToolSpec(
            name="Widget", kind=ToolKind.COMMAND, payload_key="argv", is_builtin=True
        ),
        ToolSpec(
            name="Gadget", kind=ToolKind.FILE, payload_key="doc_path", is_builtin=False
        ),
        ToolSpec(
            name="Sprocket", kind=ToolKind.FILE, payload_key="target", is_builtin=True
        ),
    )

    def test_index_keeps_every_entry_keyed_by_its_own_name(self):
        """
        Given three specs differing in every field
        When indexed
        Then the mapping is exactly name -> that same spec object
        """
        indexed = _index_by_name(self.DISTINCT)
        self.assertEqual({spec.name: spec for spec in self.DISTINCT}, indexed)
        for name, spec in indexed.items():
            with self.subTest(tool=name):
                self.assertEqual(name, spec.name)

    def test_the_real_registry_is_indexed_by_name_without_loss(self):
        """
        Given the real registry
        When TOOLS_BY_NAME is read
        Then every entry appears under its own name, as the same object
        """
        self.assertEqual({spec.name for spec in _REGISTRY}, set(TOOLS_BY_NAME))
        for spec in _REGISTRY:
            with self.subTest(tool=spec.name):
                self.assertIs(spec, TOOLS_BY_NAME[spec.name])

    def test_duplicate_name_raises_at_index_time(self):
        """
        Given a registry with two entries sharing a name
        When indexed via _index_by_name
        Then it raises ValueError instead of silently keeping only the last one
        """
        duplicated = self.DISTINCT + (
            ToolSpec(
                name="Widget",
                kind=ToolKind.FILE,
                payload_key="other_path",
                is_builtin=False,
            ),
        )
        with self.assertRaises(ValueError):
            _index_by_name(duplicated)


class TestToolSpecShape(unittest.TestCase):
    """The ToolSpec type itself."""

    def test_tool_spec_is_frozen(self):
        """Given a ToolSpec instance, when mutated, then it raises FrozenInstanceError."""
        spec = ToolSpec(
            name="Widget", kind=ToolKind.COMMAND, payload_key="argv", is_builtin=True
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.name = "Gadget"  # type: ignore[misc]

    def test_tool_kind_has_exactly_two_members(self):
        """Given ToolKind, then its members are COMMAND='command' and FILE='file'."""
        self.assertEqual(
            {"COMMAND": "command", "FILE": "file"},
            {member.name: member.value for member in ToolKind},
        )


class TestNoAmbientStateIsTouched(unittest.TestCase):
    """Everything above is decided from the passed-in Configuration: no file in
    the user's or the repository's toolguard directories may change."""

    @staticmethod
    def _snapshot():
        """Top-level entries of ~/.claude and the repo logs/, and all of ~/.toolguard."""
        home = Path.home()
        repo_logs = Path(__file__).resolve().parents[2] / "logs"
        shallow = [home / ".claude", repo_logs]
        deep = [home / ".toolguard"]
        seen = {}
        for directory in shallow:
            seen[str(directory)] = (
                sorted(str(p) for p in directory.iterdir())
                if directory.is_dir()
                else []
            )
        for directory in deep:
            seen[str(directory)] = (
                sorted(str(p) for p in directory.rglob("*"))
                if directory.is_dir()
                else []
            )
        return seen

    def test_resolving_events_writes_nothing_and_logs_nothing(self):
        """
        Given snapshots of ~/.claude, ~/.toolguard and the repository's logs/
            taken inside the test process
        When every probe this module uses is resolved through decide() and
            hook._resolve_event
        Then the snapshots are unchanged and the suite's real-log-dir guard
            records no suppressed write
        """
        before = self._snapshot()
        leaks_before = len(get_leak_events())
        config = _deny_config(
            {"hard_deny": {"deny": [f"Bash({COMMAND_RULE_BODY})"], "allow": []}}
        )

        for tool, (_, target, _rule) in sorted(PROBES.items()):
            decide(config, tool, target)
            _resolve_event(tool, _payload_for(tool), config, True)
        _resolve_event(UNREGISTERED_TOOL, {"command": COMMAND_TARGET}, config, True)

        self.assertEqual(before, self._snapshot())
        self.assertEqual(leaks_before, len(get_leak_events()))


if __name__ == "__main__":
    unittest.main()
