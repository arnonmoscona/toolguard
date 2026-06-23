"""
Unit tests for config_divergence module.
"""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_divergence import (
    check_and_warn_divergence,
    cleanup_old_markers,
    create_marker_file,
    find_divergent_patterns,
    get_marker_file_path,
    get_native_permissions,
    get_toolguard_permissions,
    marker_exists_for_today,
)


class TestMarkerFiles(unittest.TestCase):
    """Test marker file operations."""

    def test_get_marker_file_path(self):
        """
        Given a logs directory and a specific date
        When get_marker_file_path builds the path
        Then it is logs_dir/.toolguard-divergence-warned-YYYY-MM-DD for that date
        """
        logs_dir = Path("/tmp/logs")
        test_date = date(2025, 2, 5)
        marker_path = get_marker_file_path(logs_dir, test_date)

        self.assertEqual(
            marker_path, Path("/tmp/logs/.toolguard-divergence-warned-2025-02-05")
        )

    def test_marker_exists_for_today(self):
        """
        Given a logs directory with no marker, then today's marker created
        When marker_exists_for_today is checked before and after
        Then it returns False initially and True once the marker exists
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Should not exist initially
            self.assertFalse(marker_exists_for_today(logs_dir))

            # Create marker for today
            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            # Should exist now
            self.assertTrue(marker_exists_for_today(logs_dir))

    def test_create_marker_file(self):
        """
        Given a logs directory that does not yet exist
        When create_marker_file runs
        Then the directory is created and today's divergence marker exists
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "logs"

            # Directory doesn't exist yet
            self.assertFalse(logs_dir.exists())

            # Create marker file
            create_marker_file(logs_dir)

            # Directory and marker should exist
            self.assertTrue(logs_dir.exists())
            self.assertTrue(marker_exists_for_today(logs_dir))

    def test_cleanup_old_markers(self):
        """
        Given markers for today, 3 days ago, and 10 days ago
        When cleanup_old_markers runs with a 7-day threshold
        Then the 10-day-old marker is deleted while the recent and today markers remain
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create markers for various dates
            today = date.today()
            old_date = today - timedelta(days=10)
            recent_date = today - timedelta(days=3)

            old_marker = get_marker_file_path(logs_dir, old_date)
            recent_marker = get_marker_file_path(logs_dir, recent_date)
            today_marker = get_marker_file_path(logs_dir, today)

            old_marker.touch()
            recent_marker.touch()
            today_marker.touch()

            # Cleanup markers older than 7 days
            cleanup_old_markers(logs_dir, days=7)

            # Old marker should be deleted, recent ones should remain
            self.assertFalse(old_marker.exists())
            self.assertTrue(recent_marker.exists())
            self.assertTrue(today_marker.exists())


class TestGetNativePermissions(unittest.TestCase):
    """Test extracting permissions from settings.local.json."""

    def test_extract_bash_patterns(self):
        """
        Given a settings.local.json with Bash and non-governed-tool patterns across allow/deny/ask
        When get_native_permissions reads it
        Then only the governed Bash patterns are returned in each permission list
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            config = {
                "permissions": {
                    "allow": [
                        "Bash(git status:*)",
                        "Bash(ls:*)",
                        "mcp__basic-memory__read_note",  # Not a governed tool
                        "WebSearch",  # Not a governed tool
                    ],
                    "deny": ["Bash(rm -rf:*)"],
                    "ask": ["Bash(git push:*)"],
                }
            }

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertEqual(result["allow"], ["Bash(git status:*)", "Bash(ls:*)"])
            self.assertEqual(result["deny"], ["Bash(rm -rf:*)"])
            self.assertEqual(result["ask"], ["Bash(git push:*)"])

    def test_extract_file_tool_patterns(self):
        """
        Given a settings.local.json with Read, Write, Edit, and Bash allow patterns
        When get_native_permissions reads it
        Then all four governed file-tool and Bash patterns are present in allow
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            config = {
                "permissions": {
                    "allow": [
                        "Read(/tmp/**)",
                        "Write(/tmp/**)",
                        "Edit(/tmp/**)",
                        "Bash(ls:*)",
                    ]
                }
            }

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertIn("Read(/tmp/**)", result["allow"])
            self.assertIn("Write(/tmp/**)", result["allow"])
            self.assertIn("Edit(/tmp/**)", result["allow"])
            self.assertIn("Bash(ls:*)", result["allow"])

    def test_missing_file(self):
        """
        Given a path to a settings.local.json that does not exist
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists
        """
        result = get_native_permissions(Path("/nonexistent/settings.local.json"))

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

    def test_invalid_json(self):
        """
        Given a settings.local.json containing invalid JSON
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists without raising
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings_path.write_text("{ invalid json }")

            result = get_native_permissions(settings_path)

            self.assertEqual(result, {"allow": [], "deny": [], "ask": []})


def _config_from_layers(*layers):
    """
    Build a Configuration from explicit (source_type, content) layer specs.

    Each spec is a ``(source_type, content_dict)`` pair; layers are ordered
    most-specific first. Lets divergence tests exercise get_toolguard_permissions
    against the public Configuration surface without touching files.
    """
    built = []
    for i, (source_type, content) in enumerate(layers):
        prov = Provenance("project", source_type, "json", Path(f"/fake/{i}.json"), i)
        built.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(built))


class TestGetToolguardPermissions(unittest.TestCase):
    """Test extracting permissions from the resolved toolguard configuration."""

    def test_extract_from_json(self):
        """
        Given a toolguard_hook layer with allow and deny permissions
        When get_toolguard_permissions reads the resolved Configuration
        Then the allow and deny patterns are returned and ask is empty
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": ["Bash(git status:*)", "Read(/tmp/**)"],
                        "deny": ["Bash(rm -rf:*)"],
                    }
                },
            )
        )
        result = get_toolguard_permissions(config)

        self.assertEqual(result["allow"], ["Bash(git status:*)", "Read(/tmp/**)"])
        self.assertEqual(result["deny"], ["Bash(rm -rf:*)"])
        self.assertEqual(result["ask"], [])

    def test_ignore_claude_settings(self):
        """
        Given a native ('claude') layer with permissions
        When get_toolguard_permissions reads the resolved Configuration
        Then it returns empty permissions because native layers are ignored
        """
        config = _config_from_layers(
            ("claude", {"permissions": {"allow": ["Bash(git push:*)"]}})
        )
        result = get_toolguard_permissions(config)

        # Should be empty since we ignore claude settings
        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

    def test_merge_multiple_files(self):
        """
        Given two toolguard_hook layers each with a distinct allow pattern
        When get_toolguard_permissions merges them
        Then both patterns appear in the merged allow list
        """
        config = _config_from_layers(
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
            ("toolguard_hook", {"permissions": {"allow": ["Bash(ls:*)"]}}),
        )
        result = get_toolguard_permissions(config)

        self.assertIn("Bash(git status:*)", result["allow"])
        self.assertIn("Bash(ls:*)", result["allow"])

    def test_deduplicate_patterns(self):
        """
        Given two toolguard_hook layers with the same allow pattern
        When get_toolguard_permissions merges them
        Then the shared pattern appears only once
        """
        config = _config_from_layers(
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
        )
        result = get_toolguard_permissions(config)

        # Should only appear once
        self.assertEqual(result["allow"].count("Bash(git status:*)"), 1)


class TestFindDivergentPatterns(unittest.TestCase):
    """Test finding divergent patterns."""

    def test_find_new_patterns(self):
        """
        Given a native allow list with one pattern absent from toolguard
        When find_divergent_patterns compares them
        Then only the native-only pattern is reported as divergent
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(git push:*)"],
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result["allow"], ["Bash(git push:*)"])
        self.assertEqual(result["deny"], [])
        self.assertEqual(result["ask"], [])

    def test_ignore_patterns_in_takeover_mode(self):
        """
        Given native-only patterns that are all listed as ignored
        When find_divergent_patterns is given that ignored list
        Then no divergent allow patterns are reported
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(uv run pytest:*)", "Bash(open:*)"],
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        ignored = ["Bash(uv run pytest:*)", "Bash(open:*)"]

        result = find_divergent_patterns(native, toolguard, ignored)

        # Should not include ignored patterns
        self.assertEqual(result["allow"], [])

    def test_exact_string_matching(self):
        """
        Given a native pattern that differs from a toolguard pattern only by trailing whitespace
        When find_divergent_patterns compares them
        Then the whitespace-different pattern is reported as divergent (matching is exact)
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(git status:*)  "],  # Trailing space
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        # Trailing space makes it different
        self.assertIn("Bash(git status:*)  ", result["allow"])

    def test_all_permission_types(self):
        """
        Given native allow, deny, and ask patterns absent from toolguard
        When find_divergent_patterns compares them
        Then divergences are reported for all three permission types
        """
        native = {
            "allow": ["Bash(ls:*)"],
            "deny": ["Bash(rm:*)"],
            "ask": ["Bash(git push:*)"],
        }

        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result["allow"], ["Bash(ls:*)"])
        self.assertEqual(result["deny"], ["Bash(rm:*)"])
        self.assertEqual(result["ask"], ["Bash(git push:*)"])

    def test_no_divergence(self):
        """
        Given identical native and toolguard permission sets
        When find_divergent_patterns compares them
        Then no divergences are reported in any permission type
        """
        native = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})


class TestCheckAndWarnDivergence(unittest.TestCase):
    """Test the main divergence check function."""

    def test_no_divergence(self):
        """
        Given matching native settings and toolguard_hook configs in a project
        When check_and_warn_divergence runs
        Then it returns an empty list (no divergence to warn about)
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / "logs"

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            # Create matching configs
            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # No divergence
            self.assertEqual(result, [])

    def test_with_divergence(self):
        """
        Given native settings allowing a pattern that the toolguard_hook config lacks
        When check_and_warn_divergence runs
        Then the divergent pattern is included in the returned list
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / "logs"

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {
                "permissions": {"allow": ["Bash(git status:*)", "Bash(git push:*)"]}
            }

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # Should find divergence
            self.assertIn("Bash(git push:*)", result)

    def test_deduplication(self):
        """
        Given a divergent native pattern with no matching toolguard config
        When check_and_warn_divergence runs twice in a row
        Then the first call reports the divergence and the second is deduplicated to an empty list
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / "logs"

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {"permissions": {"allow": ["Bash(git push:*)"]}}

            settings_path.write_text(json.dumps(config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            # First call should find divergence
            result1 = check_and_warn_divergence(project_root, logs_dir, takeover_config)
            self.assertIn("Bash(git push:*)", result1)

            # Second call should be deduplicated
            result2 = check_and_warn_divergence(project_root, logs_dir, takeover_config)
            self.assertEqual(result2, [])

    def test_takeover_mode_ignored_patterns(self):
        """
        Given takeover mode ignoring one of two divergent native patterns
        When check_and_warn_divergence runs
        Then only the non-ignored pattern is reported as divergent
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / "logs"

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {
                "permissions": {"allow": ["Bash(uv run pytest:*)", "Bash(git push:*)"]}
            }

            settings_path.write_text(json.dumps(config))

            takeover_config = {
                "enabled": True,
                "ignored_allow_patterns": ["Bash(uv run pytest:*)"],
                "additional_ignored_patterns": [],
            }

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # Should only find git push, not pytest
            self.assertIn("Bash(git push:*)", result)
            self.assertNotIn("Bash(uv run pytest:*)", result)


if __name__ == "__main__":
    unittest.main()
