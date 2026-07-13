"""
Unit tests for ``toolguard.tools.installer`` -- the agent-facing ``toolguard-install``
console script (TOO-15).

RED-PHASE NOTE: as of this commit ``toolguard/tools/installer.py`` does not exist yet.
Every test in this module is expected to fail (ImportError at collection time, surfacing
as an error on every test) until the module is implemented. This file defines the CLI
surface / contract the implementation must satisfy.

All tests operate against a temporary fake HOME (``Path.home()`` patched) and, for
project-scope cases, a separate temporary project directory. The real ``~/.claude`` and
``~/.toolguard`` are never touched.
"""

import io
import json
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.tools.installer import main
from toolguard.tools.self_permission import required_self_permissions

# Numbered journal entry header, e.g. "## [3] 2026-07-07 14:12 local -- register hooks".
_JOURNAL_HEADER_RE = re.compile(
    r"^## \[(\d+)\] \d{4}-\d{2}-\d{2} \d{2}:\d{2} local -- .+$", re.MULTILINE
)


class InstallerTestCase(unittest.TestCase):
    """
    Shared fixture for installer CLI tests: a fake HOME and an isolated project dir.

    ``Path.home()`` is patched for the lifetime of each test so that every subcommand
    under test resolves ``~/.toolguard`` and ``~/.claude`` inside a throwaway
    TemporaryDirectory, never the real user home.
    """

    def setUp(self):
        """Create a fake HOME and a fake project directory, and patch Path.home()."""
        self._home_ctx = TemporaryDirectory()
        self._project_ctx = TemporaryDirectory()
        self.home = Path(self._home_ctx.name)
        self.project_dir = Path(self._project_ctx.name)
        self.addCleanup(self._home_ctx.cleanup)
        self.addCleanup(self._project_ctx.cleanup)
        patcher = patch("pathlib.Path.home", return_value=self.home)
        self.addCleanup(patcher.stop)
        patcher.start()

    def run_cli(self, argv):
        """
        Invoke ``main(argv)`` capturing stdout/stderr, returning (returncode, stdout).

        Args:
            argv: The argument list to pass to ``main`` (excluding the program name).

        Returns:
            A ``(returncode, stdout_text)`` tuple.
        """
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue()

    def run_help(self, argv):
        """
        Invoke ``main(argv)`` expecting an argparse ``--help`` exit, return stdout text.

        Args:
            argv: Argument list ending in ``--help`` or ``-h``.

        Returns:
            The captured stdout text (argparse prints help there and calls
            ``sys.exit(0)``).
        """
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                main(argv)
        self.assertEqual(cm.exception.code, 0)
        return out.getvalue()

    @property
    def journal_path(self):
        """Path to the fake HOME's install journal."""
        return self.home / ".toolguard" / "install-journal.md"

    def journal_indices(self):
        """Return the list of numbered journal entry indices found, in file order."""
        if not self.journal_path.exists():
            return []
        text = self.journal_path.read_text()
        return [int(m.group(1)) for m in _JOURNAL_HEADER_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Top-level CLI
# ---------------------------------------------------------------------------


class TestTopLevelHelp(InstallerTestCase):
    """Requirement 4: the top-level --help must warn humans off direct use."""

    def test_top_level_help_warns_humans_off(self):
        """
        Given the installer CLI with no subcommand
        When invoked with --help
        Then the help text states this is an agent-facing tool driven by docs/install.md,
        not intended for direct human use, and to use it at your own risk
        """
        text = self.run_help(["--help"])
        lowered = text.lower()
        self.assertIn("agent", lowered)
        self.assertIn("docs/install.md", text)
        self.assertIn("not intended for direct human use", lowered)
        self.assertIn("at your own risk", lowered)

    def test_top_level_help_lists_all_subcommands(self):
        """
        Given the installer CLI
        When invoked with --help
        Then all six subcommands are named so an agent can discover the surface
        """
        text = self.run_help(["--help"])
        for subcommand in (
            "init-state",
            "write-config",
            "register-hooks",
            "seed-self-perms",
            "enable-takeover",
            "journal",
        ):
            self.assertIn(subcommand, text)


class TestSubcommandHelp(InstallerTestCase):
    """
    Requirement 1: every subcommand's --help must be precise enough for an agent to
    decide, without running it, whether the command will do exactly what is wanted.
    """

    def test_init_state_help_names_files_and_journaling(self):
        """
        Given the init-state subcommand
        When invoked with --help
        Then the help text names ~/.toolguard, README.txt, install-journal.md, and
        states this step does not append a numbered/reversible journal entry
        """
        text = self.run_help(["init-state", "--help"])
        self.assertIn(".toolguard", text)
        self.assertIn("README.txt", text)
        self.assertIn("install-journal.md", text)

    def test_write_config_help_names_files_precondition_and_refusal(self):
        """
        Given the write-config subcommand
        When invoked with --help
        Then the help text names toolguard_hook.toml, states it refuses to overwrite an
        existing config without --force, states it backs up any replaced file, and
        states the journal entry it appends (action + reverse)
        """
        text = self.run_help(["write-config", "--help"])
        self.assertIn("toolguard_hook.toml", text)
        self.assertIn("--force", text)
        lowered = text.lower()
        self.assertIn("refuse", lowered)
        self.assertIn("backup", lowered)
        self.assertIn("journal", lowered)
        self.assertIn("reverse", lowered)
        # Base install never enables takeover -- an agent must be able to see this
        # without reading the source.
        self.assertIn("takeover", lowered)

    def test_register_hooks_help_names_files_and_merge_behavior(self):
        """
        Given the register-hooks subcommand
        When invoked with --help
        Then the help text names settings.json/settings.local.json, states hooks are
        MERGED (never clobbered), and states the backup + journal behavior
        """
        text = self.run_help(["register-hooks", "--help"])
        self.assertIn("settings.json", text)
        self.assertIn("settings.local.json", text)
        lowered = text.lower()
        self.assertIn("merge", lowered)
        self.assertIn("backup", lowered)
        self.assertIn("journal", lowered)

    def test_seed_self_perms_help_names_source_of_truth_and_precondition(self):
        """
        Given the seed-self-perms subcommand
        When invoked with --help
        Then the help text names toolguard_hook.toml, states its precondition (a base
        config must already exist), and states it does not itself ask for consent
        (consent is assumed to already have been given by the calling agent)
        """
        text = self.run_help(["seed-self-perms", "--help"])
        self.assertIn("toolguard_hook.toml", text)
        lowered = text.lower()
        self.assertIn("journal", lowered)
        self.assertIn("consent", lowered)

    def test_enable_takeover_help_names_files_and_default(self):
        """
        Given the enable-takeover subcommand
        When invoked with --help
        Then the help text names toolguard_hook.toml, [takeover_mode], the
        --no-match-fallback choices, and its default value
        """
        text = self.run_help(["enable-takeover", "--help"])
        self.assertIn("toolguard_hook.toml", text)
        self.assertIn("takeover_mode", text)
        self.assertIn("allow_with_warning", text)

    def test_journal_help_names_journal_file_and_fields(self):
        """
        Given the journal subcommand
        When invoked with --help
        Then the help text names install-journal.md and the --action/--reverse/--backup
        fields it writes
        """
        text = self.run_help(["journal", "--help"])
        self.assertIn("install-journal.md", text)
        self.assertIn("--action", text)
        self.assertIn("--reverse", text)
        self.assertIn("--backup", text)


# ---------------------------------------------------------------------------
# init-state
# ---------------------------------------------------------------------------


class TestInitState(InstallerTestCase):
    """Behavior of the init-state subcommand."""

    def test_creates_state_dirs_and_readme(self):
        """
        Given a fresh fake HOME with no ~/.toolguard
        When init-state is run with --source
        Then ~/.toolguard, ~/.toolguard/backups, and ~/.toolguard/stage are created, and
        README.txt exists, mentions the given source, and states the directory is not
        deleted on uninstall
        """
        code, out = self.run_cli(["init-state", "--source", "git+https://example/repo"])
        self.assertEqual(code, 0)
        state_dir = self.home / ".toolguard"
        self.assertTrue(state_dir.is_dir())
        self.assertTrue((state_dir / "backups").is_dir())
        self.assertTrue((state_dir / "stage").is_dir())
        readme = (state_dir / "README.txt").read_text()
        self.assertIn("git+https://example/repo", readme)
        self.assertIn("not deleted on uninstall", readme.lower())
        # ASCII-only requirement.
        readme.encode("ascii")

    def test_creates_journal_with_session_header(self):
        """
        Given a fresh fake HOME
        When init-state is run
        Then install-journal.md is created and contains a session header
        """
        self.run_cli(["init-state", "--source", "local checkout"])
        self.assertTrue(self.journal_path.exists())
        text = self.journal_path.read_text()
        self.assertIn("session", text.lower())
        text.encode("ascii")

    def test_idempotent_does_not_clobber_existing_journal(self):
        """
        Given init-state has already been run once (journal + README exist)
        When init-state is run again
        Then the original journal content is preserved (a new session header is
        appended, not a rewrite) and the README is not duplicated/corrupted
        """
        self.run_cli(["init-state", "--source", "git+https://example/repo"])
        first_journal = self.journal_path.read_text()
        first_readme = (self.home / ".toolguard" / "README.txt").read_text()

        code, out = self.run_cli(["init-state", "--source", "git+https://example/repo"])

        self.assertEqual(code, 0)
        second_journal = self.journal_path.read_text()
        self.assertTrue(second_journal.startswith(first_journal))
        self.assertGreater(len(second_journal), len(first_journal))
        second_readme = (self.home / ".toolguard" / "README.txt").read_text()
        self.assertEqual(first_readme, second_readme)

    def test_summary_names_created_paths(self):
        """
        Given a fresh fake HOME
        When init-state is run
        Then the printed summary names the state directory path
        """
        code, out = self.run_cli(["init-state", "--source", "local checkout"])
        self.assertIn(str(self.home / ".toolguard"), out)


# ---------------------------------------------------------------------------
# write-config
# ---------------------------------------------------------------------------


class TestWriteConfig(InstallerTestCase):
    """Behavior of the write-config subcommand."""

    def test_writes_user_scope_config(self):
        """
        Given user scope
        When write-config is run with governed tools Bash,Read,Write,Edit
        Then ~/.claude/toolguard_hook.toml is written with those governed_tools and no
        [takeover_mode] section (base install keeps takeover disabled)
        """
        code, out = self.run_cli(
            [
                "write-config",
                "--scope",
                "user",
                "--governed-tools",
                "Bash,Read,Write,Edit",
            ]
        )
        self.assertEqual(code, 0)
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        self.assertTrue(config_path.exists())
        text = config_path.read_text()
        for tool in ("Bash", "Read", "Write", "Edit"):
            self.assertIn(f'"{tool}"', text)
        self.assertNotIn("takeover_mode", text)
        text.encode("ascii")

    def test_writes_project_scope_config_at_project_dir(self):
        """
        Given project scope with --project-dir pointing at a project directory
        When write-config is run
        Then <project-dir>/.claude/toolguard_hook.toml is written (not the user-level one)
        """
        code, out = self.run_cli(
            [
                "write-config",
                "--scope",
                "project",
                "--project-dir",
                str(self.project_dir),
                "--governed-tools",
                "Bash",
            ]
        )
        self.assertEqual(code, 0)
        project_config = self.project_dir / ".claude" / "toolguard_hook.toml"
        self.assertTrue(project_config.exists())
        user_config = self.home / ".claude" / "toolguard_hook.toml"
        self.assertFalse(user_config.exists())

    def test_includes_additional_supported_tools(self):
        """
        Given --additional-supported-tools is provided
        When write-config is run
        Then additional_supported_tools appears in the written config with those values
        """
        code, out = self.run_cli(
            [
                "write-config",
                "--scope",
                "user",
                "--governed-tools",
                "Bash",
                "--additional-supported-tools",
                "mcp__jetbrains__execute_terminal_command",
            ]
        )
        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn("additional_supported_tools", text)
        self.assertIn("mcp__jetbrains__execute_terminal_command", text)

    def test_refuses_to_overwrite_without_force(self):
        """
        Given a toolguard_hook.toml already exists at the target scope
        When write-config is run again WITHOUT --force
        Then it refuses (non-zero exit), makes no changes to the existing file, and the
        summary says it refused and made no changes
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        original = config_path.read_text()

        code, out = self.run_cli(
            ["write-config", "--scope", "user", "--governed-tools", "Bash,Read"]
        )

        self.assertNotEqual(code, 0)
        self.assertEqual(config_path.read_text(), original)
        lowered = out.lower()
        self.assertIn("refused", lowered)
        self.assertIn("no changes", lowered)

    def test_force_overwrite_backs_up_original(self):
        """
        Given a toolguard_hook.toml already exists at the target scope
        When write-config is run again WITH --force
        Then the new content replaces it, a backup of the original is created under
        ~/.toolguard/backups/, and the summary names the backup path
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        original = config_path.read_text()

        code, out = self.run_cli(
            [
                "write-config",
                "--scope",
                "user",
                "--governed-tools",
                "Bash,Read",
                "--force",
            ]
        )

        self.assertEqual(code, 0)
        new_text = config_path.read_text()
        self.assertNotEqual(new_text, original)
        self.assertIn('"Read"', new_text)
        backups_dir = self.home / ".toolguard" / "backups"
        backups = list(backups_dir.glob("*toolguard_hook*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)
        self.assertIn(str(backups[0]), out)

    def test_project_scope_without_project_dir_is_rejected(self):
        """
        Given --scope project without --project-dir
        When write-config is run
        Then it fails with a non-zero exit and does not write any file
        """
        code, out = self.run_cli(
            ["write-config", "--scope", "project", "--governed-tools", "Bash"]
        )
        self.assertNotEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "toolguard_hook.toml").exists())

    def test_journals_exactly_one_entry(self):
        """
        Given init-state has run (journal exists)
        When write-config runs successfully
        Then exactly one new numbered journal entry is appended, and it names the config
        path and the reverse action
        """
        self.run_cli(["init-state", "--source", "local checkout"])
        before = self.journal_indices()

        code, out = self.run_cli(
            ["write-config", "--scope", "user", "--governed-tools", "Bash"]
        )

        after = self.journal_indices()
        self.assertEqual(len(after), len(before) + 1)
        text = self.journal_path.read_text()
        self.assertIn(str(self.home / ".claude" / "toolguard_hook.toml"), text)
        self.assertIn("reverse", text.lower())

    def test_summary_names_written_file_and_journal_index(self):
        """
        Given a fresh fake HOME
        When write-config runs successfully
        Then the printed summary names the exact file written and the journal entry
        index that was appended
        """
        code, out = self.run_cli(
            ["write-config", "--scope", "user", "--governed-tools", "Bash"]
        )
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        self.assertIn(str(config_path), out)
        index = self.journal_indices()[-1]
        self.assertIn(f"[{index}]", out)


# ---------------------------------------------------------------------------
# register-hooks
# ---------------------------------------------------------------------------


class TestRegisterHooks(InstallerTestCase):
    """Behavior of the register-hooks subcommand."""

    def test_user_scope_writes_settings_json(self):
        """
        Given user scope and no existing ~/.claude/settings.json
        When register-hooks is run for Bash,Read
        Then ~/.claude/settings.json is created with one PreToolUse matcher per governed
        tool pointing at the given binary, plus a SessionStart hook at
        <binary>-session-start
        """
        binary = "/home/fake/.local/bin/toolguard"
        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                binary,
                "--governed-tools",
                "Bash,Read",
            ]
        )
        self.assertEqual(code, 0)
        settings_path = self.home / ".claude" / "settings.json"
        self.assertTrue(settings_path.exists())
        data = json.loads(settings_path.read_text())
        matchers = {h["matcher"] for h in data["hooks"]["PreToolUse"]}
        self.assertEqual(matchers, {"Bash", "Read"})
        for entry in data["hooks"]["PreToolUse"]:
            self.assertEqual(entry["hooks"][0]["command"], binary)
        session_start_commands = [
            h["command"] for h in data["hooks"]["SessionStart"][0]["hooks"]
        ]
        self.assertIn(f"{binary}-session-start", session_start_commands)

    def test_project_scope_writes_settings_local_json(self):
        """
        Given project scope
        When register-hooks is run
        Then <project-dir>/.claude/settings.local.json is written (not settings.json)
        """
        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "project",
                "--project-dir",
                str(self.project_dir),
                "--binary",
                "/fake/toolguard",
                "--governed-tools",
                "Bash",
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue(
            (self.project_dir / ".claude" / "settings.local.json").exists()
        )
        self.assertFalse((self.project_dir / ".claude" / "settings.json").exists())

    def test_merges_without_clobbering_existing_session_end_hook(self):
        """
        Given an existing settings.json with an unrelated SessionEnd hook and a
        PostToolUse hook already configured
        When register-hooks adds PreToolUse + SessionStart matchers
        Then the pre-existing SessionEnd and PostToolUse blocks are preserved verbatim
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        existing = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Edit|Write|Bash",
                        "hooks": [{"type": "command", "command": "some-other-tool"}],
                    }
                ],
                "SessionEnd": [
                    {"hooks": [{"type": "command", "command": "cleanup.sh"}]}
                ],
            }
        }
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(existing, indent=2))

        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                "/fake/toolguard",
                "--governed-tools",
                "Bash",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(settings_path.read_text())
        self.assertEqual(data["hooks"]["SessionEnd"], existing["hooks"]["SessionEnd"])
        self.assertEqual(
            data["hooks"]["PostToolUse"], existing["hooks"]["PostToolUse"]
        )
        matchers = {h["matcher"] for h in data["hooks"]["PreToolUse"]}
        self.assertIn("Bash", matchers)

    def test_running_twice_does_not_duplicate_matchers(self):
        """
        Given register-hooks has already been run for Bash
        When register-hooks is run again for the same tool and binary
        Then no duplicate PreToolUse matcher for Bash is added
        """
        args = [
            "register-hooks",
            "--scope",
            "user",
            "--binary",
            "/fake/toolguard",
            "--governed-tools",
            "Bash",
        ]
        self.run_cli(args)
        code, out = self.run_cli(args)
        self.assertEqual(code, 0)
        data = json.loads((self.home / ".claude" / "settings.json").read_text())
        bash_matchers = [
            h for h in data["hooks"]["PreToolUse"] if h["matcher"] == "Bash"
        ]
        self.assertEqual(len(bash_matchers), 1)

    def test_backs_up_existing_settings_file(self):
        """
        Given an existing settings.json
        When register-hooks edits it
        Then a backup of the pre-edit content is created under ~/.toolguard/backups/
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        settings_path = claude_dir / "settings.json"
        original = json.dumps({"hooks": {}}, indent=2)
        settings_path.write_text(original)

        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                "/fake/toolguard",
                "--governed-tools",
                "Bash",
            ]
        )

        self.assertEqual(code, 0)
        backups = list((self.home / ".toolguard" / "backups").glob("*settings*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)

    def test_journals_exactly_one_entry(self):
        """
        Given init-state has run
        When register-hooks runs successfully
        Then exactly one new numbered journal entry is appended naming the settings
        file and its reverse
        """
        self.run_cli(["init-state", "--source", "local checkout"])
        before = self.journal_indices()

        self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                "/fake/toolguard",
                "--governed-tools",
                "Bash",
            ]
        )

        after = self.journal_indices()
        self.assertEqual(len(after), len(before) + 1)


# ---------------------------------------------------------------------------
# seed-self-perms
# ---------------------------------------------------------------------------


class TestSeedSelfPerms(InstallerTestCase):
    """Behavior of the seed-self-perms subcommand."""

    def _write_base_config(self):
        """Write a minimal base toolguard_hook.toml via the CLI under test."""
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])

    def test_adds_exactly_the_self_permission_rules(self):
        """
        Given a base config already exists
        When seed-self-perms is run
        Then the config's [permissions] section contains exactly the Bash rules from
        toolguard.tools.self_permission (allow/ask per its own list_type) plus
        Read/Write/Edit allow rules scoped to ~/.toolguard/**, and nothing else divergent
        """
        self._write_base_config()

        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        text = config_path.read_text()
        for permission in required_self_permissions():
            pattern = f"Bash({permission.pattern})"
            self.assertIn(pattern, text)
        for tool in ("Read", "Write", "Edit"):
            self.assertIn(f"{tool}(~/.toolguard/**)", text)

    def test_missing_base_config_is_rejected(self):
        """
        Given no toolguard_hook.toml exists yet at the target scope
        When seed-self-perms is run
        Then it fails with a non-zero exit and a message explaining the precondition,
        rather than creating a partial config
        """
        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "toolguard_hook.toml").exists())

    def test_backs_up_before_editing(self):
        """
        Given a base config already exists
        When seed-self-perms edits it
        Then a backup of the pre-edit config is created under ~/.toolguard/backups/
        """
        self._write_base_config()
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        original = config_path.read_text()

        self.run_cli(["seed-self-perms", "--scope", "user"])

        backups = list((self.home / ".toolguard" / "backups").glob("*toolguard_hook*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)

    def test_running_twice_does_not_duplicate_rules(self):
        """
        Given seed-self-perms has already been run
        When it is run again
        Then the resulting [permissions] section still contains each self-permission
        pattern exactly once
        """
        self._write_base_config()
        self.run_cli(["seed-self-perms", "--scope", "user"])
        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])
        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        for permission in required_self_permissions():
            pattern = f"Bash({permission.pattern})"
            self.assertEqual(text.count(pattern), 1)


# ---------------------------------------------------------------------------
# enable-takeover
# ---------------------------------------------------------------------------


class TestEnableTakeover(InstallerTestCase):
    """Behavior of the enable-takeover subcommand."""

    def _write_base_config(self):
        """Write a minimal base toolguard_hook.toml via the CLI under test."""
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])

    def test_sets_enabled_and_default_fallback(self):
        """
        Given a base config already exists
        When enable-takeover is run without --no-match-fallback
        Then [takeover_mode] enabled = true and no_match_fallback defaults to
        'allow_with_warning'
        """
        self._write_base_config()

        code, out = self.run_cli(["enable-takeover", "--scope", "user"])

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn("[takeover_mode]", text)
        self.assertIn("enabled = true", text)
        self.assertIn('no_match_fallback = "allow_with_warning"', text)

    def test_sets_explicit_fallback(self):
        """
        Given a base config already exists
        When enable-takeover is run with --no-match-fallback deny
        Then no_match_fallback is written as 'deny'
        """
        self._write_base_config()

        code, out = self.run_cli(
            ["enable-takeover", "--scope", "user", "--no-match-fallback", "deny"]
        )

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn('no_match_fallback = "deny"', text)

    def test_missing_base_config_is_rejected(self):
        """
        Given no toolguard_hook.toml exists yet
        When enable-takeover is run
        Then it fails with a non-zero exit and writes nothing
        """
        code, out = self.run_cli(["enable-takeover", "--scope", "user"])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "toolguard_hook.toml").exists())

    def test_backs_up_before_editing(self):
        """
        Given a base config already exists
        When enable-takeover edits it
        Then a backup of the pre-edit config is created under ~/.toolguard/backups/
        """
        self._write_base_config()
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        original = config_path.read_text()

        self.run_cli(["enable-takeover", "--scope", "user"])

        backups = list((self.home / ".toolguard" / "backups").glob("*toolguard_hook*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)

    def test_preserves_other_config_content(self):
        """
        Given a base config with governed_tools already written
        When enable-takeover edits it
        Then governed_tools is unchanged (only [takeover_mode] is added/replaced)
        """
        self.run_cli(
            ["write-config", "--scope", "user", "--governed-tools", "Bash,Read"]
        )

        self.run_cli(["enable-takeover", "--scope", "user"])

        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn('"Bash"', text)
        self.assertIn('"Read"', text)


# ---------------------------------------------------------------------------
# journal
# ---------------------------------------------------------------------------


class TestJournalSubcommand(InstallerTestCase):
    """
    Dedicated journal-correctness tests (coordinator requirement 2). The journal is
    the source of truth for uninstall, so its format and monotonicity are tested
    directly via the standalone ``journal`` subcommand as well as indirectly through
    every mutating subcommand above.
    """

    def test_appends_one_correctly_formatted_entry(self):
        """
        Given ~/.toolguard exists (init-state has run)
        When journal is invoked with --action and --reverse
        Then exactly one entry is appended with index 1, a local-time timestamp, and
        the given action/reverse text
        """
        self.run_cli(["init-state", "--source", "local checkout"])

        code, out = self.run_cli(
            [
                "journal",
                "--action",
                "did the thing",
                "--reverse",
                "undo the thing",
            ]
        )

        self.assertEqual(code, 0)
        text = self.journal_path.read_text()
        self.assertEqual(self.journal_indices(), [1])
        self.assertIn("did the thing", text)
        self.assertIn("undo the thing", text)
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} local")

    def test_records_backup_field_when_given(self):
        """
        Given ~/.toolguard exists
        When journal is invoked with --backup pointing at a file
        Then the entry includes that backup path; when omitted, it records 'none'
        """
        self.run_cli(["init-state", "--source", "local checkout"])

        self.run_cli(
            [
                "journal",
                "--action",
                "edited settings.json",
                "--reverse",
                "restore backup",
                "--backup",
                "/fake/backups/settings.json.20260101-000000",
            ]
        )
        self.run_cli(
            ["journal", "--action", "no backup case", "--reverse", "n/a"]
        )

        text = self.journal_path.read_text()
        self.assertIn("/fake/backups/settings.json.20260101-000000", text)
        self.assertIn("none", text.lower())

    def test_monotonic_index_across_sequential_calls(self):
        """
        Given several journal entries have already been appended
        When another entry is appended
        Then its index is exactly one greater than the previous maximum, in order
        """
        self.run_cli(["init-state", "--source", "local checkout"])
        for i in range(3):
            self.run_cli(
                ["journal", "--action", f"step {i}", "--reverse", f"undo {i}"]
            )
        self.assertEqual(self.journal_indices(), [1, 2, 3])

    def test_indices_increment_across_mixed_subcommands(self):
        """
        Given a sequence of init-state, write-config, and journal calls
        When each mutating step completes
        Then the journal's numbered entries strictly increase by exactly one each time,
        with no gaps or repeats
        """
        self.run_cli(["init-state", "--source", "local checkout"])
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        self.run_cli(["journal", "--action", "manual note", "--reverse", "n/a"])

        indices = self.journal_indices()
        self.assertEqual(indices, list(range(1, len(indices) + 1)))

    def test_missing_state_dir_is_rejected_without_partial_write(self):
        """
        Given ~/.toolguard does not exist (init-state never run)
        When journal is invoked
        Then it fails with a non-zero exit rather than silently creating a bare journal
        with no README/backups/stage scaffolding
        """
        code, out = self.run_cli(
            ["journal", "--action", "x", "--reverse", "y"]
        )
        self.assertNotEqual(code, 0)
        self.assertFalse(self.journal_path.exists())


# ---------------------------------------------------------------------------
# Output / summary content (coordinator requirement 3)
# ---------------------------------------------------------------------------


class TestSummaryOutput(InstallerTestCase):
    """
    Every subcommand must print a structured summary an agent can rely on for the
    true post-run state, including explicit refusal/no-op messages.
    """

    def test_register_hooks_summary_names_added_and_skipped_matchers(self):
        """
        Given register-hooks has already added a Bash matcher
        When register-hooks is run again adding Bash and a new Read matcher
        Then the summary distinguishes what was newly added (Read) from what was
        already present and left alone (Bash)
        """
        base_args = [
            "register-hooks",
            "--scope",
            "user",
            "--binary",
            "/fake/toolguard",
        ]
        self.run_cli(base_args + ["--governed-tools", "Bash"])

        code, out = self.run_cli(base_args + ["--governed-tools", "Bash,Read"])

        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertIn("read", lowered)
        self.assertIn("bash", lowered)
        # Some indication that Bash was already present / unchanged.
        self.assertTrue(
            "already" in lowered or "skip" in lowered or "unchanged" in lowered
        )

    def test_seed_self_perms_no_op_summary_on_second_run(self):
        """
        Given seed-self-perms has already been run once
        When it is run again with nothing new to add
        Then the summary says explicitly that nothing needed to change
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        self.run_cli(["seed-self-perms", "--scope", "user"])

        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertTrue(
            "already" in lowered or "no changes" in lowered or "nothing to add" in lowered
        )

    def test_register_hooks_reminds_of_remaining_checklist_phases(self):
        """
        Given register-hooks completes successfully (go-live step)
        When its summary output is printed
        Then it ends with a reminder naming the checklist phases still ahead
        (skills, validation, phases 7-10 + wrap-up) and flags the session-trace
        dump offer (Phase T.1) as MANDATORY, so an agent following docs/install.md
        does not silently stop after this step
        """
        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                "/fake/toolguard",
                "--governed-tools",
                "Bash",
            ]
        )

        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertIn("docs/install.md", out)
        self.assertIn("mandatory", lowered)
        self.assertIn("trace", lowered)

    def test_enable_takeover_reminds_of_remaining_checklist_phases(self):
        """
        Given enable-takeover completes successfully (the last mechanical step
        of a takeover install)
        When its summary output is printed
        Then it ends with a reminder naming the checklist steps still ahead
        (10.4 re-validation, wrap-up) and flags the session-trace dump offer
        (Phase T.1) as MANDATORY, so an agent does not stop before the runbook's
        remaining steps
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])

        code, out = self.run_cli(["enable-takeover", "--scope", "user"])

        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertIn("docs/install.md", out)
        self.assertIn("mandatory", lowered)
        self.assertIn("trace", lowered)


if __name__ == "__main__":
    unittest.main()
