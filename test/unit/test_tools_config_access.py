"""
Unit tests for toolguard.tools.config_access.

Tests for the thin facade over Configuration: per-layer rule listing,
effective takeover exposure, and config summary.

All tests use stdlib unittest with BDD Given/When/Then docstrings.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _write_toml(claude_dir: Path, filename: str, content: str) -> None:
    """Write a TOML config file under claude_dir."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / filename).write_text(content, encoding="utf-8")


class _IsolatedEnvTestCase(unittest.TestCase):
    """Base: removes CLAUDE_SETTINGS_PATH so hierarchy discovery is not diverted."""

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("CLAUDE_SETTINGS_PATH", None)
        self.addCleanup(self._env_patch.stop)


class TestLoadConfig(_IsolatedEnvTestCase):
    """Tests for config_access.load_config()."""

    def test_load_config_returns_configuration(self):
        """
        Given a minimal project with a toolguard_hook.toml
        When load_config is called with the project directory
        Then a Configuration object is returned with at least one layer
        """
        from toolguard.tools.config_access import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            config = load_config(proj)
            self.assertIsNotNone(config)
            self.assertGreater(len(config.layers), 0)

    def test_load_config_ignores_env_override(self):
        """
        Given CLAUDE_SETTINGS_PATH set to an unrelated file
        When load_config is called (which uses ignore_env_override=True)
        Then the project hierarchy is used, not the env override
        """
        from toolguard.tools.config_access import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(git:*)"]',
            )
            # Set env override to a nonexistent path
            with patch.dict(
                os.environ,
                {"CLAUDE_SETTINGS_PATH": "/nonexistent/settings.json"},
            ):
                config = load_config(proj)
            # Should still find the project config (ignoring the bad env path)
            allow, _ = config.allow_deny_for("Bash")
            self.assertIn("git:*", allow)


class TestPerLayerRules(_IsolatedEnvTestCase):
    """Tests for config_access.per_layer_rules()."""

    def test_per_layer_rules_returns_allow_deny_ask(self):
        """
        Given a config with allow, deny and ask rules for Bash
        When per_layer_rules is called with tool_name='Bash'
        Then the returned LayerRules carries the correct allow, deny, and ask patterns
        """
        from toolguard.tools.config_access import per_layer_rules, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                """
[permissions]
allow = ["Bash(git:*)"]
deny = ["Bash(rm -rf:*)"]
ask = ["Bash(sudo:*)"]
""",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            self.assertGreater(len(layers), 0)
            # The project-level layer should have the expected patterns
            project_layer = layers[0]
            self.assertIn("git:*", project_layer.allow)
            self.assertIn("rm -rf:*", project_layer.deny)
            self.assertIn("sudo:*", project_layer.ask)

    def test_per_layer_rules_native_layer_has_no_ask(self):
        """
        Given a native Claude settings.json file with allow rules
        When per_layer_rules is called
        Then the native layer has empty ask list (native settings have no ask concept)
        """
        from toolguard.tools.config_access import per_layer_rules, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            claude.mkdir(parents=True, exist_ok=True)
            (claude / "settings.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}),
                encoding="utf-8",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            native_layers = [
                lr for lr in layers if lr.provenance.source_type == "claude"
            ]
            for lr in native_layers:
                self.assertEqual((), lr.ask)

    def test_per_layer_rules_multiple_levels_most_specific_first(self):
        """
        Given project-level and user-level configs with different allow patterns
        When per_layer_rules is called
        Then the first returned layer corresponds to the project level (most specific)
        """
        from toolguard.tools.config_access import per_layer_rules, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            proj_claude = proj / ".claude"
            _write_toml(
                proj_claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(git:*)"]',
            )
            user_claude = Path(tmpdir) / ".claude"
            _write_toml(
                user_claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            self.assertGreater(len(layers), 1)
            # First layer (most specific = project) should have 'git:*'
            self.assertIn("git:*", layers[0].allow)


class TestEffectiveTakeover(_IsolatedEnvTestCase):
    """Tests for config_access.effective_takeover()."""

    def test_effective_takeover_enabled(self):
        """
        Given a config with takeover_mode.enabled = true
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=True
        """
        from toolguard.tools.config_access import effective_takeover, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                "[takeover_mode]\nenabled = true\n",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                takeover = effective_takeover(config)

            self.assertTrue(takeover.enabled)

    def test_effective_takeover_disabled_by_default(self):
        """
        Given a config with no takeover_mode section
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=False (default off)
        """
        from toolguard.tools.config_access import effective_takeover, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                takeover = effective_takeover(config)

            self.assertFalse(takeover.enabled)


class TestConfigSummary(_IsolatedEnvTestCase):
    """Tests for config_access.config_summary()."""

    def test_config_summary_reports_sources_and_tools(self):
        """
        Given a project config that governs Bash and Read
        When config_summary is called
        Then the summary reports the correct governed tools and non-zero source count
        """
        from toolguard.tools.config_access import config_summary, load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                'governed_tools = ["Bash", "Read"]\n[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                summary = config_summary(config)

            self.assertIn("Bash", summary.governed_tools)
            self.assertIn("Read", summary.governed_tools)
            self.assertGreater(summary.layer_count, 0)
            self.assertGreater(len(summary.sources), 0)
