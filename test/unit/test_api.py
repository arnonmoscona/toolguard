"""
Unit tests for toolguard.api -- the public decision interface (TOO-45 R6-S2).

These tests pin the re-export identity between :mod:`toolguard.api` (the real
definition) and :mod:`toolguard.tools.decision` (the backward-compatible
alias), mirroring the identity-guard pattern in ``test_architecture.py``'s
``TestReExportIdentity`` -- a class defined in both places would pass every
behaviour test while ``isinstance()``/identity checks silently failed across
the module boundary, which is exactly the failure mode a mechanical
"relocate and forward" refactor can introduce if a future edit accidentally
re-implements rather than re-imports.

The extensive behavioural coverage of :func:`decide` itself (allow/deny
patterns, compound Bash, hard-deny, file-path matching, side-effect-freedom)
already lives in ``test_tools_decision.py`` and is not duplicated here: since
this stage made ``toolguard.tools.decision.decide`` a re-export of
``toolguard.api.decide``, that suite already exercises this module's real
implementation through its existing import path. One smoke-level behavioural
test is kept here so this file is not identity-assertions-only.
"""

import os
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.api import _decide_bash, decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_types import RuntimeVerdict
from toolguard.tools import decision as decision_module


class _IsolatedEnvTestCase(unittest.TestCase):
    """Base: removes CLAUDE_SETTINGS_PATH for isolation."""

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("CLAUDE_SETTINGS_PATH", None)
        self.addCleanup(self._env_patch.stop)


class TestApiReExportIdentity(unittest.TestCase):
    """toolguard.tools.decision.decide must be the SAME object as toolguard.api.decide."""

    def test_tools_decision_decide_is_the_same_object_as_api_decide(self):
        """
        Given toolguard.api.decide (the real definition, TOO-45 R6-S2)
            AND toolguard.tools.decision.decide (its backward-compatible
            re-export)
        When both are looked up
        Then they are the identical function object, not a duplicate
             definition that happens to behave the same today
        """
        self.assertIs(decision_module.decide, decide)

    def test_api_decide_reports_its_own_module_as_the_defining_module(self):
        """
        Given toolguard.api.decide
        When its __module__ attribute is read
        Then it names toolguard.api, not toolguard.tools.decision -- proving
             the function is genuinely DEFINED in the api layer and merely
             forwarded, not the other way around
        """
        self.assertEqual(decide.__module__, "toolguard.api")


def _make_config(layers_content):
    """
    Build a minimal Configuration from a list of (level, source_type, content_dict).

    Args:
        layers_content: List of (level, source_type, content_dict) tuples.

    Returns:
        A Configuration with those layers (specificity increases with index).
    """
    layers = []
    for i, (level, source_type, content) in enumerate(layers_content):
        prov = Provenance(
            level=level,
            source_type=source_type,
            file_format="toml",
            path=Path(f"/fake/{level}/{source_type}"),
            specificity=i,
        )
        layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(layers), start_dir=None)


class TestApiDecideSmoke(_IsolatedEnvTestCase):
    """One behavioural smoke test -- full coverage lives in test_tools_decision.py."""

    def test_allow_pattern_matches_command(self):
        """
        Given a project-level config allowing "ls *"
        When decide() is called directly from toolguard.api for "ls -la"
        Then the returned RuntimeVerdict's decision is "allow"
        """
        config = _make_config(
            [("project", "toolguard_hook", {"permissions": {"allow": ["Bash(ls *)"]}})]
        )
        result = decide(config, "Bash", "ls -la")
        self.assertIsInstance(result, RuntimeVerdict)
        self.assertEqual(result.decision, "allow")


class TestDecideBashToolOverride(unittest.TestCase):
    """_decide_bash's documented tool-name override (see its own docstring)."""

    def test_tool_override_replaces_only_the_tool_field(self):
        """
        Given a caller-supplied tool name that differs from the resolver's
            hardcoded 'Bash'
        When _decide_bash is called
        Then the returned verdict's tool field is the caller's own tool name,
             with every other field unchanged from the resolver's own result
        """
        config = _make_config(
            [("project", "toolguard_hook", {"permissions": {"allow": ["Bash(ls *)"]}})]
        )
        result = _decide_bash(config, "mcp__terminal__run", "ls -la", True)
        self.assertEqual(result.tool, "mcp__terminal__run")
        self.assertEqual(result.decision, "allow")


if __name__ == "__main__":
    unittest.main()
