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
    LOG_FORMAT_JSONLINES,
    LogRecord,
    log_command,
)


class TestLogging(unittest.TestCase):
    """Test logging functionality."""

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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
                LogRecord(
                    command_str="git push origin main",
                    status="refused",
                    violated_rules=violated_rules,
                ),
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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )
            log_command(
                LogRecord(command_str="ls -la", status="executed"), log_dir=log_dir
            )
            log_command(
                LogRecord(
                    command_str="rm file.txt",
                    status="refused",
                    violated_rules=["rm *"],
                ),
                log_dir=log_dir,
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
        Given a resolved environment config whose logging_enabled is False
        When a command is logged
        Then no log file is created
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                config={"logging_enabled": False, "log_dir": log_dir},
            )

            log_files = list(log_dir.glob("toolguard-*.md"))
            self.assertEqual(
                len(log_files),
                0,
                "Log file should not be created when logging is disabled",
            )

    def test_logging_enabled_by_default_without_a_config(self):
        """
        Given no environment config is supplied at all (a direct caller)
        When a command is logged
        Then logging is ON -- a log file is created

        TOO-19 m5 regression guard: the no-config default used to be read from
        a legacy CHECKED_BASH_LOGGING_ON environment variable that defaulted to
        "true". That variable is gone; this asserts the removal left the
        default unchanged rather than accidentally switching the audit log off.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

            log_files = list(log_dir.glob("toolguard-*.md"))
            self.assertEqual(
                len(log_files),
                1,
                "Logging must default to ON when no config is supplied",
            )

    def test_legacy_checked_bash_env_vars_are_ignored(self):
        """
        Given the three legacy CHECKED_BASH_* variables are set to values that
            would previously have changed behaviour (logging off, a different
            directory, jsonlines format)
        When a command is logged with no environment config
        Then they are ignored entirely: a markdown log file is still written
            into the default location the caller asked for

        TOO-19 m5: these checked_bash.py-era fallbacks were removed. This test
        is the guard against one being quietly reintroduced.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            other_dir = Path(tmpdir) / "elsewhere"
            other_dir.mkdir()

            with patch.dict(
                "os.environ",
                {
                    "CHECKED_BASH_LOGGING_ON": "false",
                    "CHECKED_BASH_LOGGING_DIR": str(other_dir),
                    "CHECKED_BASH_LOGGING_FORMAT": "jsonlines",
                },
            ):
                log_command(
                    LogRecord(command_str="git status", status="executed"),
                    log_dir=log_dir,
                )

            self.assertEqual(
                len(list(log_dir.glob("toolguard-*.md"))),
                1,
                "CHECKED_BASH_LOGGING_ON/FORMAT must no longer be consulted",
            )
            self.assertEqual(
                len(list(other_dir.glob("toolguard-*"))),
                0,
                "CHECKED_BASH_LOGGING_DIR must no longer be consulted",
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
            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

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

    def test_unrecognised_format_falls_back_to_markdown(self):
        """
        Given an unrecognised log_format value
        When a command is logged
        Then a .md file is created containing markdown, not jsonlines, content
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format="csv",
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename

            self.assertTrue(log_file.exists(), f"{log_file} was not created")
            content = log_file.read_text()
            self.assertIn("**Status**: EXECUTED", content)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(content)

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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

            # Read the log file
            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that violated rules section is not present
            self.assertNotIn(
                "Violated Rules", content, "Violated rules should not be present"
            )

    def test_missing_log_directory_warns_but_does_not_exit(self):
        """
        Given a log directory path that does not exist
        When a command is logged
        Then the call returns normally and reports the missing directory on
             stderr, rather than terminating the process

        Losing an audit record is bad; losing enforcement as well is worse.
        The hook writes its verdict AFTER logging, so a SystemExit here would
        suppress the verdict entirely -- and Claude Code treats only exit
        code 2 as blocking, so the tool call would then proceed unjudged.
        This asserts the failure direction, not the message.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "nonexistent"

            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                log_command(
                    LogRecord(command_str="git status", status="executed"),
                    log_dir=log_dir,
                )

            self.assertIn("Logging directory does not exist", stderr_capture.getvalue())

    def test_missing_log_dir_does_not_block_caller(self):
        """
        Given a log directory path that does not exist (TOO-45)
        When a command is logged
        Then log_command returns normally instead of exiting, warning to stderr

        Superseding contract for test_log_directory_must_exist above: exiting
        the process from the audit path means the tool call proceeds with no
        verdict recorded at all. See _existing_log_dir_or_warn.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "nonexistent"

            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                log_command(
                    LogRecord(command_str="git status", status="executed"),
                    log_dir=log_dir,
                )

            self.assertIn("Logging directory does not exist", stderr_capture.getvalue())

    def test_missing_project_root_does_not_block_caller(self):
        """
        Given no explicit log_dir/config and require_project_root raises RuntimeError
        When a command is logged
        Then log_command returns normally instead of exiting, warning to stderr
        """
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            with patch(
                "toolguard.log_writer.require_project_root",
                side_effect=RuntimeError("no project root"),
            ):
                log_command(LogRecord(command_str="git status", status="executed"))

        self.assertIn("Warning: Failed to write log", stderr_capture.getvalue())


class TestMatchedRuleLogging(unittest.TestCase):
    """Test matched_rule parameter in log entries."""

    def test_matched_rule_in_markdown_format(self):
        """
        Given a command logged with a matched_rule
        When the markdown log is written
        Then it contains a Matched Rule field showing the rule as inline code
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git status", status="executed", matched_rule="git *"
                ),
                log_dir=log_dir,
            )

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
            log_command(
                LogRecord(
                    command_str="git status", status="executed", matched_rule="git *"
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

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
            log_command(
                LogRecord(
                    command_str="rm -rf /", status="refused", violated_rules=["rm *"]
                ),
                log_dir=log_dir,
            )

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
                LogRecord(
                    command_str="git status",
                    status="executed",
                    matched_rule="git *",
                    extra_info="main",
                ),
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
                LogRecord(
                    command_str="git status",
                    status="executed",
                    matched_rule="git *",
                    extra_info="main",
                ),
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


class TestProvenanceLogging(unittest.TestCase):
    """
    TOO-45 R3 follow-up: provenance is its OWN log field, not folded back
    into matched_rule/violated_rules text -- see log_command's provenance
    parameter docstring for why.
    """

    def test_provenance_in_markdown_format_for_allow(self):
        """
        Given an allowed command logged with both matched_rule and provenance
        When the markdown log is written
        Then it contains a Provenance field with the supplied text, separate
            from the Matched Rule field
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git status",
                    status="executed",
                    matched_rule="git *",
                    provenance="project: /p/toolguard_hook.toml",
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("`git *`", content)
            self.assertIn("**Provenance**: project: /p/toolguard_hook.toml", content)

    def test_provenance_in_markdown_format_for_deny(self):
        """
        Given a refused command logged with violated_rules and provenance
        When the markdown log is written
        Then it contains a Provenance field alongside the Violated Rules field
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="rm -rf /tmp/x",
                    status="refused",
                    violated_rules=["rm -rf *"],
                    provenance="project: /p/toolguard_hook.toml",
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("Violated Rules", content)
            self.assertIn("**Provenance**: project: /p/toolguard_hook.toml", content)

    def test_no_provenance_field_for_hard_deny(self):
        """
        Given a refused command logged with violated_rules but NO provenance
            (the hard-deny case -- pooled across levels, no single source)
        When the markdown log is written
        Then it shows Violated Rules but no Provenance field at all
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="curl http://x",
                    status="refused",
                    violated_rules=["curl:*"],
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("Violated Rules", content)
            self.assertNotIn("Provenance", content)

    def test_provenance_in_jsonlines_format(self):
        """
        Given jsonlines format and a command logged with matched_rule and provenance
        When the entry is parsed
        Then its provenance field equals the supplied text
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git status",
                    status="executed",
                    matched_rule="git *",
                    provenance="project: /p/toolguard_hook.toml",
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

            expected_filename = (
                f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
            )
            content = (log_dir / expected_filename).read_text().strip()
            entry = json.loads(content.split("\n")[0])

            self.assertEqual(entry["provenance"], "project: /p/toolguard_hook.toml")

    def test_no_provenance_key_in_jsonlines_when_not_provided(self):
        """
        Given jsonlines format and a command logged without provenance
        When the entry is parsed
        Then it has no provenance key
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git status", status="executed", matched_rule="git *"
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

            expected_filename = (
                f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
            )
            content = (log_dir / expected_filename).read_text().strip()
            entry = json.loads(content.split("\n")[0])

            self.assertNotIn("provenance", entry)

    def test_provenance_ordering_in_markdown(self):
        """
        Given a command logged with matched_rule, provenance, and extra_info
        When the markdown log is written
        Then Provenance appears after Matched Rule and before Agent
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git status",
                    status="executed",
                    matched_rule="git *",
                    provenance="project: /p/toolguard_hook.toml",
                    extra_info="main",
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            matched_pos = content.index("**Matched Rule**")
            provenance_pos = content.index("**Provenance**")
            agent_pos = content.index("**Agent**")

            self.assertLess(
                matched_pos,
                provenance_pos,
                "Provenance should appear after Matched Rule",
            )
            self.assertLess(
                provenance_pos, agent_pos, "Provenance should appear before Agent"
            )

    def test_provenance_ordering_in_markdown_for_deny(self):
        """
        Given a REFUSED command logged with violated_rules, provenance, and
            extra_info (no matched_rule -- the normal deny shape)
        When the markdown log is written
        Then Provenance appears AFTER Violated Rules and before Agent -- it
            describes the violated rule, so it must not render above it
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="rm -rf /tmp/x",
                    status="refused",
                    violated_rules=["rm -rf *"],
                    provenance="project: /p/toolguard_hook.toml",
                    extra_info="main",
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            violated_pos = content.index("**Violated Rules**")
            provenance_pos = content.index("**Provenance**")
            agent_pos = content.index("**Agent**")

            self.assertLess(
                violated_pos,
                provenance_pos,
                "Provenance should appear after Violated Rules",
            )
            self.assertLess(
                provenance_pos, agent_pos, "Provenance should appear before Agent"
            )


class TestPermissionModeLogging(unittest.TestCase):
    """
    Test the permission_mode parameter in log entries (TOO-15: recorded so a
    later investigation can tell whether Claude Code's own mode was a factor
    in what happened to a command after toolguard decided -- never affects
    the decision itself).
    """

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
                LogRecord(
                    command_str="cd /tmp",
                    status="ask",
                    note="no match",
                    permission_mode="default",
                ),
                log_dir=log_dir,
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
            log_command(
                LogRecord(
                    command_str="cd /tmp",
                    status="ask",
                    note="no match",
                    permission_mode="default",
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

            expected_filename = (
                f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
            )
            content = (log_dir / expected_filename).read_text().strip()
            lines = [line for line in content.split("\n") if line.strip()]
            entry = json.loads(lines[0])

            self.assertNotIn("permission_mode", entry)


class TestAdditionalContextLogging(unittest.TestCase):
    """
    Test the additional_context parameter in log entries (TOO-19 Phase 1,
    increment 7: records WHY a matching rule nudged Claude, so "why did Claude
    get this nudge" is answerable after the fact -- capped to a short preview,
    see TestPreviewAdditionalContext, so the log stays scannable).
    """

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
                LogRecord(
                    command_str="git push",
                    status="executed",
                    matched_rule="git *",
                    additional_context="prefer git status --short",
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Context**:", content)
            self.assertIn("prefer git status --short", content)

    def test_long_additional_context_is_logged_in_full(self):
        """
        Given a command logged with a long additional_context text
        When the markdown log is written
        Then the Context field carries the text in full, not a truncated preview
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            long_text = " ".join(f"word{i}" for i in range(100))
            log_command(
                LogRecord(
                    command_str="git push",
                    status="executed",
                    matched_rule="git *",
                    additional_context=long_text,
                ),
                log_dir=log_dir,
            )

            expected_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
            content = (log_dir / expected_filename).read_text()

            self.assertIn("**Context**:", content)
            self.assertIn(long_text, content)
            self.assertNotIn("words total", content)

    def test_additional_context_in_jsonlines_format(self):
        """
        Given jsonlines format and a command logged with an additional_context
        When the entry is parsed
        Then its additional_context field equals the supplied text
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(
                    command_str="git push",
                    status="executed",
                    matched_rule="git *",
                    additional_context="prefer git status --short",
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

            expected_filename = (
                f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.jsonlines"
            )
            content = (log_dir / expected_filename).read_text().strip()
            lines = [line for line in content.split("\n") if line.strip()]
            entry = json.loads(lines[0])

            self.assertEqual(entry["additional_context"], "prefer git status --short")

    def test_no_additional_context_when_not_provided(self):
        """
        Given a command logged without an additional_context
        When the markdown log is written
        Then it contains no Context field
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

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
        """Pin datetime.now() to a fixed instant."""
        self.fixed_now = datetime(2026, 1, 15, 10, 30, 0)
        self.datetime_patcher = patch("toolguard.log_writer.datetime")
        mock_datetime = self.datetime_patcher.start()
        mock_datetime.now.return_value = self.fixed_now

    def tearDown(self):
        """Undo the datetime patch."""
        self.datetime_patcher.stop()

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
                LogRecord(
                    command_str="git push origin main",
                    status="refused",
                    violated_rules=["git push:*", "**/.env/**"],
                    extra_info="main-agent",
                    matched_rule="git push *",
                    note="pushed to protected branch",
                    permission_mode="default",
                    additional_context="be careful",
                ),
                log_dir=log_dir,
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
            log_command(
                LogRecord(command_str="git status", status="executed"), log_dir=log_dir
            )

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
            log_command(
                LogRecord(
                    command_str="git push origin main",
                    status="refused",
                    violated_rules=["git push:*", "**/.env/**"],
                    extra_info="main-agent",
                    matched_rule="git push *",
                    note="pushed to protected branch",
                    permission_mode="default",
                    additional_context="be careful",
                ),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
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
            log_command(
                LogRecord(command_str="git status", status="executed"),
                log_dir=log_dir,
                log_format=LOG_FORMAT_JSONLINES,
            )

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
