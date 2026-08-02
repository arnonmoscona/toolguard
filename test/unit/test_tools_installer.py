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
import os
import re
import shlex
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools import installer as installer_module
from toolguard.tools.decision import decide
from toolguard.tools.installer import main
from toolguard.tools.self_integrity import required_self_integrity_hard_deny_patterns
from toolguard.tools.self_permission import required_self_permissions
from toolguard.tools.uninstall_readiness import required_uninstall_readiness_permissions
from toolguard.update_check import InstallInfo, InstallKind

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
        Then all nine subcommands are named so an agent can discover the surface
        """
        text = self.run_help(["--help"])
        for subcommand in (
            "init-state",
            "write-config",
            "register-hooks",
            "seed-self-perms",
            "enable-takeover",
            "journal",
            "discover-projects",
            "install-skills",
            "seed-hard-deny",
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

    def test_discover_projects_help_names_sources_and_readonly(self):
        """
        Given the discover-projects subcommand
        When invoked with --help
        Then the help text names ~/.claude.json and ~/.claude/projects as its sources,
        states it is read-only (no backup/journal), and names --format
        """
        text = self.run_help(["discover-projects", "--help"])
        self.assertIn(".claude.json", text)
        self.assertIn(".claude/projects", text)
        self.assertIn("--format", text)
        lowered = text.lower()
        self.assertIn("read-only", lowered)

    def test_install_skills_help_names_targets_and_idempotency(self):
        """
        Given the install-skills subcommand
        When invoked with --help
        Then the help text names the two skill directories, states installation is
        idempotent unless --force is given, and states backup + journal behavior
        """
        text = self.run_help(["install-skills", "--help"])
        self.assertIn("toolguard-security-audit", text)
        self.assertIn("toolguard-maintenance", text)
        self.assertIn("--force", text)
        lowered = text.lower()
        self.assertIn("idempotent", lowered)
        self.assertIn("backup", lowered)
        self.assertIn("journal", lowered)

    def test_seed_hard_deny_help_names_source_of_truth_and_precondition(self):
        """
        Given the seed-hard-deny subcommand
        When invoked with --help
        Then the help text names toolguard_hook.toml, [hard_deny], states its
        precondition (a base config must already exist), and states it does not
        itself ask for consent (consent is assumed to already have been given)
        """
        text = self.run_help(["seed-hard-deny", "--help"])
        self.assertIn("toolguard_hook.toml", text)
        self.assertIn("hard_deny", text)
        lowered = text.lower()
        self.assertIn("journal", lowered)
        self.assertIn("consent", lowered)


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
# PreToolUse hook hardening helpers (TOO-19)
# ---------------------------------------------------------------------------


def _make_fake_venv_bin(tmpdir: Path, python_name="python3", executable=True):
    """
    Build a fake ``<tmpdir>/bin/toolguard`` console script plus a
    ``<tmpdir>/bin/<python_name>`` sibling, mirroring a real venv's ``bin/``
    layout. Returns the console-script path.
    """
    bin_dir = tmpdir / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "toolguard"
    binary.write_text("#!/bin/sh\n")
    python_path = bin_dir / python_name
    python_path.write_text("#!/bin/sh\n")
    if executable:
        os.chmod(python_path, 0o755)
    return binary


def _make_fake_venv_bin_with_space(tmpdir: Path, space_dirname: str) -> Path:
    """
    Build a fake ``<tmpdir>/<space_dirname>/bin/toolguard`` console script plus
    an executable ``python3`` sibling, where *space_dirname* (a directory
    component containing a literal space, e.g. a relocated venv or a macOS
    path under a directory with a space) sits between *tmpdir* and ``bin/`` --
    mirroring the TOO-19 code review M2 repro scenario. Returns the
    console-script path.
    """
    bin_dir = tmpdir / space_dirname / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "toolguard"
    binary.write_text("#!/bin/sh\n")
    python_path = bin_dir / "python3"
    python_path.write_text("#!/bin/sh\n")
    os.chmod(python_path, 0o755)
    return binary


class TestToolVenvPython(unittest.TestCase):
    """Tests for installer_module._tool_venv_python."""

    def test_finds_python3_sibling(self):
        """
        Given a binary path whose real bin/ directory has an executable python3
        When _tool_venv_python runs
        Then it returns that sibling's absolute path
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin(Path(d), python_name="python3")
            result = installer_module._tool_venv_python(str(binary))
            self.assertEqual(Path(result).name, "python3")
            self.assertTrue(Path(result).exists())

    def test_falls_back_to_plain_python_sibling(self):
        """
        Given a binary path whose bin/ directory has only 'python' (no 'python3')
        When _tool_venv_python runs
        Then it returns the 'python' sibling
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin(Path(d), python_name="python")
            result = installer_module._tool_venv_python(str(binary))
        self.assertEqual(Path(result).name, "python")

    def test_no_sibling_python_returns_none(self):
        """
        Given a binary path whose bin/ directory has no python/python3 sibling
        When _tool_venv_python runs
        Then it returns None -- never a guess
        """
        with TemporaryDirectory() as d:
            bin_dir = Path(d) / "bin"
            bin_dir.mkdir()
            binary = bin_dir / "toolguard"
            binary.write_text("#!/bin/sh\n")
            self.assertIsNone(installer_module._tool_venv_python(str(binary)))

    def test_non_executable_sibling_is_not_used(self):
        """
        Given a python3 sibling exists but is NOT executable, and no other
        candidate exists
        When _tool_venv_python runs
        Then it returns None rather than an unusable path
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin(
                Path(d), python_name="python3", executable=False
            )
            self.assertIsNone(installer_module._tool_venv_python(str(binary)))

    def test_nonexistent_binary_path_returns_none(self):
        """
        Given a --binary path that does not exist on disk at all (e.g. a test
        fixture's fake path, or a broken installation)
        When _tool_venv_python runs
        Then it returns None -- never a guess, never raises
        """
        self.assertIsNone(
            installer_module._tool_venv_python("/definitely/does/not/exist/toolguard")
        )


class TestHardenedHookCommand(unittest.TestCase):
    """Tests for installer_module._hardened_hook_command."""

    def test_hardened_form_when_venv_python_is_found(self):
        """
        Given a binary whose bin/ directory has an executable python3 sibling
        When _hardened_hook_command runs
        Then it returns the '-E -P -m toolguard.hook' form and hardened=True
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin(Path(d))
            command, hardened = installer_module._hardened_hook_command(str(binary))
        self.assertTrue(hardened)
        self.assertIn("-E -P -m toolguard.hook", command)
        self.assertTrue(command.endswith("-E -P -m toolguard.hook"))

    def test_falls_back_to_bare_binary_when_venv_python_not_found(self):
        """
        Given a binary with no locatable venv python (e.g. a test fixture's
        fake, nonexistent path)
        When _hardened_hook_command runs
        Then it returns the bare binary path unchanged and hardened=False
        """
        command, hardened = installer_module._hardened_hook_command("/fake/toolguard")
        self.assertFalse(hardened)
        self.assertEqual(command, "/fake/toolguard")


class TestHardenedHookCommandSpacePathQuoting(unittest.TestCase):
    """
    TOO-19 code review 2026-08-02, Major finding M2: the hardened hook
    command was written unquoted into a shell string; a space in the
    interpreter path produced the exact silent fail-open the hardening
    exists to prevent.

    Given an interpreter path containing a space,
    ``_hardened_hook_command`` must write it QUOTED, and
    ``_hook_registration_findings`` must parse it back correctly,
    round-tripping through the exact JSON-embedded-shell-string path Claude
    Code uses.
    """

    def test_hardened_command_quotes_a_space_containing_interpreter_path(self):
        """
        Given a venv python sibling under a directory with a space in its name
        When _hardened_hook_command builds the registration command
        Then the interpreter path is shell-quoted (shlex.split recovers
            exactly one token for it, not two) and marked hardened
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin_with_space(Path(d), "my venv")
            command, hardened = installer_module._hardened_hook_command(str(binary))

        self.assertTrue(hardened)
        tokens = shlex.split(command)
        # If the path were written unquoted, shlex.split (and, in real use, the
        # shell Claude Code hands the command to) would split "my venv" into
        # TWO argv words and the launch would fail -- exactly the fail-open
        # M2 describes. Quoted, it recovers as ONE token ending in bin/python3.
        self.assertTrue(tokens[0].endswith("bin/python3"))
        self.assertIn("my venv", tokens[0])
        self.assertEqual(tokens[1:], ["-E", "-P", "-m", "toolguard.hook"])

    def test_hardened_command_build_then_parse_round_trips_for_space_path(self):
        """
        Given the exact command string _hardened_hook_command wrote for a
            space-containing interpreter path
        When _hook_registration_findings parses a settings.json containing
            that command back
        Then it reports hardened=True and interpreter_missing=False -- NOT a
            false "BROKEN" diagnostic from misreading the quoted path as two
            tokens (M2's second half: register-hooks quotes it, but a naive
            command.split()[0] on read-back would still misdiagnose it)
        """
        with TemporaryDirectory() as d:
            binary = _make_fake_venv_bin_with_space(Path(d), "my venv")
            command, hardened = installer_module._hardened_hook_command(str(binary))
            self.assertTrue(hardened)

            settings_path = Path(d) / "settings.json"
            settings_path.write_text(
                '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": '
                '[{"type": "command", "command": %s}]}]}}' % json.dumps(command)
            )
            findings = installer_module._hook_registration_findings(settings_path)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertTrue(finding["hardened"])
        self.assertFalse(
            finding["interpreter_missing"],
            "quoted space-containing interpreter path misread as missing "
            "(a false BROKEN diagnostic) -- M2 regressed",
        )

    def test_findings_still_flags_a_genuinely_missing_interpreter(self):
        """
        Given a hardened command naming an interpreter path that does NOT
            exist on disk (space in the path, but the venv was removed)
        When _hook_registration_findings runs
        Then interpreter_missing is True -- the M2 fix must not silently
            swallow a REAL broken-hook diagnostic while fixing the false one
        """
        with TemporaryDirectory() as d:
            missing_path = str(Path(d) / "my venv" / "bin" / "python3")
            command = f"{shlex.quote(missing_path)} -E -P -m toolguard.hook"
            settings_path = Path(d) / "settings.json"
            settings_path.write_text(
                '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": '
                '[{"type": "command", "command": %s}]}]}}' % json.dumps(command)
            )
            findings = installer_module._hook_registration_findings(settings_path)

        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["interpreter_missing"])


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
        self.assertTrue((self.project_dir / ".claude" / "settings.local.json").exists())
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
        self.assertEqual(data["hooks"]["PostToolUse"], existing["hooks"]["PostToolUse"])
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

    def test_hardened_form_registered_when_venv_python_is_locatable(self):
        """
        TOO-19: Given --binary points at a real console-script whose bin/
            directory has an executable python3 sibling (a real venv shape)
        When register-hooks runs
        Then the registered PreToolUse command is the hardened
        '<python3> -E -P -m toolguard.hook' form, NOT the bare binary
        """
        binary = _make_fake_venv_bin(self.home / "fakevenv")
        code, out = self.run_cli(
            [
                "register-hooks",
                "--scope",
                "user",
                "--binary",
                str(binary),
                "--governed-tools",
                "Bash",
            ]
        )
        self.assertEqual(code, 0)
        data = json.loads((self.home / ".claude" / "settings.json").read_text())
        command = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertTrue(command.endswith("-E -P -m toolguard.hook"))
        self.assertNotEqual(command, str(binary))
        self.assertIn("hardened", out)

    def test_unhardened_fallback_when_venv_python_not_locatable(self):
        """
        TOO-19: Given --binary is a fake path with no locatable venv python
            (the existing fixture shape used throughout this test class)
        When register-hooks runs
        Then the registered PreToolUse command is the bare --binary path,
        UNCHANGED -- confirms the fallback keeps a working (if unhardened)
        registration instead of writing an unverified interpreter path
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
        data = json.loads((self.home / ".claude" / "settings.json").read_text())
        command = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertEqual(command, "/fake/toolguard")
        self.assertIn("UNHARDENED", out)


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
        Then the config's [permissions] section contains the Bash rules from
        toolguard.tools.self_permission (allow/ask per its own list_type) and
        Read/Write/Edit allow rules scoped to ~/.toolguard/** (uninstall-readiness
        rules are covered separately, see test_adds_the_uninstall_readiness_rules)
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

    def test_adds_the_uninstall_readiness_rules(self):
        """
        Given a base config already exists at user scope
        When seed-self-perms is run
        Then the config's [permissions] section also contains every rule from
        toolguard.tools.uninstall_readiness, scoped to the fake HOME's own
        ~/.claude directory and settings.json -- seeded now (Phase 4, before
        takeover is ever enabled) so a later uninstall never hits a hard block
        """
        self._write_base_config()

        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        text = config_path.read_text()
        claude_dir = self.home / ".claude"
        settings_path = claude_dir / "settings.json"
        for permission in required_uninstall_readiness_permissions(
            claude_dir, settings_path
        ):
            pattern = f"{permission.tool}({permission.pattern})"
            self.assertIn(pattern, text)

    def test_uninstall_readiness_rules_are_scope_aware_for_project_scope(self):
        """
        Given a base config already exists at PROJECT scope
        When seed-self-perms is run at that scope
        Then the seeded uninstall-readiness rules reference the project's own
        .claude/settings.local.json and .claude/toolguard_hook.toml paths, not
        the user-level ~/.claude equivalents
        """
        self.run_cli(
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

        code, out = self.run_cli(
            [
                "seed-self-perms",
                "--scope",
                "project",
                "--project-dir",
                str(self.project_dir),
            ]
        )

        self.assertEqual(code, 0)
        config_path = self.project_dir / ".claude" / "toolguard_hook.toml"
        text = config_path.read_text()
        project_claude_dir = self.project_dir / ".claude"
        project_settings_path = project_claude_dir / "settings.local.json"
        self.assertIn(f"Write({project_settings_path})", text)
        self.assertIn(f"Edit({project_settings_path})", text)
        self.assertIn(f"rm {project_claude_dir / 'toolguard_hook.toml'}:*", text)
        # Must NOT contain the user-level equivalents.
        self.assertNotIn(f"Write({self.home / '.claude' / 'settings.json'})", text)

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

    def test_adds_the_self_integrity_hard_deny_patterns(self):
        """
        Given a base config already exists
        When seed-self-perms is run
        Then the config's [hard_deny] deny list contains every pattern from
        toolguard.tools.self_integrity.required_self_integrity_hard_deny_patterns()
        -- seeded unconditionally, alongside the self/uninstall-readiness
        permissions, not gated behind the optional Phase 10.1 secret-protection
        flow
        """
        self._write_base_config()

        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        deny_list = tomllib.loads(config_path.read_text())["hard_deny"]["deny"]
        for protection in required_self_integrity_hard_deny_patterns():
            self.assertIn(protection.pattern, deny_list)

    def test_self_integrity_hard_deny_blocks_rm_of_toolguard_state_dir(self):
        """
        Given seed-self-perms has been run (self-integrity hard_deny seeded)
        When the resulting config is loaded and a Bash `rm -rf ~/.toolguard`
        command is evaluated through the real decision engine
        Then it is hard-denied -- this is the actual regression the fix
        exists to prevent: a real install had ~/.toolguard deleted by an
        agent that decided, unprompted, to "go further for a clean slate"
        """
        self._write_base_config()
        self.run_cli(["seed-self-perms", "--scope", "user"])

        config_path = self.home / ".claude" / "toolguard_hook.toml"
        content = tomllib.loads(config_path.read_text())
        layer = ConfigLayer(
            Provenance("user", "toolguard_hook", "toml", config_path, 0),
            MappingProxyType(content),
        )
        configuration = Configuration(layers=(layer,))
        decision = decide(configuration, "Bash", "rm -rf ~/.toolguard")
        self.assertEqual(decision.verdict, "deny")

    def test_running_twice_does_not_duplicate_hard_deny_patterns(self):
        """
        Given seed-self-perms has already been run
        When it is run again
        Then the resulting [hard_deny] deny list still contains each
        self-integrity pattern exactly once
        """
        self._write_base_config()
        self.run_cli(["seed-self-perms", "--scope", "user"])
        code, out = self.run_cli(["seed-self-perms", "--scope", "user"])
        self.assertEqual(code, 0)
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        deny_list = tomllib.loads(config_path.read_text())["hard_deny"]["deny"]
        for protection in required_self_integrity_hard_deny_patterns():
            self.assertEqual(deny_list.count(protection.pattern), 1)

    def test_uv_bin_path_prepend_rule_allows_only_the_safe_form(self):
        """
        Given seed-self-perms has been run (the PATH-prepend rule seeded)
        When the resulting config is loaded and evaluated through the real
        decision engine
        Then `export PATH="$HOME/.local/bin:$PATH"` (in any common quoting)
        resolves to allow -- the defensive export an agent runs before nearly
        every toolguard console-script invocation -- but a PATH value
        pointing anywhere else (a hijacking attempt) does NOT match, and
        stays gated by the normal ask fallback
        """
        self._write_base_config()
        self.run_cli(["seed-self-perms", "--scope", "user"])

        config_path = self.home / ".claude" / "toolguard_hook.toml"
        content = tomllib.loads(config_path.read_text())
        layer = ConfigLayer(
            Provenance("user", "toolguard_hook", "toml", config_path, 0),
            MappingProxyType(content),
        )
        configuration = Configuration(layers=(layer,))

        safe_forms = [
            'export PATH="$HOME/.local/bin:$PATH"',
            "export PATH='$HOME/.local/bin:$PATH'",
            "export PATH=$HOME/.local/bin:$PATH",
        ]
        for command in safe_forms:
            with self.subTest(command=command):
                self.assertEqual(
                    decide(configuration, "Bash", command).verdict, "allow"
                )

        unsafe_forms = [
            'export PATH="/tmp/evil:$PATH"',
            'export PATH="$HOME/.local/bin:$PATH:/tmp/evil"',
            'export PATH="$HOME/.local/bin:$PATH" FOO=bar',
        ]
        for command in unsafe_forms:
            with self.subTest(command=command):
                self.assertNotEqual(
                    decide(configuration, "Bash", command).verdict, "allow"
                )


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
        'ask'
        """
        self._write_base_config()

        code, out = self.run_cli(["enable-takeover", "--scope", "user"])

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn("[takeover_mode]", text)
        self.assertIn("enabled = true", text)
        self.assertIn('no_match_fallback = "ask"', text)

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

    def test_sets_allow_fallback(self):
        """
        Given a base config already exists
        When enable-takeover is run with --no-match-fallback allow (TOO-19)
        Then no_match_fallback is written as 'allow'
        """
        self._write_base_config()

        code, out = self.run_cli(
            ["enable-takeover", "--scope", "user", "--no-match-fallback", "allow"]
        )

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn('no_match_fallback = "allow"', text)

    def test_sets_allow_with_no_warnings_fallback(self):
        """
        Given a base config already exists
        When enable-takeover is run with --no-match-fallback
            allow_with_no_warnings (TOO-19's long-form alias)
        Then no_match_fallback is written verbatim as
            'allow_with_no_warnings' -- the CLI writes the raw choice as-is;
            normalization to 'allow' happens at resolution time, not here
        """
        self._write_base_config()

        code, out = self.run_cli(
            [
                "enable-takeover",
                "--scope",
                "user",
                "--no-match-fallback",
                "allow_with_no_warnings",
            ]
        )

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn('no_match_fallback = "allow_with_no_warnings"', text)

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
        self.run_cli(["journal", "--action", "no backup case", "--reverse", "n/a"])

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
            self.run_cli(["journal", "--action", f"step {i}", "--reverse", f"undo {i}"])
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
        code, out = self.run_cli(["journal", "--action", "x", "--reverse", "y"])
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

    def test_register_hooks_preserves_existing_native_permissions(self):
        """
        TOO-19 review fix M2: given a user-scope settings.json that already
        holds Claude Code's own NATIVE permissions.allow entries (unrelated
        to toolguard's hooks)
        When register-hooks merges its PreToolUse/SessionStart hooks into
            that same file
        Then the pre-existing native permission entries are still present,
            byte-for-byte, in the resulting file (register-hooks now passes
            expected_patterns computed from the file's own prior content, so
            a merge bug that dropped them would be refused rather than
            silently written)
        """
        settings_path = self.home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls:*)", "Read(README.md)"]}})
        )

        code, _out = self.run_cli(
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
        self.assertEqual(
            data["permissions"]["allow"], ["Bash(ls:*)", "Read(README.md)"]
        )
        # And the hooks merge itself still happened.
        self.assertIn("PreToolUse", data["hooks"])

    def test_register_hooks_refuses_write_that_would_drop_native_permissions(self):
        """
        TOO-19 review fix M2: given a user-scope settings.json that already
        holds a native permissions.allow entry, and a (simulated) merge bug
        that would drop it from the serialized output
        When register-hooks attempts to write the merged file
        Then the write is refused (ConfigWriteVerificationError -> exit code
            2) and the original file on disk is left completely untouched,
            rather than silently losing the user's native permission rule
        """
        settings_path = self.home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}})
        settings_path.write_text(original_content)

        real_dumps = installer_module.json.dumps

        def _dumps_dropping_permissions(obj, *args, **kwargs):
            """Simulate a merge bug that silently drops the permissions key."""
            if isinstance(obj, dict) and "permissions" in obj:
                obj = {k: v for k, v in obj.items() if k != "permissions"}
            return real_dumps(obj, *args, **kwargs)

        with patch.object(
            installer_module.json, "dumps", side_effect=_dumps_dropping_permissions
        ):
            code, _out = self.run_cli(
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

        self.assertEqual(code, 2)
        self.assertEqual(settings_path.read_text(), original_content)

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
            "already" in lowered
            or "no changes" in lowered
            or "nothing to add" in lowered
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
        remaining steps -- AND it also prompts the agent to confirm Phase 8
        (security audit) and Phase 9 (maintenance) were already offered, since
        this is the last checkpoint reliably reached and a real install skipped
        both silently
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])

        code, out = self.run_cli(["enable-takeover", "--scope", "user"])

        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertIn("docs/install.md", out)
        self.assertIn("mandatory", lowered)
        self.assertIn("trace", lowered)
        self.assertIn("phase 8", lowered)
        self.assertIn("phase 9", lowered)
        self.assertIn("security audit", lowered)
        self.assertIn("maintenance", lowered)


# ---------------------------------------------------------------------------
# discover-projects
# ---------------------------------------------------------------------------


class TestDiscoverProjects(InstallerTestCase):
    """
    Behavior of the discover-projects subcommand (Phase 7.1 encapsulation).

    READ-ONLY: no backup, no journal entry, no init-state precondition. Uses a
    throwaway "projects root" directory (separate from the fake HOME) to hold real
    fake project directories, since a candidate's own directory must genuinely exist
    on disk to survive discovery's existence filter.
    """

    def setUp(self):
        """Extend the shared fixture with a throwaway root for fake project dirs."""
        super().setUp()
        self._projects_root_ctx = TemporaryDirectory()
        self.addCleanup(self._projects_root_ctx.cleanup)
        self.projects_root = Path(self._projects_root_ctx.name)

    def _make_project_dir(
        self,
        name,
        permissions=None,
        write_settings=True,
        takeover_enabled=None,
    ):
        """
        Create a real fake project directory, optionally with settings.local.json
        and/or a toolguard_hook.toml carrying a [takeover_mode] section.

        Args:
            name: Subdirectory name under the throwaway projects root (avoid '-' in
                the name for tests relying on lossy-encoding round-trips).
            permissions: Dict with 'allow'/'deny'/'ask' lists for settings.local.json;
                defaults to a single allow rule when write_settings is True.
            write_settings: Whether to write .claude/settings.local.json at all.
            takeover_enabled: If not None, writes .claude/toolguard_hook.toml with
                [takeover_mode] enabled = <bool>.

        Returns:
            The created project directory Path.
        """
        proj_dir = self.projects_root / name
        claude_dir = proj_dir / ".claude"
        claude_dir.mkdir(parents=True)
        if write_settings:
            perms = (
                permissions
                if permissions is not None
                else {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}
            )
            (claude_dir / "settings.local.json").write_text(
                json.dumps({"permissions": perms})
            )
        if takeover_enabled is not None:
            (claude_dir / "toolguard_hook.toml").write_text(
                'governed_tools = ["Bash"]\n\n'
                "[takeover_mode]\n"
                f"enabled = {'true' if takeover_enabled else 'false'}\n"
            )
        return proj_dir

    def _write_claude_json(self, project_dirs):
        """Write a fake ~/.claude.json with a 'projects' dict keyed by the given paths."""
        data = {"projects": {str(p): {} for p in project_dirs}}
        (self.home / ".claude.json").write_text(json.dumps(data))

    def _write_encoded_transcript_dir(self, project_dir):
        """Create ~/.claude/projects/<encoded> for the given project path (empty dir)."""
        encoded = str(project_dir).replace("/", "-")
        transcripts_root = self.home / ".claude" / "projects"
        transcripts_root.mkdir(parents=True, exist_ok=True)
        (transcripts_root / encoded).mkdir()

    def test_dedupes_project_present_in_both_sources(self):
        """
        Given a project listed both in ~/.claude.json and (via its lossy encoding) in
        ~/.claude/projects/
        When discover-projects runs
        Then it appears exactly once in the output
        """
        proj = self._make_project_dir("alpha")
        self._write_claude_json([proj])
        self._write_encoded_transcript_dir(proj)

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        data = json.loads(out)
        paths = [entry["path"] for entry in data]
        self.assertEqual(paths.count(str(proj)), 1)

    def test_lossy_encoded_project_included_when_decoded_path_exists(self):
        """
        Given a project known ONLY via its lossy ~/.claude/projects/ encoding (not in
        ~/.claude.json), and the decoded path exists on disk with real permission rules
        When discover-projects runs
        Then it is still included
        """
        proj = self._make_project_dir("bravo")
        self._write_encoded_transcript_dir(proj)

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn(str(proj), [entry["path"] for entry in data])

    def test_lossy_encoded_project_excluded_when_decoded_path_does_not_exist(self):
        """
        Given an encoded directory name under ~/.claude/projects/ whose naively decoded
        path does not exist on disk (the encoding is lossy and cannot be trusted blindly)
        When discover-projects runs
        Then no candidate is produced for it, and discovery does not crash
        """
        transcripts_root = self.home / ".claude" / "projects"
        transcripts_root.mkdir(parents=True)
        (transcripts_root / "-nonexistent-fake-project-path").mkdir()

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_excludes_project_whose_directory_no_longer_exists(self):
        """
        Given ~/.claude.json lists a project path that no longer exists on disk
        When discover-projects runs
        Then it is excluded from the candidate list
        """
        gone = self.projects_root / "deleted-project"
        self._write_claude_json([gone])

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_excludes_project_with_empty_or_missing_settings_local_json(self):
        """
        Given one project with no settings.local.json at all and another whose
        settings.local.json has only empty allow/deny/ask lists
        When discover-projects runs
        Then both are excluded (nothing worth migrating)
        """
        no_settings = self._make_project_dir("no-settings", write_settings=False)
        empty_settings = self._make_project_dir(
            "empty-settings", permissions={"allow": [], "deny": [], "ask": []}
        )
        self._write_claude_json([no_settings, empty_settings])

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_flags_takeover_enabled_project(self):
        """
        Given a candidate project whose toolguard_hook.toml has
        [takeover_mode] enabled = true
        When discover-projects runs
        Then its entry is flagged takeover_enabled = true, and a candidate with a
        toolguard config but takeover disabled is flagged false (both still report
        has_toolguard_config = true)
        """
        active = self._make_project_dir("takeoveron", takeover_enabled=True)
        inactive = self._make_project_dir("takeoveroff", takeover_enabled=False)
        self._write_claude_json([active, inactive])

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        by_path = {entry["path"]: entry for entry in json.loads(out)}
        self.assertTrue(by_path[str(active)]["takeover_enabled"])
        self.assertTrue(by_path[str(active)]["has_toolguard_config"])
        self.assertFalse(by_path[str(inactive)]["takeover_enabled"])
        self.assertTrue(by_path[str(inactive)]["has_toolguard_config"])

    def test_zero_candidates_prints_plain_message(self):
        """
        Given no ~/.claude.json and no ~/.claude/projects/ (nothing discoverable)
        When discover-projects runs with the default text format
        Then it prints a plain statement that nothing was found, not an empty table
        """
        code, out = self.run_cli(["discover-projects"])
        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertTrue("no candidate" in lowered or "nothing found" in lowered)

    def test_format_json_is_valid_and_has_expected_fields(self):
        """
        Given one discoverable candidate project
        When discover-projects runs with --format json
        Then stdout is valid JSON: a list of objects each with path,
        has_toolguard_config, takeover_enabled, and pattern_count fields
        """
        proj = self._make_project_dir(
            "gamma",
            permissions={"allow": ["Bash(git:*)", "Bash(uv:*)"], "deny": [], "ask": []},
        )
        self._write_claude_json([proj])

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        entry = data[0]
        self.assertEqual(entry["path"], str(proj))
        self.assertIn("has_toolguard_config", entry)
        self.assertIn("takeover_enabled", entry)
        self.assertEqual(entry["pattern_count"], 2)

    def test_output_sorted_by_path(self):
        """
        Given multiple candidate projects discovered in a non-alphabetical order
        When discover-projects runs
        Then the output is sorted by path for determinism
        """
        zeta = self._make_project_dir("zeta")
        alpha = self._make_project_dir("alpha")
        self._write_claude_json([zeta, alpha])

        code, out = self.run_cli(["discover-projects", "--format", "json"])

        self.assertEqual(code, 0)
        paths = [entry["path"] for entry in json.loads(out)]
        self.assertEqual(paths, sorted(paths))


# ---------------------------------------------------------------------------
# install-skills
# ---------------------------------------------------------------------------


class TestParseGitSource(unittest.TestCase):
    """Unit-level coverage of _parse_git_source's URL/ref splitting."""

    def test_uv_style_url_with_ref_splits_into_url_and_ref(self):
        """
        Given a uv-style 'git+https://host/owner/repo@ref' source
        When parsed
        Then the git+ prefix is stripped and the ref is split off separately
        """
        url, ref = installer_module._parse_git_source(
            "git+https://github.com/arnonmoscona/toolguard@master"
        )
        self.assertEqual(url, "https://github.com/arnonmoscona/toolguard")
        self.assertEqual(ref, "master")

    def test_uv_style_url_without_ref_has_no_ref(self):
        """
        Given a uv-style 'git+https://host/owner/repo' source with no @ref
        When parsed
        Then the git+ prefix is stripped and ref is None
        """
        url, ref = installer_module._parse_git_source(
            "git+https://github.com/arnonmoscona/toolguard"
        )
        self.assertEqual(url, "https://github.com/arnonmoscona/toolguard")
        self.assertIsNone(ref)

    def test_plain_url_is_returned_unchanged_with_no_ref(self):
        """
        Given a plain https URL with no git+ prefix
        When parsed
        Then it is returned unchanged, and no @ suffix is ever split off (only
        the uv-style prefix triggers ref recognition)
        """
        url, ref = installer_module._parse_git_source(
            "https://github.com/arnonmoscona/toolguard"
        )
        self.assertEqual(url, "https://github.com/arnonmoscona/toolguard")
        self.assertIsNone(ref)

    def test_ssh_user_at_host_is_not_mistaken_for_a_ref(self):
        """
        Given a uv-style ssh source whose URL itself contains 'user@host'
        (git+ssh://git@github.com/owner/repo.git) with no actual ref
        When parsed
        Then the user@host is NOT split off as a ref, because the text after
        the last @ contains a '/' (a real ref never does)
        """
        url, ref = installer_module._parse_git_source(
            "git+ssh://git@github.com/arnonmoscona/toolguard.git"
        )
        self.assertEqual(url, "ssh://git@github.com/arnonmoscona/toolguard.git")
        self.assertIsNone(ref)

    def test_ssh_user_at_host_with_a_real_ref_splits_correctly(self):
        """
        Given a uv-style ssh source with BOTH user@host in the URL and a
        trailing @ref (git+ssh://git@github.com/owner/repo@v1.2.3)
        When parsed
        Then only the trailing ref is split off; user@host stays part of the URL
        """
        url, ref = installer_module._parse_git_source(
            "git+ssh://git@github.com/arnonmoscona/toolguard@v1.2.3"
        )
        self.assertEqual(url, "ssh://git@github.com/arnonmoscona/toolguard")
        self.assertEqual(ref, "v1.2.3")


class TestInstallSkills(InstallerTestCase):
    """Behavior of the install-skills subcommand (Phase 5 encapsulation)."""

    def _make_source_repo(self, content_suffix=""):
        """
        Build a throwaway local 'source repo' with skills/toolguard-security-audit/
        and skills/toolguard-maintenance/, each holding a distinguishable SKILL.md.

        Args:
            content_suffix: Appended to each SKILL.md's content, so two calls with
                different suffixes produce distinguishable "versions" of the source.

        Returns:
            The source repo root Path (cleanup registered via addCleanup).
        """
        ctx = TemporaryDirectory()
        self.addCleanup(ctx.cleanup)
        root = Path(ctx.name)
        for skill in ("toolguard-security-audit", "toolguard-maintenance"):
            skill_dir = root / "skills" / skill
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {skill}{content_suffix}\n")
        return root

    def test_local_source_copies_both_skills_and_journals_two_entries(self):
        """
        Given --source is an existing local checkout directory
        When install-skills is run for user scope
        Then both skill directories are copied into ~/.claude/skills/, and the journal
        gains exactly two new entries (one per skill installed)
        """
        source = self._make_source_repo()
        self.run_cli(["init-state", "--source", "local checkout"])
        before = self.journal_indices()

        code, out = self.run_cli(
            ["install-skills", "--scope", "user", "--source", str(source)]
        )

        self.assertEqual(code, 0)
        for skill in ("toolguard-security-audit", "toolguard-maintenance"):
            dest = self.home / ".claude" / "skills" / skill / "SKILL.md"
            self.assertTrue(dest.exists())
            self.assertEqual(
                dest.read_text(), (source / "skills" / skill / "SKILL.md").read_text()
            )
        after = self.journal_indices()
        self.assertEqual(len(after), len(before) + 2)

    def test_rerun_without_force_is_noop(self):
        """
        Given install-skills has already installed both skills
        When it is run again without --force (even against a changed source)
        Then the target skill directories are left untouched, the summary reports them
        already installed, and no new journal entry is appended
        """
        source = self._make_source_repo()
        self.run_cli(["install-skills", "--scope", "user", "--source", str(source)])
        before = self.journal_indices()
        target = self.home / ".claude" / "skills" / "toolguard-maintenance" / "SKILL.md"
        original = target.read_text()

        changed_source = self._make_source_repo(content_suffix=" (changed)")
        code, out = self.run_cli(
            ["install-skills", "--scope", "user", "--source", str(changed_source)]
        )

        self.assertEqual(code, 0)
        self.assertEqual(target.read_text(), original)
        self.assertEqual(self.journal_indices(), before)
        self.assertIn("already installed", out.lower())

    def test_force_backs_up_old_content_before_replacing(self):
        """
        Given install-skills has already installed both skills
        When it is run again with --force against a changed source
        Then the OLD content is backed up before being overwritten, the target now has
        the NEW content, and the change is journaled
        """
        source = self._make_source_repo()
        self.run_cli(["install-skills", "--scope", "user", "--source", str(source)])
        target = self.home / ".claude" / "skills" / "toolguard-maintenance" / "SKILL.md"
        original = target.read_text()
        before = self.journal_indices()

        changed_source = self._make_source_repo(content_suffix=" (changed)")
        code, out = self.run_cli(
            [
                "install-skills",
                "--scope",
                "user",
                "--source",
                str(changed_source),
                "--force",
            ]
        )

        self.assertEqual(code, 0)
        self.assertNotEqual(target.read_text(), original)
        self.assertIn("(changed)", target.read_text())
        backups_dir = self.home / ".toolguard" / "backups"
        backup_dirs = [
            p for p in backups_dir.glob("toolguard-maintenance-*") if p.is_dir()
        ]
        self.assertEqual(len(backup_dirs), 1)
        self.assertEqual((backup_dirs[0] / "SKILL.md").read_text(), original)
        after = self.journal_indices()
        self.assertGreater(len(after), len(before))

    def test_git_source_clones_and_copies_skills(self):
        """
        Given --source is a git remote URL (not an existing local path)
        When install-skills runs
        Then it shallow-clones into a throwaway temp dir (subprocess.run mocked -- no
        real network call) and copies both skill directories from the clone
        """

        def fake_git_clone(cmd, *args, **kwargs):
            dest = Path(cmd[-1])
            for skill in ("toolguard-security-audit", "toolguard-maintenance"):
                skill_dir = dest / "skills" / skill
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(
            installer_module.subprocess, "run", side_effect=fake_git_clone
        ):
            code, out = self.run_cli(
                [
                    "install-skills",
                    "--scope",
                    "user",
                    "--source",
                    "https://example.com/toolguard.git",
                ]
            )

        self.assertEqual(code, 0)
        for skill in ("toolguard-security-audit", "toolguard-maintenance"):
            self.assertTrue(
                (self.home / ".claude" / "skills" / skill / "SKILL.md").exists()
            )

    def test_uv_style_git_plus_source_is_parsed_into_url_and_branch(self):
        """
        Given --source is a uv-style 'git+https://host/owner/repo@ref' URL (the
        SAME string that works for 'uv tool install' in Phase 3 -- a real
        install hit exactly this: it worked for the package install but
        install-skills rejected it, forcing a fallback to a plain URL that
        lost branch pinning)
        When install-skills runs
        Then git clone is invoked with the 'git+' prefix stripped from the URL
        and '--branch <ref>' added, NOT the literal unparsed source string
        """
        captured_cmd = {}

        def fake_git_clone(cmd, *args, **kwargs):
            captured_cmd["cmd"] = cmd
            dest = Path(cmd[-1])
            for skill in ("toolguard-security-audit", "toolguard-maintenance"):
                skill_dir = dest / "skills" / skill
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(
            installer_module.subprocess, "run", side_effect=fake_git_clone
        ):
            code, out = self.run_cli(
                [
                    "install-skills",
                    "--scope",
                    "user",
                    "--source",
                    "git+https://github.com/arnonmoscona/toolguard@master",
                ]
            )

        self.assertEqual(code, 0)
        cmd = captured_cmd["cmd"]
        self.assertIn("https://github.com/arnonmoscona/toolguard", cmd)
        self.assertIn("--branch", cmd)
        self.assertIn("master", cmd)
        self.assertNotIn("git+https://github.com/arnonmoscona/toolguard@master", cmd)

    def test_invalid_source_raises_installer_error(self):
        """
        Given --source is neither an existing local path nor a working git remote
        (git clone mocked to fail, simulating an unreachable/nonexistent repo)
        When install-skills runs
        Then it raises an error with a clear message and installs nothing
        """

        def fake_git_clone_failure(cmd, *args, **kwargs):
            return CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: repository not found"
            )

        with patch.object(
            installer_module.subprocess, "run", side_effect=fake_git_clone_failure
        ):
            code, out = self.run_cli(
                [
                    "install-skills",
                    "--scope",
                    "user",
                    "--source",
                    "https://example.com/does-not-exist.git",
                ]
            )

        self.assertNotEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "skills").exists())


# ---------------------------------------------------------------------------
# seed-hard-deny
# ---------------------------------------------------------------------------

# Duplicated here (rather than imported) so this test module's collection does not
# depend on the not-yet-implemented toolguard.tools.recommended_protections module --
# see test_recommended_protections.py for direct coverage of that module itself.
# Includes both the relative (project-anchored) forms and their home-anchored (~/...)
# siblings; see docs/security.md's "Why both forms of the sensitive-file patterns are
# needed" for the rationale.
_EXPECTED_HARD_DENY_PATTERNS = (
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.aws/**)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.aws/**)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)",
    "Read(~/.env)",
    "Read(~/.env.*)",
    "Read(~/.aws/**)",
    "Read(~/.ssh/**)",
    "Write(~/.env)",
    "Write(~/.aws/**)",
    "Write(~/.ssh/**)",
    "Edit(~/.env)",
)


class TestSeedHardDeny(InstallerTestCase):
    """
    Behavior of the seed-hard-deny subcommand (Phase 10.1 encapsulation).

    Architecturally mirrors seed-self-perms (see TestSeedSelfPerms) but targets
    [hard_deny].deny with the canonical patterns from
    toolguard.tools.recommended_protections.
    """

    def _write_base_config(self):
        """Write a minimal base toolguard_hook.toml via the CLI under test."""
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])

    def test_adds_full_canonical_list_in_one_call(self):
        """
        Given a base config already exists
        When seed-hard-deny is run
        Then [hard_deny].deny contains exactly the 16 canonical sensitive-file
        patterns, and the change is journaled
        """
        self._write_base_config()
        before = self.journal_indices()

        code, out = self.run_cli(["seed-hard-deny", "--scope", "user"])

        self.assertEqual(code, 0)
        text = (self.home / ".claude" / "toolguard_hook.toml").read_text()
        self.assertIn("[hard_deny]", text)
        for pattern in _EXPECTED_HARD_DENY_PATTERNS:
            self.assertIn(pattern, text)
        after = self.journal_indices()
        self.assertEqual(len(after), len(before) + 1)

    def test_running_twice_is_idempotent_noop(self):
        """
        Given seed-hard-deny has already been run once
        When it is run again
        Then it is a no-op: no new backup, no new journal entry, and the summary
        says explicitly that nothing needed to change (mirrors seed-self-perms)
        """
        self._write_base_config()
        self.run_cli(["seed-hard-deny", "--scope", "user"])
        before = self.journal_indices()
        backups_before = list((self.home / ".toolguard" / "backups").iterdir())

        code, out = self.run_cli(["seed-hard-deny", "--scope", "user"])

        self.assertEqual(code, 0)
        self.assertEqual(self.journal_indices(), before)
        backups_after = list((self.home / ".toolguard" / "backups").iterdir())
        self.assertEqual(len(backups_after), len(backups_before))
        lowered = out.lower()
        self.assertTrue(
            "already" in lowered
            or "no changes" in lowered
            or "nothing to add" in lowered
        )

    def test_preserves_preexisting_hard_deny_content(self):
        """
        Given a base config with a hand-added [hard_deny] section containing an
        unrelated deny entry and an allow carve-out
        When seed-hard-deny is run
        Then the canonical patterns are added, and the pre-existing allow carve-out
        and unrelated deny entry are preserved unchanged
        """
        self._write_base_config()
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        existing = config_path.read_text()
        config_path.write_text(
            existing
            + "\n[hard_deny]\n"
            + 'deny = [\n    "Read(**/custom-secret.key)",\n]\n'
            + 'allow = [\n    "Read(**/.env.example)",\n]\n'
        )

        code, out = self.run_cli(["seed-hard-deny", "--scope", "user"])

        self.assertEqual(code, 0)
        text = config_path.read_text()
        self.assertIn("Read(**/custom-secret.key)", text)
        self.assertIn("Read(**/.env.example)", text)
        for pattern in _EXPECTED_HARD_DENY_PATTERNS:
            self.assertIn(pattern, text)

    def test_missing_base_config_is_rejected(self):
        """
        Given no toolguard_hook.toml exists yet at the target scope
        When seed-hard-deny is run
        Then it fails with a non-zero exit and a message explaining the precondition,
        exactly like seed-self-perms, rather than creating a partial config
        """
        code, out = self.run_cli(["seed-hard-deny", "--scope", "user"])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "toolguard_hook.toml").exists())


# ---------------------------------------------------------------------------
# config-write-guard wiring (TOO-19 review fix): every installer.py write of a
# toolguard_hook.toml / settings.json must go through
# toolguard.config_write_guard.verified_write_config, never a raw
# _atomic_write_text -- these tests simulate a rendering bug that would have
# produced corrupt or pattern-dropping text and confirm the write is refused
# and the file on disk is left completely untouched.
# ---------------------------------------------------------------------------


class TestConfigWriteGuardWiring(InstallerTestCase):
    """
    Confirms installer.py's config-file writers refuse corrupt output.

    Each test injects a broken renderer (standing in for a real bug in that
    renderer) and checks that: (1) the CLI reports a non-zero exit rather than
    silently writing garbage, and (2) any pre-existing file on disk is left
    byte-for-byte unchanged -- the defining guarantee of
    ``config_write_guard.verified_write_config``.
    """

    def test_write_config_refuses_corrupt_content_and_creates_no_file(self):
        """
        Given write-config's TOML renderer is broken and produces unparseable text
        When write-config is run against a scope with no existing config file
        Then the CLI exits non-zero and no toolguard_hook.toml is created at all
        """
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        with patch.object(
            installer_module,
            "_render_config_toml",
            return_value="governed_tools = [\n",  # unterminated list -- invalid TOML
        ):
            code, out = self.run_cli(
                ["write-config", "--scope", "user", "--governed-tools", "Bash"]
            )

        self.assertNotEqual(code, 0)
        self.assertFalse(config_path.exists())

    def test_enable_takeover_refuses_corrupt_content_and_preserves_original(self):
        """
        Given a valid existing toolguard_hook.toml and a broken takeover-section
        renderer that produces unparseable text
        When enable-takeover is run
        Then the CLI exits non-zero and the config file's bytes are completely
        unchanged from before the attempted write (the backup made just before
        the write is irrelevant here -- the ORIGINAL file itself must survive)
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        original_bytes = config_path.read_bytes()

        with patch.object(
            installer_module,
            "_render_takeover_section",
            return_value="[takeover_mode\nenabled = true\n",  # missing closing bracket
        ):
            code, out = self.run_cli(["enable-takeover", "--scope", "user"])

        self.assertNotEqual(code, 0)
        self.assertEqual(config_path.read_bytes(), original_bytes)

    def test_seed_hard_deny_refuses_write_that_would_drop_existing_pattern(self):
        """
        Given an existing config with a hand-added custom [hard_deny] deny pattern,
        and a broken hard-deny-section renderer that omits that pre-existing pattern
        When seed-hard-deny is run
        Then the CLI exits non-zero (the content-loss guard refuses the write) and
        the config file's bytes are completely unchanged -- the custom pattern is
        never silently dropped, even though the syntax itself would have been valid
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        config_path = self.home / ".claude" / "toolguard_hook.toml"
        existing = config_path.read_text()
        config_path.write_text(
            existing + '\n[hard_deny]\ndeny = [\n    "Read(**/custom-secret.key)",\n]\n'
        )
        original_bytes = config_path.read_bytes()

        # Valid TOML, but silently drops the pre-existing custom-secret.key pattern.
        with patch.object(
            installer_module,
            "_render_hard_deny_section",
            return_value='[hard_deny]\ndeny = [\n    "Read(**/.env)",\n]\n',
        ):
            code, out = self.run_cli(["seed-hard-deny", "--scope", "user"])

        self.assertNotEqual(code, 0)
        self.assertEqual(config_path.read_bytes(), original_bytes)


# ---------------------------------------------------------------------------
# skills-status
# ---------------------------------------------------------------------------


class TestSkillsStatus(InstallerTestCase):
    """
    Behavior of the skills-status subcommand (TOO-15 completion-gate check).

    READ-ONLY: no backup, no journal entry, no init-state precondition. Covers
    both the bundled-skill classification (missing/installed/invalid, including
    the broken-symlink footgun) and the binary-install status block (mocked --
    no real git/network calls).
    """

    def setUp(self):
        """Extend the shared fixture with a throwaway dir for real skill sources."""
        super().setUp()
        self._elsewhere_ctx = TemporaryDirectory()
        self.addCleanup(self._elsewhere_ctx.cleanup)
        self.elsewhere = Path(self._elsewhere_ctx.name)

    def _write_skill(self, claude_dir, skill_name, with_skill_md=True):
        """Create a real ``<claude_dir>/skills/<skill_name>`` directory."""
        skill_dir = claude_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        if with_skill_md:
            (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n")
        return skill_dir

    def _symlink_skill(self, claude_dir, skill_name, target):
        """Create ``<claude_dir>/skills/<skill_name>`` as a symlink to *target*."""
        skills_dir = claude_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(target, skills_dir / skill_name)

    def _mock_git_up_to_date(self):
        """
        Patch detect_install/remote_head for a GIT install with no update pending.

        Started immediately and torn down via addCleanup, so callers just invoke
        this in setup code (no ``with`` block needed) -- avoids real git/network
        calls in every test that does not care about the binary-status block
        itself.
        """
        info = InstallInfo(
            kind=InstallKind.GIT, url="https://example.com/x", installed_commit="abc123"
        )
        patcher_detect = patch.object(
            installer_module, "detect_install", return_value=info
        )
        patcher_remote = patch.object(
            installer_module, "remote_head", return_value="abc123"
        )
        self.addCleanup(patcher_detect.stop)
        self.addCleanup(patcher_remote.stop)
        patcher_detect.start()
        patcher_remote.start()

    def test_fresh_state_both_skills_missing_both_scopes(self):
        """
        Given neither bundled skill is installed anywhere
        When skills-status runs
        Then every skill/scope combination is reported 'missing'
        """
        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        statuses = {(e["skill"], e["scope"]): e["status"] for e in data["skills"]}
        self.assertEqual(len(statuses), 4)
        self.assertTrue(all(status == "missing" for status in statuses.values()))

    def test_both_skills_fully_installed_both_scopes(self):
        """
        Given both bundled skills are real directories with SKILL.md at both scopes
        When skills-status runs
        Then every skill/scope combination is reported 'installed'
        """
        user_claude_dir = self.home / ".claude"
        project_claude_dir = self.project_dir / ".claude"
        for skill_name in installer_module._BUNDLED_SKILL_NAMES:
            self._write_skill(user_claude_dir, skill_name)
            self._write_skill(project_claude_dir, skill_name)

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        statuses = {(e["skill"], e["scope"]): e["status"] for e in data["skills"]}
        self.assertTrue(all(status == "installed" for status in statuses.values()))

    def test_symlink_to_real_valid_skill_dir_reports_installed(self):
        """
        Given a skill scope is a symlink pointing at a REAL, valid skill directory
        elsewhere on disk (this project's own dogfooding install pattern)
        When skills-status runs
        Then that scope is reported 'installed', not 'missing'
        """
        real_dir = self.elsewhere / "toolguard-maintenance"
        real_dir.mkdir()
        (real_dir / "SKILL.md").write_text("# toolguard-maintenance\n")
        user_claude_dir = self.home / ".claude"
        self._symlink_skill(user_claude_dir, "toolguard-maintenance", real_dir)

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        entry = next(
            e
            for e in data["skills"]
            if e["skill"] == "toolguard-maintenance" and e["scope"] == "user"
        )
        self.assertEqual(entry["status"], "installed")

    def test_broken_dangling_symlink_reports_missing_without_crashing(self):
        """
        Given a skill scope is a BROKEN/dangling symlink (its target does not exist)
        When skills-status runs
        Then that scope is reported 'missing' (not 'installed'), and the command
        does not crash -- this is the specific footgun this check exists to catch
        """
        user_claude_dir = self.home / ".claude"
        nonexistent_target = self.elsewhere / "does-not-exist" / "toolguard-maintenance"
        self._symlink_skill(
            user_claude_dir, "toolguard-maintenance", nonexistent_target
        )

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        entry = next(
            e
            for e in data["skills"]
            if e["skill"] == "toolguard-maintenance" and e["scope"] == "user"
        )
        self.assertEqual(entry["status"], "missing")

    def test_directory_without_skill_md_reports_invalid(self):
        """
        Given a skill scope is a real directory but has no SKILL.md inside it
        When skills-status runs
        Then that scope is reported 'invalid' -- distinct from 'missing'
        """
        user_claude_dir = self.home / ".claude"
        self._write_skill(
            user_claude_dir, "toolguard-security-audit", with_skill_md=False
        )

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        entry = next(
            e
            for e in data["skills"]
            if e["skill"] == "toolguard-security-audit" and e["scope"] == "user"
        )
        self.assertEqual(entry["status"], "invalid")

    def test_binary_status_git_update_available(self):
        """
        Given a mocked GIT install whose installed commit differs from remote HEAD
        When skills-status runs
        Then the binary block reports update_available=true with both commits
        """
        info = InstallInfo(
            kind=InstallKind.GIT, url="https://example.com/x", installed_commit="old111"
        )
        with (
            patch.object(installer_module, "detect_install", return_value=info),
            patch.object(installer_module, "remote_head", return_value="new222"),
        ):
            code, out = self.run_cli(
                [
                    "skills-status",
                    "--project-dir",
                    str(self.project_dir),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(code, 0)
        binary = json.loads(out)["binary"]
        self.assertEqual(binary["kind"], "git")
        self.assertTrue(binary["update_available"])
        self.assertEqual(binary["installed_commit"], "old111")
        self.assertEqual(binary["remote_commit"], "new222")

    def test_binary_status_unreachable_remote_reports_unknown_not_error(self):
        """
        Given a mocked GIT install where the remote cannot be reached (offline)
        When skills-status runs
        Then it does not fail: update_available is None and a note explains why,
        and the overall command still exits 0
        """
        info = InstallInfo(
            kind=InstallKind.GIT, url="https://example.com/x", installed_commit="old111"
        )
        with (
            patch.object(installer_module, "detect_install", return_value=info),
            patch.object(installer_module, "remote_head", return_value=None),
        ):
            code, out = self.run_cli(
                [
                    "skills-status",
                    "--project-dir",
                    str(self.project_dir),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(code, 0)
        binary = json.loads(out)["binary"]
        self.assertIsNone(binary["update_available"])
        self.assertIsNotNone(binary["note"])

    def test_binary_status_unknown_kind_reported_plainly(self):
        """
        Given detect_install cannot determine the install kind at all
        When skills-status runs
        Then the binary block reports kind='unknown' with update_available=None,
        and the command still exits 0 rather than failing
        """
        with patch.object(
            installer_module,
            "detect_install",
            return_value=InstallInfo(kind=InstallKind.UNKNOWN),
        ):
            code, out = self.run_cli(
                [
                    "skills-status",
                    "--project-dir",
                    str(self.project_dir),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(code, 0)
        binary = json.loads(out)["binary"]
        self.assertEqual(binary["kind"], "unknown")
        self.assertIsNone(binary["update_available"])

    def test_default_project_dir_is_current_working_directory(self):
        """
        Given --project-dir is omitted
        When skills-status runs
        Then it uses the current working directory as the project-scope root
        """
        self._mock_git_up_to_date()
        with patch("pathlib.Path.cwd", return_value=self.project_dir):
            code, out = self.run_cli(["skills-status", "--format", "json"])

        self.assertEqual(code, 0)
        data = json.loads(out)
        project_paths = {e["path"] for e in data["skills"] if e["scope"] == "project"}
        self.assertTrue(all(str(self.project_dir) in p for p in project_paths))

    def test_no_journal_entry_or_backup_is_ever_written(self):
        """
        Given any state of skills/binary
        When skills-status runs
        Then it is purely read-only: no journal entry is appended and no
        ~/.toolguard/backups content is created
        """
        self._mock_git_up_to_date()
        code, _ = self.run_cli(
            ["skills-status", "--project-dir", str(self.project_dir)]
        )

        self.assertEqual(code, 0)
        self.assertEqual(self.journal_indices(), [])

    def test_format_text_is_human_readable_and_mentions_every_skill(self):
        """
        Given the default --format text
        When skills-status runs
        Then stdout is non-JSON, human-readable text mentioning every bundled
        skill name and the binary install kind
        """
        self._mock_git_up_to_date()
        code, out = self.run_cli(
            ["skills-status", "--project-dir", str(self.project_dir)]
        )

        self.assertEqual(code, 0)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)
        for skill_name in installer_module._BUNDLED_SKILL_NAMES:
            self.assertIn(skill_name, out)
        self.assertIn("git", out)

    def test_format_json_is_valid_and_has_expected_top_level_keys(self):
        """
        Given --format json
        When skills-status runs
        Then stdout is valid, parseable JSON with top-level 'binary' and
        'skills' keys, and each skill entry has the expected fields
        """
        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )

        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("binary", data)
        self.assertIn("skills", data)
        for entry in data["skills"]:
            self.assertIn("skill", entry)
            self.assertIn("scope", entry)
            self.assertIn("path", entry)
            self.assertIn("status", entry)

    def test_no_settings_files_reports_no_hook_registrations(self):
        """
        TOO-19: Given neither settings.json nor settings.local.json exists
        When skills-status runs
        Then hook_registrations is an empty list
        """
        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["hook_registrations"], [])

    def test_unhardened_registration_is_reported(self):
        """
        TOO-19: Given settings.json has a bare-binary (unhardened) toolguard
            PreToolUse registration
        When skills-status runs
        Then hook_registrations reports it with hardened=False
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/home/x/.local/bin/toolguard",
                            }
                        ],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        user_regs = [r for r in data["hook_registrations"] if r["scope"] == "user"]
        self.assertEqual(len(user_regs), 1)
        self.assertFalse(user_regs[0]["hardened"])
        self.assertEqual(user_regs[0]["matcher"], "Bash")

    def test_hardened_registration_with_existing_interpreter_is_reported_clean(self):
        """
        TOO-19: Given settings.json has a hardened registration whose
            interpreter path DOES exist on disk
        When skills-status runs
        Then hardened=True and interpreter_missing=False
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        python_path = self.home / "fake-python3"
        python_path.write_text("#!/bin/sh\n")
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_path} -E -P -m toolguard.hook",
                            }
                        ],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        user_regs = [r for r in data["hook_registrations"] if r["scope"] == "user"]
        self.assertEqual(len(user_regs), 1)
        self.assertTrue(user_regs[0]["hardened"])
        self.assertFalse(user_regs[0]["interpreter_missing"])

    def test_hardened_registration_with_missing_interpreter_is_flagged(self):
        """
        TOO-19: Given settings.json has a hardened registration whose recorded
            interpreter path no longer exists on disk (the exact silent
            fail-open risk hardening's own docstring warns about)
        When skills-status runs
        Then hardened=True and interpreter_missing=True, and the text summary
        calls it out as BROKEN
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "/no/longer/there/python3 -E -P -m toolguard.hook"
                                ),
                            }
                        ],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            ["skills-status", "--project-dir", str(self.project_dir)]
        )
        self.assertEqual(code, 0)
        self.assertIn("BROKEN", out)

        code, out_json = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )
        data = json.loads(out_json)
        user_regs = [r for r in data["hook_registrations"] if r["scope"] == "user"]
        self.assertTrue(user_regs[0]["hardened"])
        self.assertTrue(user_regs[0]["interpreter_missing"])

    def test_non_toolguard_command_is_not_reported(self):
        """
        TOO-19: Given a PreToolUse hook registered for an UNRELATED command
        When skills-status runs
        Then it does not appear in hook_registrations
        """
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "some-other-tool"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        self._mock_git_up_to_date()
        code, out = self.run_cli(
            [
                "skills-status",
                "--project-dir",
                str(self.project_dir),
                "--format",
                "json",
            ]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["hook_registrations"], [])


class TestSeedCommandsWithStructuredEntries(InstallerTestCase):
    """
    Regression guards for review finding M3: the seed commands used to read raw
    ``tomllib`` output straight into the write path, so a config already holding
    structured ``{ match = ..., additionalContext = ... }`` entries crashed with
    ``TypeError: unhashable type: 'dict'`` (via ``sort_patterns``) or
    ``AttributeError: 'dict' object has no attribute 'replace'`` (via
    ``_render_hard_deny_section``), and a raw ``in`` membership test silently
    missed a structured entry so its pattern was re-added as a duplicate bare
    string on every run.
    """

    def user_config_path(self):
        """Return the path of the user-scope toolguard config in the fake HOME."""
        return self.home / ".claude" / "toolguard_hook.toml"

    def test_seed_self_perms_succeeds_when_config_holds_structured_entries(self):
        """
        Given a user-scope config whose permissions already contain a structured
            entry carrying additionalContext
        When seed-self-perms runs against it
        Then it exits 0 rather than crashing on the unhashable dict, and the
            structured entry's enrichment survives in the rewritten file
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        # seed-self-perms creates the [permissions] section; only then can a
        # structured entry be injected into it.
        self.run_cli(["seed-self-perms", "--scope", "user"])
        path = self.user_config_path()
        text = path.read_text()
        self.assertIn("allow = [", text)
        text = text.replace(
            "allow = [",
            'allow = [\n    { match = "Bash(uv run *)", additionalContext = "keep me" },',
            1,
        )
        path.write_text(text)

        code, _ = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        allow = tomllib.loads(path.read_text())["permissions"]["allow"]
        self.assertIn(
            {"match": "Bash(uv run *)", "additionalContext": "keep me"},
            allow,
        )

    def test_seed_self_perms_does_not_duplicate_a_structured_self_permission(self):
        """
        Given a self-permission that is already present, but expressed as a
            STRUCTURED entry rather than a bare string
        When seed-self-perms runs
        Then it recognises the pattern as already present and does NOT re-add it
            as a duplicate plain string (membership is by pattern, not by raw
            element identity)
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        self.run_cli(["seed-self-perms", "--scope", "user"])
        path = self.user_config_path()

        allow = tomllib.loads(path.read_text())["permissions"]["allow"]
        seeded = next((p for p in allow if isinstance(p, str)), None)
        self.assertIsNotNone(seeded, "expected at least one seeded plain pattern")

        # Re-express that same pattern in structured form.
        text = path.read_text().replace(
            f'"{seeded}",',
            f'{{ match = "{seeded}", additionalContext = "note" }},',
            1,
        )
        path.write_text(text)

        code, _ = self.run_cli(["seed-self-perms", "--scope", "user"])

        self.assertEqual(code, 0)
        allow = tomllib.loads(path.read_text())["permissions"]["allow"]
        patterns = [p if isinstance(p, str) else p.get("match") for p in allow]
        self.assertEqual(
            patterns.count(seeded),
            1,
            f"{seeded!r} was re-added despite already being present in structured form",
        )

    def test_seed_hard_deny_succeeds_when_hard_deny_holds_structured_entries(self):
        """
        Given a user-scope config whose [hard_deny] section already contains a
            structured entry
        When seed-hard-deny runs against it
        Then it exits 0 rather than raising AttributeError while rendering, and
            the structured hard_deny entry's enrichment survives
        """
        self.run_cli(["write-config", "--scope", "user", "--governed-tools", "Bash"])
        self.run_cli(["seed-hard-deny", "--scope", "user"])
        path = self.user_config_path()

        text = path.read_text()
        self.assertIn("[hard_deny]", text)
        text = text.replace(
            "deny = [",
            'deny = [\n    { match = "Bash(rm -rf /)", additionalContext = "never" },',
            1,
        )
        path.write_text(text)

        code, _ = self.run_cli(["seed-hard-deny", "--scope", "user"])

        self.assertEqual(code, 0)
        deny = tomllib.loads(path.read_text())["hard_deny"]["deny"]
        self.assertIn(
            {"match": "Bash(rm -rf /)", "additionalContext": "never"},
            deny,
        )


if __name__ == "__main__":
    unittest.main()
