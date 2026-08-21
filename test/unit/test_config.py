"""
Unit tests for toolguard config-file discovery, project-root detection, and
extended pattern syntax.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.config import discover_config_files, find_project_root, wrap_tool_pattern
from toolguard.env_config import find_project_root as env_find_project_root
from toolguard.patterns import PatternType, match_pattern, parse_pattern


class TestWrapToolPattern(unittest.TestCase):
    """wrap_tool_pattern's own contract, independent of any caller."""

    def test_wraps_a_plain_body(self):
        """
        Given a wrapper-free pattern body
        When wrap_tool_pattern wraps it
        Then it returns the Tool(body) envelope
        """
        self.assertEqual(wrap_tool_pattern("Bash", "git diff:*"), "Bash(git diff:*)")

    def test_an_already_wrapped_body_raises(self):
        """
        Given a body that already carries its own Tool(...) wrapper
        When wrap_tool_pattern is asked to wrap it again
        Then it raises ValueError naming the offending body, instead of silently
            producing an inert Bash(Bash(git:*)) that matches nothing
        """
        with self.assertRaisesRegex(ValueError, "Bash\\(git:\\*\\)"):
            wrap_tool_pattern("Bash", "Bash(git:*)")

    def test_a_body_wrapped_in_a_different_tool_still_raises(self):
        """
        Given a body wrapped in a DIFFERENT tool's envelope than the one requested
        When wrap_tool_pattern is asked to wrap it
        Then it still raises -- the check is "already wrapped in anything", not
            "wrapped in this specific tool"
        """
        with self.assertRaises(ValueError):
            wrap_tool_pattern("Bash", "Read(/**)")


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


class TestConfigDiscovery(ConfigIsolationMixin, unittest.TestCase):
    """Test config file discovery in hierarchy."""

    def test_discover_with_project_configs(self):
        """
        Given a project with .claude/settings.local.json and toolguard_hook.json present
        When discover_config_files runs with the project root resolved
        Then both project config files are discovered, each tagged with its own
            source type and format
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "settings.local.json").write_text("{}")
        (claude_dir / "toolguard_hook.json").write_text("{}")

        configs = discover_config_files()

        self.assertIn((claude_dir / "settings.local.json", "claude", "json"), configs)
        self.assertIn(
            (claude_dir / "toolguard_hook.json", "toolguard_hook", "json"), configs
        )

    def test_discover_finds_user_level_configs(self):
        """
        Given a user ~/.claude holding toolguard_hook.toml and settings.json, and
            a project whose .claude directory does not exist
        When discover_config_files runs
        Then both user-level files are discovered, each tagged with its own
            source type and format
        """
        home, _project_dir = self.isolate_config_environment()
        user_claude_dir = home / ".claude"
        user_claude_dir.mkdir()

        (user_claude_dir / "toolguard_hook.toml").write_text("permissions = {}\n")
        (user_claude_dir / "settings.json").write_text("{}")

        configs = discover_config_files()

        self.assertIn(
            (user_claude_dir / "toolguard_hook.toml", "toolguard_hook", "toml"),
            configs,
        )
        self.assertIn((user_claude_dir / "settings.json", "claude", "json"), configs)

    def test_discover_ranks_every_project_file_above_every_user_file(self):
        """
        Given the same two config files present at both the project and the user level
        When discover_config_files runs
        Then all four are discovered and both project files precede both user files
        """
        home, project_dir = self.isolate_config_environment()
        user_claude_dir = home / ".claude"
        project_claude_dir = project_dir / ".claude"
        for directory in (user_claude_dir, project_claude_dir):
            directory.mkdir()
            (directory / "toolguard_hook.toml").write_text("permissions = {}\n")
            (directory / "settings.json").write_text("{}")

        config_paths = [path for path, _, _ in discover_config_files()]

        self.assertEqual(len(config_paths), 4)
        project_positions = [
            i for i, p in enumerate(config_paths) if p.parent == project_claude_dir
        ]
        user_positions = [
            i for i, p in enumerate(config_paths) if p.parent == user_claude_dir
        ]
        self.assertEqual(len(project_positions), 2)
        self.assertEqual(len(user_positions), 2)
        self.assertLess(max(project_positions), min(user_positions))

    def test_discover_prefers_toml_for_toolguard_hook_sources(self):
        """
        Given both toolguard_hook.toml and toolguard_hook.json in the same .claude
        When discover_config_files runs
        Then the TOML file is discovered and the JSON one is not
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "toolguard_hook.toml").write_text("permissions = {}\n")
        (claude_dir / "toolguard_hook.json").write_text("{}")

        configs = discover_config_files()

        self.assertIn(
            (claude_dir / "toolguard_hook.toml", "toolguard_hook", "toml"), configs
        )
        self.assertNotIn(
            claude_dir / "toolguard_hook.json", [path for path, _, _ in configs]
        )

    def test_discover_keeps_native_settings_json_only(self):
        """
        Given both settings.json and a settings.toml in the same .claude
        When discover_config_files runs
        Then the JSON file is discovered and the TOML one is ignored -- native
            settings sources have no TOML form
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "settings.json").write_text("{}")
        (claude_dir / "settings.toml").write_text("permissions = {}\n")

        configs = discover_config_files()

        self.assertIn((claude_dir / "settings.json", "claude", "json"), configs)
        self.assertNotIn(claude_dir / "settings.toml", [path for path, _, _ in configs])

    def test_discover_returns_only_files_that_exist(self):
        """
        Given a project .claude holding exactly one config file, and a user
            .claude holding none
        When discover_config_files runs
        Then exactly that one file is returned -- absent candidates are not
        """
        home, project_dir = self.isolate_config_environment()
        (home / ".claude").mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "settings.json").write_text("{}")

        configs = discover_config_files()

        self.assertEqual(configs, [(claude_dir / "settings.json", "claude", "json")])

    def test_discover_does_not_double_count_when_the_project_root_is_home(self):
        """
        Given a home directory that is also the project root -- routine, since
            ~/.claude is itself a strong project anchor -- holding two config files
        When discover_config_files runs
        Then each file is discovered once, not once per level
        """
        home, _project_dir = self.isolate_config_environment()
        user_claude_dir = home / ".claude"
        user_claude_dir.mkdir()
        (user_claude_dir / "toolguard_hook.toml").write_text("permissions = {}\n")
        (user_claude_dir / "settings.json").write_text("{}")

        with patch(
            "toolguard.config.find_project_root", return_value=home
        ) as mock_find_root:
            configs = discover_config_files()

        self.assertTrue(mock_find_root.called)
        self.assertEqual(
            configs,
            [
                (user_claude_dir / "toolguard_hook.toml", "toolguard_hook", "toml"),
                (user_claude_dir / "settings.json", "claude", "json"),
            ],
        )

    def test_discover_without_project_root(self):
        """
        Given find_project_root raises RuntimeError (no project found), with
            config files present at both the project and the user level
        When discover_config_files runs
        Then find_project_root was consulted, the project-level file is skipped,
            and the user-level file is still discovered
        """
        home, project_dir = self.isolate_config_environment()
        project_claude_dir = project_dir / ".claude"
        project_claude_dir.mkdir()
        (project_claude_dir / "settings.json").write_text("{}")
        user_claude_dir = home / ".claude"
        user_claude_dir.mkdir()
        (user_claude_dir / "settings.json").write_text("{}")

        with patch(
            "toolguard.config.find_project_root", side_effect=RuntimeError("No project")
        ) as mock_find_root:
            configs = discover_config_files()

        self.assertTrue(mock_find_root.called)
        self.assertEqual(
            configs, [(user_claude_dir / "settings.json", "claude", "json")]
        )

    def test_discover_prioritizes_local_over_regular(self):
        """
        Given a project with both settings.local.json and settings.json
        When discover_config_files runs
        Then settings.local.json appears before settings.json in the ordering
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "settings.local.json").write_text("{}")
        (claude_dir / "settings.json").write_text("{}")

        configs = discover_config_files()

        config_names = [path.name for path, _, _ in configs]
        self.assertIn("settings.local.json", config_names)
        self.assertIn("settings.json", config_names)
        self.assertLess(
            config_names.index("settings.local.json"),
            config_names.index("settings.json"),
        )


class TestFindProjectRoot(ConfigIsolationMixin, unittest.TestCase):
    """
    Real (unmocked) tests of toolguard.config.find_project_root's marker walk.

    The mixin patches ``toolguard.config.find_project_root``, but this module
    imported it by value, so these tests still call the real function; the mixin
    is used here only for its ``Path.home()`` and environment isolation, which
    the walk's home stop does depend on.
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

    def test_nearest_marker_wins_over_a_higher_one(self):
        """
        Given a project containing a nested inner project, each with its own .git
        When find_project_root is called from below the inner one
        Then the inner (nearest) directory is returned, not the outer one
        """
        _home, outer = self.isolate_config_environment()
        inner = outer / "inner"
        (inner / ".git").mkdir(parents=True)
        subdir = inner / "subdir"
        subdir.mkdir()

        result = find_project_root(subdir)

        self.assertEqual(result, inner)

    def test_raises_when_nothing_found(self):
        """
        Given a directory tree with no project markers, and home mocked to bound
            the walk-up within the isolated tree
        When find_project_root is called
        Then RuntimeError is raised
        """
        home, _project = self.isolate_config_environment()
        test_dir = home / "no_project"
        test_dir.mkdir()

        with self.assertRaises(RuntimeError):
            find_project_root(test_dir)

    def test_walk_stops_at_home_and_ignores_markers_above_it(self):
        """
        Given a .git marker in home's own parent directory, and a start directory
            under home with no marker of its own
        When find_project_root is called
        Then RuntimeError is raised -- the walk stops at home, so the marker
            above home is never seen
        """
        home, _project = self.isolate_config_environment()
        (home.parent / ".git").mkdir()
        test_dir = home / "no_project"
        test_dir.mkdir()

        with self.assertRaises(RuntimeError):
            find_project_root(test_dir)

    def test_agrees_with_env_configs_own_find_project_root(self):
        """
        Given the two independent find_project_root implementations -- config's
            and env_config's -- resolving the same directories
        When a marker is reachable, and when none is
        Then they resolve the same root, and where config's raises RuntimeError
            env_config's returns None
        """
        home, project = self.isolate_config_environment()
        subdir = project / "a" / "b"
        subdir.mkdir(parents=True)
        no_marker_dir = home / "no_project"
        no_marker_dir.mkdir()

        self.assertEqual(find_project_root(subdir), env_find_project_root(subdir))
        with self.assertRaises(RuntimeError):
            find_project_root(no_marker_dir)
        self.assertIsNone(env_find_project_root(no_marker_dir))


if __name__ == "__main__":
    unittest.main()
