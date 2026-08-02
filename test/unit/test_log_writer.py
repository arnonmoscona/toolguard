"""
Unit tests for toolguard logging functionality.

Tests the logging functionality including file creation, format, and content.
"""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from toolguard.log_writer import (
    _LOG_CONTEXT_PREVIEW_WORDS,
    _preview_additional_context,
    log_command,
)


class TestLogging(unittest.TestCase):
    """Test logging functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Enable logging for tests
        self.env_patcher = patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "true"})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()

    def test_log_file_creation_with_correct_name_format(self):
        """
        Given logging is enabled and a fresh log directory
        When a command is logged
        Then a log file named toolguard-YYYY-MM-DD.md is created in that directory
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command
            log_command("git status", "executed", log_dir=log_dir)

            # Check that log file was created with correct name
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename

            self.assertTrue(log_file.exists(), f"Log file {log_file} was not created")

    def test_markdown_structure_is_correct(self):
        """
        Given logging is enabled
        When a command is logged in markdown format
        Then the file contains a header, Status and Command fields, and the command rendered as inline code
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command
            log_command("git status", "executed", log_dir=log_dir)

            # Read the log file
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check markdown structure
            self.assertIn("##", content, "Missing markdown header")
            self.assertIn("**Status**:", content, "Missing status field")
            self.assertIn("**Command**:", content, "Missing command field")
            self.assertIn("`git status`", content, "Command not formatted as code")

    def test_content_includes_command_status_violated_rules(self):
        """
        Given a refused command with a list of violated rules
        When the command is logged
        Then the log content includes the REFUSED status, the command, and every violated rule
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a refused command with violated rules
            violated_rules = ["git push:*", "**/.env/**"]
            log_command(
                "git push origin main",
                "refused",
                violated_rules=violated_rules,
                log_dir=log_dir,
            )

            # Read the log file
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that all required information is present
            self.assertIn("REFUSED", content, "Status not found")
            self.assertIn("git push origin main", content, "Command not found")
            self.assertIn("Violated Rules", content, "Violated rules section not found")
            self.assertIn("git push:*", content, "First violated rule not found")
            self.assertIn("**/.env/**", content, "Second violated rule not found")

    def test_multiple_log_entries_append_correctly(self):
        """
        Given logging is enabled
        When three commands are logged in sequence
        Then all three appear in the same daily file as three separate markdown entries
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log multiple commands
            log_command("git status", "executed", log_dir=log_dir)
            log_command("ls -la", "executed", log_dir=log_dir)
            log_command(
                "rm file.txt", "refused", violated_rules=["rm *"], log_dir=log_dir
            )

            # Read the log file
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that all commands are present
            self.assertIn("git status", content, "First command not found")
            self.assertIn("ls -la", content, "Second command not found")
            self.assertIn("rm file.txt", content, "Third command not found")

            # Count the number of entries (by counting markdown headers)
            header_count = content.count("## ")
            self.assertEqual(
                header_count, 3, f"Expected 3 entries, found {header_count}"
            )

    def test_logging_respects_disabled_flag(self):
        """
        Given CHECKED_BASH_LOGGING_ON is set to false
        When a command is logged
        Then no log file is created
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Disable logging
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "false"}):
                log_command("git status", "executed", log_dir=log_dir)

                # Check that no log file was created
                log_files = list(log_dir.glob("toolguard-*.md"))
                self.assertEqual(
                    len(log_files),
                    0,
                    "Log file should not be created when logging is disabled",
                )

    def test_jsonlines_format(self):
        """
        Given CHECKED_BASH_LOGGING_FORMAT is set to jsonlines
        When a command is logged
        Then a .jsonlines file is created whose first line parses to a JSON entry with timestamp, status, command, and violated_rules matching the logged values
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Set logging format to jsonlines
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command("git status", "executed", log_dir=log_dir)

                # Check that log file was created with .jsonlines extension
                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                log_file = log_dir / expected_filename

                self.assertTrue(
                    log_file.exists(), f"JSONLines log file {log_file} was not created"
                )

                # Read and parse the JSON content
                content = log_file.read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                self.assertGreater(len(lines), 0, "No JSON entries found")

                # Parse the first entry
                entry = json.loads(lines[0])
                self.assertIn("timestamp", entry)
                self.assertIn("status", entry)
                self.assertIn("command", entry)
                self.assertIn("violated_rules", entry)
                self.assertEqual(entry["status"], "executed")
                self.assertEqual(entry["command"], "git status")

    def test_log_without_violated_rules(self):
        """
        Given a command logged without any violated rules
        When the log file is written
        Then it contains no Violated Rules section
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command without violated rules
            log_command("git status", "executed", log_dir=log_dir)

            # Read the log file
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that violated rules section is not present
            self.assertNotIn(
                "Violated Rules", content, "Violated rules should not be present"
            )

    def test_log_directory_must_exist(self):
        """
        Given a log directory path that does not exist
        When a command is logged
        Then the process exits with code 1 and stderr reports that the logging directory does not exist
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a non-existent subdirectory
            log_dir = Path(tmpdir) / "nonexistent"

            # Capture stderr
            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                # Attempt to log - should exit with error
                with self.assertRaises(SystemExit) as cm:
                    log_command("git status", "executed", log_dir=log_dir)

                self.assertEqual(
                    cm.exception.code,
                    1,
                    "Should exit with code 1 when log directory does not exist",
                )

            # Verify error message in stderr
            stderr_output = stderr_capture.getvalue()
            self.assertIn("Logging directory does not exist", stderr_output)


class TestMatchedRuleLogging(unittest.TestCase):
    """Test matched_rule parameter in log entries."""

    def setUp(self):
        """Set up test fixtures."""
        self.env_patcher = patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "true"})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()

    def test_matched_rule_in_markdown_format(self):
        """
        Given a command logged with a matched_rule
        When the markdown log is written
        Then it contains a Matched Rule field showing the rule as inline code
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("git status", "executed", matched_rule="git *", log_dir=log_dir)

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Matched Rule**", content)
            self.assertIn("`git *`", content)

    def test_matched_rule_in_jsonlines_format(self):
        """
        Given jsonlines format and a command logged with a matched_rule
        When the entry is parsed
        Then its matched_rule field equals the supplied rule
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command(
                    "git status", "executed", matched_rule="git *", log_dir=log_dir
                )

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertEqual(entry["matched_rule"], "git *")

    def test_no_matched_rule_when_not_provided(self):
        """
        Given a command logged without a matched_rule
        When the markdown log is written
        Then it contains no Matched Rule field
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("git status", "executed", log_dir=log_dir)

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertNotIn("Matched Rule", content)

    def test_no_matched_rule_in_jsonlines_when_not_provided(self):
        """
        Given jsonlines format and a command logged without a matched_rule
        When the entry is parsed
        Then it has no matched_rule key
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command("git status", "executed", log_dir=log_dir)

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertNotIn("matched_rule", entry)

    def test_denied_command_no_matched_rule(self):
        """
        Given a refused command logged with violated rules but no matched_rule
        When the markdown log is written
        Then it shows REFUSED and a Violated Rules section but no Matched Rule field
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("rm -rf /", "refused", violated_rules=["rm *"], log_dir=log_dir)

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("REFUSED", content)
            self.assertIn("Violated Rules", content)
            self.assertNotIn("Matched Rule", content)

    def test_matched_rule_with_extra_info(self):
        """
        Given a command logged with both matched_rule and extra_info (agent)
        When the markdown log is written
        Then it shows the matched rule as inline code and an Agent field with the extra_info value
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                "git status",
                "executed",
                matched_rule="git *",
                extra_info="main",
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("`git *`", content)
            self.assertIn("**Agent**: main", content)

    def test_matched_rule_ordering_in_markdown(self):
        """
        Given a command logged with matched_rule and extra_info
        When the markdown log is written
        Then the Matched Rule field appears after Command and before Agent
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                "git status",
                "executed",
                matched_rule="git *",
                extra_info="main",
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            command_pos = content.index("**Command**")
            matched_pos = content.index("**Matched Rule**")
            agent_pos = content.index("**Agent**")

            self.assertLess(
                command_pos, matched_pos, "Matched Rule should appear after Command"
            )
            self.assertLess(
                matched_pos, agent_pos, "Matched Rule should appear before Agent"
            )


class TestPermissionModeLogging(unittest.TestCase):
    """
    Test the permission_mode parameter in log entries (TOO-15: recorded so a
    later investigation can tell whether Claude Code's own mode was a factor
    in what happened to a command after toolguard decided -- never affects
    the decision itself).
    """

    def setUp(self):
        """Set up test fixtures."""
        self.env_patcher = patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "true"})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()

    def test_permission_mode_in_markdown_format(self):
        """
        Given a command logged with a permission_mode
        When the markdown log is written
        Then it contains a Permission Mode field showing the mode as inline code
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                "cd /tmp",
                "ask",
                note="no match",
                log_dir=log_dir,
                permission_mode="default",
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Permission Mode**", content)
            self.assertIn("`default`", content)

    def test_permission_mode_in_jsonlines_format(self):
        """
        Given jsonlines format and a command logged with a permission_mode
        When the entry is parsed
        Then its permission_mode field equals the supplied mode
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command(
                    "cd /tmp",
                    "ask",
                    note="no match",
                    log_dir=log_dir,
                    permission_mode="default",
                )

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertEqual(entry["permission_mode"], "default")

    def test_no_permission_mode_when_not_provided(self):
        """
        Given a command logged without a permission_mode
        When the markdown log is written
        Then it contains no Permission Mode field
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("git status", "executed", log_dir=log_dir)

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertNotIn("Permission Mode", content)

    def test_no_permission_mode_in_jsonlines_when_not_provided(self):
        """
        Given jsonlines format and a command logged without a permission_mode
        When the entry is parsed
        Then it has no permission_mode key
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command("git status", "executed", log_dir=log_dir)

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertNotIn("permission_mode", entry)


class TestPreviewAdditionalContext(unittest.TestCase):
    """
    Unit tests for the ``_preview_additional_context`` word-budget helper
    (TOO-19 Phase 1, increment 7). The accumulated ``additionalContext`` block
    can be up to 500 words (see ``compound.py::_MAX_CONTEXT_WORDS``); the LOGGED
    copy is capped to a short preview so a human scanning the log isn't faced
    with a 500-word block on every matching invocation. The FULL text still
    reaches Claude via the hook's JSON output -- only the log copy is capped.
    """

    def test_short_text_passes_through_unchanged(self):
        """
        Given text within the word budget
        When _preview_additional_context runs
        Then the text is returned unchanged, with no ellipsis or word count
        """
        text = "prefer git status --short"
        self.assertEqual(_preview_additional_context(text), text)

    def test_long_text_is_capped_with_ellipsis_and_word_count(self):
        """
        Given text well over the word budget
        When _preview_additional_context runs
        Then only the first _LOG_CONTEXT_PREVIEW_WORDS words are kept, followed
            by an ellipsis marker and the FULL original word count
        """
        words = [f"word{i}" for i in range(100)]
        text = " ".join(words)
        preview = _preview_additional_context(text)
        expected_prefix = " ".join(words[:_LOG_CONTEXT_PREVIEW_WORDS])
        self.assertTrue(preview.startswith(expected_prefix))
        self.assertIn("...", preview)
        self.assertIn("100 words total", preview)

    def test_text_exactly_at_budget_passes_through_unchanged(self):
        """
        Given text with EXACTLY the word budget's word count
        When _preview_additional_context runs
        Then the text is returned unchanged (the cap is inclusive)
        """
        words = [f"word{i}" for i in range(_LOG_CONTEXT_PREVIEW_WORDS)]
        text = " ".join(words)
        self.assertEqual(_preview_additional_context(text), text)


class TestAdditionalContextLogging(unittest.TestCase):
    """
    Test the additional_context parameter in log entries (TOO-19 Phase 1,
    increment 7: records WHY a matching rule nudged Claude, so "why did Claude
    get this nudge" is answerable after the fact -- capped to a short preview,
    see TestPreviewAdditionalContext, so the log stays scannable).
    """

    def setUp(self):
        """Set up test fixtures."""
        self.env_patcher = patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "true"})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()

    def test_additional_context_in_markdown_format(self):
        """
        Given a command logged with an additional_context short enough to fit
            within the preview budget
        When the markdown log is written
        Then it contains a Context field with that exact text
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                "git push",
                "executed",
                matched_rule="git *",
                log_dir=log_dir,
                additional_context="prefer git status --short",
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Context**:", content)
            self.assertIn("prefer git status --short", content)

    def test_additional_context_capped_in_markdown_format(self):
        """
        Given a command logged with an additional_context text OVER the
            preview word budget
        When the markdown log is written
        Then the Context field shows only the capped preview, not the full text
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            long_text = " ".join(f"word{i}" for i in range(100))
            log_command(
                "git push",
                "executed",
                matched_rule="git *",
                log_dir=log_dir,
                additional_context=long_text,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Context**:", content)
            self.assertNotIn(long_text, content)
            self.assertIn("100 words total", content)

    def test_additional_context_in_jsonlines_format(self):
        """
        Given jsonlines format and a command logged with an additional_context
        When the entry is parsed
        Then its additional_context field equals the supplied text
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command(
                    "git push",
                    "executed",
                    matched_rule="git *",
                    log_dir=log_dir,
                    additional_context="prefer git status --short",
                )

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertEqual(
                    entry["additional_context"], "prefer git status --short"
                )

    def test_no_additional_context_when_not_provided(self):
        """
        Given a command logged without an additional_context
        When the markdown log is written
        Then it contains no Context field
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("git status", "executed", log_dir=log_dir)

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertNotIn("**Context**:", content)

    def test_no_additional_context_in_jsonlines_when_not_provided(self):
        """
        Given jsonlines format and a command logged without an
            additional_context
        When the entry is parsed
        Then it has no additional_context key
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command("git status", "executed", log_dir=log_dir)

                expected_filename = (
                    f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
                )
                content = (log_dir / expected_filename).read_text().strip()
                lines = [line for line in content.split("\n") if line.strip()]
                entry = json.loads(lines[0])

                self.assertNotIn("additional_context", entry)


class TestLogFormatGoldenFile(unittest.TestCase):
    """
    TOO-19 m5 review "Recommended follow-ups": pin the on-disk log contract
    (exact content, field/key order, falsy-omission) that
    toolguard/tools/log_harvest.py and the audit skill parse. Every other
    test in this module checks substrings or pairwise orderings; nothing
    before this asserted a full entry's exact bytes. Covers markdown and
    jsonlines, each with every optional field populated and with none, since
    falsy-omission is part of the contract in both formats.

    ``datetime.now()`` is patched to a single fixed value for the whole
    class so the rendered entry (which embeds the current time in both the
    filename and the entry body) is fully deterministic and comparable
    byte-for-byte.
    """

    def setUp(self):
        """Enable logging and pin datetime.now() to a fixed instant."""
        self.env_patcher = patch.dict("os.environ", {"CHECKED_BASH_LOGGING_ON": "true"})
        self.env_patcher.start()
        self.fixed_now = datetime(2026, 1, 15, 10, 30, 0)
        self.datetime_patcher = patch("toolguard.log_writer.datetime")
        mock_datetime = self.datetime_patcher.start()
        mock_datetime.now.return_value = self.fixed_now

    def tearDown(self):
        """Undo the datetime and environment patches."""
        self.datetime_patcher.stop()
        self.env_patcher.stop()

    def test_markdown_golden_all_optional_fields_populated(self):
        """
        Given every optional field (matched_rule, violated_rules,
            permission_mode, note, additional_context, extra_info) is
            populated
        When a command is logged in markdown format
        Then the file's content matches the exact expected markdown,
            byte-for-byte, in Status/Command/Matched Rule/Violated
            Rules/Permission Mode/Note/Context/Agent order
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                "git push origin main",
                "refused",
                violated_rules=["git push:*", "**/.env/**"],
                extra_info="main-agent",
                log_dir=log_dir,
                matched_rule="git push *",
                note="pushed to protected branch",
                permission_mode="default",
                additional_context="be careful",
            )

            content = (log_dir / "toolguard-2026-01-15.md").read_text()

            expected = (
                "## 2026-01-15 10:30:00\n\n"
                "- **Status**: REFUSED\n"
                "- **Command**: `git push origin main`\n"
                "- **Matched Rule**: `git push *`\n"
                "- **Violated Rules**: `git push:*`, `**/.env/**`\n"
                "- **Permission Mode**: `default`\n"
                "- **Note**: pushed to protected branch\n"
                "- **Context**: be careful\n"
                "- **Agent**: main-agent\n"
                "\n"
            )
            self.assertEqual(content, expected)

    def test_markdown_golden_no_optional_fields(self):
        """
        Given no optional field is populated
        When a command is logged in markdown format
        Then the file contains only the mandatory heading, Status, and
            Command lines, byte-for-byte, with every optional field omitted
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command("git status", "executed", log_dir=log_dir)

            content = (log_dir / "toolguard-2026-01-15.md").read_text()

            expected = (
                "## 2026-01-15 10:30:00\n\n"
                "- **Status**: EXECUTED\n"
                "- **Command**: `git status`\n"
                "\n"
            )
            self.assertEqual(content, expected)

    def test_jsonlines_golden_all_optional_fields_populated(self):
        """
        Given every optional field is populated and jsonlines format is
            selected
        When a command is logged
        Then the entry's keys equal, in exact insertion order, timestamp,
            status, command, violated_rules, matched_rule, note,
            extra_info, permission_mode, additional_context, with values
            matching what was logged
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command(
                    "git push origin main",
                    "refused",
                    violated_rules=["git push:*", "**/.env/**"],
                    extra_info="main-agent",
                    log_dir=log_dir,
                    matched_rule="git push *",
                    note="pushed to protected branch",
                    permission_mode="default",
                    additional_context="be careful",
                )

            content = (log_dir / "toolguard-2026-01-15.jsonlines").read_text()

            expected = {
                "timestamp": "2026-01-15T10:30:00",
                "status": "refused",
                "command": "git push origin main",
                "violated_rules": ["git push:*", "**/.env/**"],
                "matched_rule": "git push *",
                "note": "pushed to protected branch",
                "extra_info": "main-agent",
                "permission_mode": "default",
                "additional_context": "be careful",
            }
            self.assertEqual(content, json.dumps(expected) + "\n\n")
            entry = json.loads(content.strip())
            self.assertEqual(list(entry.keys()), list(expected.keys()))

    def test_jsonlines_golden_no_optional_fields(self):
        """
        Given no optional field is populated and jsonlines format is
            selected
        When a command is logged
        Then the entry contains exactly timestamp, status, command, and an
            empty violated_rules list, with every optional key omitted
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.dict("os.environ", {"CHECKED_BASH_LOGGING_FORMAT": "jsonlines"}):
                log_command("git status", "executed", log_dir=log_dir)

            content = (log_dir / "toolguard-2026-01-15.jsonlines").read_text()

            expected = {
                "timestamp": "2026-01-15T10:30:00",
                "status": "executed",
                "command": "git status",
                "violated_rules": [],
            }
            self.assertEqual(content, json.dumps(expected) + "\n\n")
            entry = json.loads(content.strip())
            self.assertEqual(list(entry.keys()), list(expected.keys()))


if __name__ == "__main__":
    unittest.main()
