"""
Shared test isolation for toolguard's config-discovery hierarchy.

toolguard/config.py reads real filesystem state from exactly three controllable
anchors: Path.home(), toolguard.config.find_project_root(), and the
XDG_CONFIG_HOME/CLAUDE_SETTINGS_PATH environment variables. This repo dogfoods
toolguard on itself, so a real ~/.claude/toolguard_hook.toml (and potentially a
real ~/.config/toolguard/rules/ and/or ~/.toolguard/rules/ -- TOO-30/TOO-19's
two candidate rules directories, both derived from Path.home()) genuinely
exists on the machine running this suite -- tests that don't redirect these
three anchors can silently depend on, or be broken by, that real state.
ConfigIsolationMixin redirects all three into a fresh temporary directory.

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
        Isolate Path.home(), find_project_root(), and the environment.

        Args:
            xdg_config_home: If given (str or Path), sets XDG_CONFIG_HOME to this
                value inside the isolated environment; otherwise left unset.
            extra_env: Optional extra environment variables to set alongside the
                cleared environment.
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
            .claude yet).
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

        env = dict(extra_env or {})
        if xdg_config_home is not None:
            env["XDG_CONFIG_HOME"] = str(xdg_config_home)

        self.enterContext(patch.object(Path, "home", return_value=home))
        self.enterContext(patch.dict(os.environ, env, clear=True))
        self.enterContext(
            patch("toolguard.config.find_project_root", return_value=project)
        )
        return home, project
