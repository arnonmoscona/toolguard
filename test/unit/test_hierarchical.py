"""
Unit tests for TOO-8 Phase 2: hierarchical configuration discovery,
more-specific-wins permission resolution, and project-root-relative paths.

These tests exercise the new behavior introduced in Phase 2:

- ``_discover_levels`` walks from the project root up to (and including) ``~``,
  assigning a specificity index per level (0 = most specific).
- ``Configuration.resolve_permission_detailed`` evaluates levels most-specific
  first; the first level that matches anything decides (deny-first within a
  level); no match anywhere => fail-closed deny.
- Relative config paths always resolve against the project root.

Tests use the standard-library ``unittest`` framework. Every test carries a
Given/When/Then docstring describing the scenario and expected outcome.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.compound import resolve_compound_permission
from toolguard.config import _discover_levels, load_configuration
from toolguard.permissions import decide_command_at_level_detailed


def _write(claude_dir: Path, filename: str, content: str) -> None:
    """Create a .claude directory (if needed) and write a config file in it."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / filename).write_text(content)


class _IsolatedEnvTestCase(unittest.TestCase):
    """
    Base class that isolates ``CLAUDE_SETTINGS_PATH`` for hierarchy tests.

    These tests patch the project-root/home discovery to a temp hierarchy. If the
    ambient shell exports ``CLAUDE_SETTINGS_PATH`` (the Claude Code hook does),
    ``load_configuration`` would honour that single-file override and bypass the
    patched hierarchy, pulling in an unrelated project's config. Popping the var
    in setUp makes these tests independent of the ambient environment, mirroring
    the pattern used in ``test_configuration.py``.
    """

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for the duration of each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop('CLAUDE_SETTINGS_PATH', None)
        self.addCleanup(self._env_patch.stop)


class TestHierarchicalTraversal(_IsolatedEnvTestCase):
    """Test hierarchical config-file discovery across directory levels."""

    def test_walk_collects_multiple_ancestor_levels(self):
        """
        Given a project nested several directories below ~ with .claude configs
            at the project, an intermediate ancestor, and ~ itself
        When _discover_levels walks the hierarchy with the toggle defaulting on
        Then all three levels are discovered with increasing specificity
            (project most specific, ~ least specific)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'a' / 'b' / 'proj'
            project.mkdir(parents=True)
            (project / '.git').mkdir()

            _write(project / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
            _write(home / 'a' / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
            _write(home / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    levels = _discover_levels(project)

            specs = {path.parent.parent.name: spec for path, _stype, _fmt, spec in levels}
            # project (.claude under 'proj') is most specific
            self.assertEqual(specs['proj'], 0)
            # intermediate ancestor 'a' is between project and user
            self.assertGreater(specs['a'], 0)
            # ~ is least specific (largest index)
            home_spec = max(spec for _p, _s, _f, spec in levels)
            self.assertEqual(specs[home.name], home_spec)

    def test_toggle_off_uses_only_project_and_user(self):
        """
        Given hierarchical_configuration = false in the project-level hook config
            and config files at project, an intermediate ancestor, and ~
        When _discover_levels runs
        Then only the project and user levels are collected (the intermediate
            ancestor is skipped), matching the pre-Phase-2 two-level behavior
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'a' / 'b' / 'proj'
            project.mkdir(parents=True)
            (project / '.git').mkdir()

            _write(
                project / '.claude',
                'toolguard_hook.toml',
                'hierarchical_configuration = false\npermissions = {}\n',
            )
            _write(home / 'a' / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
            _write(home / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    levels = _discover_levels(project)

            dirs = {path.parent.parent.name for path, _s, _f, _spec in levels}
            self.assertIn('proj', dirs)
            self.assertIn(home.name, dirs)
            self.assertNotIn('a', dirs)

    def test_toggle_on_explicit_walks_full_hierarchy(self):
        """
        Given hierarchical_configuration = true explicitly in the project config
        When _discover_levels runs with an intermediate ancestor present
        Then the intermediate ancestor level is included in the walk
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'a' / 'b' / 'proj'
            project.mkdir(parents=True)
            (project / '.git').mkdir()

            _write(
                project / '.claude',
                'toolguard_hook.toml',
                'hierarchical_configuration = true\npermissions = {}\n',
            )
            _write(home / 'a' / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    levels = _discover_levels(project)

            dirs = {path.parent.parent.name for path, _s, _f, _spec in levels}
            self.assertIn('a', dirs)

    def test_project_outside_home_still_includes_user(self):
        """
        Given a project that is NOT located under ~ (a sibling tree)
        When _discover_levels runs
        Then the project level is collected AND ~/.claude is always included as
            the least-specific level
        """
        with tempfile.TemporaryDirectory() as home_dir:
            with tempfile.TemporaryDirectory() as other_dir:
                home = Path(home_dir)
                project = Path(other_dir) / 'proj'
                project.mkdir(parents=True)
                (project / '.git').mkdir()

                _write(project / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
                _write(home / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

                with patch('toolguard.config.find_project_root', return_value=project):
                    with patch('toolguard.config.Path.home', return_value=home):
                        levels = _discover_levels(project)

                paths = [str(path) for path, _s, _f, _spec in levels]
                self.assertTrue(any(str(project) in p for p in paths))
                self.assertTrue(any(str(home / '.claude') in p for p in paths))
                # User level is least specific (largest specificity index).
                user_specs = [spec for path, _s, _f, spec in levels if str(home / '.claude') in str(path)]
                max_spec = max(spec for _p, _s, _f, spec in levels)
                self.assertEqual(user_specs[0], max_spec)

    def test_walk_stops_at_home(self):
        """
        Given a project located directly under ~ with a .claude above ~ as well
        When _discover_levels walks upward
        Then the walk never ascends above ~ (no level above home is collected)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / 'home' / 'user'
            home.mkdir(parents=True)
            project = home / 'proj'
            project.mkdir()
            (project / '.git').mkdir()

            _write(project / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
            _write(home / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
            # A .claude ABOVE home that must never be collected.
            _write(root / 'home' / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    levels = _discover_levels(project)

            paths = [str(path) for path, _s, _f, _spec in levels]
            self.assertFalse(any(str(root / 'home' / '.claude') in p for p in paths))

    def test_within_level_toml_preferred_over_json(self):
        """
        Given a single .claude level containing both toolguard_hook.toml and
            toolguard_hook.json
        When _discover_levels collects that level
        Then the TOML file is used and the JSON is not (within-level TOML wins)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            cl = project / '.claude'
            _write(cl, 'toolguard_hook.toml', 'permissions = {}\n')
            _write(cl, 'toolguard_hook.json', '{"permissions": {}}')

            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    levels = _discover_levels(project)

            hook_files = [(path, fmt) for path, stype, fmt, _spec in levels if stype == 'toolguard_hook']
            project_hook = [(p, f) for p, f in hook_files if str(project) in str(p)]
            self.assertEqual(len(project_hook), 1)
            self.assertEqual(project_hook[0][1], 'toml')


class TestMoreSpecificWinsResolution(_IsolatedEnvTestCase):
    """Test the more-specific-wins permission resolution cascade."""

    def _config(self, *level_specs):
        """
        Build a Configuration whose Bash levels are the given per-level
        (allow, deny) tuples, most-specific first. Each spec is an
        (allow_list, deny_list) pair. Avoids any file I/O.
        """
        from toolguard.config import ConfigLayer, Configuration, Provenance
        from types import MappingProxyType

        layers = []
        for spec_index, (allow, deny) in enumerate(level_specs):
            content = {
                'permissions': {
                    'allow': [f'Bash({p})' for p in allow],
                    'deny': [f'Bash({p})' for p in deny],
                }
            }
            prov = Provenance('project', 'toolguard_hook', 'toml', Path(f'/fake/{spec_index}.toml'), spec_index)
            layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
        return Configuration(layers=tuple(layers))

    @staticmethod
    def _detailed_decider(command):
        """
        Build a per-level ``decide_detailed`` closure bound to one command.

        Mirrors the inline closure the production hook builds over
        ``decide_command_at_level_detailed`` so the test exercises the same
        per-level decision logic the cascade consumes.
        """

        def _decide(allow_patterns, deny_patterns):
            return decide_command_at_level_detailed(
                command, list(allow_patterns), list(deny_patterns)
            )

        return _decide

    def _resolve(self, config, command):
        """
        Resolve a single command through the Bash level cascade.

        Returns ``(decision, reason)`` extracted from the ``ResolvedDecision``
        so existing Given/When/Then assertions remain unchanged.
        """
        resolved = config.resolve_permission_detailed('Bash', self._detailed_decider(command))
        return resolved.decision, resolved.reason

    def test_child_allow_overrides_parent_deny(self):
        """
        Given a child (more-specific) level that allows 'git *' and a parent
            level that denies 'git *'
        When 'git status' is resolved under more-specific-wins
        Then the child's allow wins (the parent's deny never gets consulted)
        """
        config = self._config((['git *'], []), ([], ['git *']))
        decision, _reason = self._resolve(config, 'git status')
        self.assertEqual(decision, 'allow')

    def test_child_deny_overrides_parent_allow(self):
        """
        Given a child level that denies 'rm *' and a parent level that allows it
        When 'rm -rf /' is resolved under more-specific-wins
        Then the child's deny wins
        """
        config = self._config(([], ['rm *']), (['rm *'], []))
        decision, reason = self._resolve(config, 'rm -rf /')
        self.assertEqual(decision, 'deny')
        self.assertIn('deny pattern', reason)

    def test_no_match_at_child_falls_through_to_parent(self):
        """
        Given a child level that matches nothing for the command and a parent
            level that allows it
        When the command is resolved
        Then the cascade falls through to the parent and the command is allowed
        """
        config = self._config((['ls *'], []), (['git *'], []))
        decision, _reason = self._resolve(config, 'git status')
        self.assertEqual(decision, 'allow')

    def test_no_match_anywhere_is_deny(self):
        """
        Given no level matches the command
        When it is resolved
        Then the result is a fail-closed deny
        """
        config = self._config((['ls *'], []), (['cat *'], []))
        decision, reason = self._resolve(config, 'git status')
        self.assertEqual(decision, 'deny')
        self.assertIn('does not match any allow patterns', reason)

    def test_deny_first_within_a_single_level(self):
        """
        Given one level that both allows 'git *' and denies 'git push *'
        When 'git push origin' is resolved
        Then deny-first within the level denies the command
        """
        config = self._config((['git *'], ['git push *']),)
        decision, _reason = self._resolve(config, 'git push origin')
        self.assertEqual(decision, 'deny')

    def test_three_level_cascade_first_match_wins(self):
        """
        Given three levels where only the middle level matches the command
        When the command is resolved most-specific first
        Then the middle level's decision wins and the least-specific level is
            never consulted
        """
        # child: no match; middle: deny; parent: allow.
        config = self._config(
            (['ls *'], []),
            ([], ['git *']),
            (['git *'], []),
        )
        decision, _reason = self._resolve(config, 'git status')
        self.assertEqual(decision, 'deny')

    def test_compound_each_subcommand_cascades_independently(self):
        """
        Given a compound command 'git status && rm -rf /' where the child level
            allows git and the parent level denies rm
        When each sub-command is cascaded independently and combined
        Then the compound is denied because one sub-command resolves to deny
        """
        config = self._config((['git *'], []), ([], ['rm *']))

        def _resolve_one(sub):
            resolved = config.resolve_permission_detailed('Bash', self._detailed_decider(sub))
            return resolved.decision, resolved.reason

        decision, _reason = resolve_compound_permission('git status && rm -rf /', _resolve_one)
        self.assertEqual(decision, 'deny')

    def test_compound_allowed_iff_all_subcommands_allowed(self):
        """
        Given a compound command whose every sub-command is allowed at some level
        When resolved through independent per-sub-command cascades
        Then the compound is allowed
        """
        config = self._config((['git *', 'ls *'], []),)

        def _resolve_one(sub):
            resolved = config.resolve_permission_detailed('Bash', self._detailed_decider(sub))
            return resolved.decision, resolved.reason

        decision, _reason = resolve_compound_permission('git status && ls -l', _resolve_one)
        self.assertEqual(decision, 'allow')


class TestProjectRootRelativePaths(_IsolatedEnvTestCase):
    """Test that relative config paths resolve against the project root."""

    def _config_with_backup_dir(self, level_dir_name, backup_dir, tmp_home):
        """
        Build a real Configuration with a toolguard_hook.toml declaring a
        relative backup_dir at the requested level (project / intermediate / user).
        Returns (config, project_root).
        """
        home = Path(tmp_home)
        project = home / 'a' / 'b' / 'proj'
        project.mkdir(parents=True)
        (project / '.git').mkdir()

        target = {
            'project': project / '.claude',
            'intermediate': home / 'a' / '.claude',
            'user': home / '.claude',
        }[level_dir_name]
        _write(target, 'toolguard_hook.toml', f'[config_sync]\nbackup_dir = "{backup_dir}"\n')
        # Ensure project always has a hook file so the toggle reads as default-on.
        if level_dir_name != 'project':
            _write(project / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')
        return project, home

    def _resolve_backup(self, level_name):
        """Resolve config_sync.backup_dir declared at the given level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project, home = self._config_with_backup_dir(level_name, 'my-backups', tmpdir)
            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    config = load_configuration(project)
                    resolved = config.resolve_config_path(config.scalar('config_sync.backup_dir'))
            return resolved, project

    def test_relative_backup_dir_at_project_level(self):
        """
        Given a relative backup_dir declared at the project level
        When it is resolved
        Then it anchors to <project_root>/my-backups
        """
        resolved, project = self._resolve_backup('project')
        self.assertEqual(resolved, str(project / 'my-backups'))

    def test_relative_backup_dir_at_intermediate_level(self):
        """
        Given a relative backup_dir declared at an intermediate ancestor level
        When it is resolved
        Then it still anchors to <project_root>/my-backups (NOT the ancestor dir)
        """
        resolved, project = self._resolve_backup('intermediate')
        self.assertEqual(resolved, str(project / 'my-backups'))

    def test_relative_backup_dir_at_user_level(self):
        """
        Given a relative backup_dir declared at the user (~) level
        When it is resolved
        Then it still anchors to <project_root>/my-backups (NOT ~/.claude)
        """
        resolved, project = self._resolve_backup('user')
        self.assertEqual(resolved, str(project / 'my-backups'))

    def test_absolute_path_unchanged(self):
        """
        Given an absolute config path
        When resolve_config_path runs
        Then the path is returned unchanged
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                self.assertEqual(config.resolve_config_path('/var/backups'), '/var/backups')

    def test_tilde_path_unchanged(self):
        """
        Given a ~-prefixed config path
        When resolve_config_path runs
        Then the path is returned unchanged (tilde expansion happens downstream)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                self.assertEqual(config.resolve_config_path('~/backups'), '~/backups')


class TestRelativeFilePathPatterns(_IsolatedEnvTestCase):
    """Test that relative Read/Write/Edit patterns anchor to the project root."""

    def _resolve_read(self, level_name):
        """
        Build a Configuration with a relative Read allow pattern at the given
        level, then resolve a Read of <project_root>/src/x.py through the
        more-specific-wins file-path cascade. Returns the decision.
        """
        from toolguard.hook import resolve_file_path_permission_detailed

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'a' / 'b' / 'proj'
            project.mkdir(parents=True)
            (project / '.git').mkdir()

            target = {
                'project': project / '.claude',
                'intermediate': home / 'a' / '.claude',
                'user': home / '.claude',
            }[level_name]
            _write(
                target,
                'toolguard_hook.toml',
                '[permissions]\nallow = ["Read(src/**)"]\n',
            )
            if level_name != 'project':
                _write(project / '.claude', 'toolguard_hook.toml', 'permissions = {}\n')

            target_file = str(project / 'src' / 'x.py')
            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    config = load_configuration(project)
                    decision, _reason, _override = resolve_file_path_permission_detailed(
                        'Read', target_file, config
                    )
            return decision

    def test_relative_read_pattern_at_project_level(self):
        """
        Given a relative Read pattern 'src/**' declared at the project level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (pattern anchored to the project root)
        """
        self.assertEqual(self._resolve_read('project'), 'allow')

    def test_relative_read_pattern_at_intermediate_level(self):
        """
        Given a relative Read pattern declared at an intermediate ancestor level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (anchored to the project root, not the ancestor dir)
        """
        self.assertEqual(self._resolve_read('intermediate'), 'allow')

    def test_relative_read_pattern_at_user_level(self):
        """
        Given a relative Read pattern declared at the user (~) level
        When a Read of <project_root>/src/x.py is resolved
        Then it is allowed (anchored to the project root, not ~/.claude)
        """
        self.assertEqual(self._resolve_read('user'), 'allow')


class TestAnchorFilePattern(_IsolatedEnvTestCase):
    """Test extended-syntax handling in project-root pattern anchoring."""

    def test_glob_prefix_relative_body_is_anchored(self):
        """
        Given a relative file pattern carrying a [glob] prefix
        When _anchor_file_pattern runs
        Then the [glob] prefix is preserved and the relative body is anchored to
            the project root
        """
        from toolguard.hook import _anchor_file_pattern

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                result = _anchor_file_pattern('[glob]src/**', config, extended_syntax=True)
                self.assertEqual(result, f'[glob]{project / "src/**"}')

    def test_regex_prefix_left_untouched(self):
        """
        Given a [regex] file pattern (a regex, not a path)
        When _anchor_file_pattern runs
        Then the pattern is returned unchanged (never path-joined)
        """
        from toolguard.hook import _anchor_file_pattern

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                result = _anchor_file_pattern('[regex]^src/.*', config, extended_syntax=True)
                self.assertEqual(result, '[regex]^src/.*')

    def test_absolute_pattern_left_untouched(self):
        """
        Given an absolute file pattern
        When _anchor_file_pattern runs
        Then the pattern is returned unchanged
        """
        from toolguard.hook import _anchor_file_pattern

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                result = _anchor_file_pattern('/etc/**', config, extended_syntax=True)
                self.assertEqual(result, '/etc/**')

    def test_tilde_pattern_left_untouched(self):
        """
        Given a ~-prefixed file pattern
        When _anchor_file_pattern runs
        Then the pattern is returned unchanged (tilde expansion happens downstream,
            it is NOT anchored to the project root)
        """
        from toolguard.hook import _anchor_file_pattern

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                result = _anchor_file_pattern('~/secrets/**', config, extended_syntax=True)
                self.assertEqual(result, '~/secrets/**')

    def test_relative_pattern_does_not_match_same_name_outside_project(self):
        """
        Given a relative Read allow pattern 'src/**' anchored to the project root
        When a Read targets a same-named 'src/x.py' OUTSIDE the project root
        Then it is DENIED -- the anchored pattern only matches inside the project,
            pinning that relative patterns are no longer matched as authored
        """
        from toolguard.hook import resolve_file_path_permission_detailed

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            project = home / 'a' / 'b' / 'proj'
            project.mkdir(parents=True)
            (project / '.git').mkdir()
            _write(
                project / '.claude',
                'toolguard_hook.toml',
                '[permissions]\nallow = ["Read(src/**)"]\n',
            )

            # A path named src/x.py but OUTSIDE the project root (in an ancestor).
            outside_file = str(home / 'a' / 'src' / 'x.py')
            with patch('toolguard.config.find_project_root', return_value=project):
                with patch('toolguard.config.Path.home', return_value=home):
                    config = load_configuration(project)
                    decision, _reason, _override = resolve_file_path_permission_detailed(
                        'Read', outside_file, config
                    )
            self.assertEqual(decision, 'deny')


class TestConfigLayerSpecificity(_IsolatedEnvTestCase):
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
            provenance=Provenance('project', 'toolguard_hook', 'toml', Path('/fake/x.toml'), 2),
            content=MappingProxyType({}),
        )
        self.assertEqual(layer.specificity, 2)

    def test_resolve_config_path_empty_string(self):
        """
        Given an empty config path string
        When resolve_config_path runs
        Then it returns the empty string unchanged
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            with patch('toolguard.config.find_project_root', return_value=project):
                config = load_configuration(project)
                self.assertEqual(config.resolve_config_path(''), '')


class TestResolveCompoundEdgeCases(_IsolatedEnvTestCase):
    """Test edge cases of the per-sub-command compound resolver."""

    def test_empty_command_is_denied(self):
        """
        Given a command line that extracts to no sub-commands
        When resolve_compound_permission runs
        Then it denies with a 'no valid commands' reason
        """
        decision, reason = resolve_compound_permission('', lambda _c: ('allow', 'x'))
        self.assertEqual(decision, 'deny')
        self.assertIn('No valid commands', reason)

    def test_any_ask_subcommand_makes_compound_ask(self):
        """
        Given a compound command where one sub-command resolves to 'ask'
        When resolve_compound_permission combines the results
        Then the compound result is 'ask'
        """

        def _resolve_one(sub):
            if sub.startswith('rm'):
                return 'ask', 'Command requires approval: rm *'
            return 'allow', 'Command matches allow pattern: git *'

        decision, reason = resolve_compound_permission('git status && rm x', _resolve_one)
        self.assertEqual(decision, 'ask')
        self.assertIn('requiring approval', reason)


class TestMigrationIgnoresEnvOverride(unittest.TestCase):
    """
    Pin that the migration/divergence READ path ignores CLAUDE_SETTINGS_PATH.

    The migration tool selects its write target via project-based discovery, so
    its analysis read path must be project-based too (load_configuration with
    ignore_env_override=True). A stale CLAUDE_SETTINGS_PATH pointing at an
    unrelated project must NOT leak into the analysis.

    This class intentionally does NOT inherit the env-isolating base: it sets
    CLAUDE_SETTINGS_PATH itself to prove the override is ignored.
    """

    def test_load_configuration_ignores_env_override_when_requested(self):
        """
        Given CLAUDE_SETTINGS_PATH points at an UNRELATED project's settings and
            the analysed project declares its own toolguard permission
        When load_configuration runs with ignore_env_override=True
        Then the resolved toolguard permissions reflect the analysed project,
            not the CLAUDE_SETTINGS_PATH file
        """
        from toolguard.config_divergence import get_toolguard_permissions

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            # Unrelated project that CLAUDE_SETTINGS_PATH points at.
            other = home / 'other'
            other.mkdir()
            (other / '.git').mkdir()
            other_claude = other / '.claude'
            other_claude.mkdir()
            other_settings = other_claude / 'settings.local.json'
            other_settings.write_text(
                '{"permissions": {"allow": ["Bash(env-leak:*)"], "deny": [], "ask": []}}'
            )

            # The project actually being migrated/analysed.
            project = home / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            _write(
                project / '.claude',
                'toolguard_hook.toml',
                '[permissions]\nallow = ["Bash(project-only:*)"]\n',
            )

            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': str(other_settings)}):
                with patch('toolguard.config.find_project_root', return_value=project):
                    with patch('toolguard.config.Path.home', return_value=home):
                        config = load_configuration(project, ignore_env_override=True)
                        perms = get_toolguard_permissions(config)

            self.assertIn('Bash(project-only:*)', perms['allow'])
            self.assertNotIn('Bash(env-leak:*)', perms['allow'])

    def test_load_configuration_honours_env_override_by_default(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a settings file
        When load_configuration runs WITHOUT ignore_env_override (the runtime hook
            default)
        Then the single-file override is honoured (project hierarchy is bypassed)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            env_claude = home / 'env' / '.claude'
            env_claude.mkdir(parents=True)
            env_settings = env_claude / 'settings.local.json'
            env_settings.write_text('{"permissions": {"allow": [], "deny": [], "ask": []}}')
            # Adjacent toolguard_hook with a distinctive permission.
            _write(env_claude, 'toolguard_hook.toml', '[permissions]\nallow = ["Bash(env-only:*)"]\n')

            project = home / 'proj'
            project.mkdir()
            (project / '.git').mkdir()
            _write(
                project / '.claude',
                'toolguard_hook.toml',
                '[permissions]\nallow = ["Bash(project-only:*)"]\n',
            )

            from toolguard.config_divergence import get_toolguard_permissions

            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': str(env_settings)}):
                with patch('toolguard.config.find_project_root', return_value=project):
                    with patch('toolguard.config.Path.home', return_value=home):
                        config = load_configuration(project)
                        perms = get_toolguard_permissions(config)

            self.assertIn('Bash(env-only:*)', perms['allow'])
            self.assertNotIn('Bash(project-only:*)', perms['allow'])


if __name__ == '__main__':
    unittest.main()
