"""
Unit tests for toolguard.session_start (TOO-8 Phase 6).

Tests the SessionStart hook entry point, which surfaces configuration conflicts
at the start of each Claude Code session.

Coverage areas:
- Static takeover conflict detection (TakeoverEnabledConflict present)
- Dynamic conflict detection (entries in toolguard-conflict-*.md logs)
- No-conflicts case produces no stdout
- Malformed / empty stdin -> graceful exit 0 with no traceback
- Missing project_root / log_dir -> static check still runs
- Conflict counting in log files
- Most-recent log file selection
- Summary formatting
"""

import contextlib
import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from toolguard.config import (
    Configuration,
    Provenance,
    TakeoverConfig,
    TakeoverEnabledConflict,
    UnrecognizedFallbackSetting,
)
from toolguard.session_start import (
    _EMPTY_SHADOW_STATUS,
    ShadowStatus,
    _check_dynamic_conflicts,
    _count_conflict_entries,
    _detect_broken_config_files,
    _detect_conflicts,
    _detect_shadow_status,
    _detect_unrecognized_fallbacks,
    _format_summary,
    _parse_session_start_input,
    _recent_conflict_logs,
    install_provenance,
    main,
)


def _make_provenance(level="project", path="/fake/.claude/toolguard_hook.toml"):
    """Helper: build a Provenance for testing."""
    return Provenance(
        level=level,
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(path),
        specificity=0,
    )


def _make_conflict(sources=None):
    """Helper: build a TakeoverEnabledConflict for testing."""
    if sources is None:
        sources = [
            (True, _make_provenance("project", "/proj/.claude/toolguard_hook.toml")),
            (False, _make_provenance("user", "/home/user/.claude/toolguard_hook.toml")),
        ]
    return TakeoverEnabledConflict(sources=tuple(sources))


def _write_conflict_entries(log_file: Path, count: int) -> None:
    """Helper: write `count` well-formed conflict entries to a log file."""
    with open(log_file, "w", encoding="utf-8") as f:
        for i in range(count):
            f.write(f"## 2025-01-0{i + 1} 10:00:00 - CONFLICT\n\n")
            f.write("**Message**: test conflict\n\n")
            f.write("**Corrective Steps**: fix it\n\n")
            f.write("---\n\n")


class TestParseSessionStartInput(unittest.TestCase):
    """Tests for _parse_session_start_input."""

    def test_parses_valid_session_start_payload(self):
        """
        Given a well-formed SessionStart JSON payload on stdin
        When _parse_session_start_input is called
        Then it returns the parsed dict with cwd and session_id
        """
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "abc-123",
            "cwd": "/tmp/myproject",
        }
        with patch("sys.stdin", StringIO(json.dumps(payload))):
            result = _parse_session_start_input()
        self.assertEqual(result["cwd"], "/tmp/myproject")
        self.assertEqual(result["session_id"], "abc-123")

    def test_returns_empty_dict_on_empty_stdin(self):
        """
        Given empty stdin (no JSON payload)
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch("sys.stdin", StringIO("")):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_malformed_json(self):
        """
        Given malformed JSON on stdin
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch("sys.stdin", StringIO("not valid {json")):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_whitespace_only(self):
        """
        Given whitespace-only stdin
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch("sys.stdin", StringIO("   \n\t  ")):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_parses_payload_without_tool_fields(self):
        """
        Given a SessionStart payload that has no tool_name or tool_input
        When _parse_session_start_input is called
        Then it succeeds and the result has neither tool_name nor tool_input
        """
        payload = {"hook_event_name": "SessionStart", "cwd": "/tmp"}
        with patch("sys.stdin", StringIO(json.dumps(payload))):
            result = _parse_session_start_input()
        self.assertNotIn("tool_name", result)
        self.assertNotIn("tool_input", result)


class TestRecentConflictLogs(unittest.TestCase):
    """Tests for _recent_conflict_logs."""

    def test_returns_conflict_logs_most_recent_first(self):
        """
        Given multiple toolguard-conflict-*.md files in log_dir
        When _recent_conflict_logs is called
        Then it returns them ordered by date descending (most recent first)
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            (log_dir / "toolguard-conflict-2025-01-01.md").touch()
            (log_dir / "toolguard-conflict-2025-01-15.md").touch()
            (log_dir / "toolguard-conflict-2025-01-10.md").touch()

            result = _recent_conflict_logs(log_dir)

            self.assertEqual(
                [p.name for p in result],
                [
                    "toolguard-conflict-2025-01-15.md",
                    "toolguard-conflict-2025-01-10.md",
                    "toolguard-conflict-2025-01-01.md",
                ],
            )

    def test_returns_empty_when_no_conflict_logs(self):
        """
        Given a log_dir with no toolguard-conflict-*.md files
        When _recent_conflict_logs is called
        Then it returns an empty list
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            (
                log_dir / "toolguard-2025-01-01.md"
            ).touch()  # resolution log, not conflict

            self.assertEqual(_recent_conflict_logs(log_dir), [])

    def test_returns_empty_when_log_dir_missing(self):
        """
        Given a log_dir that does not exist
        When _recent_conflict_logs is called
        Then it returns an empty list without raising
        """
        self.assertEqual(_recent_conflict_logs(Path("/nonexistent/logs")), [])


class TestCountConflictEntries(unittest.TestCase):
    """Tests for _count_conflict_entries."""

    def test_counts_correct_number_of_entries(self):
        """
        Given a conflict log file with 3 CONFLICT entries
        When _count_conflict_entries is called
        Then it returns 3
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "toolguard-conflict-2025-01-01.md"
            _write_conflict_entries(log_file, 3)

            result = _count_conflict_entries(log_file)

            self.assertEqual(result, 3)

    def test_returns_zero_for_empty_file(self):
        """
        Given an empty conflict log file
        When _count_conflict_entries is called
        Then it returns 0
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "toolguard-conflict-2025-01-01.md"
            log_file.write_text("", encoding="utf-8")

            result = _count_conflict_entries(log_file)

            self.assertEqual(result, 0)

    def test_returns_zero_for_nonexistent_file(self):
        """
        Given a file path that does not exist
        When _count_conflict_entries is called
        Then it returns 0 without raising
        """
        result = _count_conflict_entries(Path("/nonexistent/file.md"))
        self.assertEqual(result, 0)

    def test_counts_single_entry(self):
        """
        Given a conflict log file with exactly 1 CONFLICT entry
        When _count_conflict_entries is called
        Then it returns 1
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "toolguard-conflict-2025-01-01.md"
            _write_conflict_entries(log_file, 1)

            result = _count_conflict_entries(log_file)

            self.assertEqual(result, 1)

    def test_does_not_count_non_conflict_headings(self):
        """
        Given a file with headings that are not CONFLICT entries
        When _count_conflict_entries is called
        Then only lines with '- CONFLICT' in the heading are counted
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "toolguard-conflict-2025-01-01.md"
            log_file.write_text(
                "## 2025-01-01 10:00:00 - CONFLICT\n\n"
                "## Some Other Heading\n\n"
                "## 2025-01-01 11:00:00 - WARNING\n\n",
                encoding="utf-8",
            )

            result = _count_conflict_entries(log_file)

            self.assertEqual(result, 1)


class TestCheckDynamicConflicts(unittest.TestCase):
    """Tests for _check_dynamic_conflicts."""

    def test_returns_none_when_log_dir_is_none(self):
        """
        Given log_dir is None
        When _check_dynamic_conflicts is called
        Then it returns None without raising
        """
        result = _check_dynamic_conflicts(None)
        self.assertIsNone(result)

    def test_returns_none_when_no_conflict_logs_exist(self):
        """
        Given a log_dir with no toolguard-conflict-*.md files
        When _check_dynamic_conflicts is called
        Then it returns None
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            result = _check_dynamic_conflicts(log_dir)
            self.assertIsNone(result)

    def test_returns_none_when_conflict_log_is_empty(self):
        """
        Given a toolguard-conflict-*.md file that exists but has 0 entries
        When _check_dynamic_conflicts is called
        Then it returns None (no recorded conflicts)
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            (log_dir / "toolguard-conflict-2025-01-01.md").write_text(
                "", encoding="utf-8"
            )

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNone(result)

    def test_returns_path_and_count_when_entries_exist(self):
        """
        Given a toolguard-conflict-*.md file with 5 recorded entries
        When _check_dynamic_conflicts is called
        Then it returns a (path_str, 5) tuple
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "toolguard-conflict-2025-06-18.md"
            _write_conflict_entries(log_file, 5)

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertEqual(count, 5)
            self.assertIn("toolguard-conflict-2025-06-18.md", path_str)

    def test_picks_most_recent_file_with_entries(self):
        """
        Given two conflict log files where the later one has entries
        When _check_dynamic_conflicts is called
        Then it reports the later (more recent) file
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            old_file = log_dir / "toolguard-conflict-2025-01-01.md"
            new_file = log_dir / "toolguard-conflict-2025-06-18.md"
            _write_conflict_entries(old_file, 2)
            _write_conflict_entries(new_file, 3)

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertIn("2025-06-18", path_str)
            self.assertEqual(count, 3)

    def test_empty_recent_file_does_not_shadow_older_entries(self):
        """
        Given an empty most-recent conflict log AND an older log that still has entries
        When _check_dynamic_conflicts is called
        Then it walks past the empty file and reports the older log's unresolved entries
        (the nag must persist until conflicts are actually cleared)
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            older_with_entries = log_dir / "toolguard-conflict-2025-01-01.md"
            empty_recent = log_dir / "toolguard-conflict-2025-06-18.md"
            _write_conflict_entries(older_with_entries, 2)
            empty_recent.write_text("", encoding="utf-8")

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertIn("2025-01-01", path_str)
            self.assertEqual(count, 2)


class TestFormatSummary(unittest.TestCase):
    """Tests for _format_summary."""

    def test_includes_header_line(self):
        """
        Given both static and dynamic conflicts
        When _format_summary is called
        Then the result starts with the standard conflict-detected header
        """
        conflict = _make_conflict()
        summary = _format_summary(
            conflict, ("logs/toolguard-conflict-2025-01-01.md", 2)
        )
        self.assertIn("toolguard: configuration conflicts detected", summary)

    def test_includes_takeover_conflict_line_when_present(self):
        """
        Given a static TakeoverEnabledConflict
        When _format_summary is called
        Then the result mentions takeover_mode.enabled and failed safe to OFF
        """
        conflict = _make_conflict()
        summary = _format_summary(conflict, None)
        self.assertIn("takeover_mode.enabled", summary)
        self.assertIn("failed safe to OFF", summary)

    def test_includes_dynamic_conflict_line_when_present(self):
        """
        Given a dynamic conflict with 3 entries in a named log file
        When _format_summary is called
        Then the result mentions the log path and entry count
        """
        summary = _format_summary(None, ("logs/toolguard-conflict-2025-06-18.md", 3))
        self.assertIn("toolguard-conflict-2025-06-18.md", summary)
        self.assertIn("3", summary)
        self.assertIn("entries", summary)

    def test_uses_singular_noun_for_one_entry(self):
        """
        Given a dynamic conflict with exactly 1 entry
        When _format_summary is called
        Then the result uses 'entry' (singular) not 'entries' (plural)
        """
        summary = _format_summary(None, ("logs/toolguard-conflict-2025-01-01.md", 1))
        self.assertIn("1 recorded entry", summary)

    def test_includes_review_action_prompt(self):
        """
        Given any conflict combination
        When _format_summary is called
        Then the result ends with a review/resolve prompt
        """
        conflict = _make_conflict()
        summary = _format_summary(conflict, None)
        self.assertIn("Review and resolve", summary)

    def test_includes_provenance_in_static_line(self):
        """
        Given a static conflict with known level/path in the provenance
        When _format_summary is called
        Then the static conflict line cites the provenance
        """
        conflict = _make_conflict(
            [
                (
                    True,
                    _make_provenance("project", "/proj/.claude/toolguard_hook.toml"),
                ),
                (
                    False,
                    _make_provenance("user", "/home/u/.claude/toolguard_hook.toml"),
                ),
            ]
        )
        summary = _format_summary(conflict, None)
        self.assertIn("project", summary)
        self.assertIn("user", summary)

    def test_no_conflicts_no_broken_files_returns_empty_string(self):
        """
        Given no static conflict, no dynamic conflict, and no broken files
        When _format_summary is called
        Then the result is an empty string (main() only prints when at least
            one section is non-empty; this documents that contract)
        """
        summary = _format_summary(None, None)
        self.assertEqual(summary, "")

    def test_includes_broken_file_section_when_present(self):
        """
        TOO-19: Given one broken (unparseable) config file and no takeover
            conflicts
        When _format_summary is called with broken_files set
        Then the result names the broken file, its parse error, and states
            that toolguard is falling back to ask for every tool call
        """
        broken = Path("/proj/.claude/toolguard_hook.local.toml")
        summary = _format_summary(None, None, broken_files=((broken, "bad TOML"),))
        self.assertIn(str(broken), summary)
        self.assertIn("bad TOML", summary)
        self.assertIn("ASK", summary)
        self.assertIn("BROKEN", summary)

    def test_broken_file_section_coexists_with_conflict_section(self):
        """
        TOO-19: Given both a broken config file AND a static takeover
            conflict
        When _format_summary is called with both
        Then the result contains both the broken-file section and the
            existing conflict-detected section, unmodified
        """
        conflict = _make_conflict()
        broken = Path("/proj/.claude/toolguard_hook.toml")
        summary = _format_summary(conflict, None, broken_files=((broken, "boom"),))
        self.assertIn(str(broken), summary)
        self.assertIn("configuration conflicts detected", summary)
        self.assertIn("takeover_mode.enabled", summary)

    def test_existing_conflict_only_output_unchanged_by_new_parameter(self):
        """
        Given a static + dynamic conflict combination identical to
            test_includes_header_line, called WITHOUT broken_files
        When _format_summary is called
        Then the output is byte-identical to calling it with the explicit
            default broken_files=() -- the new optional parameter does not
            alter the pre-existing conflict-only formatting
        """
        conflict = _make_conflict()
        dynamic = ("logs/toolguard-conflict-2025-01-01.md", 2)
        without_default = _format_summary(conflict, dynamic)
        with_explicit_default = _format_summary(conflict, dynamic, broken_files=())
        self.assertEqual(without_default, with_explicit_default)


class TestDetectBrokenConfigFiles(unittest.TestCase):
    """
    Tests for _detect_broken_config_files (TOO-19).

    TOO-19 review fix: this function now takes an already-loaded
    Configuration directly (no load_configuration() call of its own -- see
    the function's docstring for why), so these tests build and pass a
    Configuration double straight in rather than patching
    toolguard.session_start.load_configuration.
    """

    def test_returns_parse_failures_from_configuration(self):
        """
        Given a Configuration whose parse_failures has one entry
        When _detect_broken_config_files is called with it
        Then it returns that same (path, message) tuple
        """
        broken = Path("/fake/.claude/toolguard_hook.toml")
        config = MagicMock(spec=Configuration)
        config.parse_failures = ((broken, "bad TOML"),)

        result = _detect_broken_config_files(config)

        self.assertEqual(result, ((broken, "bad TOML"),))

    def test_returns_empty_tuple_when_no_parse_failures(self):
        """
        Given a Configuration with an empty parse_failures
        When _detect_broken_config_files is called with it
        Then it returns an empty tuple
        """
        config = MagicMock(spec=Configuration)
        config.parse_failures = ()

        result = _detect_broken_config_files(config)

        self.assertEqual(result, ())


class TestUnrecognizedFallbackAtSessionStart(unittest.TestCase):
    """
    TOO-19 m5: a ``*_fallback`` setting written with an unrecognized value must
    warn LOUDLY at session start, not only in the resolution log.

    The log alone is not enough for this failure mode: it presents as maximum
    prompting with no stated cause, and on an unattended run nobody reads the
    log until after the round trip has already been paid.
    """

    @staticmethod
    def _bad(key="no_match_fallback", value="allow_with_no_warning"):
        """Build one UnrecognizedFallbackSetting record for the given key/value."""
        return UnrecognizedFallbackSetting(
            key=key,
            value=value,
            provenance=_make_provenance(level="user"),
            accepted=("allow", "allow_with_no_warnings", "ask", "deny"),
        )

    def test_detect_returns_the_configurations_records(self):
        """
        Given a Configuration reporting one unrecognized fallback setting
        When _detect_unrecognized_fallbacks is called with it
        Then that record is returned as a tuple
        """
        config = MagicMock(spec=Configuration)
        config.unrecognized_fallback_settings.return_value = (self._bad(),)

        self.assertEqual(_detect_unrecognized_fallbacks(config), (self._bad(),))

    def test_detect_returns_empty_when_every_setting_is_valid(self):
        """
        Given a Configuration reporting no unrecognized fallback settings
        When _detect_unrecognized_fallbacks is called with it
        Then it returns an empty tuple
        """
        config = MagicMock(spec=Configuration)
        config.unrecognized_fallback_settings.return_value = ()

        self.assertEqual(_detect_unrecognized_fallbacks(config), ())

    def test_summary_names_value_setting_file_and_accepted_spellings(self):
        """
        Given one unrecognized fallback record
        When _format_summary renders it
        Then the section names the offending value, the setting it was on,
            the file it came from, the accepted spellings, and the fact that
            the effective behaviour is 'ask'
        """
        summary = _format_summary(None, None, (), None, (self._bad(),))

        self.assertIn("allow_with_no_warning", summary)
        self.assertIn("no_match_fallback", summary)
        self.assertIn("toolguard_hook.toml", summary)
        self.assertIn("allow_with_no_warnings", summary)
        self.assertIn("ask", summary)

    def test_summary_omits_the_section_when_there_is_nothing_to_report(self):
        """
        Given no unrecognized fallback records and nothing else to report
        When _format_summary renders
        Then the summary is empty -- a valid or unset value must not warn
        """
        self.assertEqual(_format_summary(None, None, (), None, ()), "")

    def test_main_prints_the_warning_for_an_otherwise_clean_config(self):
        """
        Given a config with NO conflicts, NO parse failures and NO shadowed
            install, whose only problem is a misspelled fallback value
        When main() runs the SessionStart hook
        Then the warning is printed to stdout on its own -- it must not
            depend on some other problem also being present
        """
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
            conflict=None,
        )
        config.parse_failures = ()
        config.project_root = None
        config.unrecognized_fallback_settings.return_value = (self._bad(),)

        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/fake"})
        with (
            patch("sys.stdin", StringIO(payload)),
            patch("toolguard.session_start.load_configuration", return_value=config),
            patch(
                "toolguard.session_start._check_dynamic_conflicts", return_value=None
            ),
            patch(
                "toolguard.session_start._detect_shadow_status",
                return_value=_EMPTY_SHADOW_STATUS,
            ),
            patch("sys.stdout", new_callable=StringIO) as out,
        ):
            with contextlib.suppress(SystemExit):
                main()

        printed = out.getvalue()
        self.assertIn("UNRECOGNIZED FALLBACK SETTING", printed)
        self.assertIn("allow_with_no_warning", printed)


class TestDetectConflicts(unittest.TestCase):
    """
    Tests for _detect_conflicts.

    TOO-19 review fix: this function now takes an already-loaded
    Configuration directly (no load_configuration() call of its own -- see
    the function's docstring for why), so these tests build and pass a
    Configuration double straight in rather than patching
    toolguard.session_start.load_configuration.
    """

    def _make_config_with_conflict(self, conflict=None, project_root=None):
        """Build a Configuration mock with the given takeover conflict and project_root."""
        takeover = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
            conflict=conflict,
        )
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = takeover
        config.project_root = project_root
        return config

    def test_returns_static_conflict_when_present(self):
        """
        Given a configuration with a TakeoverEnabledConflict
        When _detect_conflicts is called with it
        Then the returned static_conflict is the TakeoverEnabledConflict
        """
        expected_conflict = _make_conflict()
        config = self._make_config_with_conflict(conflict=expected_conflict)

        static_conflict, dynamic_conflict = _detect_conflicts(config)

        self.assertIs(static_conflict, expected_conflict)

    def test_returns_no_static_conflict_when_none(self):
        """
        Given a configuration with no takeover conflict
        When _detect_conflicts is called with it
        Then static_conflict is None
        """
        config = self._make_config_with_conflict(conflict=None)

        static_conflict, _dynamic = _detect_conflicts(config)

        self.assertIsNone(static_conflict)

    def test_returns_no_dynamic_conflict_when_no_log_dir(self):
        """
        Given a configuration with no project_root (hence no log_dir)
        When _detect_conflicts is called with it
        Then dynamic_conflict is None
        """
        config = self._make_config_with_conflict(conflict=None, project_root=None)

        _static, dynamic_conflict = _detect_conflicts(config)

        self.assertIsNone(dynamic_conflict)

    def test_returns_dynamic_conflict_when_log_file_has_entries(self):
        """
        Given a project_root whose logs/ directory has a conflict log with entries
        When _detect_conflicts is called with a configuration pointing at it
        Then dynamic_conflict is a (path_str, count) tuple
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            log_dir = project_root / "logs"
            log_dir.mkdir()
            log_file = log_dir / "toolguard-conflict-2025-06-18.md"
            _write_conflict_entries(log_file, 2)

            config = self._make_config_with_conflict(
                conflict=None, project_root=project_root
            )

            _static, dynamic_conflict = _detect_conflicts(config)

        self.assertIsNotNone(dynamic_conflict)
        path_str, count = dynamic_conflict
        self.assertEqual(count, 2)

    def test_handles_missing_project_root_gracefully(self):
        """
        Given a configuration with project_root=None (no project found)
        When _detect_conflicts is called with it
        Then it completes without raising and returns (None, None)
        """
        config = self._make_config_with_conflict(conflict=None, project_root=None)

        static_conflict, dynamic_conflict = _detect_conflicts(config)

        self.assertIsNone(static_conflict)
        self.assertIsNone(dynamic_conflict)


def _write_fake_toolguard_checkout(root: Path) -> Path:
    """Build a minimal on-disk toolguard checkout shape under *root*."""
    (root / "pyproject.toml").write_text('[project]\nname = "toolguard"\n')
    pkg = root / "toolguard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return pkg


class TestDetectShadowStatus(unittest.TestCase):
    """
    Tests for _detect_shadow_status (TOO-19).

    Both messages are gated on the active session's project itself being a
    toolguard source checkout; every other project must report the
    all-empty/False _EMPTY_SHADOW_STATUS regardless of what
    install_provenance's other primitives would say.
    """

    def _make_config(self, project_root):
        """Build a Configuration mock exposing only project_root."""
        config = MagicMock(spec=Configuration)
        config.project_root = project_root
        return config

    def test_no_project_root_returns_empty_status(self):
        """
        Given a configuration with project_root=None
        When _detect_shadow_status runs
        Then it returns _EMPTY_SHADOW_STATUS without touching install_provenance
        """
        config = self._make_config(project_root=None)
        self.assertEqual(_detect_shadow_status(config), _EMPTY_SHADOW_STATUS)

    def test_project_that_is_not_a_toolguard_checkout_returns_empty_status(self):
        """
        Given the active project is an ordinary (non-toolguard) directory
        When _detect_shadow_status runs
        Then it returns _EMPTY_SHADOW_STATUS -- meaningless for any other project
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config = self._make_config(project_root=project_root)
            self.assertEqual(_detect_shadow_status(config), _EMPTY_SHADOW_STATUS)

    def test_governing_copy_matching_checkout_reports_running_from_checkout(self):
        """
        Given the active project IS a toolguard checkout, and the copy that
        produced THIS process's import resolves to that SAME checkout
        When _detect_shadow_status runs
        Then running_from_checkout is True
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg = _write_fake_toolguard_checkout(project_root)
            config = self._make_config(project_root=project_root)

            with (
                patch.object(
                    install_provenance,
                    "governing_package_root",
                    return_value=pkg.resolve(),
                ),
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=None,
                ),
                patch.object(
                    install_provenance,
                    "stale_install_report",
                    return_value=install_provenance.StaleInstallReport(
                        False, project_root, None
                    ),
                ),
            ):
                status = _detect_shadow_status(config)

        self.assertTrue(status.running_from_checkout)
        self.assertEqual(status.checkout_root, project_root)

    def test_governing_copy_elsewhere_reports_not_running_from_checkout(self):
        """
        Given the active project IS a toolguard checkout, but the copy that
        produced THIS process's import resolves SOMEWHERE ELSE (a properly
        installed distribution)
        When _detect_shadow_status runs
        Then running_from_checkout is False
        """
        with (
            TemporaryDirectory() as tmpdir,
            TemporaryDirectory() as installed_dir,
        ):
            project_root = Path(tmpdir)
            _write_fake_toolguard_checkout(project_root)
            config = self._make_config(project_root=project_root)
            elsewhere = Path(installed_dir) / "toolguard"
            elsewhere.mkdir()

            with (
                patch.object(
                    install_provenance,
                    "governing_package_root",
                    return_value=elsewhere,
                ),
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=elsewhere,
                ),
                patch.object(
                    install_provenance,
                    "stale_install_report",
                    return_value=install_provenance.StaleInstallReport(
                        False, project_root, elsewhere
                    ),
                ),
            ):
                status = _detect_shadow_status(config)

        self.assertFalse(status.running_from_checkout)
        self.assertEqual(status.installed_root, elsewhere)

    def test_stale_flag_comes_from_stale_install_report(self):
        """
        Given install_provenance.stale_install_report reports is_stale=True
        When _detect_shadow_status runs
        Then the returned ShadowStatus.stale is True
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg = _write_fake_toolguard_checkout(project_root)
            config = self._make_config(project_root=project_root)

            with (
                patch.object(
                    install_provenance,
                    "governing_package_root",
                    return_value=pkg.resolve(),
                ),
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=Path("/fake/installed/toolguard"),
                ),
                patch.object(
                    install_provenance,
                    "stale_install_report",
                    return_value=install_provenance.StaleInstallReport(
                        True, project_root, Path("/fake/installed/toolguard")
                    ),
                ),
            ):
                status = _detect_shadow_status(config)

        self.assertTrue(status.stale)
        self.assertEqual(status.installed_root, Path("/fake/installed/toolguard"))


class TestFormatSummaryShadowStatus(unittest.TestCase):
    """Tests for _format_summary's TOO-19 shadow/stale-install sections."""

    def test_no_shadow_status_produces_no_extra_section(self):
        """
        Given shadow_status is None (the default)
        When _format_summary is called
        Then the output is unchanged (empty) -- existing 3-argument call sites unaffected
        """
        self.assertEqual(_format_summary(None, None, ()), "")

    def test_running_from_checkout_section_names_both_paths(self):
        """
        Given a ShadowStatus with running_from_checkout=True
        When _format_summary is called
        Then the output names both the governing checkout path and the installed path
        """
        status = ShadowStatus(
            checkout_root=Path("/home/dev/toolguard"),
            running_from_checkout=True,
            installed_root=Path(
                "/home/dev/.local/share/uv/tools/toolguard/lib/toolguard"
            ),
            stale=False,
        )
        text = _format_summary(None, None, (), status)
        self.assertIn("RUNNING FROM A SOURCE TREE", text)
        self.assertIn("/home/dev/toolguard", text)
        self.assertIn("/home/dev/.local/share/uv/tools/toolguard/lib/toolguard", text)

    def test_running_from_checkout_with_no_installed_root_says_so(self):
        """
        Given running_from_checkout=True but no installed distribution was found
        When _format_summary is called
        Then the output states that plainly instead of printing 'None'
        """
        status = ShadowStatus(
            checkout_root=Path("/home/dev/toolguard"),
            running_from_checkout=True,
            installed_root=None,
            stale=False,
        )
        text = _format_summary(None, None, (), status)
        self.assertIn("no installed distribution found", text)

    def test_stale_section_names_reinstall_command(self):
        """
        Given a ShadowStatus with stale=True
        When _format_summary is called
        Then the output names the reinstall command and warns about uncommitted changes
        """
        status = ShadowStatus(
            checkout_root=Path("/home/dev/toolguard"),
            running_from_checkout=False,
            installed_root=Path("/installed/toolguard"),
            stale=True,
        )
        text = _format_summary(None, None, (), status)
        self.assertIn("INSTALLED COPY IS STALE", text)
        self.assertIn("uv tool install --force /home/dev/toolguard toolguard", text)
        self.assertIn("uncommitted changes", text)

    def test_neither_flag_set_produces_no_shadow_sections(self):
        """
        Given a ShadowStatus with both flags False (the gate passed but nothing
        is actually wrong)
        When _format_summary is called
        Then neither shadow section appears
        """
        status = ShadowStatus(
            checkout_root=Path("/home/dev/toolguard"),
            running_from_checkout=False,
            installed_root=Path("/installed/toolguard"),
            stale=False,
        )
        text = _format_summary(None, None, (), status)
        self.assertEqual(text, "")

    def test_both_sections_can_appear_together(self):
        """
        Given a ShadowStatus with BOTH running_from_checkout and stale True
        When _format_summary is called
        Then both sections appear, separated by a blank line
        """
        status = ShadowStatus(
            checkout_root=Path("/home/dev/toolguard"),
            running_from_checkout=True,
            installed_root=Path("/installed/toolguard"),
            stale=True,
        )
        text = _format_summary(None, None, (), status)
        self.assertIn("RUNNING FROM A SOURCE TREE", text)
        self.assertIn("INSTALLED COPY IS STALE", text)


class TestMain(unittest.TestCase):
    """End-to-end tests for main() -- the actual hook entry point."""

    def _run_main_with_stdin(self, stdin_text, config=None):
        """
        Run main() with the given stdin text, capturing stdout and the exit code.

        Returns:
            Tuple (stdout_text, exit_code)
        """
        if config is None:
            # Default: no conflicts
            config = MagicMock(spec=Configuration)
            config.takeover_mode.return_value = TakeoverConfig(
                enabled=False,
                ignored_allow_patterns=(),
                additional_ignored_patterns=(),
                no_match_fallback="deny",
                conflict=None,
            )
            config.project_root = None

        with (
            patch("sys.stdin", StringIO(stdin_text)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.session_start.load_configuration", return_value=config),
        ):
            exit_code = None
            try:
                main()
            except SystemExit as e:
                exit_code = e.code
        return mock_stdout.getvalue(), exit_code

    def test_exits_zero_always(self):
        """
        Given any stdin input
        When main() is called
        Then it always exits with code 0
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        _stdout, exit_code = self._run_main_with_stdin(payload)
        self.assertEqual(exit_code, 0)

    def test_exits_zero_on_empty_stdin(self):
        """
        Given empty stdin
        When main() is called
        Then it exits 0 without traceback
        """
        _stdout, exit_code = self._run_main_with_stdin("")
        self.assertEqual(exit_code, 0)

    def test_exits_zero_on_malformed_stdin(self):
        """
        Given malformed JSON on stdin
        When main() is called
        Then it exits 0 without traceback
        """
        _stdout, exit_code = self._run_main_with_stdin("not valid json {{{")
        self.assertEqual(exit_code, 0)

    def test_no_stdout_when_no_conflicts(self):
        """
        Given a configuration with no static or dynamic conflicts
        When main() is called
        Then nothing is printed to stdout
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        stdout_text, _exit = self._run_main_with_stdin(payload)
        self.assertEqual(stdout_text.strip(), "")

    def test_stdout_summary_when_static_conflict_present(self):
        """
        Given a configuration with a TakeoverEnabledConflict
        When main() is called
        Then stdout contains the conflict summary mentioning takeover_mode.enabled
        """
        conflict = _make_conflict()
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
            conflict=conflict,
        )
        config.project_root = None

        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        stdout_text, exit_code = self._run_main_with_stdin(payload, config=config)

        self.assertEqual(exit_code, 0)
        self.assertIn("takeover_mode.enabled", stdout_text)
        self.assertIn("configuration conflicts detected", stdout_text)

    def test_stdout_summary_when_dynamic_conflict_present(self):
        """
        Given a conflict log file with recorded entries in log_dir
        When main() is called
        Then stdout contains the conflict log path and entry count
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            log_dir = project_root / "logs"
            log_dir.mkdir()
            log_file = log_dir / "toolguard-conflict-2025-06-18.md"
            _write_conflict_entries(log_file, 4)

            config = MagicMock(spec=Configuration)
            config.takeover_mode.return_value = TakeoverConfig(
                enabled=False,
                ignored_allow_patterns=(),
                additional_ignored_patterns=(),
                no_match_fallback="deny",
                conflict=None,
            )
            config.project_root = project_root

            payload = json.dumps(
                {"hook_event_name": "SessionStart", "cwd": str(project_root)}
            )
            stdout_text, exit_code = self._run_main_with_stdin(payload, config=config)

        self.assertEqual(exit_code, 0)
        self.assertIn("4", stdout_text)
        self.assertIn("toolguard-conflict-2025-06-18.md", stdout_text)

    def test_stdout_alert_when_config_broken(self):
        """
        TOO-19: Given a Configuration reporting a broken (unparseable) config
            file via parse_failures, and no takeover conflicts
        When main() is called
        Then stdout names the broken file and states toolguard is falling
            back to ask -- the loudest channel (SessionStart stdout is
            injected into the session context) surfaces this even when no
            takeover conflict exists, and the hook still exits 0
        """
        broken = Path("/proj/.claude/toolguard_hook.local.toml")
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
            conflict=None,
        )
        config.project_root = None
        config.parse_failures = ((broken, "bad TOML"),)

        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        stdout_text, exit_code = self._run_main_with_stdin(payload, config=config)

        self.assertEqual(exit_code, 0)
        self.assertIn(str(broken), stdout_text)
        self.assertIn("ASK", stdout_text)

    def test_no_stdout_when_no_conflicts_or_broken_files_default_mock(self):
        """
        TOO-19 regression guard: Given the default no-conflict MagicMock(spec=
            Configuration) used throughout this test class, which does NOT
            explicitly set parse_failures
        When main() is called
        Then nothing is printed -- _detect_broken_config_files must treat an
            unconfigured mock's parse_failures the same as a real empty
            tuple (via iteration, not bare truthiness), so this pre-existing
            test fixture shape is unaffected by the new check
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        stdout_text, _exit = self._run_main_with_stdin(payload)
        self.assertEqual(stdout_text.strip(), "")

    def test_stdout_alert_when_running_from_shadowed_source_tree(self):
        """
        TOO-19 end-to-end: Given the active project IS a toolguard checkout and
            the copy governing THIS process resolves to that same checkout
        When main() is called
        Then stdout contains the RUNNING FROM A SOURCE TREE alert
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg = _write_fake_toolguard_checkout(project_root)

            config = MagicMock(spec=Configuration)
            config.takeover_mode.return_value = TakeoverConfig(
                enabled=False,
                ignored_allow_patterns=(),
                additional_ignored_patterns=(),
                no_match_fallback="deny",
                conflict=None,
            )
            config.project_root = project_root
            config.parse_failures = ()

            payload = json.dumps(
                {"hook_event_name": "SessionStart", "cwd": str(project_root)}
            )
            with (
                patch.object(
                    install_provenance,
                    "governing_package_root",
                    return_value=pkg.resolve(),
                ),
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=None,
                ),
                patch.object(
                    install_provenance,
                    "stale_install_report",
                    return_value=install_provenance.StaleInstallReport(
                        False, project_root, None
                    ),
                ),
            ):
                stdout_text, exit_code = self._run_main_with_stdin(
                    payload, config=config
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("RUNNING FROM A SOURCE TREE", stdout_text)

    def test_graceful_on_load_configuration_exception(self):
        """
        Given load_configuration raises an unexpected exception
        When main() is called
        Then it still exits 0 with no traceback propagation
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        with (
            patch("sys.stdin", StringIO(payload)),
            patch(
                "toolguard.session_start.load_configuration",
                side_effect=RuntimeError("boom"),
            ),
            patch("sys.stderr", new_callable=StringIO),
        ):
            exit_code = None
            try:
                main()
            except SystemExit as e:
                exit_code = e.code
        self.assertEqual(exit_code, 0)

    def test_uses_getcwd_when_cwd_absent_from_payload(self):
        """
        Given a SessionStart payload without a 'cwd' key
        When main() is called
        Then os.getcwd() is used as the working directory (no KeyError)
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "session_id": "x"})
        # No cwd in payload; should fall back gracefully.
        _stdout, exit_code = self._run_main_with_stdin(payload)
        self.assertEqual(exit_code, 0)


class TestSessionStartArgparseAndIsatty(unittest.TestCase):
    """
    Tests for the argparse --help flag and the interactive (TTY) guard added to
    session_start.main (TOO-16 Change 2+3).
    """

    def test_help_flag_exits_zero(self):
        """
        Given --help on the command line
        When main is called
        Then argparse exits with code 0 (informational, not an error)
        """
        import sys

        with (
            patch.object(sys, "argv", ["toolguard-session-start", "--help"]),
            patch("sys.stdout", StringIO()),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 0)

    def test_isatty_true_prints_explanation_and_does_not_read_stdin(self):
        """
        Given a terminal invocation (sys.stdin.isatty() returns True)
        When main is called
        Then it prints an explanation to stderr, exits 0, and does not read from stdin
        """
        err = StringIO()
        # Empty stdin -- any attempt to parse it would fail cleanly but shouldn't happen
        stdin_mock = StringIO("")

        with (
            patch("sys.stdin", stdin_mock),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr", err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        # A meaningful explanation mentioning Claude Code should appear in stderr
        self.assertIn("Claude Code", err.getvalue())

    def test_isatty_false_processes_piped_event_normally(self):
        """
        Given a piped (non-TTY) invocation with a valid SessionStart payload
        When main is called (sys.stdin.isatty() returns False)
        Then the hook processes the event normally (exits 0, no traceback)
        """
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/tmp"})
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
            conflict=None,
        )
        config.project_root = None

        with (
            patch("sys.stdin", StringIO(payload)),
            patch("sys.stdin.isatty", return_value=False),
            patch("toolguard.session_start.load_configuration", return_value=config),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
