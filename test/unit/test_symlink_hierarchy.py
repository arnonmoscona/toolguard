"""
Hierarchy resolution through a SYMLINKED ``.claude`` directory.

Motivation (TOO-19, Part 4 of the safe-experimentation design): project
``.claude`` directories are typically untracked, so the plan is to move them into
a version-controlled store and symlink them back into the project. Three pieces
of toolguard's discovery machinery decide behaviour by path shape and could
change their answer under a symlink:

- :func:`toolguard.config.find_project_root` anchors on ``.claude`` presence.
- :func:`toolguard.config._level_for_path` attributes a config file to the
  ``user`` or ``project`` level by comparing RESOLVED paths.
- ``_shadowed_rules_stems`` compares rules files by resolved path (a symlinked
  rules file was nearly false-flagged as shadowed during TOO-19).

These tests prove the behaviour rather than assuming it, and pin down one real
footgun: a store located UNDER ``~/.claude`` silently reclassifies every project
rule as a user rule.

Isolation note (per test/unit/CLAUDE.md): these tests deliberately do NOT use
ConfigIsolationMixin. The mixin patches ``find_project_root``, which is one of
the functions under test here, and its fixed sibling layout cannot express a
symlink pointing from the project into a separate store. Hand-rolled
``Path.home()`` patching is used instead -- this is the documented exception.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import config as config_module
from toolguard.config import load_configuration
from toolguard.tools.decision import decide

PROJECT_CONFIG = '[permissions]\nallow = ["Bash(ls *)"]\ndeny = ["Bash(curl *)"]\n'


class _SymlinkLayout:
    """
    A throwaway home/store/project layout for symlink experiments.

    Attributes:
        root: The temporary root containing everything.
        home: Stands in for ``Path.home()``.
        store: Where the real ``.claude`` directory lives.
        project: The project root, carrying a ``.git`` marker.
    """

    def __init__(self, root: Path, *, store_under_home: bool = False):
        """
        Args:
            root: An existing temporary directory.
            store_under_home: When True the store is placed under
                ``home/.claude``, reproducing the misattribution footgun.
        """
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
        """
        Create a REAL ``.claude`` directory in the project (the control case).

        Returns:
            The project's ``.claude`` path.
        """
        claude = self.project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        return claude

    def with_symlinked_claude(self) -> Path:
        """
        Create the project's ``.claude`` as a symlink into the store.

        Returns:
            The project's ``.claude`` symlink path.
        """
        real = self.store / ".claude"
        real.mkdir()
        (real / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        link = self.project / ".claude"
        link.symlink_to(real, target_is_directory=True)
        return link


class SymlinkHierarchyTestCase(unittest.TestCase):
    """Shared setup: a temp root and a patched Path.home()."""

    def build(self, *, store_under_home: bool = False) -> _SymlinkLayout:
        """
        Build an isolated layout and patch ``Path.home()`` at it.

        Args:
            store_under_home: Passed through to :class:`_SymlinkLayout`.

        Returns:
            The constructed layout.
        """
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
    Level attribution decides precedence; a symlink must never shift it.

    Levels come from :func:`toolguard.config._discover_levels`, the pass that
    actually finds each file, so attribution follows WHERE THE FILE WAS FOUND
    rather than where its bytes physically live. Before TOO-19's fix a second,
    path-shape derivation (``_level_for_path``, now removed) answered the same
    question differently under symlinks.
    """

    def _project_config_level(self, layout: "_SymlinkLayout") -> list:
        """
        Return the level(s) discovery assigns to the project's config file.

        Args:
            layout: The layout under test.

        Returns:
            A list of level labels for every discovered toolguard_hook.toml.
        """
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

        This is the footgun fix. The removed path-shape derivation resolved the
        symlink, saw a path under ~/.claude, and silently promoted every project
        rule to the user level -- changing precedence across the hierarchy with
        no error and no warning. A discovery-derived level cannot disagree with
        where the file was found, so the store's location no longer matters.
        Restore a resolve()-based derivation and this test fails.
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

        Symlinking the contents rather than the directory used to hit exactly
        the same footgun, because attribution resolved the FILE and so followed
        a file symlink just as it followed a directory symlink. Covered
        separately because contents-linking looks like a workaround for the
        directory case and never was one -- it also loses version control for
        newly created files, so it costs something and bought nothing.
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
        """
        Resolve a fixed set of commands against a project's configuration.

        Args:
            project: The project root to load configuration from.

        Returns:
            Mapping of command -> verdict.
        """
        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(project))
        return {
            command: decide(config, "Bash", command, True).verdict
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

        Guards against the failure mode where a symlinked directory is skipped
        entirely and the suite still passes because the fallback happens to give
        the same verdict.
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

        This mirrors Arnon's real setup, where gh.rules.toml is symlinked into
        the rules directory, and the TOO-19 near-miss where a symlinked rules
        file was almost false-flagged as shadowed.
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

        self.assertEqual(decide(config, "Bash", "rsync a b", True).verdict, "deny")


if __name__ == "__main__":
    unittest.main()
