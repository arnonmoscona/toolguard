"""
Unit tests for toolguard environment configuration.

Tests environment variable loading, .env file parsing, and configuration merging.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.env_config import (
    find_project_root,
    get_bool_env,
    get_env_config,
    load_env_file,
)


class TestFindProjectRoot(unittest.TestCase):
    """Test project root detection."""

    def test_finds_git_directory(self):
        """
        Given a project directory containing a .git directory and a nested subdir
        When find_project_root is called from the subdir
        Then the project directory is returned as the root
        """
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            # Should find project_dir from subdir
            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)

    def test_finds_pyproject_toml(self):
        """
        Given a project directory containing pyproject.toml and a deeply nested subdir
        When find_project_root is called from the deep subdir
        Then the project directory is returned as the root
        """
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "pyproject.toml").touch()
            subdir = project_dir / "subdir" / "deep"
            subdir.mkdir(parents=True)

            # Should find project_dir from deep subdir
            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)

    def test_returns_none_when_not_found(self):
        """
        Given a directory with no project markers (no .git, no pyproject.toml)
        When find_project_root is called from it
        Then None is returned
        """
        with TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "no_project"
            test_dir.mkdir()

            # Should return None
            result = find_project_root(test_dir)
            self.assertIsNone(result)

    def test_prefers_git_over_pyproject(self):
        """
        Given a project directory containing both .git and pyproject.toml at the same level
        When find_project_root is called from that directory
        Then that directory is returned as the root
        """
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            (project_dir / "pyproject.toml").touch()

            # Should find project_dir (with .git taking precedence)
            result = find_project_root(project_dir)
            self.assertEqual(result, project_dir)

    def test_stops_at_home_directory(self):
        """
        Given a directory with no project markers and the home directory mocked to its parent
        When find_project_root searches upward
        Then the search stops at home and returns None
        """
        # Create a temp dir that's NOT under home
        with TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Mock Path.home() to return a directory we control
            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path(tmpdir)

                # Should return None (stopped at mock home)
                result = find_project_root(test_dir)
                self.assertIsNone(result)


class TestLoadEnvFile(unittest.TestCase):
    """Test .env file loading."""

    def test_load_basic_env_file(self):
        """
        Given a .env file in the project root with two KEY=value lines
        When load_env_file is called on the project root
        Then both keys are returned with their values
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("KEY1=value1\nKEY2=value2\n")

            result = load_env_file(project_root)

            self.assertEqual(result.get("KEY1"), "value1")
            self.assertEqual(result.get("KEY2"), "value2")

    def test_load_with_source_root(self):
        """
        Given a .env file located in a 'src' subdirectory of the project root
        When load_env_file is called with source_root 'src'
        Then the variable from the src/.env file is returned
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            env_file = src_dir / ".env"
            env_file.write_text("SOURCE_VAR=from_src\n")

            result = load_env_file(project_root, "src")

            self.assertEqual(result.get("SOURCE_VAR"), "from_src")

    def test_load_nonexistent_file_returns_empty(self):
        """
        Given a project root with no .env file
        When load_env_file is called on it
        Then an empty dict is returned
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = load_env_file(project_root)

            self.assertEqual(result, {})

    def test_load_handles_comments(self):
        """
        Given a .env file containing comment lines and one KEY=value line
        When load_env_file parses it
        Then the key is returned and comment lines are excluded
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("# Comment\nKEY=value\n# Another comment\n")

            result = load_env_file(project_root)

            self.assertEqual(result.get("KEY"), "value")
            self.assertNotIn("# Comment", result)

    def test_load_handles_quotes(self):
        """
        Given a .env file with double-quoted and single-quoted values
        When load_env_file parses it
        Then the surrounding quotes are stripped from the returned values
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text(
                "DOUBLE=\"value with spaces\"\nSINGLE='another value'\n"
            )

            result = load_env_file(project_root)

            self.assertEqual(result.get("DOUBLE"), "value with spaces")
            self.assertEqual(result.get("SINGLE"), "another value")

    def test_load_handles_empty_lines(self):
        """
        Given a .env file with blank lines interspersed between two KEY=value lines
        When load_env_file parses it
        Then only the two keys are returned and blank lines are ignored
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("\nKEY1=value1\n\n\nKEY2=value2\n\n")

            result = load_env_file(project_root)

            self.assertEqual(len(result), 2)
            self.assertEqual(result.get("KEY1"), "value1")
            self.assertEqual(result.get("KEY2"), "value2")


class TestGetBoolEnv(unittest.TestCase):
    """Test boolean environment variable parsing."""

    def test_parse_true_values(self):
        """
        Given the env var set to each truthy string ('true', '1', 'yes', and case variants)
        When get_bool_env reads it with a False default
        Then it returns True for every variant
        """
        test_cases = ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]

        for value in test_cases:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                result = get_bool_env("TEST_VAR", False)
                self.assertTrue(result, f"Failed for value: {value}")

    def test_parse_false_values(self):
        """
        Given the env var set to each falsy string ('false', '0', 'no', and case variants)
        When get_bool_env reads it with a True default
        Then it returns False for every variant
        """
        test_cases = ["false", "False", "FALSE", "0", "no", "No", "NO"]

        for value in test_cases:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                result = get_bool_env("TEST_VAR", True)
                self.assertFalse(result, f"Failed for value: {value}")

    def test_fallback_to_env_vars_dict(self):
        """
        Given the variable absent from os.environ but present as 'true' in an env_vars dict
        When get_bool_env is called with that dict and a False default
        Then it falls back to the dict value and returns True
        """
        env_vars = {"TEST_VAR": "true"}

        result = get_bool_env("TEST_VAR", False, env_vars)

        self.assertTrue(result)

    def test_env_takes_precedence_over_dict(self):
        """
        Given os.environ sets the variable to 'true' while the env_vars dict sets it 'false'
        When get_bool_env is called with both sources
        Then the os.environ value wins and True is returned
        """
        env_vars = {"TEST_VAR": "false"}

        with patch.dict(os.environ, {"TEST_VAR": "true"}):
            result = get_bool_env("TEST_VAR", False, env_vars)

        self.assertTrue(result)

    def test_default_when_not_found(self):
        """
        Given a variable that is not set anywhere
        When get_bool_env is called with a True default and again with a False default
        Then the respective default value is returned in each case
        """
        result_true = get_bool_env("NONEXISTENT", True)
        result_false = get_bool_env("NONEXISTENT", False)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_invalid_value_uses_default(self):
        """
        Given the env var set to an unrecognized value ('maybe')
        When get_bool_env is called with a True default
        Then the default True is returned
        """
        with patch.dict(os.environ, {"TEST_VAR": "maybe"}):
            result = get_bool_env("TEST_VAR", True)

        self.assertTrue(result)


class TestGetEnvConfig(unittest.TestCase):
    """Test complete environment configuration loading."""

    def test_default_config(self):
        """
        Given no toolguard env vars set and a project root resolving to a temp dir
        When get_env_config is called
        Then defaults are returned: logging and extended syntax enabled, create_log_dir
        disabled, log_dir under the project root, and empty source_root
        """
        with TemporaryDirectory() as tmpdir:
            with patch("toolguard.env_config.find_project_root") as mock_find:
                mock_find.return_value = Path(tmpdir)

                config = get_env_config()

                self.assertTrue(config["logging_enabled"])
                self.assertTrue(config["extended_syntax"])
                self.assertFalse(config["create_log_dir"])
                # Resolve both paths for comparison (handles macOS /private/var vs /var symlink)
                self.assertEqual(config["log_dir"], (Path(tmpdir) / "logs").resolve())
                self.assertEqual(config["project_root"], Path(tmpdir))
                self.assertEqual(config["source_root"], "")

    def test_explicit_project_root(self):
        """
        Given TOOLGUARD_PROJECT_ROOT set to a temp directory
        When get_env_config is called
        Then config['project_root'] equals the resolved temp directory
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_PROJECT_ROOT": tmpdir}):
                config = get_env_config()

                self.assertEqual(config["project_root"], Path(tmpdir).resolve())

    def test_start_dir_anchors_project_root_and_env(self):
        """
        Given a start_dir whose own .env sets TOOLGUARD_EXTENDED_SYNTAX=false
        When get_env_config(start_dir=...) is called
        Then project_root and the extended_syntax setting come from THAT directory
        (this is what keeps the --eval probe faithful to each probed project)
        """
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text(
                "TOOLGUARD_EXTENDED_SYNTAX=false\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {}, clear=False):
                # Remove any ambient override so the project's .env is what decides.
                os.environ.pop("TOOLGUARD_EXTENDED_SYNTAX", None)
                with patch(
                    "toolguard.env_config.find_project_root",
                    return_value=Path(tmpdir),
                ):
                    config = get_env_config(start_dir=Path(tmpdir))
            self.assertEqual(config["project_root"], Path(tmpdir))
            self.assertFalse(config["extended_syntax"])

    def test_start_dir_bypasses_project_root_override(self):
        """
        Given TOOLGUARD_PROJECT_ROOT points at one directory but start_dir names another
        When get_env_config(start_dir=...) is called
        Then start_dir wins and the override is ignored, so a cross-project probe
        stays anchored to the target project rather than the sweep-runner's env
        """
        with TemporaryDirectory() as target, TemporaryDirectory() as other:
            with patch.dict(os.environ, {"TOOLGUARD_PROJECT_ROOT": other}):
                with patch(
                    "toolguard.env_config.find_project_root",
                    return_value=Path(target),
                ):
                    config = get_env_config(start_dir=Path(target))
            self.assertEqual(config["project_root"], Path(target))

    def test_explicit_log_dir_absolute(self):
        """
        Given TOOLGUARD_LOG_DIR set to an absolute path
        When get_env_config is called
        Then config['log_dir'] equals that resolved absolute path
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "mylogs"
            with patch.dict(os.environ, {"TOOLGUARD_LOG_DIR": str(log_dir)}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    # Resolve both paths for comparison (handles macOS /private/var vs /var symlink)
                    self.assertEqual(config["log_dir"], log_dir.resolve())

    def test_explicit_log_dir_relative(self):
        """
        Given TOOLGUARD_LOG_DIR set to a relative path ('custom/logs')
        When get_env_config is called with project root at a temp dir
        Then config['log_dir'] is that relative path resolved under the project root
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_LOG_DIR": "custom/logs"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    expected = (Path(tmpdir) / "custom" / "logs").resolve()
                    self.assertEqual(config["log_dir"], expected)

    def test_disable_logging(self):
        """
        Given TOOLGUARD_LOGGING_ENABLED set to 'false'
        When get_env_config is called
        Then config['logging_enabled'] is False
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_LOGGING_ENABLED": "false"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertFalse(config["logging_enabled"])

    def test_disable_extended_syntax(self):
        """
        Given TOOLGUARD_EXTENDED_SYNTAX set to 'false'
        When get_env_config is called
        Then config['extended_syntax'] is False
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_EXTENDED_SYNTAX": "false"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertFalse(config["extended_syntax"])

    def test_enable_create_log_dir(self):
        """
        Given TOOLGUARD_CREATE_LOG_DIR set to 'true'
        When get_env_config is called
        Then config['create_log_dir'] is True
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_CREATE_LOG_DIR": "true"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertTrue(config["create_log_dir"])

    def test_source_root_configuration(self):
        """
        Given TOOLGUARD_SOURCE_ROOT set to 'src'
        When get_env_config is called
        Then config['source_root'] equals 'src'
        """
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TOOLGUARD_SOURCE_ROOT": "src"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertEqual(config["source_root"], "src")

    def test_loads_from_env_file(self):
        """
        Given a .env file in the project root disabling logging and extended syntax
        When get_env_config is called with no overriding os.environ values
        Then both config['logging_enabled'] and config['extended_syntax'] are False
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text(
                "TOOLGUARD_LOGGING_ENABLED=false\nTOOLGUARD_EXTENDED_SYNTAX=false\n"
            )

            with patch("toolguard.env_config.find_project_root") as mock_find:
                mock_find.return_value = project_root

                config = get_env_config()

                self.assertFalse(config["logging_enabled"])
                self.assertFalse(config["extended_syntax"])

    def test_env_overrides_env_file(self):
        """
        Given a .env file disabling logging but os.environ enabling it
        When get_env_config is called
        Then the os.environ value wins and config['logging_enabled'] is True
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("TOOLGUARD_LOGGING_ENABLED=false\n")

            with patch.dict(os.environ, {"TOOLGUARD_LOGGING_ENABLED": "true"}):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

                    self.assertTrue(config["logging_enabled"])

    def test_no_project_root_uses_cwd(self):
        """
        Given find_project_root returns None (no project found)
        When get_env_config is called
        Then config['project_root'] falls back to the current working directory
        """
        with patch("toolguard.env_config.find_project_root") as mock_find:
            mock_find.return_value = None

            config = get_env_config()

            self.assertEqual(config["project_root"], Path.cwd())


if __name__ == "__main__":
    unittest.main()
