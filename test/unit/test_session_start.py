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
)
from toolguard.session_start import (
    _check_dynamic_conflicts,
    _count_conflict_entries,
    _detect_conflicts,
    _format_summary,
    _parse_session_start_input,
    _recent_conflict_logs,
    main,
)


def _make_provenance(level='project', path='/fake/.claude/toolguard_hook.toml'):
    """Helper: build a Provenance for testing."""
    return Provenance(
        level=level,
        source_type='toolguard_hook',
        file_format='toml',
        path=Path(path),
        specificity=0,
    )


def _make_conflict(sources=None):
    """Helper: build a TakeoverEnabledConflict for testing."""
    if sources is None:
        sources = [
            (True, _make_provenance('project', '/proj/.claude/toolguard_hook.toml')),
            (False, _make_provenance('user', '/home/user/.claude/toolguard_hook.toml')),
        ]
    return TakeoverEnabledConflict(sources=tuple(sources))


def _write_conflict_entries(log_file: Path, count: int) -> None:
    """Helper: write `count` well-formed conflict entries to a log file."""
    with open(log_file, 'w', encoding='utf-8') as f:
        for i in range(count):
            f.write(f'## 2025-01-0{i + 1} 10:00:00 - CONFLICT\n\n')
            f.write('**Message**: test conflict\n\n')
            f.write('**Corrective Steps**: fix it\n\n')
            f.write('---\n\n')


class TestParseSessionStartInput(unittest.TestCase):
    """Tests for _parse_session_start_input."""

    def test_parses_valid_session_start_payload(self):
        """
        Given a well-formed SessionStart JSON payload on stdin
        When _parse_session_start_input is called
        Then it returns the parsed dict with cwd and session_id
        """
        payload = {
            'hook_event_name': 'SessionStart',
            'session_id': 'abc-123',
            'cwd': '/tmp/myproject',
        }
        with patch('sys.stdin', StringIO(json.dumps(payload))):
            result = _parse_session_start_input()
        self.assertEqual(result['cwd'], '/tmp/myproject')
        self.assertEqual(result['session_id'], 'abc-123')

    def test_returns_empty_dict_on_empty_stdin(self):
        """
        Given empty stdin (no JSON payload)
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch('sys.stdin', StringIO('')):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_malformed_json(self):
        """
        Given malformed JSON on stdin
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch('sys.stdin', StringIO('not valid {json')):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_whitespace_only(self):
        """
        Given whitespace-only stdin
        When _parse_session_start_input is called
        Then it returns an empty dict without raising
        """
        with patch('sys.stdin', StringIO('   \n\t  ')):
            result = _parse_session_start_input()
        self.assertEqual(result, {})

    def test_parses_payload_without_tool_fields(self):
        """
        Given a SessionStart payload that has no tool_name or tool_input
        When _parse_session_start_input is called
        Then it succeeds and the result has neither tool_name nor tool_input
        """
        payload = {'hook_event_name': 'SessionStart', 'cwd': '/tmp'}
        with patch('sys.stdin', StringIO(json.dumps(payload))):
            result = _parse_session_start_input()
        self.assertNotIn('tool_name', result)
        self.assertNotIn('tool_input', result)


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
            (log_dir / 'toolguard-conflict-2025-01-01.md').touch()
            (log_dir / 'toolguard-conflict-2025-01-15.md').touch()
            (log_dir / 'toolguard-conflict-2025-01-10.md').touch()

            result = _recent_conflict_logs(log_dir)

            self.assertEqual(
                [p.name for p in result],
                [
                    'toolguard-conflict-2025-01-15.md',
                    'toolguard-conflict-2025-01-10.md',
                    'toolguard-conflict-2025-01-01.md',
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
            (log_dir / 'toolguard-2025-01-01.md').touch()  # resolution log, not conflict

            self.assertEqual(_recent_conflict_logs(log_dir), [])

    def test_returns_empty_when_log_dir_missing(self):
        """
        Given a log_dir that does not exist
        When _recent_conflict_logs is called
        Then it returns an empty list without raising
        """
        self.assertEqual(_recent_conflict_logs(Path('/nonexistent/logs')), [])


class TestCountConflictEntries(unittest.TestCase):
    """Tests for _count_conflict_entries."""

    def test_counts_correct_number_of_entries(self):
        """
        Given a conflict log file with 3 CONFLICT entries
        When _count_conflict_entries is called
        Then it returns 3
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / 'toolguard-conflict-2025-01-01.md'
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
            log_file = Path(tmpdir) / 'toolguard-conflict-2025-01-01.md'
            log_file.write_text('', encoding='utf-8')

            result = _count_conflict_entries(log_file)

            self.assertEqual(result, 0)

    def test_returns_zero_for_nonexistent_file(self):
        """
        Given a file path that does not exist
        When _count_conflict_entries is called
        Then it returns 0 without raising
        """
        result = _count_conflict_entries(Path('/nonexistent/file.md'))
        self.assertEqual(result, 0)

    def test_counts_single_entry(self):
        """
        Given a conflict log file with exactly 1 CONFLICT entry
        When _count_conflict_entries is called
        Then it returns 1
        """
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / 'toolguard-conflict-2025-01-01.md'
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
            log_file = Path(tmpdir) / 'toolguard-conflict-2025-01-01.md'
            log_file.write_text(
                '## 2025-01-01 10:00:00 - CONFLICT\n\n'
                '## Some Other Heading\n\n'
                '## 2025-01-01 11:00:00 - WARNING\n\n',
                encoding='utf-8',
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
            (log_dir / 'toolguard-conflict-2025-01-01.md').write_text('', encoding='utf-8')

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
            log_file = log_dir / 'toolguard-conflict-2025-06-18.md'
            _write_conflict_entries(log_file, 5)

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertEqual(count, 5)
            self.assertIn('toolguard-conflict-2025-06-18.md', path_str)

    def test_picks_most_recent_file_with_entries(self):
        """
        Given two conflict log files where the later one has entries
        When _check_dynamic_conflicts is called
        Then it reports the later (more recent) file
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            old_file = log_dir / 'toolguard-conflict-2025-01-01.md'
            new_file = log_dir / 'toolguard-conflict-2025-06-18.md'
            _write_conflict_entries(old_file, 2)
            _write_conflict_entries(new_file, 3)

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertIn('2025-06-18', path_str)
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
            older_with_entries = log_dir / 'toolguard-conflict-2025-01-01.md'
            empty_recent = log_dir / 'toolguard-conflict-2025-06-18.md'
            _write_conflict_entries(older_with_entries, 2)
            empty_recent.write_text('', encoding='utf-8')

            result = _check_dynamic_conflicts(log_dir)

            self.assertIsNotNone(result)
            path_str, count = result
            self.assertIn('2025-01-01', path_str)
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
        summary = _format_summary(conflict, ('logs/toolguard-conflict-2025-01-01.md', 2))
        self.assertIn('toolguard: configuration conflicts detected', summary)

    def test_includes_takeover_conflict_line_when_present(self):
        """
        Given a static TakeoverEnabledConflict
        When _format_summary is called
        Then the result mentions takeover_mode.enabled and failed safe to OFF
        """
        conflict = _make_conflict()
        summary = _format_summary(conflict, None)
        self.assertIn('takeover_mode.enabled', summary)
        self.assertIn('failed safe to OFF', summary)

    def test_includes_dynamic_conflict_line_when_present(self):
        """
        Given a dynamic conflict with 3 entries in a named log file
        When _format_summary is called
        Then the result mentions the log path and entry count
        """
        summary = _format_summary(None, ('logs/toolguard-conflict-2025-06-18.md', 3))
        self.assertIn('toolguard-conflict-2025-06-18.md', summary)
        self.assertIn('3', summary)
        self.assertIn('entries', summary)

    def test_uses_singular_noun_for_one_entry(self):
        """
        Given a dynamic conflict with exactly 1 entry
        When _format_summary is called
        Then the result uses 'entry' (singular) not 'entries' (plural)
        """
        summary = _format_summary(None, ('logs/toolguard-conflict-2025-01-01.md', 1))
        self.assertIn('1 recorded entry', summary)

    def test_includes_review_action_prompt(self):
        """
        Given any conflict combination
        When _format_summary is called
        Then the result ends with a review/resolve prompt
        """
        conflict = _make_conflict()
        summary = _format_summary(conflict, None)
        self.assertIn('Review and resolve', summary)

    def test_includes_provenance_in_static_line(self):
        """
        Given a static conflict with known level/path in the provenance
        When _format_summary is called
        Then the static conflict line cites the provenance
        """
        conflict = _make_conflict([
            (True, _make_provenance('project', '/proj/.claude/toolguard_hook.toml')),
            (False, _make_provenance('user', '/home/u/.claude/toolguard_hook.toml')),
        ])
        summary = _format_summary(conflict, None)
        self.assertIn('project', summary)
        self.assertIn('user', summary)


class TestDetectConflicts(unittest.TestCase):
    """Tests for _detect_conflicts -- integration-like, mocking load_configuration."""

    def _make_config_with_conflict(self, conflict=None, project_root=None):
        """Build a Configuration mock with the given takeover conflict and project_root."""
        takeover = TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback='deny',
            conflict=conflict,
        )
        config = MagicMock(spec=Configuration)
        config.takeover_mode.return_value = takeover
        config.project_root = project_root
        return config

    def test_returns_static_conflict_when_present(self):
        """
        Given a configuration with a TakeoverEnabledConflict
        When _detect_conflicts is called
        Then the returned static_conflict is the TakeoverEnabledConflict
        """
        expected_conflict = _make_conflict()
        config = self._make_config_with_conflict(conflict=expected_conflict)

        with patch('toolguard.session_start.load_configuration', return_value=config):
            static_conflict, dynamic_conflict = _detect_conflicts('/tmp')

        self.assertIs(static_conflict, expected_conflict)

    def test_returns_no_static_conflict_when_none(self):
        """
        Given a configuration with no takeover conflict
        When _detect_conflicts is called
        Then static_conflict is None
        """
        config = self._make_config_with_conflict(conflict=None)

        with patch('toolguard.session_start.load_configuration', return_value=config):
            static_conflict, _dynamic = _detect_conflicts('/tmp')

        self.assertIsNone(static_conflict)

    def test_returns_no_dynamic_conflict_when_no_log_dir(self):
        """
        Given a configuration with no project_root (hence no log_dir)
        When _detect_conflicts is called
        Then dynamic_conflict is None
        """
        config = self._make_config_with_conflict(conflict=None, project_root=None)

        with patch('toolguard.session_start.load_configuration', return_value=config):
            _static, dynamic_conflict = _detect_conflicts('/tmp')

        self.assertIsNone(dynamic_conflict)

    def test_returns_dynamic_conflict_when_log_file_has_entries(self):
        """
        Given a project_root whose logs/ directory has a conflict log with entries
        When _detect_conflicts is called
        Then dynamic_conflict is a (path_str, count) tuple
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            log_dir = project_root / 'logs'
            log_dir.mkdir()
            log_file = log_dir / 'toolguard-conflict-2025-06-18.md'
            _write_conflict_entries(log_file, 2)

            config = self._make_config_with_conflict(conflict=None, project_root=project_root)

            with patch('toolguard.session_start.load_configuration', return_value=config):
                _static, dynamic_conflict = _detect_conflicts(str(project_root))

        self.assertIsNotNone(dynamic_conflict)
        path_str, count = dynamic_conflict
        self.assertEqual(count, 2)

    def test_handles_missing_project_root_gracefully(self):
        """
        Given a configuration with project_root=None (no project found)
        When _detect_conflicts is called
        Then it completes without raising and returns (None, None)
        """
        config = self._make_config_with_conflict(conflict=None, project_root=None)

        with patch('toolguard.session_start.load_configuration', return_value=config):
            static_conflict, dynamic_conflict = _detect_conflicts(None)

        self.assertIsNone(static_conflict)
        self.assertIsNone(dynamic_conflict)


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
                no_match_fallback='deny',
                conflict=None,
            )
            config.project_root = None

        with (
            patch('sys.stdin', StringIO(stdin_text)),
            patch('sys.stdout', new_callable=StringIO) as mock_stdout,
            patch('toolguard.session_start.load_configuration', return_value=config),
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
        payload = json.dumps({'hook_event_name': 'SessionStart', 'cwd': '/tmp'})
        _stdout, exit_code = self._run_main_with_stdin(payload)
        self.assertEqual(exit_code, 0)

    def test_exits_zero_on_empty_stdin(self):
        """
        Given empty stdin
        When main() is called
        Then it exits 0 without traceback
        """
        _stdout, exit_code = self._run_main_with_stdin('')
        self.assertEqual(exit_code, 0)

    def test_exits_zero_on_malformed_stdin(self):
        """
        Given malformed JSON on stdin
        When main() is called
        Then it exits 0 without traceback
        """
        _stdout, exit_code = self._run_main_with_stdin('not valid json {{{')
        self.assertEqual(exit_code, 0)

    def test_no_stdout_when_no_conflicts(self):
        """
        Given a configuration with no static or dynamic conflicts
        When main() is called
        Then nothing is printed to stdout
        """
        payload = json.dumps({'hook_event_name': 'SessionStart', 'cwd': '/tmp'})
        stdout_text, _exit = self._run_main_with_stdin(payload)
        self.assertEqual(stdout_text.strip(), '')

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
            no_match_fallback='deny',
            conflict=conflict,
        )
        config.project_root = None

        payload = json.dumps({'hook_event_name': 'SessionStart', 'cwd': '/tmp'})
        stdout_text, exit_code = self._run_main_with_stdin(payload, config=config)

        self.assertEqual(exit_code, 0)
        self.assertIn('takeover_mode.enabled', stdout_text)
        self.assertIn('configuration conflicts detected', stdout_text)

    def test_stdout_summary_when_dynamic_conflict_present(self):
        """
        Given a conflict log file with recorded entries in log_dir
        When main() is called
        Then stdout contains the conflict log path and entry count
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            log_dir = project_root / 'logs'
            log_dir.mkdir()
            log_file = log_dir / 'toolguard-conflict-2025-06-18.md'
            _write_conflict_entries(log_file, 4)

            config = MagicMock(spec=Configuration)
            config.takeover_mode.return_value = TakeoverConfig(
                enabled=False,
                ignored_allow_patterns=(),
                additional_ignored_patterns=(),
                no_match_fallback='deny',
                conflict=None,
            )
            config.project_root = project_root

            payload = json.dumps({'hook_event_name': 'SessionStart', 'cwd': str(project_root)})
            stdout_text, exit_code = self._run_main_with_stdin(payload, config=config)

        self.assertEqual(exit_code, 0)
        self.assertIn('4', stdout_text)
        self.assertIn('toolguard-conflict-2025-06-18.md', stdout_text)

    def test_graceful_on_load_configuration_exception(self):
        """
        Given load_configuration raises an unexpected exception
        When main() is called
        Then it still exits 0 with no traceback propagation
        """
        payload = json.dumps({'hook_event_name': 'SessionStart', 'cwd': '/tmp'})
        with (
            patch('sys.stdin', StringIO(payload)),
            patch('toolguard.session_start.load_configuration', side_effect=RuntimeError('boom')),
            patch('sys.stderr', new_callable=StringIO),
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
        payload = json.dumps({'hook_event_name': 'SessionStart', 'session_id': 'x'})
        # No cwd in payload; should fall back gracefully.
        _stdout, exit_code = self._run_main_with_stdin(payload)
        self.assertEqual(exit_code, 0)


if __name__ == '__main__':
    unittest.main()
