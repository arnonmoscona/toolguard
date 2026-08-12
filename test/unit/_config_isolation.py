"""
Shared test isolation for toolguard's config-discovery hierarchy.

``toolguard.config`` reads real filesystem state from exactly three
controllable anchors: ``Path.home()``, ``toolguard.config.find_project_root()``,
and the ``XDG_CONFIG_HOME``/``CLAUDE_SETTINGS_PATH`` environment variables.
This repo dogfoods toolguard on itself, so real config genuinely exists on
the machine running this suite (``~/.claude/toolguard_hook.toml`` and
possibly ``~/.config/toolguard/rules/`` and/or ``~/.toolguard/rules/``, both
derived from ``Path.home()``) -- a test that doesn't redirect all three
anchors can silently depend on, or be broken by, that real state.
``ConfigIsolationMixin`` redirects all three into a fresh temporary directory.

A fourth, separate anchor: ``toolguard.env_config`` has its OWN
``find_project_root()`` -- distinct from ``toolguard.config``'s, and not
patched by the three anchors above -- that resolves the log directory
(``TOOLGUARD_LOG_DIR``, or ``<project_root>/logs`` by default) from the
process's real ``Path.cwd()``. A test that calls ``toolguard.hook.main()`` (or
anything else reaching ``get_env_config()``) without an explicit
``TOOLGUARD_LOG_DIR`` therefore silently resolves the REAL repo's ``logs/``
directory, since the test process's cwd genuinely is the repo root -- this
bit tests that already used this mixin, because its original scope covered
only the first three anchors. ``isolate_config_environment()`` below also
sets ``TOOLGUARD_LOG_DIR``; ``isolate_log_dir_for_module()`` gives
module-level (not per-``TestCase``) callers the same protection for tests
that never call ``isolate_config_environment()`` at all.

This module deliberately does NOT start with "test" so that
``unittest discover``'s ``test*.py`` pattern never picks it up as a test module
in its own right.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


class ConfigIsolationMixin:
    """
    Mixin for unittest.TestCase subclasses exercising toolguard.config discovery.

    Combine via multiple inheritance: class TestFoo(ConfigIsolationMixin, unittest.TestCase).
    Uses TestCase.enterContext() (stdlib, 3.11+) to register cleanup automatically,
    so call sites need no `with` nesting -- just call isolate_config_environment()
    as the first line of a test method (or from setUp for a whole class).
    """

    def isolate_config_environment(
        self, *, xdg_config_home=None, extra_env=None, project_under_home=None
    ):
        """
        Isolate Path.home(), find_project_root(), TOOLGUARD_LOG_DIR, and the
        environment.

        Args:
            xdg_config_home: If given (str or Path), sets XDG_CONFIG_HOME to this
                value inside the isolated environment; otherwise left unset.
            extra_env: Optional extra environment variables to set alongside the
                cleared environment. May set "TOOLGUARD_LOG_DIR" to override the
                default isolated log directory described below.
            project_under_home: If given (a '/'-separated relative path string,
                e.g. "a/b/proj"), creates `project` NESTED under `home` at that
                path instead of as home's sibling -- for tests that exercise the
                ancestor walk itself and need intermediate directories between
                project and home (e.g. to place a `.claude` at an intermediate
                level). Intermediate directories are created but not otherwise
                populated; callers add `.claude` dirs/files as needed.

        Returns:
            (home, project): fresh, empty Path directories. `home` stands in for
            Path.home() (no .claude yet -- callers create it). `project` stands
            in for the discovered project root (contains a .git marker, no
            .claude yet). The isolated log directory (not created on disk; a
            test that needs it to exist should ``mkdir`` it, or set
            ``TOOLGUARD_CREATE_LOG_DIR=1`` via extra_env) is also exposed as
            ``self.isolated_log_dir`` for tests that want to assert against it.
        """
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home = tmp / "home"
        home.mkdir()
        if project_under_home is not None:
            project = home.joinpath(*project_under_home.split("/"))
        else:
            project = tmp / "project"
        project.mkdir(parents=True)
        (project / ".git").mkdir()

        self.isolated_log_dir = tmp / "logs"

        env = dict(extra_env or {})
        env.setdefault("TOOLGUARD_LOG_DIR", str(self.isolated_log_dir))
        if xdg_config_home is not None:
            env["XDG_CONFIG_HOME"] = str(xdg_config_home)

        self.enterContext(patch.object(Path, "home", return_value=home))
        self.enterContext(patch.dict(os.environ, env, clear=True))
        self.enterContext(
            patch("toolguard.config.find_project_root", return_value=project)
        )
        return home, project


def isolate_log_dir_for_module(prefix="too19_module_logs_"):
    """
    Module-level (not per-TestCase) TOOLGUARD_LOG_DIR isolation.

    For test modules whose tests drive ``toolguard.hook.main()`` end-to-end
    without going through ``ConfigIsolationMixin`` at all -- typically because
    they mock ``toolguard.hook.load_configuration()`` directly and so never
    reach ``toolguard.config``'s discovery path, but DO reach
    ``toolguard.env_config.get_env_config()``, which resolves the log
    directory independently (see the module docstring above). Retrofitting
    every individual test method in a large file like test_hook.py to call
    ``isolate_config_environment()`` would be a much larger, more invasive
    diff than the leak warrants; a single module-level env override is
    equivalent in effect and far smaller.

    Intended for ``setUpModule()``/``tearDownModule()``:

        _log_tmp_dir = _log_patcher = None

        def setUpModule():
            global _log_tmp_dir, _log_patcher
            _log_tmp_dir, _log_patcher, _log_dir = isolate_log_dir_for_module()

        def tearDownModule():
            _log_patcher.stop()
            _log_tmp_dir.cleanup()

    Returns:
        (tmp_dir, patcher, log_dir): ``tmp_dir`` is the live
        ``tempfile.TemporaryDirectory`` (caller must call ``.cleanup()`` in
        ``tearDownModule``); ``patcher`` is the started ``patch.dict`` (caller
        must call ``.stop()`` in ``tearDownModule``); ``log_dir`` is the
        isolated ``Path`` now bound to ``TOOLGUARD_LOG_DIR``.
    """
    tmp_dir = tempfile.TemporaryDirectory(prefix=prefix)
    log_dir = Path(tmp_dir.name) / "logs"
    # clear=False: additive only. These modules do not rely on a cleared
    # environment for config isolation (they mock load_configuration()
    # directly), so wiping unrelated variables here would be an unwarranted
    # side effect on unrelated env-driven behaviour under test.
    patcher = patch.dict(os.environ, {"TOOLGUARD_LOG_DIR": str(log_dir)}, clear=False)
    patcher.start()
    return tmp_dir, patcher, log_dir
