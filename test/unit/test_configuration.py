"""
Unit tests for the TOO-8 Phase 1 public config abstraction.

These tests exercise :func:`toolguard.config.load_configuration` and the
:class:`Configuration` public API, plus the internal delegating helper
``config_sync_settings_from_sources`` that ``auto_migrate`` uses.

Run with:
    uv run python -m unittest discover -s test -t .
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Issue,
    Provenance,
    TakeoverConfig,
    ToolPatternLayer,
    config_sync_settings_from_sources,
    load_configuration,
)


def _make_project(tmpdir, files):
    """
    Build a project skeleton under tmpdir/project with the given .claude files.

    Args:
        tmpdir: Temp directory path string.
        files: Mapping of filename -> file content string (written to .claude/).

    Returns:
        Path to the project root directory.
    """
    project_dir = Path(tmpdir) / 'project'
    project_dir.mkdir()
    (project_dir / '.git').mkdir()
    claude_dir = project_dir / '.claude'
    claude_dir.mkdir()
    for name, content in files.items():
        (claude_dir / name).write_text(content)
    return project_dir


class TestLoadConfigurationHierarchy(unittest.TestCase):
    """load_configuration() discovery + layering."""

    def test_layers_built_from_project(self):
        """
        Given a project with settings.local.json and toolguard_hook.json under .claude
        When load_configuration discovers them
        Then a Configuration with at least two layers is returned, each with provenance and a read-only mapping, and the project files are labelled 'project'
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(
                tmp,
                {
                    'settings.local.json': json.dumps({'permissions': {'allow': ['Bash(git *)']}}),
                    'toolguard_hook.json': json.dumps({'permissions': {'allow': ['Bash(ls *)']}}),
                },
            )
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop('CLAUDE_SETTINGS_PATH', None)
                with patch('toolguard.config.find_project_root', return_value=project):
                    config = load_configuration()

            self.assertIsInstance(config, Configuration)
            self.assertGreaterEqual(len(config.layers), 2)
            # Every layer carries provenance and a read-only mapping. The real
            # user-level ~/.claude files may also be discovered, so only assert
            # that the project files are present and labelled 'project'.
            for layer in config.layers:
                self.assertIsInstance(layer, ConfigLayer)
                self.assertIsInstance(layer.provenance, Provenance)
                self.assertIsInstance(layer.content, MappingProxyType)
            project_levels = [
                layer.provenance.level
                for layer in config.layers
                if str(project) in str(layer.provenance.path)
            ]
            self.assertTrue(project_levels)
            self.assertTrue(all(level == 'project' for level in project_levels))

    def test_unparseable_file_skipped(self):
        """
        Given a project with an unparseable toolguard_hook.json and a valid settings.local.json
        When load_configuration runs
        Then the unparseable file is skipped and the valid layer's Bash allow patterns are still available
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(
                tmp,
                {
                    'toolguard_hook.json': 'not valid json{',
                    'settings.local.json': json.dumps({'permissions': {'allow': ['Bash(git *)']}}),
                },
            )
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop('CLAUDE_SETTINGS_PATH', None)
                with patch('toolguard.config.find_project_root', return_value=project):
                    config = load_configuration()
            # The valid settings layer is still present.
            allow, _ = config.allow_deny_for('Bash')
            self.assertIn('git *', allow)

    def test_claude_settings_path_single_file(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a single settings file with no adjacent hook
        When load_configuration runs
        Then exactly one layer is produced, labelled 'explicit' and recognized as native
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'permissions': {'allow': ['Bash(git *)']}}, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': path}):
                config = load_configuration()
            self.assertEqual(len(config.layers), 1)
            self.assertEqual(config.layers[0].provenance.level, 'explicit')
            self.assertTrue(config.layers[0].is_native)
        finally:
            Path(path).unlink()

    def test_claude_settings_path_with_adjacent_hook(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a settings file with an adjacent toolguard_hook.json
        When load_configuration runs
        Then both a 'claude' and a 'toolguard_hook' source layer are produced
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / 'settings.json'
            settings.write_text(json.dumps({'permissions': {'allow': ['Bash(git *)']}}))
            hook = Path(tmp) / 'toolguard_hook.json'
            hook.write_text(json.dumps({'permissions': {'allow': ['Bash(ls *)']}}))
            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': str(settings)}):
                config = load_configuration()
            types = [layer.provenance.source_type for layer in config.layers]
            self.assertIn('claude', types)
            self.assertIn('toolguard_hook', types)


class TestPermissionLayers(unittest.TestCase):
    """permission_layers() and allow_deny_for() flattening + takeover filtering."""

    def test_allow_deny_union_dedup(self):
        """
        Given two hook layers with overlapping Read allow patterns and one deny
        When allow_deny_for('Read') flattens them (no takeover)
        Then allow is the order-preserving de-duplicated union and deny carries the single pattern
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/toolguard_hook.json')),
                MappingProxyType({'permissions': {'allow': ['Read(/tmp/**)', 'Read(/a/**)'], 'deny': ['Read(/s/**)']}}),
            ),
            ConfigLayer(
                Provenance('user', 'toolguard_hook', 'json', Path('/u/toolguard_hook.json')),
                MappingProxyType({'permissions': {'allow': ['Read(/a/**)', 'Read(/b/**)'], 'deny': []}}),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            'takeover_mode',
            return_value=TakeoverConfig(False, (), (), 'deny'),
        ):
            allow, deny = config.allow_deny_for('Read')
        self.assertEqual(allow, ('/tmp/**', '/a/**', '/b/**'))
        self.assertEqual(deny, ('/s/**',))

    def test_only_requested_tool_extracted(self):
        """
        Given a layer with Read, Write, and Bash allow patterns
        When allow_deny_for('Read') runs
        Then only the Read pattern is returned and Write/Bash are ignored
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'claude', 'json', Path('/p/settings.json')),
                MappingProxyType(
                    {'permissions': {'allow': ['Read(/tmp/**)', 'Write(/tmp/*)', 'Bash(git *)'], 'deny': []}}
                ),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(Configuration, 'takeover_mode', return_value=TakeoverConfig(False, (), (), 'deny')):
            allow, _ = config.allow_deny_for('Read')
        self.assertEqual(allow, ('/tmp/**',))

    def test_takeover_filters_native_allow_only(self):
        """
        Given a native layer and a hook layer that both allow 'Read(*)', with takeover ignoring 'Read(*)'
        When permission_layers('Read') is computed
        Then the native layer drops the blanket '*' (keeping '/tmp/**') while the hook layer keeps '*'
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'claude', 'json', Path('/p/settings.json')),
                MappingProxyType({'permissions': {'allow': ['Read(*)', 'Read(/tmp/**)'], 'deny': []}}),
            ),
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/toolguard_hook.json')),
                MappingProxyType({'permissions': {'allow': ['Read(*)'], 'deny': []}}),
            ),
        )
        config = Configuration(layers=layers)
        takeover = TakeoverConfig(True, ('Read(*)',), (), 'deny')
        with patch.object(Configuration, 'takeover_mode', return_value=takeover):
            per_layer = config.permission_layers('Read')
        # Native layer: blanket '*' filtered out, '/tmp/**' kept.
        self.assertEqual(per_layer[0].allow, ('/tmp/**',))
        # Hook layer: '*' kept (never filtered).
        self.assertEqual(per_layer[1].allow, ('*',))

    def test_per_layer_provenance_preserved(self):
        """
        Given a project hook layer and a user hook layer
        When permission_layers('Bash') is computed
        Then the resulting ToolPatternLayers retain their provenance with project before user
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'toml', Path('/p/toolguard_hook.toml')),
                MappingProxyType({'permissions': {'allow': ['Bash(git *)'], 'deny': []}}),
            ),
            ConfigLayer(
                Provenance('user', 'toolguard_hook', 'json', Path('/u/toolguard_hook.json')),
                MappingProxyType({'permissions': {'allow': ['Bash(ls *)'], 'deny': []}}),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(Configuration, 'takeover_mode', return_value=TakeoverConfig(False, (), (), 'deny')):
            per_layer = config.permission_layers('Bash')
        self.assertEqual(per_layer[0].provenance.level, 'project')
        self.assertEqual(per_layer[1].provenance.level, 'user')
        self.assertIsInstance(per_layer[0], ToolPatternLayer)

    def test_non_dict_permissions_tolerated(self):
        """
        Given a layer whose 'permissions' value is a string rather than a dict
        When allow_deny_for('Bash') runs
        Then extraction does not crash and returns empty allow and deny tuples
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/toolguard_hook.json')),
                MappingProxyType({'permissions': 'oops-not-a-dict'}),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(Configuration, 'takeover_mode', return_value=TakeoverConfig(False, (), (), 'deny')):
            allow, deny = config.allow_deny_for('Bash')
        self.assertEqual(allow, ())
        self.assertEqual(deny, ())


class TestScalarsAndConfigSync(unittest.TestCase):
    """scalar() resolution and config_sync_settings()."""

    def _hook_layer(self, level, content):
        return ConfigLayer(
            Provenance(level, 'toolguard_hook', 'json', Path(f'/{level}/toolguard_hook.json')),
            MappingProxyType(content),
        )

    def test_scalar_dotted_last_wins(self):
        """
        Given project and user hook layers each defining config_sync.backup_dir
        When scalar('config_sync.backup_dir') resolves the value
        Then the user (least-specific) value wins, preserving Phase 1 last-occurrence-wins behaviour

        Phase 1 is behaviour-preserving: the legacy resolver iterates discovery
        order (project first, user last) with last-occurrence-wins. See
        test_config_sync_conflict_is_user_wins_phase1 for the explicit pin and
        the Phase 2 flip note.
        """
        layers = (
            self._hook_layer('project', {'config_sync': {'backup_dir': 'proj/backups'}}),
            self._hook_layer('user', {'config_sync': {'backup_dir': 'user/backups'}}),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.scalar('config_sync.backup_dir', 'default'), 'user/backups')

    def test_config_sync_conflict_is_user_wins_phase1(self):
        """
        Given project and user hook layers with conflicting config_sync values
        When scalar() and config_sync_settings() resolve them in Phase 1
        Then the USER value wins on every conflict, pinning the conflict direction (HEAD behaviour)

        This pins the conflict DIRECTION so the Phase 2 change to
        more-specific-wins (project-wins) is a conscious, test-visible flip.

        # FIXME(TOO-8 Phase 2, decision #4): Phase 2 will intentionally switch
        # config_sync (and other scalars) to more-specific-wins (project-wins).
        # When that lands, flip the expected values in this test (and in
        # test_scalar_dotted_last_wins) to assert project-wins, so the behaviour
        # change is explicit and reviewed.
        """
        layers = (
            self._hook_layer('project', {'config_sync': {'auto_migrate': True, 'backup_dir': 'proj/backups'}}),
            self._hook_layer('user', {'config_sync': {'auto_migrate': False, 'backup_dir': 'user/backups'}}),
        )
        config = Configuration(layers=layers)

        # scalar() resolves user-wins on conflict.
        self.assertEqual(config.scalar('config_sync.backup_dir', 'default'), 'user/backups')
        self.assertIs(config.scalar('config_sync.auto_migrate', None), False)

        # config_sync_settings() (the public accessor used by the hook) reflects
        # the same user-wins resolution.
        cs = config.config_sync_settings()
        self.assertEqual(cs['backup_dir'], 'user/backups')
        self.assertIs(cs['auto_migrate'], False)

    def test_scalar_default_when_absent(self):
        """
        Given a configuration with no layers
        When scalar('config_sync.backup_dir', 'fallback') resolves
        Then the supplied default 'fallback' is returned
        """
        config = Configuration(layers=())
        self.assertEqual(config.scalar('config_sync.backup_dir', 'fallback'), 'fallback')

    def test_scalar_ignores_native_layers(self):
        """
        Given only a native ('claude') layer that defines config_sync.backup_dir
        When scalar('config_sync.backup_dir', 'default') resolves
        Then the native value is ignored and the default is returned
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'claude', 'json', Path('/p/settings.json')),
                MappingProxyType({'config_sync': {'backup_dir': 'should-be-ignored'}}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.scalar('config_sync.backup_dir', 'default'), 'default')

    def test_scalar_bare_top_level_key(self):
        """
        Given a hook layer with a top-level 'some_flag' set to True
        When scalar('some_flag', False) resolves the bare key
        Then it returns True
        """
        layers = (self._hook_layer('project', {'some_flag': True}),)
        config = Configuration(layers=layers)
        self.assertIs(config.scalar('some_flag', False), True)

    def test_config_sync_settings_defaults(self):
        """
        Given a configuration with no layers
        When config_sync_settings() is called
        Then it returns a read-only mapping of the documented defaults that rejects mutation
        """
        config = Configuration(layers=())
        cs = config.config_sync_settings()
        self.assertIsInstance(cs, MappingProxyType)
        self.assertEqual(cs['auto_migrate'], False)
        self.assertEqual(cs['backup_dir'], 'logs/config-backups')
        self.assertEqual(cs['auto_sort_on_migrate'], True)
        with self.assertRaises(TypeError):
            cs['auto_migrate'] = True  # read-only


class TestToolguardPermissions(unittest.TestCase):
    """toolguard_permissions() aggregation from hook layers."""

    def test_aggregates_wrapper_intact(self):
        """
        Given a native layer and a hook layer with allow/deny/ask permissions
        When toolguard_permissions() aggregates them
        Then the hook patterns are returned with their tool wrappers intact and the native pattern is skipped
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'claude', 'json', Path('/p/settings.json')),
                MappingProxyType({'permissions': {'allow': ['Bash(should-skip)']}}),
            ),
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/toolguard_hook.json')),
                MappingProxyType({'permissions': {'allow': ['Bash(git *)'], 'deny': ['Bash(rm *)'], 'ask': []}}),
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertEqual(perms['allow'], ('Bash(git *)',))
        self.assertEqual(perms['deny'], ('Bash(rm *)',))
        self.assertEqual(perms['ask'], ())
        self.assertNotIn('Bash(should-skip)', perms['allow'])


class TestValidationIssues(unittest.TestCase):
    """validation_issues() structured issue detection (no logging side effects)."""

    def test_duplicate_toml_json_issue(self):
        """
        Given both toolguard_hook.toml and toolguard_hook.json layers at the same base
        When validation_issues() runs
        Then it reports an Issue warning about the duplicate TOML+JSON pair
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'toml', Path('/p/.claude/toolguard_hook.toml')),
                MappingProxyType({}),
            ),
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/.claude/toolguard_hook.json')),
                MappingProxyType({}),
            ),
        )
        config = Configuration(layers=layers)
        issues = config.validation_issues()
        self.assertTrue(any('Both toolguard_hook.toml and toolguard_hook.json' in i.message for i in issues))
        for i in issues:
            self.assertIsInstance(i, Issue)

    def test_ungoverned_and_unsupported_tools(self):
        """
        Given a hook layer governing only Bash but allowing Read and WebSearch
        When validation_issues() runs
        Then it flags WebSearch as unsupported and Read as supported-but-ungoverned
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/.claude/toolguard_hook.json')),
                MappingProxyType(
                    {
                        'governed_tools': ['Bash'],
                        'permissions': {'allow': ['Read(/tmp/**)', 'WebSearch']},
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        messages = ' '.join(i.message for i in config.validation_issues())
        self.assertIn('WebSearch', messages)  # unsupported
        self.assertIn('Read', messages)  # supported but ungoverned

    def test_native_layers_not_validated(self):
        """
        Given only a native settings.local.json layer allowing WebSearch and WebFetch
        When validation_issues() runs
        Then no issues are reported because native layers are not validated
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'claude', 'json', Path('/p/.claude/settings.local.json')),
                MappingProxyType({'permissions': {'allow': ['WebSearch', 'WebFetch']}}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.validation_issues(), ())


class TestTakeoverConfig(unittest.TestCase):
    """TakeoverConfig normalization helper."""

    def test_normalized_ignored_strips_wrappers(self):
        """
        Given a TakeoverConfig with wrapped and already-bare ignored patterns
        When normalized_ignored_patterns() runs
        Then it returns the frozenset of patterns with tool wrappers stripped and bare ones kept
        """
        tc = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=('Bash(*)', 'Read(/tmp/**)'),
            additional_ignored_patterns=('already-bare',),
            no_match_fallback='deny',
        )
        self.assertEqual(tc.normalized_ignored_patterns(), frozenset({'*', '/tmp/**', 'already-bare'}))


class TestImmutability(unittest.TestCase):
    """Public dataclasses are frozen."""

    def test_configuration_frozen(self):
        """
        Given a Configuration instance
        When its layers attribute is reassigned
        Then an exception is raised because the dataclass is frozen
        """
        config = Configuration(layers=())
        with self.assertRaises(Exception):
            config.layers = (1,)

    def test_provenance_frozen(self):
        """
        Given a Provenance instance
        When its level attribute is reassigned
        Then an exception is raised because the dataclass is frozen
        """
        prov = Provenance('project', 'claude', 'json', Path('/x'))
        with self.assertRaises(Exception):
            prov.level = 'user'


class TestInternalHelpers(unittest.TestCase):
    """Delegating helpers used by config_divergence / auto_migrate."""

    def test_config_sync_settings_from_sources_last_wins(self):
        """
        Given two toolguard_hook sources with overlapping config_sync keys
        When config_sync_settings_from_sources merges them
        Then the last source wins on conflict and defaults fill unset keys
        """
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'toolguard_hook.json'
            first.write_text(json.dumps({'config_sync': {'auto_migrate': True, 'backup_dir': 'a'}}))
            second = Path(tmp) / 'toolguard_hook.local.json'
            second.write_text(json.dumps({'config_sync': {'backup_dir': 'b'}}))
            config_files = [
                (first, 'toolguard_hook', 'json'),
                (second, 'toolguard_hook', 'json'),
            ]
            result = config_sync_settings_from_sources(config_files)
            self.assertEqual(result['auto_migrate'], True)
            self.assertEqual(result['backup_dir'], 'b')  # last wins
            self.assertEqual(result['auto_sort_on_migrate'], True)  # default

    def test_config_sync_settings_from_sources_defaults(self):
        """
        Given an empty list of config sources
        When config_sync_settings_from_sources runs
        Then it returns the full set of documented defaults
        """
        result = config_sync_settings_from_sources([])
        self.assertEqual(
            result,
            {'auto_migrate': False, 'backup_dir': 'logs/config-backups', 'auto_sort_on_migrate': True},
        )

    def test_config_sync_skips_unparseable_and_empty(self):
        """
        Given hook sources where one is unparseable and one has an empty config_sync
        When config_sync_settings_from_sources runs
        Then nothing usable is found and the documented defaults are returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'toolguard_hook.json'
            bad.write_text('}{ not json')
            empty = Path(tmp) / 'toolguard_hook.local.json'
            empty.write_text(json.dumps({'config_sync': {}}))
            config_files = [
                (bad, 'toolguard_hook', 'json'),
                (empty, 'toolguard_hook', 'json'),
            ]
            result = config_sync_settings_from_sources(config_files)
            # Falls back to defaults since nothing usable was found.
            self.assertEqual(result['auto_migrate'], False)
            self.assertEqual(result['backup_dir'], 'logs/config-backups')


class TestGovernedAndTakeoverDelegation(unittest.TestCase):
    """governed_tools() and takeover_mode() delegate to legacy resolution."""

    def test_governed_tools_default(self):
        """
        Given _load_governed_tools is stubbed to return ['Bash', 'Read']
        When Configuration.governed_tools() delegates to it
        Then it returns the governed tools as a tuple
        """
        with patch('toolguard.config._load_governed_tools', return_value=['Bash', 'Read']):
            config = Configuration(layers=())
            self.assertEqual(config.governed_tools(), ('Bash', 'Read'))

    def test_takeover_mode_shape(self):
        """
        Given load_takeover_mode_config returns a raw takeover dict
        When Configuration.takeover_mode() builds the TakeoverConfig
        Then the resulting object reflects enabled, ignored_allow_patterns, and no_match_fallback
        """
        raw = {
            'enabled': True,
            'ignored_allow_patterns': ['Bash(*)'],
            'additional_ignored_patterns': ['Read(/x/**)'],
            'no_match_fallback': 'warn_deny',
        }
        with patch('toolguard.config.load_takeover_mode_config', return_value=raw):
            config = Configuration(layers=())
            tc = config.takeover_mode()
        self.assertTrue(tc.enabled)
        self.assertEqual(tc.ignored_allow_patterns, ('Bash(*)',))
        self.assertEqual(tc.no_match_fallback, 'warn_deny')


class TestProvenanceAndIntrospection(unittest.TestCase):
    """Provenance.describe, source_type property, describe_sources."""

    def test_describe_and_source_type(self):
        """
        Given a toolguard_hook TOML provenance and its layer
        When describe(), source_type, and is_native are inspected
        Then describe mentions the level and source, source_type is 'toolguard_hook', and is_native is False
        """
        prov = Provenance('project', 'toolguard_hook', 'toml', Path('/p/toolguard_hook.toml'))
        layer = ConfigLayer(prov, MappingProxyType({}))
        self.assertIn('project', prov.describe())
        self.assertIn('toolguard_hook', prov.describe())
        self.assertEqual(layer.source_type, 'toolguard_hook')
        self.assertFalse(layer.is_native)

    def test_describe_sources(self):
        """
        Given a configuration with a single claude settings layer
        When describe_sources() is called
        Then it returns one description mentioning the settings.json file
        """
        layers = (
            ConfigLayer(Provenance('project', 'claude', 'json', Path('/p/settings.json')), MappingProxyType({})),
        )
        config = Configuration(layers=layers)
        descs = config.describe_sources()
        self.assertEqual(len(descs), 1)
        self.assertIn('settings.json', descs[0])


class TestBashPermissionsDelegation(unittest.TestCase):
    """bash_permissions() delegates to legacy _load_permissions."""

    def test_bash_permissions_tuple(self):
        """
        Given _load_permissions is stubbed to return allow and deny lists
        When Configuration.bash_permissions() delegates to it
        Then the allow and deny patterns are returned as tuples
        """
        with patch('toolguard.config._load_permissions', return_value=(['git *'], ['rm *'])):
            config = Configuration(layers=())
            allow, deny = config.bash_permissions()
        self.assertEqual(allow, ('git *',))
        self.assertEqual(deny, ('rm *',))


class TestToolguardPermissionsEdgeCases(unittest.TestCase):
    """toolguard_permissions() tolerates malformed permissions."""

    def test_non_dict_permissions_skipped(self):
        """
        Given a hook layer whose 'permissions' value is a list rather than a dict
        When toolguard_permissions() aggregates it
        Then the malformed entry is skipped and allow is empty
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/toolguard_hook.json')),
                MappingProxyType({'permissions': ['not', 'a', 'dict']}),
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertEqual(perms['allow'], ())


class TestValidationAdditionalSupportedTools(unittest.TestCase):
    """additional_supported_tools suppress the unsupported-tool issue."""

    def test_additional_supported_tool_recognized(self):
        """
        Given a hook layer that declares a custom tool via additional_supported_tools and uses it
        When validation_issues() runs
        Then no 'not a known supported tool' issue is raised for that custom tool
        """
        layers = (
            ConfigLayer(
                Provenance('project', 'toolguard_hook', 'json', Path('/p/.claude/toolguard_hook.json')),
                MappingProxyType(
                    {
                        'governed_tools': ['Bash', 'mcp__custom__tool'],
                        'additional_supported_tools': ['mcp__custom__tool'],
                        'permissions': {'allow': ['mcp__custom__tool(do *)']},
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        messages = ' '.join(i.message for i in config.validation_issues())
        self.assertNotIn('not a known supported tool', messages)


class TestExplicitModeAdjacentToml(unittest.TestCase):
    """CLAUDE_SETTINGS_PATH with an adjacent toolguard_hook.toml (TOML preferred)."""

    def test_adjacent_toml_layer(self):
        """
        Given CLAUDE_SETTINGS_PATH with both an adjacent toolguard_hook.toml and .json
        When load_configuration runs
        Then the TOML hook layer is used and the JSON one is excluded
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / 'settings.json'
            settings.write_text(json.dumps({'permissions': {'allow': ['Bash(git *)']}}))
            hook_toml = Path(tmp) / 'toolguard_hook.toml'
            hook_toml.write_text('[permissions]\nallow = ["Bash(ls *)"]\n')
            # A JSON also present, but TOML must win.
            (Path(tmp) / 'toolguard_hook.json').write_text(json.dumps({'permissions': {'allow': ['Bash(skip)']}}))
            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': str(settings)}):
                config = load_configuration()
            formats = {layer.provenance.file_format for layer in config.layers if not layer.is_native}
            self.assertIn('toml', formats)
            self.assertNotIn('json', formats)


if __name__ == '__main__':
    unittest.main()
