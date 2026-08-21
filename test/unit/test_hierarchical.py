"""Hierarchical config discovery, more-specific-wins resolution, project-root-relative paths."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.compound import ResolveOneResult, resolve_compound_permission
from toolguard.config import _discover_levels, load_configuration
from toolguard.permission_resolution import resolve_command_permission


def _write(claude_dir: Path, filename: str, content: str) -> None:
    """Create a .claude directory (if needed) and write a config file in it."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / filename).write_text(content)


class TestHierarchicalTraversal(ConfigIsolationMixin, unittest.TestCase):
    """Test hierarchical config-file discovery across directory levels."""

    def test_walk_collects_multiple_ancestor_levels(self):
        """
        Given a project nested several directories below ~ with .claude configs
            at the project, an intermediate ancestor, and ~ itself
        When _discover_levels walks the hierarchy with the toggle defaulting on
        Then exactly those three levels are discovered, and their specificity
            indices STRICTLY increase project < intermediate < ~, so the
            intermediate ancestor is its own tier rather than collapsing into
            the user level
        """
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(project / ".claude", "toolguard_hook.toml", "permissions = {}\n")
        _write(home / "a" / ".claude", "toolguard_hook.toml", "permissions = {}\n")
        _write(home / ".claude", "toolguard_hook.toml", "permissions = {}\n")

        levels = _discover_levels(project)

        specs = {
            path.parent.parent.name: spec for path, _stype, _fmt, spec, _lvl in levels
        }
        self.assertEqual({"proj", "a", home.name}, set(specs))
        self.assertEqual(specs["proj"], 0)
        # Strict, not just "> project": a shared index would merge the
        # intermediate ancestor into the user level, changing which rule wins.
        self.assertLess(specs["proj"], specs["a"])
        self.assertLess(specs["a"], specs[home.name])
        home_spec = max(spec for _p, _s, _f, spec, _lvl in levels)
        self.assertEqual(specs[home.name], home_spec)

    def test_toggle_off_uses_only_project_and_user(self):
        """
        Given hierarchical_configuration = false in the project-level hook config
            and config files at project, an intermediate ancestor, and ~
        When _discover_levels runs
        Then only the project and user levels are collected (the intermediate
            ancestor is skipped), matching the pre-Phase-2 two-level behavior
        """
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            "hierarchical_configuration = false\npermissions = {}\n",
        )
        _write(home / "a" / ".claude", "toolguard_hook.toml", "permissions = {}\n")
        _write(home / ".claude", "toolguard_hook.toml", "permissions = {}\n")

        levels = _discover_levels(project)

        dirs = {path.parent.parent.name for path, _s, _f, _spec, _lvl in levels}
        self.assertIn("proj", dirs)
        self.assertIn(home.name, dirs)
        self.assertNotIn("a", dirs)

    def test_toggle_on_explicit_walks_full_hierarchy(self):
        """
        Given hierarchical_configuration = true explicitly in the project config
        When _discover_levels runs with an intermediate ancestor present
        Then the intermediate ancestor level is included in the walk
        """
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            "hierarchical_configuration = true\npermissions = {}\n",
        )
        _write(home / "a" / ".claude", "toolguard_hook.toml", "permissions = {}\n")

        levels = _discover_levels(project)

        dirs = {path.parent.parent.name for path, _s, _f, _spec, _lvl in levels}
        self.assertIn("a", dirs)

    def test_project_outside_home_still_includes_user(self):
        """
        Given a project that is NOT located under ~ (a sibling tree)
        When _discover_levels runs
        Then the project level is collected AND ~/.claude is always included as
            the least-specific level
        """
        home, project = self.isolate_config_environment()
        _write(project / ".claude", "toolguard_hook.toml", "permissions = {}\n")
        _write(home / ".claude", "toolguard_hook.toml", "permissions = {}\n")

        levels = _discover_levels(project)

        paths = [str(path) for path, _s, _f, _spec, _lvl in levels]
        self.assertTrue(any(str(project) in p for p in paths))
        self.assertTrue(any(str(home / ".claude") in p for p in paths))
        user_specs = [
            spec
            for path, _s, _f, spec, _lvl in levels
            if str(home / ".claude") in str(path)
        ]
        max_spec = max(spec for _p, _s, _f, spec, _lvl in levels)
        self.assertEqual(user_specs[0], max_spec)

    def test_walk_stops_at_home(self):
        """
        Given a project located directly under ~ with a .claude above ~ as well
        When _discover_levels walks upward
        Then the walk never ascends above ~ (no level above home is collected)
        """
        # Hand-rolled: ConfigIsolationMixin cannot represent a .claude ABOVE home.
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home" / "user"
            home.mkdir(parents=True)
            project = home / "proj"
            project.mkdir()
            (project / ".git").mkdir()

            _write(project / ".claude", "toolguard_hook.toml", "permissions = {}\n")
            _write(home / ".claude", "toolguard_hook.toml", "permissions = {}\n")
            _write(
                root / "home" / ".claude", "toolguard_hook.toml", "permissions = {}\n"
            )

            with patch("toolguard.config.find_project_root", return_value=project):
                with patch("toolguard.config.Path.home", return_value=home):
                    levels = _discover_levels(project)

            paths = [str(path) for path, _s, _f, _spec, _lvl in levels]
            self.assertFalse(any(str(root / "home" / ".claude") in p for p in paths))

    def test_within_level_toml_preferred_over_json(self):
        """
        Given a single .claude level containing both toolguard_hook.toml and
            toolguard_hook.json
        When _discover_levels collects that level
        Then the TOML file is used and the JSON is not (within-level TOML wins)
        """
        _home, project = self.isolate_config_environment()
        cl = project / ".claude"
        _write(cl, "toolguard_hook.toml", "permissions = {}\n")
        _write(cl, "toolguard_hook.json", '{"permissions": {}}')

        levels = _discover_levels(project)

        hook_files = [
            (path, fmt)
            for path, stype, fmt, _spec, _lvl in levels
            if stype == "toolguard_hook"
        ]
        project_hook = [(p, f) for p, f in hook_files if str(project) in str(p)]
        self.assertEqual(len(project_hook), 1)
        self.assertEqual(project_hook[0][1], "toml")


class TestDiscoveredHierarchyPrecedence(ConfigIsolationMixin, unittest.TestCase):
    """Test that the order files are DISCOVERED in is the order they win in."""

    def _resolve(self, project, command):
        """Resolve a Bash command against a configuration loaded from real files."""
        config = load_configuration(project)
        return resolve_command_permission(config, "Bash", command).decision

    def test_project_file_beats_ancestor_and_user_files(self):
        """
        Given real .claude files at the project, an intermediate ancestor and ~,
            where the project ALLOWS 'git *' and both ancestors DENY it
        When the command is resolved through the loaded configuration
        Then the project file's allow wins
        """
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(git *)"]\n',
        )
        _write(
            home / "a" / ".claude",
            "toolguard_hook.toml",
            '[permissions]\ndeny = ["Bash(git *)"]\n',
        )
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            '[permissions]\ndeny = ["Bash(git *)"]\n',
        )

        self.assertEqual(self._resolve(project, "git status"), "allow")

    def test_ancestor_file_beats_user_file(self):
        """
        Given a project file that matches nothing for the command, an
            intermediate ancestor that DENIES 'git *' and ~ that ALLOWS it
        When the command is resolved through the loaded configuration
        Then the intermediate ancestor's deny wins over the user level
        """
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(ls *)"]\n',
        )
        _write(
            home / "a" / ".claude",
            "toolguard_hook.toml",
            '[permissions]\ndeny = ["Bash(git *)"]\n',
        )
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(git *)"]\n',
        )

        self.assertEqual(self._resolve(project, "git status"), "deny")


class TestMoreSpecificWinsResolution(unittest.TestCase):
    """Test the more-specific-wins permission resolution cascade."""

    def _config(self, *level_specs):
        """Build a Configuration from per-level (allow, deny) Bash pattern pairs, most-specific first."""
        from toolguard.config import ConfigLayer, Configuration, Provenance
        from types import MappingProxyType

        layers = []
        for spec_index, (allow, deny) in enumerate(level_specs):
            content = {
                "permissions": {
                    "allow": [f"Bash({p})" for p in allow],
                    "deny": [f"Bash({p})" for p in deny],
                }
            }
            prov = Provenance(
                "project",
                "toolguard_hook",
                "toml",
                Path(f"/fake/{spec_index}.toml"),
                spec_index,
            )
            layers.append(
                ConfigLayer(provenance=prov, content=MappingProxyType(content))
            )
        return Configuration(layers=tuple(layers))

    def _resolve(self, config, command):
        """Resolve one command through the Bash level cascade; return ``(decision, reason)``."""
        resolved = resolve_command_permission(config, "Bash", command)
        return resolved.decision, resolved.reason

    def test_child_allow_overrides_parent_deny(self):
        """
        Given a child (more-specific) level that allows 'git *' and a parent
            level that denies 'git *'
        When 'git status' is resolved under more-specific-wins
        Then the child's allow wins (the parent's deny never gets consulted)
        """
        config = self._config((["git *"], []), ([], ["git *"]))
        decision, _reason = self._resolve(config, "git status")
        self.assertEqual(decision, "allow")

    def test_child_deny_overrides_parent_allow(self):
        """
        Given a child level that denies 'rm *' and a parent level that allows it
        When 'rm -rf /' is resolved under more-specific-wins
        Then the child's deny wins
        """
        config = self._config(([], ["rm *"]), (["rm *"], []))
        decision, reason = self._resolve(config, "rm -rf /")
        self.assertEqual(decision, "deny")
        self.assertIn("deny pattern", reason)

    def test_no_match_at_child_falls_through_to_parent(self):
        """
        Given a child level that matches nothing for the command and a parent
            level that allows it
        When the command is resolved
        Then the cascade falls through to the parent and the command is allowed
        """
        config = self._config((["ls *"], []), (["git *"], []))
        decision, _reason = self._resolve(config, "git status")
        self.assertEqual(decision, "allow")

    def test_no_match_anywhere_falls_through_to_no_match_fallback(self):
        """
        Given no level matches the command (the cascade exhausts every level)
        When it is resolved
        Then the result falls through to the shared no_match_fallback
            resolution -- 'ask' by default (TOO-15). The reason assertion is
            load-bearing: the "no rules configured anywhere" branch also
            answers 'ask', and it words the reason differently.
        """
        config = self._config((["ls *"], []), (["cat *"], []))
        decision, reason = self._resolve(config, "git status")
        self.assertEqual(decision, "ask")
        self.assertIn("does not match any allow patterns", reason)

    def test_deny_first_within_a_single_level(self):
        """
        Given one level that both allows 'git *' and denies 'git push *'
        When 'git push origin' is resolved
        Then deny-first within the level denies the command
        """
        config = self._config(
            (["git *"], ["git push *"]),
        )
        decision, _reason = self._resolve(config, "git push origin")
        self.assertEqual(decision, "deny")

    def test_three_level_cascade_first_match_wins(self):
        """
        Given three levels where only the middle level matches the command
        When the command is resolved most-specific first
        Then the middle level's decision wins and the least-specific level is
            never consulted
        """
        config = self._config(
            (["ls *"], []),
            ([], ["git *"]),
            (["git *"], []),
        )
        decision, _reason = self._resolve(config, "git status")
        self.assertEqual(decision, "deny")

    def test_compound_each_subcommand_cascades_independently(self):
        """
        Given a compound command 'git status && rm -rf /' where the child level
            allows git and the parent level denies rm
        When each sub-command is cascaded independently and combined
        Then the compound is denied because one sub-command resolves to deny
        """
        config = self._config((["git *"], []), ([], ["rm *"]))

        def _resolve_one(sub):
            resolved = resolve_command_permission(config, "Bash", sub)
            return ResolveOneResult(
                resolved.decision, resolved.reason, resolved.additional_context
            )

        _verdict = resolve_compound_permission("git status && rm -rf /", _resolve_one)
        decision, _reason, _context = (
            _verdict.decision,
            _verdict.reason,
            _verdict.additional_context,
        )
        self.assertEqual(decision, "deny")

    def test_compound_allowed_iff_all_subcommands_allowed(self):
        """
        Given a compound command whose every sub-command is allowed at some level
        When resolved through independent per-sub-command cascades
        Then the compound is allowed, and EVERY sub-command was cascaded --
            an allow reached without consulting them all is not this verdict
        """
        config = self._config(
            (["git *", "ls *"], []),
        )
        cascaded = []

        def _resolve_one(sub):
            cascaded.append(sub)
            resolved = resolve_command_permission(config, "Bash", sub)
            return ResolveOneResult(
                resolved.decision, resolved.reason, resolved.additional_context
            )

        _verdict = resolve_compound_permission("git status && ls -l", _resolve_one)
        decision, _reason, _context = (
            _verdict.decision,
            _verdict.reason,
            _verdict.additional_context,
        )
        self.assertEqual(decision, "allow")
        self.assertEqual(["git status", "ls -l"], cascaded)


class TestProjectRootRelativePaths(ConfigIsolationMixin, unittest.TestCase):
    """Test that relative config paths resolve against the project root."""

    def _config_with_backup_dir(self, level_dir_name, backup_dir, home, project):
        """Write a toolguard_hook.toml declaring a relative backup_dir at the requested level."""
        target = {
            "project": project / ".claude",
            "intermediate": home / "a" / ".claude",
            "user": home / ".claude",
        }[level_dir_name]
        _write(
            target,
            "toolguard_hook.toml",
            f'[config_sync]\nbackup_dir = "{backup_dir}"\n',
        )
        if level_dir_name != "project":
            _write(project / ".claude", "toolguard_hook.toml", "permissions = {}\n")

    def _resolve_backup(self, level_name):
        """Resolve config_sync.backup_dir declared at the given level."""
        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        self._config_with_backup_dir(level_name, "my-backups", home, project)
        config = load_configuration(project)
        resolved = config.resolve_config_path(config.scalar("config_sync.backup_dir"))
        return resolved, project

    def test_relative_backup_dir_at_project_level(self):
        """
        Given a relative backup_dir declared at the project level
        When it is resolved
        Then it anchors to <project_root>/my-backups
        """
        resolved, project = self._resolve_backup("project")
        self.assertEqual(resolved, str(project / "my-backups"))

    def test_relative_backup_dir_at_intermediate_level(self):
        """
        Given a relative backup_dir declared at an intermediate ancestor level
        When it is resolved
        Then it still anchors to <project_root>/my-backups (NOT the ancestor dir)
        """
        resolved, project = self._resolve_backup("intermediate")
        self.assertEqual(resolved, str(project / "my-backups"))

    def test_relative_backup_dir_at_user_level(self):
        """
        Given a relative backup_dir declared at the user (~) level
        When it is resolved
        Then it still anchors to <project_root>/my-backups (NOT ~/.claude)
        """
        resolved, project = self._resolve_backup("user")
        self.assertEqual(resolved, str(project / "my-backups"))

    def test_absolute_path_unchanged(self):
        """
        Given an absolute config path, including a non-normalised one
        When resolve_config_path runs
        Then the path is returned BYTE-identical -- not merely equivalent, so
            the early return is what produces it rather than the project-root
            join, which silently normalises an absolute right operand away
        """
        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        self.assertEqual(config.resolve_config_path("/var/backups"), "/var/backups")
        self.assertEqual(config.resolve_config_path("/var//backups/"), "/var//backups/")

    def test_tilde_path_unchanged(self):
        """
        Given a ~-prefixed config path
        When resolve_config_path runs
        Then the path is returned unchanged (tilde expansion happens downstream)
        """
        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        self.assertEqual(config.resolve_config_path("~/backups"), "~/backups")


class TestRelativeFilePathPatterns(ConfigIsolationMixin, unittest.TestCase):
    """Test that relative Read/Write/Edit patterns anchor to the project root."""

    def _resolve_read(self, level_name):
        """Resolve a Read of <project_root>/src/x.py against a relative pattern at the given level."""
        from toolguard.hook import resolve_file_path_permission_detailed

        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        target = {
            "project": project / ".claude",
            "intermediate": home / "a" / ".claude",
            "user": home / ".claude",
        }[level_name]
        _write(
            target,
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Read(src/**)"]\n',
        )
        if level_name != "project":
            _write(project / ".claude", "toolguard_hook.toml", "permissions = {}\n")

        target_file = str(project / "src" / "x.py")
        config = load_configuration(project)
        result = resolve_file_path_permission_detailed("Read", target_file, config)
        return result.decision

    def test_relative_read_pattern_at_project_level(self):
        """
        Given a relative Read pattern 'src/**' declared at the project level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (pattern anchored to the project root)
        """
        self.assertEqual(self._resolve_read("project"), "allow")

    def test_relative_read_pattern_at_intermediate_level(self):
        """
        Given a relative Read pattern declared at an intermediate ancestor level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (anchored to the project root, not the ancestor dir)
        """
        self.assertEqual(self._resolve_read("intermediate"), "allow")

    def test_relative_read_pattern_at_user_level(self):
        """
        Given a relative Read pattern declared at the user (~) level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (anchored to the project root, not ~/.claude)
        """
        self.assertEqual(self._resolve_read("user"), "allow")


class TestAnchorFilePattern(ConfigIsolationMixin, unittest.TestCase):
    """Test extended-syntax handling in project-root pattern anchoring."""

    def test_glob_prefix_relative_body_is_anchored(self):
        """
        Given a relative file pattern carrying a [glob] prefix
        When _anchor_file_pattern runs
        Then the [glob] prefix is preserved and the relative body is anchored to
            the project root
        """
        from toolguard.file_matching import _anchor_file_pattern

        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        result = _anchor_file_pattern("[glob]src/**", config, extended_syntax=True)
        self.assertEqual(result, f"[glob]{project / 'src/**'}")

    def test_regex_prefix_left_untouched(self):
        """
        Given a [regex] file pattern (a regex, not a path)
        When _anchor_file_pattern runs
        Then the pattern is returned unchanged (never path-joined)
        """
        from toolguard.file_matching import _anchor_file_pattern

        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        result = _anchor_file_pattern("[regex]^src/.*", config, extended_syntax=True)
        self.assertEqual(result, "[regex]^src/.*")

    def test_absolute_pattern_left_untouched(self):
        """
        Given an absolute file pattern, including a non-normalised one
        When _anchor_file_pattern runs
        Then the pattern is returned BYTE-identical -- the project-root join
            would normalise it away rather than leave it alone (see
            test_absolute_path_unchanged)
        """
        from toolguard.file_matching import _anchor_file_pattern

        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        result = _anchor_file_pattern("/etc/**", config, extended_syntax=True)
        self.assertEqual(result, "/etc/**")
        trailing = _anchor_file_pattern("/etc/sub/**/", config, extended_syntax=True)
        self.assertEqual(trailing, "/etc/sub/**/")

    def test_tilde_pattern_left_untouched(self):
        """
        Given a ~-prefixed file pattern
        When _anchor_file_pattern runs
        Then the pattern is returned unchanged (tilde expansion happens downstream,
            it is NOT anchored to the project root)
        """
        from toolguard.file_matching import _anchor_file_pattern

        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        result = _anchor_file_pattern("~/secrets/**", config, extended_syntax=True)
        self.assertEqual(result, "~/secrets/**")

    def test_relative_pattern_does_not_match_same_name_outside_project(self):
        """
        Given a relative Read allow pattern 'src/**' anchored to the project root
        When a Read targets <project_root>/src/x.py and a same-named
            'src/x.py' OUTSIDE the project root
        Then the inside path is ALLOWED and the outside path is not (it falls
            through to no_match_fallback, 'ask' by default, TOO-15). Both legs
            are asserted here because only the PAIR distinguishes anchoring
            from a pattern that matches nothing at all -- an unanchored
            'src/**' fails to match either absolute path, so the outside leg
            alone is 'ask' under both implementations.
        """
        from toolguard.hook import resolve_file_path_permission_detailed

        home, project = self.isolate_config_environment(project_under_home="a/b/proj")
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Read(src/**)"]\n',
        )

        inside_file = str(project / "src" / "x.py")
        outside_file = str(home / "a" / "src" / "x.py")
        config = load_configuration(project)
        inside = resolve_file_path_permission_detailed("Read", inside_file, config)
        outside = resolve_file_path_permission_detailed("Read", outside_file, config)
        self.assertEqual(inside.decision, "allow")
        self.assertEqual(outside.decision, "ask")


class TestConfigLayerSpecificity(ConfigIsolationMixin, unittest.TestCase):
    """Test the ConfigLayer specificity convenience accessor."""

    def test_specificity_reflects_provenance(self):
        """
        Given a ConfigLayer whose provenance carries specificity 2
        When the layer's specificity property is read
        Then it returns 2
        """
        from toolguard.config import ConfigLayer, Provenance
        from types import MappingProxyType

        layer = ConfigLayer(
            provenance=Provenance(
                "project", "toolguard_hook", "toml", Path("/fake/x.toml"), 2
            ),
            content=MappingProxyType({}),
        )
        self.assertEqual(layer.specificity, 2)

    def test_resolve_config_path_empty_string(self):
        """
        Given an empty config path string
        When resolve_config_path runs
        Then it returns the empty string unchanged
        """
        _home, project = self.isolate_config_environment()
        config = load_configuration(project)
        self.assertEqual(config.resolve_config_path(""), "")


class TestResolveCompoundEdgeCases(unittest.TestCase):
    """Test edge cases of the per-sub-command compound resolver."""

    def test_empty_command_is_denied(self):
        """
        Given a command line that extracts to no sub-commands
        When resolve_compound_permission runs
        Then it denies with a 'no valid commands' reason
        """
        _verdict = resolve_compound_permission(
            "", lambda _c: ResolveOneResult("allow", "x", None)
        )
        decision, reason, _context = (
            _verdict.decision,
            _verdict.reason,
            _verdict.additional_context,
        )
        self.assertEqual(decision, "deny")
        self.assertIn("No valid commands", reason)

    def test_any_ask_subcommand_makes_compound_ask(self):
        """
        Given a compound command where one sub-command resolves to 'ask'
        When resolve_compound_permission combines the results
        Then the compound result is 'ask'
        """

        def _resolve_one(sub):
            if sub.startswith("rm"):
                return ResolveOneResult("ask", "Command requires approval: rm *", None)
            return ResolveOneResult(
                "allow", "Command matches allow pattern: git *", None
            )

        _verdict = resolve_compound_permission("git status && rm x", _resolve_one)
        decision, reason, _context = (
            _verdict.decision,
            _verdict.reason,
            _verdict.additional_context,
        )
        self.assertEqual(decision, "ask")
        self.assertIn("requiring approval", reason)


class TestMigrationIgnoresEnvOverride(ConfigIsolationMixin, unittest.TestCase):
    """Test how load_configuration's ignore_env_override flag treats CLAUDE_SETTINGS_PATH."""

    def test_load_configuration_ignores_env_override_when_requested(self):
        """
        Given CLAUDE_SETTINGS_PATH points at an UNRELATED project's settings,
            with an adjacent toolguard_hook declaring a distinctive permission,
            and the analysed project declares its own
        When load_configuration runs with ignore_env_override=True
        Then the resolved toolguard permissions reflect the analysed project,
            not the CLAUDE_SETTINGS_PATH file
        """
        from toolguard.config_divergence import get_toolguard_permissions

        home, project = self.isolate_config_environment()

        other = home / "other"
        other.mkdir()
        (other / ".git").mkdir()
        other_claude = other / ".claude"
        other_claude.mkdir()
        other_settings = other_claude / "settings.local.json"
        other_settings.write_text(
            '{"permissions": {"allow": ["Bash(env-leak:*)"], "deny": [], "ask": []}}'
        )
        # get_toolguard_permissions skips native layers, so the settings file
        # alone could never surface here; the adjacent hook file is what makes
        # the assertNotIn below able to fail.
        _write(
            other_claude,
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(env-leak:*)"]\n',
        )

        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(project-only:*)"]\n',
        )

        self.enterContext(
            patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": str(other_settings)})
        )
        config = load_configuration(project, ignore_env_override=True)
        perms = get_toolguard_permissions(config)

        self.assertNotIn("Bash(env-leak:*)", perms["allow"])
        self.assertIn("Bash(project-only:*)", perms["allow"])

    def test_load_configuration_honours_env_override_by_default(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a settings file
        When load_configuration runs WITHOUT ignore_env_override (the runtime hook
            default)
        Then the single-file override is honoured (project hierarchy is bypassed)
        """
        home, project = self.isolate_config_environment()
        env_claude = home / "env" / ".claude"
        env_claude.mkdir(parents=True)
        env_settings = env_claude / "settings.local.json"
        env_settings.write_text('{"permissions": {"allow": [], "deny": [], "ask": []}}')
        _write(
            env_claude,
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(env-only:*)"]\n',
        )

        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(project-only:*)"]\n',
        )

        from toolguard.config_divergence import get_toolguard_permissions

        self.enterContext(
            patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": str(env_settings)})
        )
        config = load_configuration(project)
        perms = get_toolguard_permissions(config)

        self.assertIn("Bash(env-only:*)", perms["allow"])
        self.assertNotIn("Bash(project-only:*)", perms["allow"])


if __name__ == "__main__":
    unittest.main()
