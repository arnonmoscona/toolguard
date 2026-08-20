"""Unit tests for toolguard environment configuration."""

import io
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import ambient, error_reporter
from toolguard.env_config import (
    find_project_root,
    get_bool_env,
    get_env_config,
    load_env_file,
)


def clean_env(**overrides):
    """
    Patch ``os.environ`` down to *overrides* alone.

    The subject reads the ambient environment, so anything the developer or CI
    happens to export (``TOOLGUARD_LOG_DIR``, ``TOOLGUARD_PROJECT_ROOT``, ...)
    otherwise decides the result. ``clear=True`` is the only form that keeps a
    test's outcome independent of the machine it runs on.
    """
    return patch.dict(os.environ, overrides, clear=True)


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

            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)

    def test_returns_none_when_not_found(self):
        """
        Given a directory with no project markers, and home mocked to the temp
            directory so that nothing above it can be reached
        When find_project_root is called from it
        Then None is returned
        """
        with TemporaryDirectory() as tmpdir:
            # Bounding the walk is what makes this independent of where TMPDIR
            # points: unbounded, it finds whatever project TMPDIR sits inside.
            boundary = Path(tmpdir).resolve()
            test_dir = boundary / "no_project"
            test_dir.mkdir()

            with patch("pathlib.Path.home", return_value=boundary) as mock_home:
                result = find_project_root(test_dir)

            self.assertIsNone(result)
            self.assertTrue(mock_home.called, "Path.home mock was never consulted")

    def test_nearest_marker_wins_over_a_strong_anchor_further_up(self):
        """
        Given .git in a parent directory and pyproject.toml in its child
        When find_project_root is called from below the child
        Then the child is returned: this resolver is the flat 'nearest marker of
            any kind' shape and has no .git-over-manifest preference
        """
        with TemporaryDirectory() as tmpdir:
            outer = (Path(tmpdir) / "outer").resolve()
            inner = outer / "inner"
            (inner / "sub").mkdir(parents=True)
            (outer / ".git").mkdir()
            (inner / "pyproject.toml").touch()

            result = find_project_root(inner / "sub")
            self.assertEqual(result, inner)

    def test_stops_at_home_directory(self):
        """
        Given a pyproject.toml in a directory ABOVE the mocked home directory,
            and a start directory below home
        When find_project_root searches upward
        Then None is returned: the walk stopped at home and never reached the
            marker above it
        """
        with TemporaryDirectory() as tmpdir:
            above_home = Path(tmpdir).resolve()
            (above_home / "pyproject.toml").touch()
            home = above_home / "home"
            start = home / "test"
            start.mkdir(parents=True)

            with patch("pathlib.Path.home", return_value=home) as mock_home:
                result = find_project_root(start)

            self.assertIsNone(result)
            self.assertTrue(mock_home.called, "Path.home mock was never consulted")

    def test_defaults_to_the_current_working_directory(self):
        """
        Given no start_dir argument and the process cwd mocked to a subdir of a
            directory holding .git
        When find_project_root is called
        Then that directory is returned, so the search started at the cwd
        """
        with TemporaryDirectory() as tmpdir:
            project_dir = (Path(tmpdir) / "project").resolve()
            subdir = project_dir / "subdir"
            subdir.mkdir(parents=True)
            (project_dir / ".git").mkdir()

            with patch("pathlib.Path.cwd", return_value=subdir) as mock_cwd:
                result = find_project_root()

            self.assertEqual(result, project_dir)
            self.assertTrue(mock_cwd.called, "Path.cwd mock was never consulted")

    def test_finds_claude_directory_alone(self):
        """
        Given a project directory containing only a .claude directory (no .git,
            no pyproject.toml)
        When find_project_root is called from a nested subdir
        Then the project directory is returned as the root (TOO-15: .claude is a
            strong project anchor, same tier as .git)
        """
        with TemporaryDirectory() as tmpdir:
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
        Then the project directory is returned as the root (TOO-15: CLAUDE.md is
            a strong project anchor, same tier as .git)
        """
        with TemporaryDirectory() as tmpdir:
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
        Then the project directory is returned as the root (TOO-15: .hg is now a
            recognised anchor, matching the migration gate's VCS tier)
        """
        with TemporaryDirectory() as tmpdir:
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
        Then the project directory is returned as the root (TOO-15: .jj is now a
            recognised anchor, matching the migration gate's VCS tier)
        """
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".jj").mkdir()
            subdir = project_dir / "subdir"
            subdir.mkdir()

            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)


class _FailsAfterOneLine:
    """A file-like whose iteration yields one usable line and then raises."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __iter__(self):
        yield "KEY1=value1\n"
        raise OSError("disk error")


class TestLoadEnvFile(unittest.TestCase):
    """Test .env file loading."""

    def test_load_basic_env_file(self):
        """
        Given a .env file in the project root with two KEY=value lines
        When load_env_file is called on the project root
        Then exactly those two keys are returned with their values
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("KEY1=value1\nKEY2=value2\n")

            result = load_env_file(project_root)

            self.assertEqual(result, {"KEY1": "value1", "KEY2": "value2"})

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
        Then an empty dict is returned and nothing is reported to stderr -- an
            absent .env is the normal case, not a read failure
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            buf = io.StringIO()
            with redirect_stderr(buf):
                result = load_env_file(project_root)

            self.assertEqual(result, {})
            self.assertEqual(buf.getvalue(), "")

    def test_load_handles_comments(self):
        """
        Given a .env file whose comment lines would themselves parse as KEY=value
        When load_env_file parses it
        Then only the real assignment is returned: neither the commented-out key
            nor the '#'-prefixed spelling of it appears
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text(
                "# COMMENTED=would_parse\nKEY=value\n# ANOTHER=also_would_parse\n"
            )

            result = load_env_file(project_root)

            self.assertEqual(result, {"KEY": "value"})
            self.assertNotIn("# COMMENTED", result)
            self.assertNotIn("COMMENTED", result)

    def test_line_without_an_equals_sign_is_skipped(self):
        """
        Given a .env file with a bare word on its own line and one KEY=value line
        When load_env_file parses it
        Then the bare line is skipped and the rest of the file still parses
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("JUST_A_WORD\nKEY=value\n")

            result = load_env_file(project_root)

            self.assertEqual(result, {"KEY": "value"})

    def test_value_may_contain_equals_signs(self):
        """
        Given a .env line whose value itself contains '=' characters
        When load_env_file parses it
        Then the split happens on the first '=' only and the whole remainder is
            the value
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("KEY=a=b=c\n")

            result = load_env_file(project_root)

            self.assertEqual(result, {"KEY": "a=b=c"})

    def test_whitespace_around_the_separator_is_stripped(self):
        """
        Given a .env line written as 'KEY = value' with spaces around the '='
        When load_env_file parses it
        Then both the key and the value are stripped
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("KEY = value\n")

            result = load_env_file(project_root)

            self.assertEqual(result, {"KEY": "value"})

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

    def test_the_grammar_interprets_nothing_beyond_key_equals_value(self):
        """
        Given .env lines using shell habits the parser does not implement -- a
            trailing '# comment' after a value, and a leading 'export '
        When load_env_file parses them
        Then neither is interpreted: the comment stays inside the value and
            'export NAME' becomes the key, both silently
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("A=/x  # trailing comment\nexport B=1\n")

            result = load_env_file(project_root)

            self.assertEqual(result, {"A": "/x  # trailing comment", "export B": "1"})

    def test_reading_the_file_does_not_touch_os_environ(self):
        """
        Given a .env file setting a variable that is not in os.environ
        When load_env_file is called
        Then os.environ is unchanged: the file is read, never applied
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".env").write_text("TOOLGUARD_LOGGING_ENABLED=false\n")

            with clean_env(KEEP="1"):
                before = dict(os.environ)
                result = load_env_file(project_root)

                self.assertEqual(result, {"TOOLGUARD_LOGGING_ENABLED": "false"})
                self.assertEqual(dict(os.environ), before)

    def test_unmatched_quotes_are_kept_in_the_value(self):
        """
        Given .env values whose leading quote has no matching trailing one
        When load_env_file parses them
        Then the quote characters stay in the value: stripping needs both ends
            to match
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / ".env"
            env_file.write_text("MIXED=\"value'\nHALF=\"value\nBARE='value\n")

            result = load_env_file(project_root)

            self.assertEqual(result["MIXED"], "\"value'")
            self.assertEqual(result["HALF"], '"value')
            self.assertEqual(result["BARE"], "'value")

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

            self.assertEqual(result, {"KEY1": "value1", "KEY2": "value2"})

    def test_read_failure_reports_a_warning_to_stderr_and_returns_empty(self):
        """
        Given a .env file exists but reading it raises (TOO-45 punch-list #04:
            this now goes through error_reporter.report_warning, not a bare
            print)
        When load_env_file is called
        Then the failure reaches stderr (no invocation is active in this
             test, so it degrades to the bare message) and an empty dict is
             returned
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".env").write_text("KEY=value\n")

            buf = io.StringIO()
            with redirect_stderr(buf):
                with patch(
                    "builtins.open", side_effect=OSError("disk error")
                ) as mock_open:
                    result = load_env_file(project_root)

            self.assertTrue(mock_open.called, "builtins.open mock was never consulted")
            self.assertEqual(result, {})
            self.assertIn("Failed to load .env file", buf.getvalue())
            self.assertIn("disk error", buf.getvalue())

    def test_read_failure_partway_through_discards_the_lines_already_parsed(self):
        """
        Given a .env file whose first line parses and whose second read raises
        When load_env_file is called
        Then the partially built result is discarded rather than returned, and
             the failure still reaches stderr
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".env").write_text("KEY1=value1\nKEY2=value2\n")

            buf = io.StringIO()
            with redirect_stderr(buf):
                with patch(
                    "builtins.open", return_value=_FailsAfterOneLine()
                ) as mock_open:
                    result = load_env_file(project_root)

            self.assertTrue(mock_open.called, "builtins.open mock was never consulted")
            self.assertEqual(result, {})
            self.assertIn("Failed to load .env file", buf.getvalue())

    def test_read_failure_reaches_the_warning_log_with_an_active_reporter(self):
        """
        Given a .env file exists but reading it raises, AND a registered
            error_reporter.Reporter with a resolvable log directory is
            active (TOO-45 punch-list #04 fix pass item 8a: a real converted
            call site, not a synthetic error_reporter message)
        When load_env_file is called
        Then the failure lands in the WARNING log file, not just stderr
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            env_path = project_root / ".env"
            env_path.write_text("KEY=value\n")
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()

            real_open = open

            def _boom(path, *args, **kwargs):
                """Fail only the .env read; the log write must go through for real."""
                if str(path) == str(env_path):
                    raise OSError("disk error")
                return real_open(path, *args, **kwargs)

            with error_reporter.active(error_reporter.Reporter(log_dir=log_dir)):
                with patch("builtins.open", side_effect=_boom) as mock_open:
                    load_env_file(project_root)

            self.assertTrue(mock_open.called, "builtins.open mock was never consulted")
            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            content = warning_files[0].read_text()
            self.assertIn("Failed to load .env file", content)
            self.assertIn("disk error", content)


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
            with clean_env(TEST_VAR=value):
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
            with clean_env(TEST_VAR=value):
                result = get_bool_env("TEST_VAR", True)
                self.assertFalse(result, f"Failed for value: {value}")

    def test_fallback_to_env_vars_dict(self):
        """
        Given the variable absent from os.environ but present as 'true' in an env_vars dict
        When get_bool_env is called with that dict and a False default
        Then it falls back to the dict value and returns True
        """
        env_vars = {"TEST_VAR": "true"}

        with clean_env():
            result = get_bool_env("TEST_VAR", False, env_vars)

        self.assertTrue(result)

    def test_env_takes_precedence_over_dict(self):
        """
        Given os.environ sets the variable to 'true' while the env_vars dict sets it 'false'
        When get_bool_env is called with both sources
        Then the os.environ value wins and True is returned
        """
        env_vars = {"TEST_VAR": "false"}

        with clean_env(TEST_VAR="true"):
            result = get_bool_env("TEST_VAR", False, env_vars)

        self.assertTrue(result)

    def test_default_when_not_found(self):
        """
        Given a variable that is not set anywhere
        When get_bool_env is called with a True default and again with a False default
        Then the respective default value is returned in each case
        """
        with clean_env():
            result_true = get_bool_env("NONEXISTENT", True)
            result_false = get_bool_env("NONEXISTENT", False)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_default_when_env_vars_dict_lacks_the_key(self):
        """
        Given an env_vars dict that holds other keys but not the requested one
        When get_bool_env is called with a True default and again with a False default
        Then the respective default is returned rather than any dict value
        """
        env_vars = {"OTHER_VAR": "false"}

        with clean_env():
            result_true = get_bool_env("TEST_VAR", True, env_vars)
            result_false = get_bool_env("TEST_VAR", False, env_vars)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_invalid_value_uses_default(self):
        """
        Given the env var set to an unrecognized value ('maybe')
        When get_bool_env is called with a True default and again with a False default
        Then the respective default is returned, in both directions
        """
        with clean_env(TEST_VAR="maybe"):
            result_true = get_bool_env("TEST_VAR", True)
            result_false = get_bool_env("TEST_VAR", False)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_empty_value_is_not_a_boolean(self):
        """
        Given the env var set to the empty string
        When get_bool_env is called with a True default and again with a False default
        Then the empty string is treated as unrecognized and the default is returned
        """
        with clean_env(TEST_VAR=""):
            result_true = get_bool_env("TEST_VAR", True)
            result_false = get_bool_env("TEST_VAR", False)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_invalid_value_reports_a_warning_to_stderr(self):
        """
        Given the env var set to an unrecognized value ('maybe')
        When get_bool_env is called
        Then the invalid value and the variable name reach stderr (TOO-45
             punch-list #04: via error_reporter.report_warning)
        """
        buf = io.StringIO()
        with redirect_stderr(buf):
            with clean_env(TEST_VAR="maybe"):
                get_bool_env("TEST_VAR", True)

        self.assertIn("TEST_VAR", buf.getvalue())
        self.assertIn("maybe", buf.getvalue())

    def test_recognised_value_reports_nothing(self):
        """
        Given the env var set to a recognized value
        When get_bool_env is called
        Then nothing is written to stderr
        """
        buf = io.StringIO()
        with redirect_stderr(buf):
            with clean_env(TEST_VAR="true"):
                get_bool_env("TEST_VAR", False)

        self.assertEqual(buf.getvalue(), "")


class TestGetEnvConfig(unittest.TestCase):
    """Test complete environment configuration loading."""

    def test_default_config(self):
        """
        Given no toolguard env vars set and a project root resolving to a temp dir
        When get_env_config is called
        Then defaults are returned: logging and extended syntax enabled, create_log_dir
        disabled, log_dir under the project root, empty source_root, and no other keys
        """
        with TemporaryDirectory() as tmpdir:
            with clean_env():
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(
                set(config),
                {
                    "logging_enabled",
                    "log_dir",
                    "extended_syntax",
                    "project_root",
                    "source_root",
                    "create_log_dir",
                },
            )
            self.assertTrue(config["logging_enabled"])
            self.assertTrue(config["extended_syntax"])
            self.assertFalse(config["create_log_dir"])
            self.assertEqual(config["log_dir"], (Path(tmpdir) / "logs").resolve())
            self.assertEqual(config["project_root"], Path(tmpdir))
            self.assertEqual(config["source_root"], "")

    def test_explicit_project_root_is_resolved(self):
        """
        Given TOOLGUARD_PROJECT_ROOT set to a non-normalised path into a temp directory
        When get_env_config is called
        Then config['project_root'] is the resolved directory, and project-root
            detection is not consulted at all
        """
        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir).resolve()
            (target / "sub").mkdir()

            with clean_env(TOOLGUARD_PROJECT_ROOT=f"{target}/sub/.."):
                # A concrete return value, not a bare MagicMock: were the
                # override ever to stop short-circuiting, a MagicMock project
                # root reaches open() through __index__ and closes a file
                # descriptor instead of failing the assertion.
                with patch(
                    "toolguard.env_config.find_project_root", return_value=None
                ) as mock_find:
                    config = get_env_config()

            self.assertEqual(config["project_root"], target)
            self.assertFalse(
                mock_find.called, "the explicit override must short-circuit detection"
            )

    def test_explicit_project_root_expands_a_tilde(self):
        """
        Given TOOLGUARD_PROJECT_ROOT written as '~/proj' with HOME set to a temp dir
        When get_env_config is called
        Then config['project_root'] is that directory under the temp home
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir).resolve()
            (home / "proj").mkdir()

            with clean_env(HOME=str(home), TOOLGUARD_PROJECT_ROOT="~/proj"):
                config = get_env_config()

            self.assertEqual(config["project_root"], home / "proj")

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
            with clean_env():
                with patch(
                    "toolguard.env_config.find_project_root",
                    return_value=Path(tmpdir),
                ) as mock_find:
                    config = get_env_config(start_dir=Path(tmpdir))

            mock_find.assert_called_once_with(Path(tmpdir))
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
            with clean_env(TOOLGUARD_PROJECT_ROOT=other):
                with patch(
                    "toolguard.env_config.find_project_root",
                    return_value=Path(target),
                ) as mock_find:
                    config = get_env_config(start_dir=Path(target))

            mock_find.assert_called_once_with(Path(target))
            self.assertEqual(config["project_root"], Path(target))

    def test_start_dir_without_a_marker_falls_back_to_start_dir_itself(self):
        """
        Given a start_dir containing no project marker, so detection finds nothing
        When get_env_config(start_dir=...) is called
        Then project_root is the resolved start_dir rather than None
        """
        with TemporaryDirectory() as tmpdir:
            start = (Path(tmpdir) / "sub").resolve()
            start.mkdir()

            with clean_env():
                with patch(
                    "toolguard.env_config.find_project_root", return_value=None
                ) as mock_find:
                    config = get_env_config(start_dir=start)

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(config["project_root"], start)

    def test_explicit_log_dir_absolute(self):
        """
        Given TOOLGUARD_LOG_DIR set to an absolute path
        When get_env_config is called
        Then config['log_dir'] equals that resolved absolute path
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "mylogs"
            with clean_env(TOOLGUARD_LOG_DIR=str(log_dir)):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(config["log_dir"], log_dir.resolve())

    def test_explicit_log_dir_relative(self):
        """
        Given TOOLGUARD_LOG_DIR set to a relative path ('custom/logs')
        When get_env_config is called with project root at a temp dir
        Then config['log_dir'] is that relative path resolved under the project root
        """
        with TemporaryDirectory() as tmpdir:
            with clean_env(TOOLGUARD_LOG_DIR="custom/logs"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            expected = (Path(tmpdir) / "custom" / "logs").resolve()
            self.assertEqual(config["log_dir"], expected)

    def test_explicit_log_dir_expands_a_tilde(self):
        """
        Given TOOLGUARD_LOG_DIR written as '~/mylogs' with HOME set to a temp dir
        When get_env_config is called
        Then config['log_dir'] is that directory under the temp home, not a path
            containing a literal '~'
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir).resolve()
            project_root = home / "project"
            project_root.mkdir()

            with clean_env(HOME=str(home), TOOLGUARD_LOG_DIR="~/mylogs"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(config["log_dir"], home / "mylogs")

    def test_a_bound_ambient_home_governs_a_tilde_log_dir(self):
        """
        Given an ambient binding whose home is a temp directory, no $HOME in the
              process environment, and TOOLGUARD_LOG_DIR set to '~/mylogs'
        When get_env_config is called
        Then config['log_dir'] lands under the bound home rather than under the
             machine's real home, which is where the passwd fallback would put it
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir).resolve()
            project_root = home / "project"
            project_root.mkdir()
            facts = ambient.AmbientFacts(
                home=home,
                cwd=project_root,
                env={"TOOLGUARD_LOG_DIR": "~/mylogs"},
            )

            with clean_env():
                with ambient.active(facts):
                    with patch("toolguard.env_config.find_project_root") as mock_find:
                        mock_find.return_value = project_root

                        config = get_env_config()

            self.assertEqual(config["log_dir"], home / "mylogs")

    def test_log_dir_may_come_from_the_env_file(self):
        """
        Given TOOLGUARD_LOG_DIR absent from os.environ but set in the project's .env
        When get_env_config is called
        Then the .env value decides config['log_dir']
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".env").write_text("TOOLGUARD_LOG_DIR=from_env_file\n")

            with clean_env():
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(
                config["log_dir"], (project_root / "from_env_file").resolve()
            )

    def test_os_environ_log_dir_overrides_the_env_file(self):
        """
        Given TOOLGUARD_LOG_DIR set in both os.environ and the project's .env
        When get_env_config is called
        Then the os.environ value wins
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".env").write_text("TOOLGUARD_LOG_DIR=from_env_file\n")

            with clean_env(TOOLGUARD_LOG_DIR="from_environ"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(
                config["log_dir"], (project_root / "from_environ").resolve()
            )

    def test_disable_logging(self):
        """
        Given TOOLGUARD_LOGGING_ENABLED set to 'false'
        When get_env_config is called
        Then config['logging_enabled'] is False
        """
        with TemporaryDirectory() as tmpdir:
            with clean_env(TOOLGUARD_LOGGING_ENABLED="false"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertFalse(config["logging_enabled"])

    def test_disable_extended_syntax(self):
        """
        Given TOOLGUARD_EXTENDED_SYNTAX set to 'false'
        When get_env_config is called
        Then config['extended_syntax'] is False
        """
        with TemporaryDirectory() as tmpdir:
            with clean_env(TOOLGUARD_EXTENDED_SYNTAX="false"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertFalse(config["extended_syntax"])

    def test_enable_create_log_dir(self):
        """
        Given TOOLGUARD_CREATE_LOG_DIR set to 'true'
        When get_env_config is called
        Then config['create_log_dir'] is True
        """
        with TemporaryDirectory() as tmpdir:
            with clean_env(TOOLGUARD_CREATE_LOG_DIR="true"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertTrue(config["create_log_dir"])

    def test_source_root_configuration(self):
        """
        Given TOOLGUARD_SOURCE_ROOT set to 'src' and a .env only inside src/
        When get_env_config is called
        Then config['source_root'] is 'src' and the src/.env is what was read
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / ".env").write_text("TOOLGUARD_LOGGING_ENABLED=false\n")

            with clean_env(TOOLGUARD_SOURCE_ROOT="src"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertEqual(config["source_root"], "src")
            self.assertFalse(config["logging_enabled"])

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

            with clean_env():
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
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

            with clean_env(TOOLGUARD_LOGGING_ENABLED="true"):
                with patch("toolguard.env_config.find_project_root") as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertTrue(config["logging_enabled"])

    def test_no_project_root_uses_cwd(self):
        """
        Given find_project_root returns None (no project found) and the process
            cwd mocked to a temp directory
        When get_env_config is called
        Then config['project_root'] is that mocked working directory
        """
        with TemporaryDirectory() as tmpdir:
            fallback = Path(tmpdir).resolve()

            with clean_env():
                with patch(
                    "toolguard.env_config.find_project_root", return_value=None
                ) as mock_find:
                    with patch("pathlib.Path.cwd", return_value=fallback) as mock_cwd:
                        config = get_env_config()

            self.assertTrue(
                mock_find.called, "find_project_root mock was not consulted"
            )
            self.assertTrue(mock_cwd.called, "Path.cwd mock was never consulted")
            self.assertEqual(config["project_root"], fallback)


if __name__ == "__main__":
    unittest.main()
