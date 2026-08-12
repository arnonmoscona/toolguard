"""
Unit tests for :mod:`toolguard.testing.sandbox`.

This module intentionally does NOT use ConfigIsolationMixin: the object under
test is itself an isolation mechanism, and layering another one over it would
hide exactly the failures these tests exist to catch.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from toolguard.testing.sandbox import (
    SCRUBBED_ENV_VARS,
    SandboxEscapeError,
    experiment,
    main,
)

ALLOW_LS = '[permissions]\nallow = ["Bash(ls *)"]\n'

ALLOW_LS_ENRICHED = (
    "[permissions]\n"
    'allow = [{ match = "Bash(ls *)", additionalContext = "prefer the Read tool" }]\n'
)


class TestSandboxIsolation(unittest.TestCase):
    """Isolation of the four config-discovery anchors."""

    def test_home_is_redirected_into_the_sandbox(self):
        """
        Given a sandbox experiment
        When Path.home() is called inside the context
        Then it resolves to the sandbox's fake home, not the real one
        """
        real_home = Path.home()
        with experiment() as sandbox:
            self.assertEqual(Path.home(), sandbox.home)
            self.assertNotEqual(Path.home(), real_home)

    def test_home_is_restored_after_the_context(self):
        """
        Given a sandbox experiment that has exited
        When Path.home() is called again
        Then the real home is restored
        """
        real_home = Path.home()
        with experiment():
            pass
        self.assertEqual(Path.home(), real_home)

    def test_xdg_config_home_points_inside_the_sandbox(self):
        """
        Given a sandbox experiment
        When XDG_CONFIG_HOME is read inside the context
        Then it points inside the sandbox rather than being merely unset
        """
        with experiment() as sandbox:
            xdg = Path(os.environ["XDG_CONFIG_HOME"])
            self.assertEqual(xdg, sandbox.home / ".config")

    def test_scrubbed_variables_do_not_leak_into_the_sandbox(self):
        """
        Given CLAUDE_SETTINGS_PATH and friends are exported in the real environment
        When a sandbox experiment runs
        Then none of them survive except XDG_CONFIG_HOME, which is redirected inward
        """
        hostile = {name: "/real/leaked/path" for name in SCRUBBED_ENV_VARS}
        with unittest.mock.patch.dict(os.environ, hostile):
            with experiment() as sandbox:
                self.assertNotIn("CLAUDE_SETTINGS_PATH", os.environ)
                self.assertNotIn("TOOLGUARD_PROJECT_ROOT", os.environ)
                self.assertNotIn("CLAUDE_PROJECT_DIR", os.environ)
                self.assertEqual(
                    os.environ["XDG_CONFIG_HOME"], str(sandbox.home / ".config")
                )

    def test_environment_is_restored_after_the_context(self):
        """
        Given an environment variable set before the experiment
        When the experiment exits
        Then the original environment is restored
        """
        with unittest.mock.patch.dict(os.environ, {"TOOLGUARD_SENTINEL": "outside"}):
            with experiment():
                self.assertNotIn("TOOLGUARD_SENTINEL", os.environ)
            self.assertEqual(os.environ["TOOLGUARD_SENTINEL"], "outside")

    def test_project_root_carries_a_git_marker(self):
        """
        Given a sandbox experiment
        When the project directory is inspected
        Then it carries a .git marker so project-root discovery anchors correctly
        """
        with experiment() as sandbox:
            self.assertTrue((sandbox.project / ".git").is_dir())


class TestSandboxTripwire(unittest.TestCase):
    """The tripwire converts safety-by-inspection into safety-by-construction."""

    def test_write_inside_the_sandbox_is_permitted(self):
        """
        Given a sandbox experiment
        When a file is written inside the sandbox root
        Then the write succeeds and the tripwire stays silent
        """
        with experiment() as sandbox:
            target = sandbox.project / "scratch.txt"
            target.write_text("fine", encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), "fine")

    def test_write_outside_the_sandbox_raises(self):
        """
        Given a sandbox experiment
        When code attempts to write to a path outside the sandbox root
        Then SandboxEscapeError is raised and no file is created
        """
        real_home = Path.home()
        victim = real_home / "__toolguard_sandbox_tripwire_probe__.txt"
        self.addCleanup(self._fail_if_created, victim)
        with experiment():
            with self.assertRaises(SandboxEscapeError):
                victim.write_text("escaped", encoding="utf-8")

    def test_tripwire_covers_the_toolguard_rules_directory(self):
        """
        Given a sandbox experiment
        When code attempts to write into the REAL ~/.toolguard/rules directory
        Then SandboxEscapeError is raised and nothing is written there
        """
        victim = Path.home() / ".toolguard" / "rules" / "__tripwire_probe__.toml"
        self.addCleanup(self._fail_if_created, victim)
        with experiment():
            with self.assertRaises(SandboxEscapeError):
                victim.write_text(
                    '[permissions]\nallow = ["Bash(*)"]\n', encoding="utf-8"
                )

    def test_tripwire_covers_the_xdg_rules_directory(self):
        """
        Given a sandbox experiment
        When code attempts to write into the REAL ~/.config/toolguard/rules directory
        Then SandboxEscapeError is raised and nothing is written there
        """
        victim = (
            Path.home() / ".config" / "toolguard" / "rules" / "__tripwire_probe__.toml"
        )
        self.addCleanup(self._fail_if_created, victim)
        with experiment():
            with self.assertRaises(SandboxEscapeError):
                victim.write_text(
                    '[permissions]\nallow = ["Bash(*)"]\n', encoding="utf-8"
                )

    def test_tripwire_covers_open_in_write_mode(self):
        """
        Given a sandbox experiment
        When code opens an outside path with a write mode via builtins.open
        Then SandboxEscapeError is raised
        """
        victim = Path.home() / "__toolguard_sandbox_open_probe__.txt"
        self.addCleanup(self._fail_if_created, victim)
        with experiment():
            with self.assertRaises(SandboxEscapeError):
                open(victim, "w").close()

    def test_tripwire_allows_reading_outside_the_sandbox(self):
        """
        Given a sandbox experiment
        When code READS a file outside the sandbox
        Then no error is raised, because reading is never the hazard
        """
        with experiment():
            content = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("test_tripwire_allows_reading_outside_the_sandbox", content)

    def test_tripwire_covers_os_replace_destination(self):
        """
        Given a sandbox experiment
        When code atomically replaces a file OUTSIDE the sandbox
        Then SandboxEscapeError is raised
        """
        victim = Path.home() / "__toolguard_sandbox_replace_probe__.txt"
        self.addCleanup(self._fail_if_created, victim)
        with experiment() as sandbox:
            source = sandbox.project / "staged.txt"
            source.write_text("staged", encoding="utf-8")
            with self.assertRaises(SandboxEscapeError):
                os.replace(source, victim)

    def test_tripwire_covers_shutil_rmtree(self):
        """
        Given a sandbox experiment
        When code attempts to delete a tree outside the sandbox
        Then SandboxEscapeError is raised
        """
        import shutil

        with experiment():
            with self.assertRaises(SandboxEscapeError):
                shutil.rmtree(Path.home() / ".toolguard")

    def test_tripwire_is_disarmed_after_the_context(self):
        """
        Given a sandbox experiment that has exited
        When an ordinary write happens outside any sandbox
        Then it succeeds, proving the guards were removed
        """
        with experiment():
            pass
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "after.txt"
            probe.write_text("ok", encoding="utf-8")
            self.assertEqual(probe.read_text(encoding="utf-8"), "ok")

    def test_guard_logic_rejects_the_real_rules_directories_without_any_io(self):
        """
        Given the tripwire guard for a sandbox root
        When it is asked about paths in the two REAL rules directories
        Then it raises for both, proving the decision itself rather than a side effect
        """
        import tempfile

        from toolguard.testing.sandbox import _Tripwire

        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            for victim in (
                Path.home() / ".toolguard" / "rules" / "x.toml",
                Path.home() / ".config" / "toolguard" / "rules" / "x.toml",
                Path.home() / ".claude" / "toolguard_hook.toml",
                Path.home() / ".claude" / "settings.json",
            ):
                with self.subTest(victim=str(victim)):
                    with self.assertRaises(SandboxEscapeError):
                        guard._check(victim, "probe")

    def test_guard_logic_accepts_paths_inside_the_sandbox_root(self):
        """
        Given the tripwire guard for a sandbox root
        When it is asked about a path inside that root
        Then it permits it, so the guard is not trivially rejecting everything
        """
        import tempfile

        from toolguard.testing.sandbox import _Tripwire

        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            guard._check(Path(tmp) / "nested" / "file.toml", "probe")

    def _fail_if_created(self, victim: Path) -> None:
        """Fail loudly (and clean up) if a tripwire probe file actually got created."""
        if victim.exists():
            victim.unlink()
            self.fail(
                f"TRIPWIRE FAILED: {victim} was actually created outside the "
                f"sandbox. It has been removed, but the sandbox is not safe."
            )


class TestSandboxEvaluation(unittest.TestCase):
    """The sandbox drives the real decision path."""

    def test_project_allow_rule_permits_a_matching_command(self):
        """
        Given a sandbox whose project config allows 'ls *'
        When a matching command is evaluated
        Then the verdict is allow
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "allow")

    def test_unmatched_command_does_not_come_back_allow(self):
        """
        Given a sandbox whose project config allows only 'ls *'
        When a command matching nothing is evaluated
        Then the verdict is not allow (it falls to the configured fallback)
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertIn(
                sandbox.evaluate("Bash", "curl example.com").decision, {"ask", "deny"}
            )

    def test_hard_deny_cannot_be_overridden_by_a_project_allow(self):
        """
        Given a hard_deny on curl and a project config that explicitly allows curl
        When the curl command is evaluated
        Then the verdict is deny, because hard_deny is unoverridable
        """
        config = '[permissions]\nallow = ["Bash(curl *)"]\n'
        with experiment(project_config=config, hard_deny=["Bash(curl *)"]) as sandbox:
            self.assertEqual(
                sandbox.evaluate("Bash", "curl example.com").decision, "deny"
            )

    def test_ask_floor_applies_to_inline_foreign_code(self):
        """
        Given a sandbox that allows everything, including the inline-python form
        When a `python -c` command is evaluated
        Then the verdict is still ask, because the ASK floor is unsuppressible
        """
        config = '[permissions]\nallow = ["Bash(*)", "Bash(python -c *)"]\n'
        with experiment(project_config=config) as sandbox:
            self.assertEqual(
                sandbox.evaluate("Bash", "python -c 'x=1'").decision, "ask"
            )

    def test_rules_file_in_toolguard_rules_dir_is_discovered(self):
        """
        Given a rules file placed in the sandbox's ~/.toolguard/rules
        When a command matching it is evaluated
        Then the rule takes effect, proving that directory is on the search path
        """
        rules = '[permissions]\ndeny = ["Bash(rsync *)"]\n'
        with experiment(
            project_config=ALLOW_LS, rules_files={"sync.rules.toml": rules}
        ) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "rsync a b").decision, "deny")

    def test_rules_file_in_xdg_rules_dir_is_discovered(self):
        """
        Given a rules file placed in the sandbox's ~/.config/toolguard/rules
        When a command matching it is evaluated
        Then the rule takes effect, proving that directory is on the search path
        """
        rules = '[permissions]\ndeny = ["Bash(rsync *)"]\n'
        with experiment(
            project_config=ALLOW_LS, xdg_rules_files={"sync.rules.toml": rules}
        ) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "rsync a b").decision, "deny")

    def test_rewriting_the_config_changes_the_next_verdict(self):
        """
        Given a sandbox that has already evaluated a command once
        When the config is rewritten to deny that command and it is re-evaluated
        Then the new verdict reflects the NEW config, not a cached parse
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "allow")
            sandbox.write_config('[permissions]\ndeny = ["Bash(ls *)"]\n')
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "deny")

    def test_write_config_and_config_text_round_trip(self):
        """
        Given a sandbox
        When a config is written and read back at each level
        Then the text round-trips and the levels stay distinct
        """
        with experiment() as sandbox:
            sandbox.write_config("# project\n", level="project")
            sandbox.write_config("# user\n", level="user")
            self.assertEqual(sandbox.config_text(level="project"), "# project\n")
            self.assertEqual(sandbox.config_text(level="user"), "# user\n")

    def test_unknown_level_is_rejected(self):
        """
        Given a sandbox
        When a config is written at an unrecognised level
        Then ValueError is raised rather than silently writing somewhere odd
        """
        with experiment() as sandbox:
            with self.assertRaises(ValueError):
                sandbox.write_config("x", level="global")


class TestSandboxHookEndToEnd(unittest.TestCase):
    """run_hook exercises the real binary in a subprocess."""

    def test_run_hook_returns_a_permission_decision(self):
        """
        Given a sandbox allowing 'ls *'
        When the real hook is run end-to-end on a matching event
        Then it returns a hook JSON payload carrying an allow decision
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            result = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
            )
        self.assertEqual(result.get("_returncode"), 0, msg=result.get("_stderr"))
        payload = json.dumps(result)
        self.assertIn("allow", payload)

    def test_run_hook_does_not_see_the_real_home(self):
        """
        Given a sandbox
        When the hook subprocess runs
        Then its HOME points at the sandbox, so it cannot read real user config
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            env = sandbox._subprocess_env()
        self.assertEqual(env["HOME"], str(sandbox.home))
        self.assertNotIn("CLAUDE_SETTINGS_PATH", env)
        self.assertNotIn("TOOLGUARD_PROJECT_ROOT", env)


class TestSandboxCli(unittest.TestCase):
    """The CLI is the ergonomic lever: one safe command answers a question."""

    def test_cli_prints_the_verdict_for_a_command(self):
        """
        Given a config file on disk allowing 'ls *'
        When the sandbox CLI evaluates a matching command
        Then it prints an allow verdict and exits 0
        """
        import io
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "cfg.toml"
            config_file.write_text(ALLOW_LS, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--config", str(config_file), "--command", "ls -la"])
        self.assertEqual(code, 0)
        self.assertIn("verdict: allow", buffer.getvalue())

    def test_cli_json_output_is_machine_readable(self):
        """
        Given the --json flag
        When the CLI evaluates a command
        Then the output parses as JSON carrying the verdict
        """
        import io
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "cfg.toml"
            config_file.write_text(ALLOW_LS, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main(["--config", str(config_file), "--command", "ls -la", "--json"])
        self.assertEqual(json.loads(buffer.getvalue())["verdict"], "allow")

    def test_cli_json_reports_additional_context_when_the_rule_carries_one(self):
        """
        Given a structured allow entry carrying additionalContext
        When the CLI evaluates a matching command with --json
        Then the payload carries 'additionalContext' with that text
        """
        import io
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "cfg.toml"
            config_file.write_text(ALLOW_LS_ENRICHED, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main(["--config", str(config_file), "--command", "ls -la", "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["additionalContext"], "prefer the Read tool")

    def test_cli_json_omits_additional_context_when_there_is_none(self):
        """
        Given a plain-string allow rule carrying no enrichment
        When the CLI evaluates a matching command with --json
        Then the 'additionalContext' key is ABSENT from the payload, not present as null
        """
        import io
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "cfg.toml"
            config_file.write_text(ALLOW_LS, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main(["--config", str(config_file), "--command", "ls -la", "--json"])
        self.assertNotIn("additionalContext", json.loads(buffer.getvalue()))

    def test_cli_text_output_shows_additional_context(self):
        """
        Given a structured allow entry carrying additionalContext
        When the CLI evaluates a matching command without --json
        Then the human-readable output includes a 'context:' line
        """
        import io
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "cfg.toml"
            config_file.write_text(ALLOW_LS_ENRICHED, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main(["--config", str(config_file), "--command", "ls -la"])
        self.assertIn("context: prefer the Read tool", buffer.getvalue())

    def test_cli_module_is_runnable_as_a_subprocess(self):
        """
        Given the documented invocation form
        When `python -m toolguard.testing.sandbox` is run with a command
        Then it exits 0 and prints a verdict
        """
        completed = subprocess.run(
            [sys.executable, "-m", "toolguard.testing.sandbox", "--command", "ls -la"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("verdict:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
