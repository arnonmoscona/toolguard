"""
Symlinks in the configuration path: project-root anchoring through a symlinked
``.claude``, level attribution, end-to-end verdicts, a symlinked rules file, and the
symlink resolution that :mod:`toolguard.normalization` applies to command tokens.

Isolation exception (`.claude/rules/test-config-isolation.md`): these tests do NOT
use ConfigIsolationMixin. It patches ``find_project_root``, one of the functions
under test, and its fixed sibling layout cannot express a symlink pointing from the
project into a separate store; ``Path.home()`` is patched by hand instead. The
fixture puts the project UNDER the patched home so every walk-up terminates inside
the fixture -- a project beside home walks on to ``/``, and would then see any real
``/tmp/.claude`` or ``/.claude``.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import config as config_module
from toolguard.api import decide
from toolguard.config import load_configuration

PROJECT_CONFIG = '[permissions]\nallow = ["Bash(ls *)"]\ndeny = ["Bash(curl *)"]\n'

USER_CONFIG = '[permissions]\nallow = ["Bash(git status)"]\n'

#: Commands probed end-to-end: one allowed by PROJECT_CONFIG, one denied, one matched
#: by no rule at all -- so a lost config is distinguishable from a rule match.
PROBE_COMMANDS = ("ls -la", "curl example.com", "rsync a b")

#: What PROJECT_CONFIG must produce for PROBE_COMMANDS: (decision, matched_rule).
#: ``matched_rule`` is the part a fail-closed or fallback verdict cannot fake -- it is
#: None whenever no single rule decided (shape 25, proposed ticket 31).
EXPECTED_VERDICTS = {
    "ls -la": ("allow", "ls *"),
    "curl example.com": ("deny", "curl *"),
    "rsync a b": ("ask", None),
}


class _SymlinkLayout:
    """A throwaway home/store/project layout for symlink experiments."""

    def __init__(
        self, root: Path, *, store_under_home: bool = False, git_marker: bool = True
    ):
        """Build the layout under ``root``; ``git_marker`` adds a ``.git`` anchor to the project."""
        self.root = root
        self.home = root / "home"
        (self.home / ".claude").mkdir(parents=True)
        if store_under_home:
            self.store = self.home / ".claude" / "store" / "toolguard"
        else:
            self.store = root / "store" / "toolguard"
        self.store.mkdir(parents=True)
        self.project = self.new_project("project", git_marker=git_marker)

    def new_project(self, name: str, *, git_marker: bool = True) -> Path:
        """Create another project directory under ``home/work`` and return it."""
        project = self.home / "work" / name
        project.mkdir(parents=True)
        if git_marker:
            (project / ".git").mkdir()
        return project

    def with_user_config(self) -> Path:
        """Write a user-level config into ``~/.claude`` and return its path."""
        path = self.home / ".claude" / "toolguard_hook.toml"
        path.write_text(USER_CONFIG, encoding="utf-8")
        return path

    def with_real_claude(self, project: Path = None) -> Path:
        """Create a REAL ``.claude`` directory holding PROJECT_CONFIG and return it."""
        project = project or self.project
        claude = project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        return claude

    def with_symlinked_claude(self, project: Path = None) -> Path:
        """Create the project's ``.claude`` as a symlink into the store and return the link."""
        project = project or self.project
        real = self.store / f"{project.name}.claude"
        real.mkdir(parents=True)
        (real / "toolguard_hook.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
        link = project / ".claude"
        link.symlink_to(real, target_is_directory=True)
        return link


class SymlinkHierarchyTestCase(unittest.TestCase):
    """Shared setup: a temp root and a patched Path.home()."""

    def build(self, **kwargs) -> _SymlinkLayout:
        """Build an isolated layout, patch ``Path.home()`` at it, and return it."""
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        layout = _SymlinkLayout(root, **kwargs)
        self.enterContext(patch.object(Path, "home", return_value=layout.home))
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        config_module._parse_config_file_cached.cache_clear()
        self.addCleanup(config_module._parse_config_file_cached.cache_clear)
        return layout

    def verdicts(self, project: Path) -> dict:
        """Resolve PROBE_COMMANDS against a project, command -> (decision, matched_rule)."""
        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(project))
        resolved = {}
        for command in PROBE_COMMANDS:
            verdict = decide(config, "Bash", command, True)
            resolved[command] = (verdict.decision, verdict.matched_rule)
        return resolved


class TestProjectRootThroughSymlink(SymlinkHierarchyTestCase):
    """
    A symlinked ``.claude`` must anchor the project root exactly as a real one does.

    Every project here is built WITHOUT the ``.git`` marker: with it, ``.git`` anchors
    the root on its own and the symlink is never consulted.
    """

    def test_symlinked_claude_alone_anchors_the_project_root(self):
        """
        Given a project whose only marker is a SYMLINKED .claude directory
        When find_project_root runs from a nested directory inside that project
        Then it returns the project directory
        """
        layout = self.build(git_marker=False)
        layout.with_symlinked_claude()
        nested = layout.project / "src" / "pkg"
        nested.mkdir(parents=True)

        found = config_module.find_project_root(nested)

        self.assertEqual(found, layout.project)

    def test_without_the_symlink_the_root_escapes_to_the_home_directory(self):
        """
        Given the same marker-less project with NO .claude at all
        When find_project_root runs from a nested directory inside it
        Then the walk climbs past the project and anchors on ~ instead

        The negative case for the test above: it establishes that the fixture can
        produce a non-project answer, so the symlink there is load-bearing.
        """
        layout = self.build(git_marker=False)
        nested = layout.project / "src" / "pkg"
        nested.mkdir(parents=True)

        found = config_module.find_project_root(nested)

        self.assertEqual(found, layout.home)
        self.assertNotEqual(found, layout.project)

    def test_real_and_symlinked_claude_projects_each_anchor_on_themselves(self):
        """
        Given two marker-less projects under one home, one with a real .claude and
        one with a symlinked .claude
        When find_project_root runs in each
        Then each returns its own project directory, and the two differ
        """
        layout = self.build(git_marker=False)
        real_project = layout.new_project("real", git_marker=False)
        linked_project = layout.new_project("linked", git_marker=False)
        layout.with_real_claude(real_project)
        layout.with_symlinked_claude(linked_project)

        self.assertEqual(config_module.find_project_root(real_project), real_project)
        self.assertEqual(
            config_module.find_project_root(linked_project), linked_project
        )
        self.assertNotEqual(real_project, linked_project)

    def test_dangling_claude_symlink_does_not_anchor(self):
        """
        Given a project whose .claude is a symlink to a target that does not exist
        When find_project_root runs from inside it
        Then the dangling link is not treated as a marker and the root escapes to ~
        """
        layout = self.build(git_marker=False)
        (layout.project / ".claude").symlink_to(
            layout.store / "absent", target_is_directory=True
        )

        found = config_module.find_project_root(layout.project)

        self.assertEqual(found, layout.home)

    def test_project_reached_through_a_symlinked_directory_anchors_on_the_real_path(
        self,
    ):
        """
        Given a project reachable both directly and through a symlink to it
        When find_project_root runs from inside the SYMLINKED path
        Then it returns the real project directory, not the symlinked spelling

        The permission decision is therefore attributed to one canonical root however
        the project was reached.
        """
        layout = self.build(git_marker=False)
        layout.with_symlinked_claude()
        (layout.project / "src").mkdir()
        link = layout.home / "work" / "project-link"
        link.symlink_to(layout.project, target_is_directory=True)

        found = config_module.find_project_root(link / "src")

        self.assertEqual(found, layout.project)
        self.assertNotEqual(found, link)


class TestLevelAttributionThroughSymlink(SymlinkHierarchyTestCase):
    """
    Level attribution decides precedence, and a symlink must never shift it. Levels
    come from :func:`toolguard.config._discover_levels`, the pass that finds each
    file, so attribution follows where the file was FOUND, not where its bytes live.
    """

    def _config_levels(self, layout: "_SymlinkLayout") -> dict:
        """Map every discovered toolguard_hook.toml to the level it was attributed."""
        config_module._parse_config_file_cached.cache_clear()
        return {
            path: level
            for path, _stype, _fmt, _spec, level in config_module._discover_levels(
                layout.project
            )
            if path.name == "toolguard_hook.toml"
        }

    def test_symlinked_project_config_is_still_attributed_to_the_project_level(self):
        """
        Given a project .claude symlinked to a store OUTSIDE ~/.claude, and a
        user-level config in ~/.claude
        When the hierarchy levels are discovered
        Then the project config is attributed to 'project' and the user config to
        'user', so precedence is unchanged
        """
        layout = self.build()
        claude = layout.with_symlinked_claude()
        user_config = layout.with_user_config()

        levels = self._config_levels(layout)

        self.assertEqual(
            levels,
            {claude / "toolguard_hook.toml": "project", user_config: "user"},
        )

    def test_real_directory_control_is_attributed_to_the_project_level(self):
        """
        Given a project with a REAL .claude directory
        When the hierarchy levels are discovered
        Then the config is attributed to 'project', establishing the control
        """
        layout = self.build()
        claude = layout.with_real_claude()

        levels = self._config_levels(layout)

        self.assertEqual(levels, {claude / "toolguard_hook.toml": "project"})

    def test_store_under_home_claude_is_still_a_project_level_config(self):
        """
        Given a project .claude symlinked to a store located UNDER ~/.claude, and a
        user-level config in ~/.claude
        When the hierarchy levels are discovered
        Then the project config is STILL attributed to 'project' and stays distinct
        from the user config beside its own store
        """
        layout = self.build(store_under_home=True)
        claude = layout.with_symlinked_claude()
        user_config = layout.with_user_config()

        levels = self._config_levels(layout)

        self.assertEqual(
            levels,
            {claude / "toolguard_hook.toml": "project", user_config: "user"},
        )

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

        levels = self._config_levels(layout)

        self.assertEqual(levels, {claude / "toolguard_hook.toml": "project"})

    def test_claude_symlinked_onto_the_user_directory_is_discovered_once(self):
        """
        Given a project .claude that is a symlink to ~/.claude itself
        When the hierarchy levels are discovered
        Then the one real file is discovered once, under the project spelling

        The de-duplication compares RESOLVED directories; comparing the literal paths
        would admit the same file twice, once per level.
        """
        layout = self.build()
        (layout.home / ".claude" / "toolguard_hook.toml").write_text(
            PROJECT_CONFIG, encoding="utf-8"
        )
        (layout.project / ".claude").symlink_to(
            layout.home / ".claude", target_is_directory=True
        )

        levels = self._config_levels(layout)

        self.assertEqual(
            levels,
            {layout.project / ".claude" / "toolguard_hook.toml": "project"},
        )


class TestEndToEndResolutionThroughSymlink(SymlinkHierarchyTestCase):
    """The verdicts themselves must be identical through a symlink."""

    def test_symlinked_claude_produces_the_same_verdicts_as_a_real_directory(self):
        """
        Given two projects under one home with identical configs, one behind a
        symlinked .claude and one in a real .claude directory
        When PROBE_COMMANDS are resolved against each
        Then both produce the expected decision AND the expected matching rule
        """
        layout = self.build()
        real_project = layout.new_project("real")
        linked_project = layout.new_project("linked")
        layout.with_real_claude(real_project)
        layout.with_symlinked_claude(linked_project)

        real_verdicts = self.verdicts(real_project)
        symlink_verdicts = self.verdicts(linked_project)

        self.assertEqual(symlink_verdicts, real_verdicts)
        self.assertEqual(symlink_verdicts, EXPECTED_VERDICTS)

    def test_symlinked_claude_config_is_actually_discovered(self):
        """
        Given a project .claude that is a symlink
        When the configuration is loaded
        Then the project's own config path appears among the discovered sources

        Not covered by the verdict test above: a skipped symlink can still produce
        the same verdict via the fallback.
        """
        layout = self.build()
        claude = layout.with_symlinked_claude()

        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        sources = " ".join(config.describe_sources())
        self.assertIn(str(claude / "toolguard_hook.toml"), sources)


class TestSymlinkedRulesFile(SymlinkHierarchyTestCase):
    """A symlinked rules FILE must load, and must not be mistaken for a shadowed duplicate."""

    def _shadowing_issues(self, config) -> list:
        """The validation issues that report one rules file shadowing another."""
        return [i.message for i in config.validation_issues() if "shadows" in i.message]

    def test_symlinked_rules_file_is_loaded(self):
        """
        Given a rules file in ~/.toolguard/rules that is a symlink to a file
        held elsewhere
        When the configuration is loaded
        Then the rule takes effect, and it is that rule that decides
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

        verdict = decide(config, "Bash", "rsync a b", True)
        self.assertEqual(verdict.decision, "deny")
        self.assertEqual(verdict.matched_rule, "rsync *")

    def test_one_file_linked_into_both_rules_directories_is_not_shadowed(self):
        """
        Given one real rules file symlinked into BOTH candidate rules directories
        under the same stem
        When the configuration is loaded
        Then no shadowing is reported and the rule still decides
        """
        layout = self.build()
        layout.with_real_claude()
        held = layout.store / "git.rules.toml"
        held.write_text('[permissions]\ndeny = ["Bash(rsync *)"]\n', encoding="utf-8")
        for rules_dir in (
            layout.home / ".config" / "toolguard" / "rules",
            layout.home / ".toolguard" / "rules",
        ):
            rules_dir.mkdir(parents=True)
            (rules_dir / "git.rules.toml").symlink_to(held)

        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        self.assertEqual(self._shadowing_issues(config), [])
        self.assertEqual(decide(config, "Bash", "rsync a b", True).decision, "deny")

    def test_two_different_files_under_one_stem_are_reported_as_shadowed(self):
        """
        Given two DIFFERENT rules files sharing a stem across the two rules
        directories
        When the configuration is loaded
        Then the collision is reported and the legacy directory's rule is dropped

        The control for the test above: shadowing is reportable, so its absence
        there is a statement about the symlink and not about the machinery.
        """
        layout = self.build()
        layout.with_real_claude()
        xdg_dir = layout.home / ".config" / "toolguard" / "rules"
        legacy_dir = layout.home / ".toolguard" / "rules"
        xdg_dir.mkdir(parents=True)
        legacy_dir.mkdir(parents=True)
        (xdg_dir / "git.rules.toml").write_text(
            '[permissions]\ndeny = ["Bash(rsync *)"]\n', encoding="utf-8"
        )
        (legacy_dir / "git.rules.toml").write_text(
            '[permissions]\ndeny = ["Bash(scp *)"]\n', encoding="utf-8"
        )

        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        self.assertEqual(len(self._shadowing_issues(config)), 1)
        self.assertEqual(decide(config, "Bash", "rsync a b", True).decision, "deny")
        self.assertEqual(decide(config, "Bash", "scp a b", True).decision, "ask")


class TestSymlinkResolutionInCommandMatching(SymlinkHierarchyTestCase):
    """
    Matching resolves a symlinked path token to its target, so a rule written against
    the real file governs every name that reaches it.
    """

    def _project_with_link(self, layout: "_SymlinkLayout") -> tuple:
        """Deny the store's secret.txt by its real path; return (config, link, decoy)."""
        secret = layout.store / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        decoy = layout.store / "harmless.txt"
        decoy.write_text("harmless", encoding="utf-8")
        link = layout.project / "link.txt"
        link.symlink_to(secret)
        claude = layout.project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(
            f'[permissions]\ndeny = ["Bash(cat {secret})"]\nallow = ["Bash(cat *)"]\n',
            encoding="utf-8",
        )
        config_module._parse_config_file_cached.cache_clear()
        return load_configuration(str(layout.project)), link, decoy

    def test_deny_rule_on_the_target_matches_a_command_naming_the_symlink(self):
        """
        Given a deny rule naming a file by its real path, and a symlink to that file
        When a command names the SYMLINK, the real path, and an unrelated real file
        Then the first two are denied by that rule and the third is allowed

        The third case is what makes this a test of resolution rather than of
        matching: an already-canonical path that is not the target must not be denied.
        """
        layout = self.build()
        config, link, decoy = self._project_with_link(layout)

        via_link = decide(config, "Bash", f"cat {link}", True)
        via_target = decide(config, "Bash", f"cat {layout.store / 'secret.txt'}", True)
        via_decoy = decide(config, "Bash", f"cat {decoy}", True)

        self.assertEqual(via_link.decision, "deny")
        self.assertEqual(via_link.matched_rule, via_target.matched_rule)
        self.assertEqual(via_target.decision, "deny")
        self.assertEqual(via_decoy.decision, "allow")

    def test_repointing_the_symlink_changes_the_verdict_for_the_same_command(self):
        """
        Given a command naming a symlink that resolves to a denied file
        When the symlink is repointed at a harmless file and the SAME command string
        is re-decided against the SAME configuration
        Then the verdict flips from deny to allow

        Characterisation, not endorsement: matching reads live filesystem state, so a
        verdict describes the target at match time only. That is the observable half
        of the check-to-use race :mod:`toolguard.resolve` documents; nothing else in
        the suite pins it.
        """
        layout = self.build()
        config, link, decoy = self._project_with_link(layout)
        command = f"cat {link}"

        before = decide(config, "Bash", command, True)
        link.unlink()
        link.symlink_to(decoy)
        after = decide(config, "Bash", command, True)

        self.assertEqual(before.decision, "deny")
        self.assertEqual(after.decision, "allow")

    def test_a_dangling_symlink_does_not_evade_a_deny_rule_on_its_target(self):
        """
        Given a deny rule naming a file that does not exist yet, and a symlink
        pointing at that file
        When a creating command (cp) names the symlink
        Then the command is denied, as it is when it names the target directly

        EXPECTED TO FAIL at the time of writing -- an asserted defect, not a
        regression. :func:`toolguard.normalization.normalize_path` resolves a
        symlink only when it ``exists()``, and ``exists()`` follows the link, so a
        DANGLING link is left as its own spelling and matches no rule written
        against the target. Measured: the dangling link is allowed by the
        catch-all while the same write through a LIVE link, and the target path
        itself, are denied -- and the write creates exactly the protected file.
        """
        layout = self.build()
        protected = layout.store / "not_yet_there.toml"
        live = layout.store / "already_there.toml"
        live.write_text("x", encoding="utf-8")
        dangling_link = layout.project / "dangling.toml"
        dangling_link.symlink_to(protected)
        live_link = layout.project / "live.toml"
        live_link.symlink_to(live)
        claude = layout.project / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(
            "[permissions]\n"
            f'deny = ["Bash(cp * {protected})", "Bash(cp * {live})"]\n'
            'allow = ["Bash(cp *)"]\n',
            encoding="utf-8",
        )
        config_module._parse_config_file_cached.cache_clear()
        config = load_configuration(str(layout.project))

        via_live = decide(config, "Bash", f"cp payload.txt {live_link}", True)
        direct = decide(config, "Bash", f"cp payload.txt {protected}", True)
        via_dangling = decide(config, "Bash", f"cp payload.txt {dangling_link}", True)

        self.assertEqual(via_live.decision, "deny")
        self.assertEqual(direct.decision, "deny")
        self.assertEqual(via_dangling.decision, "deny")


if __name__ == "__main__":
    unittest.main()
