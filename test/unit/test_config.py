"""
Unit tests for toolguard config hierarchy and pattern parsing.

Tests config file discovery, loading, merging, and extended pattern syntax.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.config import discover_config_files, find_project_root
from toolguard.patterns import PatternType, match_pattern, parse_pattern


class TestPatternParsing(unittest.TestCase):
    """Test extended pattern syntax parsing."""

    def test_parse_default_pattern(self):
        """
        Given a pattern string with no type prefix
        When parse_pattern parses it
        Then the type is DEFAULT and the pattern is returned unchanged
        """
        pattern_type, pattern = parse_pattern("git *")
        self.assertEqual(pattern_type, PatternType.DEFAULT)
        self.assertEqual(pattern, "git *")

    def test_parse_regex_pattern(self):
        """
        Given a pattern string prefixed with [regex]
        When parse_pattern parses it
        Then the type is REGEX and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern("[regex]^git (status|log).*")
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, "^git (status|log).*")

    def test_parse_glob_pattern(self):
        """
        Given a pattern string prefixed with [glob]
        When parse_pattern parses it
        Then the type is GLOB and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern("[glob]/Users/*/projects/**/*.py")
        self.assertEqual(pattern_type, PatternType.GLOB)
        self.assertEqual(pattern, "/Users/*/projects/**/*.py")

    def test_parse_pattern_with_whitespace(self):
        """
        Given a [regex] pattern with leading and trailing whitespace
        When parse_pattern parses it
        Then the type is REGEX and surrounding whitespace is stripped from the body
        """
        pattern_type, pattern = parse_pattern("  [regex]test.*  ")
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, "test.*")


class TestPatternMatching(unittest.TestCase):
    """Test pattern matching with different types."""

    def test_match_regex_pattern(self):
        """
        Given a REGEX pattern with an alternation (e.g. ^git (status|log))
        When matched against commands inside and outside the alternation
        Then matching commands match and non-matching ones do not
        """
        self.assertTrue(
            match_pattern(PatternType.REGEX, r"^git (status|log)", "git status")
        )
        self.assertTrue(
            match_pattern(PatternType.REGEX, r"^git (status|log)", "git log")
        )
        self.assertFalse(
            match_pattern(PatternType.REGEX, r"^git (status|log)", "git push")
        )

    def test_match_regex_anywhere(self):
        """
        Given an unanchored REGEX pattern (e.g. \\.env)
        When matched against commands where the pattern appears anywhere
        Then it matches regardless of position in the command
        """
        self.assertTrue(match_pattern(PatternType.REGEX, r"\.env", "cat /path/.env"))
        self.assertTrue(match_pattern(PatternType.REGEX, r"\.env", "cat .env"))

    def test_match_glob_pattern(self):
        """
        Given a GLOB pattern with a trailing wildcard (e.g. 'git *')
        When matched against commands starting with that prefix versus others
        Then prefixed commands match and unrelated commands do not
        """
        self.assertTrue(match_pattern(PatternType.GLOB, "git *", "git status"))
        self.assertTrue(match_pattern(PatternType.GLOB, "git *", "git log"))
        self.assertFalse(match_pattern(PatternType.GLOB, "git *", "cat file"))

    def test_match_invalid_regex(self):
        """
        Given a malformed REGEX pattern
        When match_pattern attempts to match a command against it
        Then it returns False instead of raising
        """
        self.assertFalse(match_pattern(PatternType.REGEX, "[invalid(regex", "test"))


class TestConfigDiscovery(unittest.TestCase):
    """Test config file discovery in hierarchy."""

    def test_discover_with_project_configs(self):
        """
        Given a project with .claude/settings.local.json and toolguard_hook.json present
        When discover_config_files runs with the project root resolved
        Then both project config files appear in the discovered config paths
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project structure
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Create some config files
            (claude_dir / "settings.local.json").write_text("{}")
            (claude_dir / "toolguard_hook.json").write_text("{}")

            # Mock find_project_root to return our temp project
            with patch("toolguard.config.find_project_root", return_value=project_dir):
                configs = discover_config_files()

            # Should find project configs
            config_paths = [str(path) for path, _, _ in configs]
            self.assertIn(str(claude_dir / "settings.local.json"), config_paths)
            self.assertIn(str(claude_dir / "toolguard_hook.json"), config_paths)

    def test_discover_without_project_root(self):
        """
        Given find_project_root raises RuntimeError (no project found)
        When discover_config_files runs
        Then it does not crash and returns a list (only user-level configs, if any)
        """
        with patch(
            "toolguard.config.find_project_root", side_effect=RuntimeError("No project")
        ):
            configs = discover_config_files()
            # Should only find user-level configs (if they exist)
            # Since we're in a test environment, user configs may or may not exist
            # Just verify it doesn't crash
            self.assertIsInstance(configs, list)

    def test_discover_prioritizes_local_over_regular(self):
        """
        Given a project with both settings.local.json and settings.json
        When discover_config_files runs
        Then settings.local.json appears before settings.json in the ordering
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Create both local and regular files
            (claude_dir / "settings.local.json").write_text("{}")
            (claude_dir / "settings.json").write_text("{}")

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                configs = discover_config_files()

            config_paths = [path for path, _, _ in configs]
            # settings.local.json should come before settings.json
            local_idx = next(
                i for i, p in enumerate(config_paths) if p.name == "settings.local.json"
            )
            regular_idx = next(
                i for i, p in enumerate(config_paths) if p.name == "settings.json"
            )
            self.assertLess(local_idx, regular_idx)


class TestFindProjectRoot(unittest.TestCase):
    """
    Real (unmocked) tests of toolguard.config.find_project_root's marker walk.

    TOO-15: consolidates config.py's walk-up with env_config.py's onto a shared
    "strong project anchor" tier (.git/.hg/.jj/.claude/CLAUDE.md) plus
    pyproject.toml. These tests exercise the real function directly, since every
    other test in this file mocks it (see discover_config_files tests above).
    """

    def test_finds_git_directory(self):
        """
        Given a project directory containing a .git directory and a nested subdir
        When find_project_root is called from the subdir
        Then the project directory is returned as the root
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_finds_pyproject_toml(self):
        """
        Given a project directory containing only pyproject.toml
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "pyproject.toml").touch()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_finds_claude_directory_alone(self):
        """
        Given a project directory containing only a .claude directory (no .git,
            no pyproject.toml)
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root (does not raise)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".claude").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_finds_claude_md_file_alone(self):
        """
        Given a project directory containing only a bare CLAUDE.md file
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root (does not raise)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "CLAUDE.md").touch()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_finds_hg_directory_alone(self):
        """
        Given a project directory containing only a .hg directory (Mercurial)
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".hg").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_finds_jj_directory_alone(self):
        """
        Given a project directory containing only a .jj directory (Jujutsu)
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".jj").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)

            self.assertEqual(result, project_dir)

    def test_raises_when_nothing_found(self):
        """
        Given a directory tree with no project markers, and home mocked to bound
            the walk-up within the isolated tree
        When find_project_root is called
        Then RuntimeError is raised
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "no_project"
            test_dir.mkdir()

            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path(tmpdir)

                with self.assertRaises(RuntimeError):
                    find_project_root(test_dir)


if __name__ == "__main__":
    unittest.main()
