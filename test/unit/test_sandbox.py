"""
Unit tests for :mod:`toolguard.testing.sandbox`.

This module intentionally does NOT use ConfigIsolationMixin: the object under
test is itself an isolation mechanism, and layering another one over it would
hide exactly the failures these tests exist to catch. For the same reason the
hostile-environment tests below hand-roll their own patching -- they have to
build an environment the sandbox is supposed to survive.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import toolguard.config as toolguard_config
from toolguard.api import decide
from toolguard.file_matching import check_file_path_hard_deny
from toolguard.testing.sandbox import (
    SCRUBBED_ENV_VARS,
    SandboxEscapeError,
    _Tripwire,
    experiment,
    main,
)

ALLOW_LS = '[permissions]\nallow = ["Bash(ls *)"]\n'

ALLOW_LS_ENRICHED = (
    "[permissions]\n"
    'allow = [{ match = "Bash(ls *)", additionalContext = "prefer the Read tool" }]\n'
)

#: Denies the same command ALLOW_LS permits, for hostile-environment fixtures.
DENY_LS = '[permissions]\ndeny = ["Bash(ls *)"]\n'

#: Same byte length as ALLOW_LS, so a rewrite collides with the parsed-config
#: cache key (path, format, mtime_ns, size) rather than missing on size.
DENY_LS_SAME_LENGTH = '[permissions]\ndeny  = ["Bash(ls *)"]\n'


def _hook_decision(result):
    """Pull the permissionDecision out of a :meth:`Sandbox.run_hook` payload."""
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


class TestSandboxIsolation(unittest.TestCase):
    """Every discovery anchor the sandbox redirects, asserted by its effect."""

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

    def test_home_is_redirected_by_the_patch_and_not_only_by_the_environment(self):
        """
        Given a sandbox experiment
        When HOME is removed from the environment inside the context
        Then Path.home() still resolves to the sandbox home -- the redirection is
            the Path.home patch, not a side effect of the rebuilt environment
        """
        with experiment() as sandbox:
            with mock.patch.dict(os.environ):
                os.environ.pop("HOME", None)
                os.environ.pop("USERPROFILE", None)
                self.assertEqual(Path.home(), sandbox.home)

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

    def test_project_root_discovery_is_redirected_into_the_sandbox(self):
        """
        Given a sandbox experiment
        When toolguard's project-root discovery runs inside the context
        Then it returns the sandbox project, and the loaded project layer comes
        from a file inside the sandbox rather than from the real repository
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(toolguard_config.find_project_root(), sandbox.project)
            project_layers = [
                layer
                for layer in sandbox.load_configuration().layers
                if layer.provenance.level == "project"
            ]
            self.assertEqual(len(project_layers), 1)
            self.assertEqual(
                project_layers[0].provenance.path, sandbox.project_config_path
            )

    def test_xdg_config_home_points_inside_the_sandbox(self):
        """
        Given a sandbox experiment
        When XDG_CONFIG_HOME is read inside the context
        Then it points inside the sandbox rather than being merely unset
        """
        with experiment() as sandbox:
            xdg = Path(os.environ["XDG_CONFIG_HOME"])
            self.assertEqual(xdg, sandbox.home / ".config")

    def test_log_directory_points_inside_the_sandbox(self):
        """
        Given a sandbox experiment
        When TOOLGUARD_LOG_DIR is read inside the context
        Then it points at the sandbox's own log directory, so no experiment can
        write into the real repository's logs/
        """
        with experiment() as sandbox:
            self.assertEqual(
                Path(os.environ["TOOLGUARD_LOG_DIR"]).resolve(),
                sandbox.log_dir.resolve(),
            )

    def test_scrubbed_variables_do_not_leak_into_the_sandbox(self):
        """
        Given every name in SCRUBBED_ENV_VARS is exported in the real environment
        When a sandbox experiment runs
        Then none of them survive except XDG_CONFIG_HOME, which is redirected inward
        """
        hostile = {name: "/real/leaked/path" for name in SCRUBBED_ENV_VARS}
        with mock.patch.dict(os.environ, hostile):
            for name in SCRUBBED_ENV_VARS:
                self.assertEqual(os.environ[name], "/real/leaked/path")
            with experiment() as sandbox:
                for name in SCRUBBED_ENV_VARS:
                    with self.subTest(variable=name):
                        if name == "XDG_CONFIG_HOME":
                            self.assertEqual(
                                os.environ[name], str(sandbox.home / ".config")
                            )
                        else:
                            self.assertNotIn(name, os.environ)

    def test_environment_is_restored_after_the_context(self):
        """
        Given an environment variable set before the experiment
        When the experiment exits
        Then the original environment is restored
        """
        with mock.patch.dict(os.environ, {"TOOLGUARD_SENTINEL": "outside"}):
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


class TestSandboxUnderAHostileEnvironment(unittest.TestCase):
    """
    Isolation measured against an environment that WOULD change the verdict.

    Every fixture here is proved potent in the same test: the hostile config is
    first shown to flip 'ls -la' to deny when it is the one in force, so a green
    assertion inside the sandbox means the leak was blocked rather than that the
    fixture was inert.
    """

    def setUp(self):
        """Build a hostile home that denies at every level the sandbox reads."""
        self.hostile_home = Path(tempfile.mkdtemp(prefix="toolguard-hostile-home-"))
        self.addCleanup(shutil.rmtree, self.hostile_home, ignore_errors=True)
        self.bare_project = Path(tempfile.mkdtemp(prefix="toolguard-bare-project-"))
        self.addCleanup(shutil.rmtree, self.bare_project, ignore_errors=True)
        (self.bare_project / ".git").mkdir()

        for relative in (
            Path(".claude") / "toolguard_hook.toml",
            Path(".toolguard") / "rules" / "hostile.rules.toml",
            Path(".config") / "toolguard" / "rules" / "hostile.rules.toml",
        ):
            target = self.hostile_home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(DENY_LS, encoding="utf-8")
        self.hostile_settings = self.hostile_home / "settings.json"
        self.hostile_settings.write_text(
            json.dumps({"permissions": {"deny": ["Bash(ls *)"]}}), encoding="utf-8"
        )
        self.hostile_env = {
            "HOME": str(self.hostile_home),
            "XDG_CONFIG_HOME": str(self.hostile_home / ".config"),
            "CLAUDE_SETTINGS_PATH": str(self.hostile_settings),
            "TOOLGUARD_PROJECT_ROOT": str(self.hostile_home),
            "CLAUDE_PROJECT_DIR": str(self.hostile_home),
            "PATH": os.environ.get("PATH", ""),
        }
        self.addCleanup(toolguard_config._parse_config_file_cached.cache_clear)

    def _assert_the_hostile_home_would_deny(self):
        """
        Prove the fixture bites: with the hostile home actually in force, the
        command the sandbox tests expect to be allowed comes back denied.
        """
        toolguard_config._parse_config_file_cached.cache_clear()
        with (
            mock.patch.object(Path, "home", return_value=self.hostile_home),
            mock.patch(
                "toolguard.config.find_project_root", return_value=self.bare_project
            ),
            mock.patch.dict(os.environ, self.hostile_env, clear=True),
        ):
            config = toolguard_config.load_configuration(str(self.bare_project))
            self.assertEqual(decide(config, "Bash", "ls -la").decision, "deny")
        toolguard_config._parse_config_file_cached.cache_clear()

    def test_a_hostile_home_does_not_reach_an_in_process_evaluation(self):
        """
        Given a real environment whose HOME, XDG and CLAUDE_SETTINGS_PATH all deny 'ls *'
        When a sandbox allowing 'ls *' evaluates 'ls -la' in-process
        Then the verdict is allow and it is attributed to the SANDBOX's project file
        """
        self._assert_the_hostile_home_would_deny()
        with mock.patch.dict(os.environ, self.hostile_env, clear=True):
            with experiment(project_config=ALLOW_LS) as sandbox:
                verdict = sandbox.evaluate("Bash", "ls -la")
                self.assertEqual(verdict.decision, "allow")
                self.assertEqual(verdict.matched_rule, "ls *")
                self.assertEqual(verdict.provenance.path, sandbox.project_config_path)

    def test_a_hostile_home_does_not_reach_the_run_hook_subprocess(self):
        """
        Given the same hostile environment
        When the sandbox runs the REAL hook in a subprocess
        Then the child decides from the sandbox config -- and names that file in
        its reason -- proving environment-only isolation holds for the path the
        tripwire cannot watch
        """
        self._assert_the_hostile_home_would_deny()
        with mock.patch.dict(os.environ, self.hostile_env, clear=True):
            with experiment(project_config=ALLOW_LS) as sandbox:
                result = sandbox.run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
                )
                sandbox_config = str(sandbox.project_config_path)
        self.assertEqual(result.get("_returncode"), 0, msg=result.get("_stderr"))
        self.assertEqual(_hook_decision(result), "allow")
        self.assertIn(
            sandbox_config, result["hookSpecificOutput"]["permissionDecisionReason"]
        )

    def _run_hook_child(self, sandbox, extra_env):
        """Run the same hook subprocess run_hook runs, with extra_env added."""
        env = dict(sandbox._subprocess_env())
        env.update(extra_env)
        event = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
                "cwd": str(sandbox.project),
                "hook_event_name": "PreToolUse",
                "session_id": "control",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-m", "toolguard.hook"],
            input=event,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(sandbox.project),
        )
        return _hook_decision(json.loads(completed.stdout))

    def test_run_hook_builds_the_child_environment_from_an_allow_list(self):
        """
        Given CLAUDE_SETTINGS_PATH exported INSIDE the sandbox context, pointing at
            settings that deny the command
        When the hook subprocess runs
        Then it still allows, because the child's environment is built from an
            allow-list rather than copied from the parent -- while the identical
            child WITH that variable added denies, proving the vector was potent
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            os.environ["CLAUDE_SETTINGS_PATH"] = str(self.hostile_settings)
            leaked = self._run_hook_child(
                sandbox, {"CLAUDE_SETTINGS_PATH": str(self.hostile_settings)}
            )
            self.assertEqual(leaked, "deny")
            result = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
            )
        self.assertEqual(result.get("_returncode"), 0, msg=result.get("_stderr"))
        self.assertEqual(_hook_decision(result), "allow")

    def test_the_cli_subprocess_ignores_a_hostile_home(self):
        """
        Given the documented `python -m toolguard.testing.sandbox` invocation
        When it runs with a hostile HOME that denies the command
        Then it still reports the verdict its --config argument implies
        """
        self._assert_the_hostile_home_would_deny()
        config_file = self.bare_project / "cfg.toml"
        config_file.write_text(ALLOW_LS, encoding="utf-8")
        env = dict(os.environ)
        env.update(self.hostile_env)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "toolguard.testing.sandbox",
                "--config",
                str(config_file),
                "--command",
                "ls -la",
                "--json",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.bare_project),
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["verdict"], "allow")


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
        Then no error is raised and the REAL file's content comes back, because
        reading is never the hazard and is never redirected
        """
        outside = Path(sys.modules["toolguard.testing.sandbox"].__file__).resolve()
        with experiment() as sandbox:
            self.assertFalse(str(outside).startswith(str(sandbox.root)))
            content = outside.read_text(encoding="utf-8")
        self.assertIn("class _Tripwire:", content)

    def test_tripwire_covers_the_pathlib_operations_that_never_reach_open(self):
        """
        Given a sandbox experiment
        When code calls Path.touch, Path.chmod or Path.symlink_to on an outside path
        Then each raises, and nothing is created -- these three are guarded only by
            the pathlib layer, so the open and os guards cannot stand in for it
        """
        victim = Path.home() / "__toolguard_sandbox_pathlib_probe__.txt"
        self.addCleanup(self._fail_if_created, victim)
        with experiment() as sandbox:
            for operation in (
                lambda: victim.touch(),
                lambda: victim.chmod(0o600),
                lambda: victim.symlink_to(sandbox.project / "staged.txt"),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaises(SandboxEscapeError):
                        operation()

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
        Given a real directory created outside the sandbox
        When code inside an experiment attempts to delete it
        Then SandboxEscapeError is raised and the directory survives

        The target is a throwaway directory rather than a real protected path:
        this test only proves anything if the delete would otherwise succeed,
        so a regression here destroys whatever it points at.  It also has to be
        created BEFORE the experiment -- inside, Path.home() answers with the
        sandbox's own fake home, which is not outside the sandbox at all.
        """
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "canary.txt").write_text("intact", encoding="utf-8")

        with experiment():
            with self.assertRaises(SandboxEscapeError):
                shutil.rmtree(outside)

        self.assertTrue(
            (outside / "canary.txt").exists(), "the tripwire let the delete through"
        )

    def test_tripwire_is_disarmed_after_the_context(self):
        """
        Given a sandbox experiment that has exited
        When an ordinary write happens outside any sandbox
        Then it succeeds, proving the guards were removed
        """
        with experiment():
            pass
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "after.txt"
            probe.write_text("ok", encoding="utf-8")
            self.assertEqual(probe.read_text(encoding="utf-8"), "ok")

    def test_guard_logic_rejects_every_real_configuration_anchor_without_any_io(self):
        """
        Given the tripwire guard for a sandbox root
        When it is asked about the two real rules directories and the two real
            ~/.claude config files
        Then it raises for all four, proving the decision itself rather than a
            side effect
        """
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
        When it is asked about a path inside that root, and about the root itself
        Then it permits both, so the guard is not trivially rejecting everything
        """
        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            guard._check(Path(tmp) / "nested" / "file.toml", "probe")
            guard._check(Path(tmp), "probe")

    def test_guard_logic_rejects_an_outside_path_given_as_bytes(self):
        """
        Given the tripwire guard for a sandbox root
        When the write target arrives as bytes rather than str
        Then it is decoded and rejected, so the bytes API is not a way past
        """
        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            with self.assertRaises(SandboxEscapeError):
                guard._check(os.fsencode(str(Path.home() / "escaped.txt")), "probe")
            guard._check(os.fsencode(str(Path(tmp) / "inside.txt")), "probe")

    def test_guard_logic_still_decides_when_the_path_cannot_be_resolved(self):
        """
        Given a write target the OS refuses to resolve (an embedded NUL byte)
        When the guard falls back to abspath
        Then an outside target is still rejected and an inside one still
            permitted, so the fallback stays location-aware rather than
            blanket-allowing or blanket-rejecting
        """
        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            with self.assertRaises(ValueError):
                Path("/etc/pass\x00wd").resolve()
            with self.assertRaises(SandboxEscapeError):
                guard._check("/etc/pass\x00wd", "probe")
            guard._check(tmp + "/na\x00me.txt", "probe")

    def test_guard_logic_ignores_a_target_that_is_not_a_path(self):
        """
        Given the tripwire guard for a sandbox root
        When the write target is an open file descriptor rather than a path
        Then it is let through, because there is no location to attribute
        """
        with tempfile.TemporaryDirectory() as tmp:
            _Tripwire(Path(tmp))._check(3, "probe")

    def test_guard_logic_permits_bytecode_caching_outside_the_sandbox(self):
        """
        Given the tripwire guard for a sandbox root
        When an import writes a __pycache__ entry outside the sandbox
        Then it is permitted, while a non-bytecode write to the same directory
            is still rejected
        """
        with tempfile.TemporaryDirectory() as tmp:
            guard = _Tripwire(Path(tmp))
            outside = Path.home() / ".toolguard"
            guard._check(outside / "__pycache__" / "mod.cpython-314.pyc", "probe")
            guard._check(outside / "mod.pyc", "probe")
            with self.assertRaises(SandboxEscapeError):
                guard._check(outside / "mod.toml", "probe")

    def test_guard_logic_dir_fd_relative_target_is_checked_against_the_directory_not_cwd(
        self,
    ):
        """
        Given a bare relative name and a dir_fd for a REAL directory outside the sandbox,
            with cwd pointing INSIDE the sandbox root
        When the guard checks that name with dir_fd given
        Then it raises, proving the check resolves against the fd's directory -- a cwd-based
            resolution would land the same bare name inside the sandbox and stay silent,
            masking the escape shutil.rmtree's fd-relative descent (os.rmdir(name,
            dir_fd=...), Python 3.14) performs
        """
        with tempfile.TemporaryDirectory() as sandbox_root:
            outside = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
            guard = _Tripwire(Path(sandbox_root))
            fd = os.open(outside, os.O_RDONLY)
            self.addCleanup(os.close, fd)
            original_cwd = os.getcwd()
            self.addCleanup(os.chdir, original_cwd)
            os.chdir(sandbox_root)

            with self.assertRaises(SandboxEscapeError):
                guard._check("victim", "probe", dir_fd=fd)

    def test_guard_logic_dir_fd_relative_target_inside_the_sandbox_is_permitted(self):
        """
        Given a bare relative name and a dir_fd for a directory INSIDE the sandbox root,
            with cwd pointing OUTSIDE the sandbox
        When the guard checks that name with dir_fd given
        Then it permits it, proving the check is not "any dir_fd raises" but genuinely
            follows the fd to its real directory
        """
        with tempfile.TemporaryDirectory() as sandbox_root:
            outside = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
            guard = _Tripwire(Path(sandbox_root))
            fd = os.open(sandbox_root, os.O_RDONLY)
            self.addCleanup(os.close, fd)
            original_cwd = os.getcwd()
            self.addCleanup(os.chdir, original_cwd)
            os.chdir(outside)

            guard._check("victim", "probe", dir_fd=fd)

    def _fail_if_created(self, victim: Path) -> None:
        """Fail loudly (and clean up) if a tripwire probe file actually got created."""
        if victim.exists():
            victim.unlink()
            self.fail(
                f"TRIPWIRE FAILED: {victim} was actually created outside the "
                f"sandbox. It has been removed, but the sandbox is not safe."
            )


class TestSandboxEvaluation(unittest.TestCase):
    """
    The sandbox drives the real decision path.

    Every verdict assertion here is paired with the rule that produced it.
    A bare ``allow``/``ask``/``deny`` cannot distinguish a rule match from the
    decision path's safety nets -- an unloadable config also asks, an empty
    extraction also denies -- so ``matched_rule`` and provenance carry the
    discrimination.
    """

    def test_project_allow_rule_permits_a_matching_command(self):
        """
        Given a sandbox whose project config allows 'ls *'
        When a matching command is evaluated
        Then the verdict is allow, attributed to that rule in the project file
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            verdict = sandbox.evaluate("Bash", "ls -la")
            self.assertEqual(verdict.decision, "allow")
            self.assertEqual(verdict.matched_rule, "ls *")
            self.assertEqual(verdict.provenance.level, "project")
            self.assertEqual(verdict.provenance.source_type, "toolguard_hook")
            self.assertEqual(verdict.provenance.path, sandbox.project_config_path)

    def test_unmatched_command_does_not_come_back_allow(self):
        """
        Given a sandbox whose project config allows only 'ls *'
        When a command matching nothing is evaluated
        Then the verdict falls to the fallback with no rule attributed, while the
            allowed command still matches -- so 'not allow' is the rules speaking
            rather than a config that never loaded
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "allow")
            verdict = sandbox.evaluate("Bash", "curl example.com")
            self.assertIn(verdict.decision, {"ask", "deny"})
            self.assertIsNone(verdict.matched_rule)
            self.assertIsNone(verdict.provenance)

    def test_a_sandbox_with_no_configuration_reports_no_rules_rather_than_a_match(self):
        """
        Given a sandbox with no config file written at any level
        When a command is evaluated
        Then the verdict is ask with nothing attributed, and the loaded
            configuration is genuinely empty -- an evaluation over zero rules is
            distinguishable from a rule that decided
        """
        with experiment() as sandbox:
            self.assertEqual(len(sandbox.load_configuration().layers), 0)
            verdict = sandbox.evaluate("Bash", "ls -la")
            self.assertEqual(verdict.decision, "ask")
            self.assertIsNone(verdict.matched_rule)
            self.assertIsNone(verdict.provenance)

    def test_an_unparseable_config_does_not_masquerade_as_a_rule_decision(self):
        """
        Given a sandbox whose project config is not valid TOML
        When a command is evaluated
        Then the verdict is ask, nothing is attributed, and the reason names the
            unparseable file, so a config that failed to load is not reported as
            an ordinary fallback
        """
        with experiment(project_config="this is not valid toml [[[") as sandbox:
            verdict = sandbox.evaluate("Bash", "ls -la")
            self.assertEqual(verdict.decision, "ask")
            self.assertIsNone(verdict.matched_rule)
            self.assertIn(str(sandbox.project_config_path), verdict.reason)

    def test_an_empty_command_is_denied_by_the_fail_closed_path(self):
        """
        Given any sandbox
        When an empty command is evaluated
        Then the verdict is deny with NO matched rule -- the fail-closed route
            every other 'deny' assertion in this file must be distinguished from
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            verdict = sandbox.evaluate("Bash", "")
            self.assertEqual(verdict.decision, "deny")
            self.assertIsNone(verdict.matched_rule)

    def test_hard_deny_cannot_be_overridden_by_a_project_allow(self):
        """
        Given a hard_deny on curl and a project config that explicitly allows curl
        When the curl command is evaluated
        Then the verdict is deny attributed to the hard_deny pattern, while the
            same config WITHOUT the hard_deny allows curl -- so the deny is the
            hard_deny and not the fail-closed path
        """
        config = '[permissions]\nallow = ["Bash(curl *)"]\n'
        with experiment(project_config=config) as sandbox:
            self.assertEqual(
                sandbox.evaluate("Bash", "curl example.com").decision, "allow"
            )
        with experiment(project_config=config, hard_deny=["Bash(curl *)"]) as sandbox:
            verdict = sandbox.evaluate("Bash", "curl example.com")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "curl *")

    def test_file_path_hard_deny_is_attributed_by_its_matched_pattern(self):
        """
        Given a hard_deny on Read of /etc/**
        When that path is read
        Then the verdict is deny and matched_rule names the hard-deny pattern
            that decided it, agreeing with check_file_path_hard_deny
        """
        with experiment(
            project_config=ALLOW_LS, hard_deny=["Read(/etc/**)"]
        ) as sandbox:
            config = sandbox.load_configuration()
            verdict = sandbox.evaluate("Read", "/etc/passwd")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "/etc/**")
            hard = check_file_path_hard_deny("Read", "/etc/passwd", config, True)
            self.assertIsNotNone(hard)
            self.assertEqual(hard.matched_pattern, "/etc/**")
            self.assertIsNone(
                check_file_path_hard_deny("Read", "/var/log/x", config, True)
            )

    def test_ask_floor_applies_to_inline_foreign_code(self):
        """
        Given a sandbox that allows everything, including the inline-python form
        When a `python -c` command is evaluated
        Then the verdict is ask with NOTHING attributed -- the floor decided, not
            the rule -- while an ordinary command under the same config is allowed
            by 'Bash(*)', so the ask is the floor and not a config that failed
        """
        config = '[permissions]\nallow = ["Bash(*)", "Bash(python -c *)"]\n'
        with experiment(project_config=config) as sandbox:
            control = sandbox.evaluate("Bash", "python script.py")
            self.assertEqual(control.decision, "allow")
            self.assertEqual(control.matched_rule, "*")

            verdict = sandbox.evaluate("Bash", "python -c 'x=1'")
            self.assertEqual(verdict.decision, "ask")
            self.assertIsNone(verdict.matched_rule)
            self.assertIsNone(verdict.provenance)
            self.assertEqual(len(verdict.sub_matches), 1)
            unit = verdict.sub_matches[0]
            self.assertEqual(unit.sub_command, "python -c 'x=1'")
            self.assertEqual(unit.decision, "ask")
            self.assertIsNone(unit.matched_rule)
            self.assertIsNone(unit.fallback_kind)

    def test_rules_file_in_toolguard_rules_dir_is_discovered(self):
        """
        Given a rules file placed in the sandbox's ~/.toolguard/rules
        When a command matching it is evaluated
        Then the deny is attributed to that exact file, proving the verdict came
            from that directory rather than from the fallback or the other one
        """
        rules = '[permissions]\ndeny = ["Bash(rsync *)"]\n'
        with experiment(
            project_config=ALLOW_LS, rules_files={"sync.rules.toml": rules}
        ) as sandbox:
            verdict = sandbox.evaluate("Bash", "rsync a b")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "rsync *")
            self.assertEqual(
                verdict.provenance.path, sandbox.toolguard_rules_dir / "sync.rules.toml"
            )
            self.assertEqual(verdict.provenance.source_type, "toolguard_hook_rules")

    def test_rules_file_in_xdg_rules_dir_is_discovered(self):
        """
        Given a rules file placed in the sandbox's ~/.config/toolguard/rules
        When a command matching it is evaluated
        Then the deny is attributed to that exact file, proving the verdict came
            from that directory rather than from the fallback or the other one
        """
        rules = '[permissions]\ndeny = ["Bash(rsync *)"]\n'
        with experiment(
            project_config=ALLOW_LS, xdg_rules_files={"sync.rules.toml": rules}
        ) as sandbox:
            verdict = sandbox.evaluate("Bash", "rsync a b")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "rsync *")
            self.assertEqual(
                verdict.provenance.path, sandbox.xdg_rules_dir / "sync.rules.toml"
            )

    def test_write_rules_file_places_each_file_in_the_requested_directory(self):
        """
        Given a sandbox
        When rules files are added through write_rules_file at both locations
        Then each lands in its own directory and takes effect immediately
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            written = sandbox.write_rules_file(
                "sync.rules.toml", '[permissions]\ndeny = ["Bash(rsync *)"]\n'
            )
            self.assertEqual(written.parent, sandbox.toolguard_rules_dir)
            self.assertEqual(
                sandbox.evaluate("Bash", "rsync a b").matched_rule, "rsync *"
            )

            written_xdg = sandbox.write_rules_file(
                "copy.rules.toml", '[permissions]\ndeny = ["Bash(scp *)"]\n', xdg=True
            )
            self.assertEqual(written_xdg.parent, sandbox.xdg_rules_dir)
            self.assertEqual(sandbox.evaluate("Bash", "scp a b").matched_rule, "scp *")

    def test_user_level_config_is_read(self):
        """
        Given a sandbox configured only at the USER level
        When a matching command is evaluated
        Then the allow is attributed to the user-level file
        """
        with experiment(user_config=ALLOW_LS) as sandbox:
            verdict = sandbox.evaluate("Bash", "ls -la")
            self.assertEqual(verdict.decision, "allow")
            self.assertEqual(verdict.provenance.level, "user")
            self.assertEqual(verdict.provenance.path, sandbox.user_config_path)

    def test_native_settings_json_is_read(self):
        """
        Given a sandbox whose project settings.json denies 'ls *' natively
        When the command is evaluated
        Then the deny is attributed to that rule, so the native format is on the
            search path too
        """
        settings = {"permissions": {"deny": ["Bash(ls *)"]}}
        with experiment(settings_json=settings) as sandbox:
            verdict = sandbox.evaluate("Bash", "ls -la")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "ls *")
            self.assertEqual(verdict.provenance.file_format, "json")

    def test_a_verbatim_settings_json_string_can_be_deliberately_malformed(self):
        """
        Given settings_json passed as a raw string that is not valid JSON
        When the file is inspected and a command evaluated
        Then the text is written verbatim and the verdict falls back to ask
        """
        with experiment(settings_json="{not json") as sandbox:
            written = sandbox.project / ".claude" / "settings.json"
            self.assertEqual(written.read_text(encoding="utf-8"), "{not json")
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "ask")

    def test_rewriting_the_config_changes_the_next_verdict(self):
        """
        Given a config already evaluated once, then rewritten to the same byte
            length and forced back to the same mtime, so it collides with the
            parsed-config cache key
        When it is re-evaluated
        Then the new verdict is returned, through the sandbox and through a
            plain load alike -- the cache key hashes content, so a same-length
            same-mtime rewrite is not served stale
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.evaluate("Bash", "ls -la").decision, "allow")

            before = sandbox.project_config_path.stat()
            sandbox.project_config_path.write_text(
                DENY_LS_SAME_LENGTH, encoding="utf-8"
            )
            os.utime(
                sandbox.project_config_path,
                ns=(before.st_atime_ns, before.st_mtime_ns),
            )
            after = sandbox.project_config_path.stat()
            self.assertEqual(after.st_size, before.st_size)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)

            reloaded = toolguard_config.load_configuration(str(sandbox.project))
            self.assertEqual(decide(reloaded, "Bash", "ls -la").decision, "deny")

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

    def test_config_text_is_empty_for_a_level_never_written(self):
        """
        Given a sandbox with only a project config
        When the user level is read back
        Then the empty string comes back rather than an error
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.config_text(level="user"), "")
            self.assertEqual(sandbox.config_text(level="project"), ALLOW_LS)

    def test_unknown_level_is_rejected(self):
        """
        Given a sandbox
        When a config is written or read at an unrecognised level
        Then ValueError is raised rather than silently using somewhere odd
        """
        with experiment() as sandbox:
            with self.assertRaises(ValueError):
                sandbox.write_config("x", level="global")
            with self.assertRaises(ValueError):
                sandbox.config_text(level="global")


class TestSandboxMatchesTheRealHook(unittest.TestCase):
    """
    The sandbox's contract: a verdict it reports is a verdict the hook produces.

    ``evaluate`` short-circuits to :func:`toolguard.api.decide` while ``run_hook``
    drives the real hook binary end to end. Agreement between them is what makes
    a sandbox measurement quotable as evidence about toolguard's behaviour; the
    one documented divergence (the governed-tools gate) is pinned separately.
    """

    #: (config, tool, target) triples, including the two control-structure forms
    #: proposed ticket 67's evidence was gathered on.
    SCENARIOS = (
        (ALLOW_LS, "Bash", "ls -la"),
        (ALLOW_LS, "Bash", "curl example.com"),
        (ALLOW_LS, "Bash", "ls -la && curl example.com"),
        (ALLOW_LS, "Bash", "ls -la; rm -rf /tmp/nothing"),
        ('[permissions]\ndeny = ["Bash(rm *)"]\n', "Bash", "rm -rf /tmp/x"),
        ('[permissions]\nallow = ["Bash(*)"]\n', "Bash", 'python -c "import os"'),
        (
            '[permissions]\nallow = ["Bash(*)"]\n',
            "Bash",
            'if python -c "import os"; then :; fi',
        ),
        (
            '[permissions]\nallow = ["Bash(*)"]\n',
            "Bash",
            'while python -c "import os"; do :; done',
        ),
        (ALLOW_LS, "Read", "/etc/passwd"),
        (ALLOW_LS, "Write", "/etc/shadow"),
    )

    def test_evaluate_agrees_with_the_real_hook_on_every_scenario(self):
        """
        Given a range of configs and commands, including compound and
            control-structure forms
        When each is evaluated in-process AND through the real hook subprocess
        Then the two verdicts are identical, so an in-process sandbox measurement
            is evidence about the hook and not only about the resolver
        """
        for config, tool, target in self.SCENARIOS:
            with self.subTest(tool=tool, target=target):
                key = "file_path" if tool in {"Read", "Write", "Edit"} else "command"
                with experiment(project_config=config) as sandbox:
                    in_process = sandbox.evaluate(tool, target).decision
                    result = sandbox.run_hook(
                        {"tool_name": tool, "tool_input": {key: target}}
                    )
                self.assertEqual(
                    result.get("_returncode"), 0, msg=result.get("_stderr")
                )
                self.assertEqual(
                    in_process,
                    _hook_decision(result),
                    msg=f"sandbox says {in_process!r}, hook says "
                    f"{_hook_decision(result)!r} for {target!r}",
                )

    def test_the_scenario_table_covers_more_than_one_verdict(self):
        """
        Given the agreement scenarios above
        When every one is evaluated
        Then all three verdicts appear, so agreement is not trivially satisfied
            by a table that only ever produces one answer
        """
        seen = set()
        for config, tool, target in self.SCENARIOS:
            with experiment(project_config=config) as sandbox:
                seen.add(sandbox.evaluate(tool, target).decision)
        self.assertEqual(seen, {"allow", "ask", "deny"})

    def test_the_ask_floor_survives_the_full_hook_path(self):
        """
        Given a config allowing everything
        When inline foreign code goes through the REAL hook
        Then the hook asks, while an ordinary command under the same config is
            allowed -- the floor is reproduced end to end, not only by evaluate
        """
        config = '[permissions]\nallow = ["Bash(*)"]\n'
        with experiment(project_config=config) as sandbox:
            allowed = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "python script.py"}}
            )
            floored = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "python -c 'x=1'"}}
            )
        self.assertEqual(_hook_decision(allowed), "allow")
        self.assertEqual(_hook_decision(floored), "ask")

    def test_an_ungoverned_tool_diverges_exactly_as_documented(self):
        """
        Given a blanket Bash deny and a tool that is not in governed_tools
        When it is evaluated both ways
        Then evaluate returns the Bash rule set's deny -- it does not consult
            governed_tools -- while the hook allows the call untouched, which is
            the single divergence Sandbox.evaluate's docstring declares
        """
        config = '[permissions]\ndeny = ["Bash(*)"]\n'
        with experiment(project_config=config) as sandbox:
            self.assertNotIn("WebFetch", sandbox.load_configuration().governed_tools())
            verdict = sandbox.evaluate("WebFetch", "https://example.com")
            self.assertEqual(verdict.decision, "deny")
            self.assertEqual(verdict.matched_rule, "*")
            result = sandbox.run_hook(
                {
                    "tool_name": "WebFetch",
                    "tool_input": {"command": "https://example.com"},
                }
            )
        self.assertEqual(_hook_decision(result), "allow")
        self.assertIn(
            "Not a governed tool",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )


class TestSandboxHookEndToEnd(unittest.TestCase):
    """run_hook exercises the real binary in a subprocess."""

    def test_run_hook_returns_a_permission_decision(self):
        """
        Given a sandbox allowing 'ls *'
        When the real hook is run end-to-end on a matching event
        Then hookSpecificOutput.permissionDecision is exactly 'allow'
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            result = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
            )
        self.assertEqual(result.get("_returncode"), 0, msg=result.get("_stderr"))
        self.assertEqual(_hook_decision(result), "allow")

    def test_run_hook_reports_a_non_allow_verdict_distinctly(self):
        """
        Given the same sandbox and a command the config does not allow
        When the hook runs
        Then permissionDecision is not 'allow' -- even though the word 'allow'
            still appears elsewhere in the payload, which is why the assertion
            above reads the field rather than the serialised dump
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            result = sandbox.run_hook(
                {"tool_name": "Bash", "tool_input": {"command": "curl example.com"}}
            )
        self.assertEqual(result.get("_returncode"), 0, msg=result.get("_stderr"))
        self.assertNotEqual(_hook_decision(result), "allow")

    def test_run_hook_logs_into_the_sandbox_log_directory(self):
        """
        Given a sandbox that has not run the hook yet
        When run_hook is invoked
        Then trace() goes from empty to carrying the command, and the log files
            live inside the sandbox rather than in the real repository
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            self.assertEqual(sandbox.trace(), [])
            sandbox.run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
            trace = sandbox.trace()
            self.assertTrue(any("ls -la" in line for line in trace), msg=str(trace))
            written = list(sandbox.log_dir.glob("*.md"))
            self.assertTrue(written)
            for path in written:
                self.assertTrue(str(path).startswith(str(sandbox.root)))

    def test_run_hook_does_not_see_the_real_home(self):
        """
        Given a sandbox
        When the hook subprocess's environment is built
        Then HOME points at the sandbox and every scrubbed variable is either
            absent or redirected inward
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            env = sandbox._subprocess_env()
            self.assertEqual(env["HOME"], str(sandbox.home))
            self.assertEqual(env["XDG_CONFIG_HOME"], str(sandbox.home / ".config"))
            self.assertEqual(env["TOOLGUARD_LOG_DIR"], str(sandbox.log_dir))
            for name in SCRUBBED_ENV_VARS:
                with self.subTest(variable=name):
                    if name == "XDG_CONFIG_HOME":
                        continue
                    self.assertNotIn(name, env)

    def test_run_hook_reports_non_json_output_rather_than_raising(self):
        """
        Given a hook invocation whose stdout is not JSON
        When run_hook parses it
        Then the raw text comes back under _raw_stdout with the exit status
        """
        with experiment(project_config=ALLOW_LS) as sandbox:
            completed = subprocess.CompletedProcess(
                args=[], returncode=3, stdout="not json at all", stderr="boom"
            )
            with mock.patch(
                "toolguard.testing.sandbox.subprocess.run", return_value=completed
            ):
                result = sandbox.run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
                )
        self.assertEqual(result["_raw_stdout"], "not json at all")
        self.assertEqual(result["_stderr"], "boom")
        self.assertEqual(result["_returncode"], 3)


class TestSandboxCli(unittest.TestCase):
    """The CLI is the ergonomic lever: one safe command answers a question."""

    def setUp(self):
        """Give each CLI test a scratch directory for its config files."""
        self.tmp = Path(tempfile.mkdtemp(prefix="toolguard-cli-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run(self, argv):
        """Run the CLI, returning (exit_code, stdout)."""
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def _config_file(self, name, text):
        """Write a config file into this test's scratch directory."""
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_cli_prints_the_verdict_for_a_command(self):
        """
        Given a config file on disk allowing 'ls *'
        When the sandbox CLI evaluates a matching command
        Then it prints an allow verdict naming the rule, and exits 0
        """
        code, out = self._run(
            ["--config", self._config_file("cfg.toml", ALLOW_LS), "--command", "ls -la"]
        )
        self.assertEqual(code, 0)
        self.assertIn("verdict: allow", out)
        self.assertIn("ls *", out)

    def test_cli_prints_a_non_allow_verdict_for_an_unmatched_command(self):
        """
        Given the same config file
        When a command it does not allow is evaluated
        Then the printed verdict is not allow, so the verdict line is reporting
            the evaluation rather than a fixed string
        """
        code, out = self._run(
            [
                "--config",
                self._config_file("cfg.toml", ALLOW_LS),
                "--command",
                "curl example.com",
            ]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("verdict: allow", out)
        self.assertIn("verdict: ask", out)

    def test_cli_json_output_is_machine_readable(self):
        """
        Given the --json flag
        When the CLI evaluates a command
        Then the output parses as JSON carrying the verdict, tool and target
        """
        _, out = self._run(
            [
                "--config",
                self._config_file("cfg.toml", ALLOW_LS),
                "--command",
                "ls -la",
                "--json",
            ]
        )
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "allow")
        self.assertEqual(payload["tool"], "Bash")
        self.assertEqual(payload["target"], "ls -la")

    def test_cli_json_reports_additional_context_when_the_rule_carries_one(self):
        """
        Given a structured allow entry carrying additionalContext
        When the CLI evaluates a matching command with --json
        Then the payload carries 'additionalContext' with that text
        """
        _, out = self._run(
            [
                "--config",
                self._config_file("cfg.toml", ALLOW_LS_ENRICHED),
                "--command",
                "ls -la",
                "--json",
            ]
        )
        self.assertEqual(json.loads(out)["additionalContext"], "prefer the Read tool")

    def test_cli_json_omits_additional_context_when_there_is_none(self):
        """
        Given a plain-string allow rule carrying no enrichment
        When the CLI evaluates a matching command with --json
        Then the 'additionalContext' key is ABSENT from the payload, not present as null
        """
        _, out = self._run(
            [
                "--config",
                self._config_file("cfg.toml", ALLOW_LS),
                "--command",
                "ls -la",
                "--json",
            ]
        )
        self.assertNotIn("additionalContext", json.loads(out))

    def test_cli_text_output_shows_additional_context(self):
        """
        Given a structured allow entry carrying additionalContext
        When the CLI evaluates a matching command without --json
        Then the human-readable output includes a 'context:' line
        """
        _, out = self._run(
            [
                "--config",
                self._config_file("cfg.toml", ALLOW_LS_ENRICHED),
                "--command",
                "ls -la",
            ]
        )
        self.assertIn("context: prefer the Read tool", out)

    def test_cli_text_output_omits_the_context_line_when_there_is_none(self):
        """
        Given a plain allow rule carrying no enrichment
        When the CLI evaluates it without --json
        Then no 'context:' line is printed
        """
        _, out = self._run(
            ["--config", self._config_file("cfg.toml", ALLOW_LS), "--command", "ls -la"]
        )
        self.assertNotIn("context:", out)

    def test_cli_reads_the_user_level_config(self):
        """
        Given a user-level config file passed with --user-config
        When a command it denies is evaluated
        Then the deny is reported, so the flag reaches the USER level
        """
        _, out = self._run(
            [
                "--user-config",
                self._config_file("user.toml", DENY_LS),
                "--command",
                "ls -la",
                "--json",
            ]
        )
        self.assertEqual(json.loads(out)["verdict"], "deny")

    def test_cli_hard_deny_flag_is_unoverridable(self):
        """
        Given a config that allows 'ls *' and a --hard-deny for the same pattern
        When the command is evaluated
        Then the verdict is deny, whereas the identical run without --hard-deny
            is allow, so the flag is what decided
        """
        config = self._config_file("cfg.toml", ALLOW_LS)
        _, without = self._run(["--config", config, "--command", "ls -la", "--json"])
        self.assertEqual(json.loads(without)["verdict"], "allow")

        _, with_flag = self._run(
            [
                "--config",
                config,
                "--hard-deny",
                "Bash(ls *)",
                "--command",
                "ls -la",
                "--json",
            ]
        )
        self.assertEqual(json.loads(with_flag)["verdict"], "deny")

    def test_cli_tool_flag_selects_a_file_path_tool(self):
        """
        Given --tool Read and a config denying a Read path
        When the CLI evaluates that path
        Then the deny is reported against tool 'Read', so --tool is honoured
        """
        _, out = self._run(
            [
                "--config",
                self._config_file(
                    "cfg.toml", '[permissions]\ndeny = ["Read(/etc/**)"]\n'
                ),
                "--tool",
                "Read",
                "--command",
                "/etc/passwd",
                "--json",
            ]
        )
        payload = json.loads(out)
        self.assertEqual(payload["tool"], "Read")
        self.assertEqual(payload["target"], "/etc/passwd")
        self.assertEqual(payload["verdict"], "deny")

    def test_cli_module_is_runnable_as_a_subprocess(self):
        """
        Given the documented invocation form
        When `python -m toolguard.testing.sandbox` is run against a config file
        Then it exits 0 and prints the verdict that config implies
        """
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "toolguard.testing.sandbox",
                "--config",
                self._config_file("cfg.toml", ALLOW_LS),
                "--command",
                "ls -la",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("verdict: allow", completed.stdout)


if __name__ == "__main__":
    unittest.main()
