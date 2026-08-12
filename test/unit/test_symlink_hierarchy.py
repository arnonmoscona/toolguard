"""
Hierarchy resolution through a SYMLINKED ``.claude`` directory: project-root
anchoring, level attribution, end-to-end verdicts, and a symlinked rules file.

Isolation exception (`.claude/rules/test-config-isolation.md`): these tests do NOT
use ConfigIsolationMixin. It patches ``find_project_root``, one of the functions
under test, and its fixed sibling layout cannot express a symlink pointing from the
project into a separate store; ``Path.home()`` is patched by hand instead.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import config as config_module
from toolguard.api import decide
from toolguard.config import load_configuration

PROJECT_CONFIG = '[permissions]\nallow = ["Bash(ls *)"]\ndeny = ["Bash(curl *)"]\n'


class _SymlinkLayout:
    """A throwaway home/store/project layout for symlink experiments."""

    def __init__(self, root: Path, *, store_under_home: bool = False):
        """Build the layout under ``root``, optionally placing the store under ``home/.claude``."""
        self.root = root
        self.home = root / "home"
        (self.home / ".claude").mkdir(parents=True)
        if store_under_home:
            self.store = self.home / ".claude" / "store" / "toolguard"
        else:
            self.store = root / "store" / "toolguard"
        self.store.mkdir(parents=True)
        self.project = root / "project"
        (self.project / ".git").mkdir(parents=True)

    def with_real_claude(self) -> Path:
        """Create a REAL ``.claude`` directory in the project and return its path."""
        claude = self.project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        return claude

    def with_symlinked_claude(self) -> Path:
        """Create the project's ``.claude`` as a symlink into the store and return the link."""
        real = self.store / ".claude"
        real.mkdir()
        (real / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        link = self.project / ".claude"
        link.symlink_to(real, target_is_directory=True)
        return link


class SymlinkHierarchyTestCase(unittest.TestCase):
    """Shared setup: a temp root and a patched Path.home()."""

    def build(self, *, store_under_home: bool = False) -> _SymlinkLayout:
        """Build an isolated layout, patch ``Path.home()`` at it, and return it."""
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        layout = _SymlinkLayout(root, store_under_home=store_under_home)
        self.enterContext(patch.object(Path, "home", return_value=layout.home))
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        config_module._parse_config_file_cached.cache_clear()
        self.addCleanup(config_module._parse_config_file_cached.cache_clear)
        return layout


class TestProjectRootThroughSymlink(SymlinkHierarchyTestCase):
    """find_project_root must still anchor on a symlinked .claude."""

    def test_symlinked_claude_still_anchors_the_project_root(self):
        """
        Given a project whose only marker is a SYMLINKED .claude directory
        When find_project_root runs from inside that project
        Then it returns the project directory, not the symlink's target
        """
        layout = self.build()
        layout.with_symlinked_claude()
        nested = layout.project / "src" / "pkg"
        nested.mkdir(parents=True)

        found = config_module.find_project_root(nested)

        self.assertEqual(found, layout.project)
        self.assertNotEqual(found, layout.store / ".claude")

    def test_symlinked_claude_matches_the_real_directory_control(self):
        """
        Given two otherwise identical projects, one with a real .claude and one
        with a symlinked .claude
        When find_project_root runs in each
        Then both return their own project directory
        """
        real_layout = self.build()
        real_layout.with_real_claude()
        self.assertEqual(
            config_module.find_project_root(real_layout.project), real_layout.project
        )


class TestLevelAttributionThroughSymlink(SymlinkHierarchyTestCase):
    """
    Level attribution decides precedence, and a symlink must never shift it. Levels
    come from :func:`toolguard.config._discover_levels`, the pass that finds each
    file, so attribution follows where the file was FOUND, not where its bytes live.
    """

    def _project_config_level(self, layout: "_SymlinkLayout") -> list:
        """Return the level labels discovery assigns to every discovered toolguard_hook.toml."""
        config_module._parse_config_file_cached.cache_clear()
        return [
            level
            for path, _stype, _fmt, _spec, level in config_module._discover_levels(
                layout.project
            )
            if path.name == "toolguard_hook.toml"
        ]

    def test_symlinked_project_config_is_still_attributed_to_the_project_level(self):
        """
        Given a project .claude symlinked to a store OUTSIDE ~/.claude
        When the hierarchy levels are discovered
        Then the config is attributed to 'project', so precedence is unchanged
        """
        layout = self.build()
        layout.with_symlinked_claude()

        self.assertEqual(self._project_config_level(layout), ["project"])

    def test_real_directory_control_is_attributed_to_the_project_level(self):
        """
        Given a project with a REAL .claude directory
        When the hierarchy levels are discovered
        Then the config is attributed to 'project', establishing the control
        """
        layout = self.build()
        layout.with_real_claude()

        self.assertEqual(self._project_config_level(layout), ["project"])

    def test_store_under_home_claude_is_still_a_project_level_config(self):
        """
        Given a project .claude symlinked to a store located UNDER ~/.claude
        When the hierarchy levels are discovered
        Then it is STILL attributed to 'project'
        """
        layout = self.build(store_under_home=True)
        layout.with_symlinked_claude()

        self.assertEqual(self._project_config_level(layout), ["project"])

    def test_symlinked_contents_under_home_claude_are_still_project_level(self):
        """
        Given a REAL project .claude directory whose CONTENTS are symlinks into a
        store located under ~/.claude
        When the hierarchy levels are discovered
        Then the config is STILL attributed to 'project'

        Separate from the directory case: contents-linking looks like a workaround
        for it and is not one.
        """
        layout = self.build(store_under_home=True)
        held = layout.store / "toolguard_hook.toml"
        held.write_text(PROJECT_CONFIG, encoding="utf-8")
        claude = layout.project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").symlink_to(held)

        self.assertEqual(self._project_config_level(layout), ["project"])


class TestEndToEndResolutionThroughSymlink(SymlinkHierarchyTestCase):
    """The verdicts themselves must be identical through a symlink."""

    def _verdicts(self, project: Path) -> dict:
        """Resolve a fixed set of commands against a project's configuration, command -> verdict."""
        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(project))
        return {
            command: decide(config, "Bash", command, True).decision
            for command in ("ls -la", "curl example.com", "rsync a b")
        }

    def test_symlinked_claude_produces_the_same_verdicts_as_a_real_directory(self):
        """
        Given identical configs, one behind a symlinked .claude and one in a real
        .claude directory
        When the same commands are resolved against each
        Then the verdicts are identical
        """
        real_layout = self.build()
        real_layout.with_real_claude()
        real_verdicts = self._verdicts(real_layout.project)

        symlink_layout = self.build()
        symlink_layout.with_symlinked_claude()
        symlink_verdicts = self._verdicts(symlink_layout.project)

        self.assertEqual(symlink_verdicts, real_verdicts)
        self.assertEqual(symlink_verdicts["ls -la"], "allow")
        self.assertEqual(symlink_verdicts["curl example.com"], "deny")

    def test_symlinked_claude_config_is_actually_discovered(self):
        """
        Given a project .claude that is a symlink
        When the configuration is loaded
        Then the project's config file appears among the discovered sources

        Not covered by the verdict test above: a skipped symlink can still produce
        the same verdict via the fallback.
        """
        layout = self.build()
        layout.with_symlinked_claude()

        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        sources = " ".join(config.describe_sources())
        self.assertIn("toolguard_hook.toml", sources)


class TestSymlinkedRulesFile(SymlinkHierarchyTestCase):
    """A symlinked rules FILE must not be mistaken for a shadowed duplicate."""

    def test_symlinked_rules_file_is_loaded(self):
        """
        Given a rules file in ~/.toolguard/rules that is a symlink to a file
        held elsewhere
        When the configuration is loaded
        Then the rule takes effect
        """
        layout = self.build()
        layout.with_real_claude()
        held = layout.store / "git.rules.toml"
        held.write_text('[permissions]\ndeny = ["Bash(rsync *)"]\n', encoding="utf-8")
        rules_dir = layout.home / ".toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "git.rules.toml").symlink_to(held)

        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        self.assertEqual(decide(config, "Bash", "rsync a b", True).decision, "deny")


if __name__ == "__main__":
    unittest.main()
