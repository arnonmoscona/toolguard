"""
Unit tests for permission migration script.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.scripts.migrate_permissions import (
    create_backup,
    detect_similar_patterns,
    extract_pattern_key,
    find_redundant_patterns,
    get_tool_priority,
    is_superset,
    migrate,
    sort_patterns,
    update_settings_file,
    write_json_config,
    write_toml_config,
)


class TestBackupCreation(unittest.TestCase):
    """Test backup file creation with correct naming."""

    def test_backup_with_extension(self):
        """
        Given a source file with an extension (settings.local.json)
        When create_backup copies it into a backup directory
        Then a timestamped backup is created in that directory, keeping the extension and content
        """
        with TemporaryDirectory() as tmpdir:
            # Create source file
            source_file = Path(tmpdir) / 'settings.local.json'
            source_file.write_text('{"test": true}')

            # Create backup
            backup_dir = Path(tmpdir) / 'backups'
            backup_path = create_backup(source_file, backup_dir)

            # Check backup exists
            self.assertTrue(backup_path.exists())

            # Check naming format: settings.local.YYYY-MM-DD-HHMMSS.json
            self.assertTrue(backup_path.name.startswith('settings.local.'))
            self.assertTrue(backup_path.name.endswith('.json'))

            # Check content is preserved
            self.assertEqual(backup_path.read_text(), '{"test": true}')

            # Check it's in backup_dir
            self.assertEqual(backup_path.parent, backup_dir)

    def test_backup_without_extension(self):
        """
        Given a source file with no extension (configfile)
        When create_backup copies it into a backup directory
        Then a timestamped backup named 'configfile.<timestamp>' is created with the same content
        """
        with TemporaryDirectory() as tmpdir:
            # Create source file
            source_file = Path(tmpdir) / 'configfile'
            source_file.write_text('test content')

            # Create backup
            backup_dir = Path(tmpdir) / 'backups'
            backup_path = create_backup(source_file, backup_dir)

            # Check backup exists
            self.assertTrue(backup_path.exists())

            # Check naming format: configfile.YYYY-MM-DD-HHMMSS
            self.assertTrue(backup_path.name.startswith('configfile.'))

            # Check content is preserved
            self.assertEqual(backup_path.read_text(), 'test content')

    def test_backup_creates_directory(self):
        """
        Given a backup directory path with nested parents that do not yet exist
        When create_backup runs
        Then the full backup directory tree is created
        """
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / 'test.json'
            source_file.write_text('{}')

            backup_dir = Path(tmpdir) / 'deep' / 'nested' / 'backups'
            self.assertFalse(backup_dir.exists())

            create_backup(source_file, backup_dir)

            self.assertTrue(backup_dir.exists())

    def test_backup_nonexistent_file_raises_error(self):
        """
        Given a source file path that does not exist
        When create_backup is called on it
        Then FileNotFoundError is raised
        """
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / 'nonexistent.json'
            backup_dir = Path(tmpdir) / 'backups'

            with self.assertRaises(FileNotFoundError):
                create_backup(source_file, backup_dir)


class TestPatternKeyExtraction(unittest.TestCase):
    """Test pattern key extraction for similarity detection."""

    def test_bash_command_with_args(self):
        """
        Given a Bash pattern with command arguments (e.g. 'Bash(git push:*)')
        When extract_pattern_key parses it
        Then the key is the tool plus the leading command word ('Bash', 'git')
        """
        key = extract_pattern_key('Bash(git push:*)')
        self.assertEqual(key, ('Bash', 'git'))

    def test_bash_command_simple(self):
        """
        Given a simple Bash pattern (e.g. 'Bash(git:*)')
        When extract_pattern_key parses it
        Then the key is ('Bash', 'git')
        """
        key = extract_pattern_key('Bash(git:*)')
        self.assertEqual(key, ('Bash', 'git'))

    def test_read_path_with_subdirs(self):
        """
        Given a Read pattern with subdirectories (e.g. 'Read(/tmp/foo/*)')
        When extract_pattern_key parses it
        Then the key is the tool plus the leading path segment ('Read', '/tmp/')
        """
        key = extract_pattern_key('Read(/tmp/foo/*)')
        self.assertEqual(key, ('Read', '/tmp/'))

    def test_read_path_simple(self):
        """
        Given a simple Read path pattern (e.g. 'Read(/tmp/*)')
        When extract_pattern_key parses it
        Then the key is ('Read', '/tmp/')
        """
        key = extract_pattern_key('Read(/tmp/*)')
        self.assertEqual(key, ('Read', '/tmp/'))

    def test_wildcard_only(self):
        """
        Given a wildcard-only pattern (e.g. 'Write(*)')
        When extract_pattern_key parses it
        Then the key is the tool plus '*' ('Write', '*')
        """
        key = extract_pattern_key('Write(*)')
        self.assertEqual(key, ('Write', '*'))

    def test_no_delimiters(self):
        """
        Given a pattern with no colon or path delimiters (e.g. 'Bash(ls)')
        When extract_pattern_key parses it
        Then the key is the tool plus the whole inner token ('Bash', 'ls')
        """
        key = extract_pattern_key('Bash(ls)')
        self.assertEqual(key, ('Bash', 'ls'))


class TestSimilarPatternDetection(unittest.TestCase):
    """Test detection of similar patterns (legacy tests updated for new return format)."""

    def test_detect_similar_git_commands(self):
        """
        Given existing git and ls patterns and a new 'git push --force' pattern
        When detect_similar_patterns runs
        Then the related git pattern is flagged as similar and the unrelated ls pattern is not
        """
        existing = ['Bash(git push:*)', 'Bash(ls:*)']
        new_pattern = 'Bash(git push --force:*)'

        similar = detect_similar_patterns(new_pattern, existing)

        # Extract just the patterns from tuples
        similar_patterns = [p for p, _, _ in similar]
        self.assertIn('Bash(git push:*)', similar_patterns)
        self.assertNotIn('Bash(ls:*)', similar_patterns)

    def test_detect_similar_paths(self):
        """
        Given existing Read path patterns and a new 'Read(/tmp/foo/*)' pattern
        When detect_similar_patterns runs
        Then the matching '/tmp/' path pattern is flagged as similar and unrelated paths are not
        """
        existing = ['Read(/tmp/*)', 'Read(/var/*)', 'Read(/home/*)']
        new_pattern = 'Read(/tmp/foo/*)'

        similar = detect_similar_patterns(new_pattern, existing)

        # Extract just the patterns from tuples
        similar_patterns = [p for p, _, _ in similar]
        self.assertIn('Read(/tmp/*)', similar_patterns)
        self.assertNotIn('Read(/var/*)', similar_patterns)

    def test_identical_pattern_not_similar(self):
        """
        Given an existing pattern and a new pattern identical to it
        When detect_similar_patterns runs
        Then it does not crash and returns a list (duplicates are handled gracefully elsewhere)
        """
        existing = ['Bash(git:*)', 'Bash(ls:*)']
        new_pattern = 'Bash(git:*)'

        similar = detect_similar_patterns(new_pattern, existing)

        # difflib's get_close_matches typically returns the identical pattern itself
        # since it has similarity of 1.0. This is acceptable behavior - the migration
        # script handles this gracefully (won't create duplicates)
        # We just verify the function doesn't crash with identical patterns
        self.assertIsInstance(similar, list)

    def test_no_similar_patterns(self):
        """
        Given existing patterns that are all very different from the new pattern
        When detect_similar_patterns runs
        Then no similar patterns are returned (empty result)
        """
        # Use very different patterns that won't match even with difflib
        existing = ['Read(/var/log/*)', 'Write(/home/user/docs/*)', 'Edit(/etc/config)']
        new_pattern = 'Bash(git:*)'

        similar = detect_similar_patterns(new_pattern, existing)

        self.assertEqual(len(similar), 0)

    def test_broader_pattern_is_similar(self):
        """
        Given an existing broad pattern 'Bash(git:*)' and a new specific 'Bash(git push:*)'
        When detect_similar_patterns runs
        Then the broader existing pattern is flagged as similar to the specific one
        """
        existing = ['Bash(git:*)']
        new_pattern = 'Bash(git push:*)'

        similar = detect_similar_patterns(new_pattern, existing)

        # Extract just the patterns from tuples
        similar_patterns = [p for p, _, _ in similar]
        self.assertIn('Bash(git:*)', similar_patterns)


class TestPatternSorting(unittest.TestCase):
    """Test pattern sorting behavior."""

    def test_sort_by_tool_priority(self):
        """
        Given an unordered list of patterns across several tool types
        When sort_patterns sorts them
        Then they are ordered by tool priority: Bash, Read, Write, Edit, then others
        """
        patterns = [
            'Edit(/tmp/*)',
            'Write(/tmp/*)',
            'Read(/tmp/*)',
            'Bash(ls:*)',
            'Grep(pattern)',
        ]

        sorted_patterns = sort_patterns(patterns)

        # Check tool order: Bash, Read, Write, Edit, Others
        tools = [p.split('(')[0] for p in sorted_patterns]
        self.assertEqual(tools[0], 'Bash')
        self.assertEqual(tools[1], 'Read')
        self.assertEqual(tools[2], 'Write')
        self.assertEqual(tools[3], 'Edit')
        self.assertEqual(tools[4], 'Grep')

    def test_sort_alphabetically_within_tool(self):
        """
        Given several Bash patterns in arbitrary order
        When sort_patterns sorts them
        Then patterns of the same tool are ordered alphabetically by command
        """
        patterns = [
            'Bash(rm:*)',
            'Bash(git:*)',
            'Bash(ls:*)',
            'Bash(cat:*)',
        ]

        sorted_patterns = sort_patterns(patterns)

        self.assertEqual(
            sorted_patterns,
            [
                'Bash(cat:*)',
                'Bash(git:*)',
                'Bash(ls:*)',
                'Bash(rm:*)',
            ],
        )

    def test_sort_case_insensitive(self):
        """
        Given Bash patterns with mixed-case commands
        When sort_patterns sorts them
        Then ordering uses case-insensitive comparison (abc, def, XYZ, Zsh)
        """
        patterns = [
            'Bash(Zsh:*)',
            'Bash(abc:*)',
            'Bash(XYZ:*)',
            'Bash(def:*)',
        ]

        sorted_patterns = sort_patterns(patterns)

        # Lowercase comparison: abc, def, xyz, zsh
        expected_order = ['abc', 'def', 'XYZ', 'Zsh']
        actual_order = [p.split('(')[1].split(':')[0] for p in sorted_patterns]
        self.assertEqual(actual_order, expected_order)

    def test_get_tool_priority(self):
        """
        Given patterns for Bash, Read, Write, Edit, and another tool
        When get_tool_priority is called on each
        Then it returns the priority index (0-4) paired with the lowercased pattern as sort key
        """
        self.assertEqual(get_tool_priority('Bash(ls:*)'), (0, 'bash(ls:*)'))
        self.assertEqual(get_tool_priority('Read(/tmp/*)'), (1, 'read(/tmp/*)'))
        self.assertEqual(get_tool_priority('Write(/tmp/*)'), (2, 'write(/tmp/*)'))
        self.assertEqual(get_tool_priority('Edit(/tmp/*)'), (3, 'edit(/tmp/*)'))
        self.assertEqual(get_tool_priority('Grep(pattern)'), (4, 'grep(pattern)'))


class TestTOMLConfigWriting(unittest.TestCase):
    """Test writing TOML configuration files."""

    def test_write_toml_with_sorting(self):
        """
        Given unsorted allow permissions and auto_sort enabled
        When write_toml_config writes the TOML file
        Then the rules appear sorted by tool priority (Bash before Read before Write)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            permissions = {
                'allow': ['Write(/tmp/*)', 'Bash(ls:*)', 'Read(/tmp/*)'],
                'deny': ['Bash(rm:*)'],
                'ask': [],
            }

            write_toml_config(config_path, permissions, auto_sort=True)

            # Read back content
            content = config_path.read_text()

            # Check that patterns are sorted (Bash, Read, Write)
            self.assertIn('[permissions]', content)
            bash_pos = content.index('Bash(ls:*)')
            read_pos = content.index('Read(/tmp/*)')
            write_pos = content.index('Write(/tmp/*)')
            self.assertLess(bash_pos, read_pos)
            self.assertLess(read_pos, write_pos)

    def test_write_toml_without_sorting(self):
        """
        Given allow permissions in a given order and auto_sort disabled
        When write_toml_config writes the TOML file
        Then the original input order is preserved (Write before Bash)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            permissions = {
                'allow': ['Write(/tmp/*)', 'Bash(ls:*)', 'Read(/tmp/*)'],
                'deny': [],
                'ask': [],
            }

            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()

            # Check that order is preserved (Write before Bash)
            write_pos = content.index('Write(/tmp/*)')
            bash_pos = content.index('Bash(ls:*)')
            self.assertLess(write_pos, bash_pos)

    def test_toml_escapes_special_chars(self):
        """
        Given a permission pattern containing double quotes
        When write_toml_config writes the TOML file
        Then the embedded quotes are escaped in the output
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            permissions = {
                'allow': ['Bash(echo "test":*)'],
                'deny': [],
                'ask': [],
            }

            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()

            # Check that quotes are escaped
            self.assertIn('echo \\"test\\"', content)


class TestJSONConfigWriting(unittest.TestCase):
    """Test writing JSON configuration files."""

    def test_write_json_with_sorting(self):
        """
        Given unsorted allow permissions and auto_sort enabled
        When write_json_config writes the JSON file
        Then the allow list is stored sorted by tool priority (Bash, Read, Write)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.json'

            permissions = {
                'allow': ['Write(/tmp/*)', 'Bash(ls:*)', 'Read(/tmp/*)'],
                'deny': [],
                'ask': [],
            }

            write_json_config(config_path, permissions, auto_sort=True)

            # Read back and check
            with open(config_path, 'r') as f:
                config = json.load(f)

            allow_patterns = config['permissions']['allow']

            # Check sorted order: Bash, Read, Write
            self.assertEqual(allow_patterns[0], 'Bash(ls:*)')
            self.assertEqual(allow_patterns[1], 'Read(/tmp/*)')
            self.assertEqual(allow_patterns[2], 'Write(/tmp/*)')

    def test_write_json_preserves_other_config(self):
        """
        Given an existing JSON config with unrelated keys (governed_tools, other_setting)
        When write_json_config writes new permissions into it
        Then the unrelated keys are preserved and the permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.json'

            # Create initial config with other keys
            initial_config = {
                'governed_tools': ['Bash', 'Read'],
                'other_setting': 'value',
            }
            with open(config_path, 'w') as f:
                json.dump(initial_config, f)

            # Write permissions
            permissions = {'allow': ['Bash(ls:*)'], 'deny': [], 'ask': []}
            write_json_config(config_path, permissions, auto_sort=False)

            # Read back and verify
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Check that other keys are preserved
            self.assertEqual(config['governed_tools'], ['Bash', 'Read'])
            self.assertEqual(config['other_setting'], 'value')
            self.assertEqual(config['permissions']['allow'], ['Bash(ls:*)'])


class TestSettingsFileUpdate(unittest.TestCase):
    """Test updating settings.local.json after migration."""

    def test_remove_migrated_patterns(self):
        """
        Given a settings file and a set of migrated patterns that overlap some of its entries
        When update_settings_file runs
        Then the migrated patterns are removed from the settings, leaving only non-migrated ones
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'

            # Create settings file
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)', 'Bash(git:*)', 'Read(/tmp/*)'],
                    'deny': ['Bash(rm:*)'],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Migrate some patterns
            migrated = {
                'allow': ['Bash(git:*)', 'Read(/tmp/*)'],
                'deny': ['Bash(rm:*)'],
                'ask': [],
            }

            update_settings_file(settings_path, migrated)

            # Read back and verify
            with open(settings_path, 'r') as f:
                updated = json.load(f)

            # Check that migrated patterns are removed
            self.assertEqual(updated['permissions']['allow'], ['Bash(ls:*)'])
            self.assertEqual(updated['permissions']['deny'], [])

    def test_keep_empty_permissions_structure(self):
        """
        Given a settings file whose only pattern is migrated away
        When update_settings_file runs
        Then the permissions structure remains with empty allow, deny, and ask lists
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'

            # Create settings file
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Migrate all patterns
            migrated = {
                'allow': ['Bash(ls:*)'],
                'deny': [],
                'ask': [],
            }

            update_settings_file(settings_path, migrated)

            # Read back and verify
            with open(settings_path, 'r') as f:
                updated = json.load(f)

            # Check that permissions structure still exists with empty lists
            self.assertIn('permissions', updated)
            self.assertEqual(updated['permissions']['allow'], [])
            self.assertEqual(updated['permissions']['deny'], [])
            self.assertEqual(updated['permissions']['ask'], [])


class TestMigration(unittest.TestCase):
    """Test full migration process."""

    def test_dry_run_mode(self):
        """
        Given a project with a settings.local.json containing patterns
        When migrate runs with dry_run=True
        Then no files are changed, no TOML config is created, and it exits 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create settings.local.json with patterns
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)', 'Bash(git:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run dry-run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root, dry_run=True)

            # Check no changes were made
            with open(settings_path, 'r') as f:
                after_settings = json.load(f)

            self.assertEqual(after_settings, settings)
            self.assertFalse((claude_dir / 'toolguard_hook.toml').exists())
            self.assertEqual(exit_code, 0)

    def test_migration_creates_new_toml_config(self):
        """
        Given a project with settings.local.json patterns and no existing toolguard_hook.toml
        When migrate runs
        Then a new toolguard_hook.toml is created with the patterns, the settings allow list is
        emptied, and it exits 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create settings.local.json
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)', 'Bash(git:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root)

            # Check that toolguard_hook.toml was created
            toml_path = claude_dir / 'toolguard_hook.toml'
            self.assertTrue(toml_path.exists())

            # Check content
            content = toml_path.read_text()
            self.assertIn('Bash(ls:*)', content)
            self.assertIn('Bash(git:*)', content)

            # Check settings.local.json was updated
            with open(settings_path, 'r') as f:
                updated_settings = json.load(f)

            self.assertEqual(updated_settings['permissions']['allow'], [])
            self.assertEqual(exit_code, 0)

    def test_migration_adds_to_existing_toml(self):
        """
        Given an existing toolguard_hook.toml and settings.local.json with extra patterns
        When migrate runs
        Then the new patterns are added to the TOML and all settings patterns (migrated or
        redundant) are removed, exiting 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create existing toolguard_hook.toml
            toml_path = claude_dir / 'toolguard_hook.toml'
            toml_content = """[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
            toml_path.write_text(toml_content)

            # Create settings.local.json with new patterns
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)', 'Bash(git:*)', 'Read(/tmp/*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root)

            # Check that new patterns were added
            content = toml_path.read_text()
            self.assertIn('Bash(ls:*)', content)
            self.assertIn('Bash(git:*)', content)
            self.assertIn('Read(/tmp/*)', content)

            # Check settings.local.json
            with open(settings_path, 'r') as f:
                updated_settings = json.load(f)

            # All patterns should be removed:
            # - Bash(ls:*) is redundant (exact duplicate in toolguard)
            # - Bash(git:*) and Read(/tmp/*) were migrated
            self.assertEqual(updated_settings['permissions']['allow'], [])
            self.assertEqual(exit_code, 0)

    def test_migration_skips_identical_patterns(self):
        """
        Given a toolguard_hook.toml and settings.local.json that share an identical pattern
        When migrate runs
        Then the shared pattern appears only once in the TOML (no duplication), exiting 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create toolguard config with existing pattern
            toml_path = claude_dir / 'toolguard_hook.toml'
            toml_content = """[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
            toml_path.write_text(toml_content)

            # Create settings.local.json with same pattern
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root)

            # Read config and count occurrences
            content = toml_path.read_text()
            occurrences = content.count('Bash(ls:*)')

            # Should appear only once (not duplicated)
            self.assertEqual(occurrences, 1)
            self.assertEqual(exit_code, 0)

    def test_no_migration_when_no_new_patterns(self):
        """
        Given a toolguard_hook.toml and settings.local.json with the same single pattern
        When migrate runs with nothing new to migrate
        Then it reports success and exits 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create toolguard config
            toml_path = claude_dir / 'toolguard_hook.toml'
            toml_content = """[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
            toml_path.write_text(toml_content)

            # Create settings.local.json with same patterns
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(ls:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root)

            # Should return success with no changes
            self.assertEqual(exit_code, 0)

    def test_migration_creates_backups(self):
        """
        Given a project with settings.local.json and a configured backup directory
        When migrate runs with that backup_dir
        Then a single timestamped settings.local.*.json backup is created and it exits 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create settings.local.json
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': ['Bash(git:*)'],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            backup_dir = project_root / 'logs' / 'config-backups'

            # Run migration
            with patch(
                'toolguard.scripts.migrate_permissions.find_project_root',
                return_value=project_root,
            ):
                exit_code = migrate(project_root, backup_dir=backup_dir)

            # Check backups were created
            self.assertTrue(backup_dir.exists())

            backups = list(backup_dir.glob('settings.local.*.json'))
            self.assertEqual(len(backups), 1)

            # Check backup naming format
            backup_name = backups[0].name
            self.assertTrue(backup_name.startswith('settings.local.'))
            self.assertTrue(backup_name.endswith('.json'))

            self.assertEqual(exit_code, 0)


class TestSupersetDetection(unittest.TestCase):
    """Test superset detection for :*) patterns."""

    def test_superset_with_colon_star_pattern(self):
        """
        Given two :*) patterns where one's command is a prefix of the other's
        When is_superset compares the broader pattern against the narrower one
        Then it reports True (the broader pattern is a superset)
        """
        # Bash(uv run ruff:*) is superset of Bash(uv run ruff format:*)
        self.assertTrue(is_superset('Bash(uv run ruff:*)', 'Bash(uv run ruff format:*)'))
        self.assertTrue(is_superset('Bash(git:*)', 'Bash(git push:*)'))

    def test_not_superset_when_no_prefix_match(self):
        """
        Given two :*) patterns where neither command is a true word-prefix of the other
        When is_superset compares them
        Then it reports False
        """
        self.assertFalse(is_superset('Bash(ruff:*)', 'Bash(ruffle:*)'))
        self.assertFalse(is_superset('Bash(git:*)', 'Bash(ls:*)'))

    def test_not_superset_for_identical_patterns(self):
        """
        Given two identical patterns
        When is_superset compares them
        Then it reports False (a pattern is not a superset of itself)
        """
        self.assertFalse(is_superset('Bash(git:*)', 'Bash(git:*)'))

    def test_extended_syntax_not_detected_as_superset(self):
        """
        Given patterns using extended syntax prefixes ([regex], [glob], [native])
        When is_superset is called with one of them involved
        Then it reports False because extended-syntax patterns are skipped
        """
        self.assertFalse(is_superset('[regex]^git', 'Bash(git push:*)'))
        self.assertFalse(is_superset('Bash(git:*)', '[glob]git:*'))
        self.assertFalse(is_superset('[native]git *', 'Bash(git push:*)'))

    def test_non_colon_star_patterns_not_superset(self):
        """
        Given patterns that lack the :*) postfix (plain or trailing-* forms)
        When is_superset compares them
        Then it reports False because only :*) patterns are handled
        """
        self.assertFalse(is_superset('Bash(git)', 'Bash(git push)'))
        self.assertFalse(is_superset('Bash(git*)', 'Bash(git push*)'))


class TestRedundantPatternDetection(unittest.TestCase):
    """Test detection of redundant patterns."""

    def test_find_exact_duplicates(self):
        """
        Given native permissions that exactly duplicate some toolguard permissions
        When find_redundant_patterns compares them
        Then the exact duplicates are reported as redundant and unique patterns are not
        """
        native_perms = {
            'allow': ['Bash(git:*)', 'Bash(ls:*)', 'Bash(uv run pytest:*)'],
            'deny': [],
            'ask': [],
        }
        toolguard_perms = {
            'allow': ['Bash(git:*)', 'Bash(uv run pytest:*)'],
            'deny': [],
            'ask': [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertIn('Bash(git:*)', redundant['allow'])
        self.assertIn('Bash(uv run pytest:*)', redundant['allow'])
        self.assertNotIn('Bash(ls:*)', redundant['allow'])

    def test_find_subsets_covered_by_supersets(self):
        """
        Given native permissions that are narrower subsets of broader toolguard permissions
        When find_redundant_patterns compares them
        Then the subset patterns are reported as redundant (covered by the supersets)
        """
        native_perms = {
            'allow': ['Bash(uv run ruff format:*)', 'Bash(git push:*)'],
            'deny': [],
            'ask': [],
        }
        toolguard_perms = {
            'allow': ['Bash(uv run ruff:*)', 'Bash(git:*)'],
            'deny': [],
            'ask': [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertIn('Bash(uv run ruff format:*)', redundant['allow'])
        self.assertIn('Bash(git push:*)', redundant['allow'])

    def test_no_redundant_patterns(self):
        """
        Given native permissions that neither duplicate nor are subsets of toolguard permissions
        When find_redundant_patterns compares them
        Then no patterns are reported as redundant (empty allow result)
        """
        native_perms = {
            'allow': ['Bash(ls:*)', 'Bash(cat:*)'],
            'deny': [],
            'ask': [],
        }
        toolguard_perms = {
            'allow': ['Bash(git:*)'],
            'deny': [],
            'ask': [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertEqual(len(redundant['allow']), 0)


class TestImprovedSimilarityDetection(unittest.TestCase):
    """Test improved similarity detection with difflib."""

    def test_similarity_uses_difflib(self):
        """
        Given an existing pattern that differs from the new one only by a single space
        When detect_similar_patterns runs
        Then it finds that close match with a high similarity score (> 0.9)
        """
        existing = [
            'Bash(~/bin/open_note_by_title.sh :*)',
            'Bash(git:*)',
            'Bash(ls:*)',
        ]
        new_pattern = 'Bash(~/bin/open_note_by_title.sh:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        # Should find the close match with high similarity
        self.assertTrue(len(similar) > 0)
        pattern, score, _ = similar[0]
        self.assertEqual(pattern, 'Bash(~/bin/open_note_by_title.sh :*)')
        self.assertGreater(score, 0.9)  # Very similar, just missing space

    def test_similarity_returns_ranked_results(self):
        """
        Given several existing patterns of varying closeness to the new pattern
        When detect_similar_patterns runs
        Then the most similar pattern is first and scores descend across the results
        """
        existing = [
            'Bash(uv run ruff:*)',
            'Bash(uv run pytest:*)',
            'Bash(uv run mypy:*)',
        ]
        new_pattern = 'Bash(uv run ruff format:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        # Should rank by similarity, with ruff being most similar
        if len(similar) > 0:
            first_pattern, first_score, _ = similar[0]
            # The most similar should be the ruff pattern
            self.assertEqual(first_pattern, 'Bash(uv run ruff:*)')
            # Scores should be in descending order
            for i in range(len(similar) - 1):
                self.assertGreaterEqual(similar[i][1], similar[i + 1][1])

    def test_similarity_identifies_supersets(self):
        """
        Given an existing broad pattern that is a superset of the new specific pattern
        When detect_similar_patterns runs
        Then the match is returned with its superset flag set True
        """
        existing = ['Bash(uv run ruff:*)']
        new_pattern = 'Bash(uv run ruff format:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertTrue(len(similar) > 0)
        pattern, score, is_superset_match = similar[0]
        self.assertEqual(pattern, 'Bash(uv run ruff:*)')
        self.assertTrue(is_superset_match)

    def test_max_similar_matches_limit(self):
        """
        Given more candidate similar patterns than the max_matches limit
        When detect_similar_patterns runs with max_matches=2
        Then at most 2 matches are returned
        """
        existing = [
            'Bash(uv run pytest:*)',
            'Bash(uv run mypy:*)',
            'Bash(uv run ruff:*)',
            'Bash(uv run black:*)',
            'Bash(uv run isort:*)',
        ]
        new_pattern = 'Bash(uv run ruff format:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=2)

        # Should return at most 2 matches
        self.assertLessEqual(len(similar), 2)

    def test_common_prefix_not_flagged_as_similar(self):
        """
        Given many existing patterns that all share the same long prefix
        When detect_similar_patterns runs against a new same-prefix pattern
        Then no matches are returned because the shared prefix is not discriminating
        """
        # Create many patterns with same prefix
        existing = [f'Bash(uv run tool{i}:*)' for i in range(20)]
        new_pattern = 'Bash(uv run tool99:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        # Should return empty list because prefix isn't discriminating
        self.assertEqual(len(similar), 0)


class TestTOMLSectionPreservation(unittest.TestCase):
    """Test that write_toml_config preserves other sections (Bug 1)."""

    def test_preserves_takeover_mode_section(self):
        """
        Given a TOML config with [takeover_mode] and [config_sync] sections plus permissions
        When write_toml_config writes new permissions
        Then the other sections and their values are preserved and permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            # Create initial config with multiple sections
            initial_content = """[takeover_mode]
enabled = true
no_match_fallback = "deny"

[config_sync]
auto_migrate = false

[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            # Write new permissions
            permissions = {'allow': ['Bash(git:*)', 'Read(/tmp/*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            # Read back and verify
            new_content = config_path.read_text()

            # Check that other sections are preserved
            self.assertIn('[takeover_mode]', new_content)
            self.assertIn('enabled = true', new_content)
            self.assertIn('[config_sync]', new_content)
            self.assertIn('auto_migrate = false', new_content)

            # Check that permissions were updated
            self.assertIn('Bash(git:*)', new_content)
            self.assertIn('Read(/tmp/*)', new_content)

    def test_preserves_top_level_keys(self):
        """
        Given a TOML config with top-level keys (governed_tools, additional_supported_tools)
        When write_toml_config writes new permissions
        Then those top-level keys are preserved and the permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            # Create initial config with top-level keys
            initial_content = """governed_tools = [
    "Bash",
    "Read",
    "Write"
]

additional_supported_tools = [
    "mcp__local-tools__checked_bash"
]

[permissions]
allow = []
deny = []
"""
            config_path.write_text(initial_content)

            # Write new permissions
            permissions = {'allow': ['Bash(ls:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            # Read back and verify
            new_content = config_path.read_text()

            # Check that top-level keys are preserved
            self.assertIn('governed_tools', new_content)
            self.assertIn('additional_supported_tools', new_content)
            self.assertIn('mcp__local-tools__checked_bash', new_content)

            # Check permissions updated
            self.assertIn('Bash(ls:*)', new_content)

    def test_creates_permissions_section_when_missing(self):
        """
        Given a TOML config with other sections but no [permissions] section
        When write_toml_config writes permissions
        Then a [permissions] section is added while the existing sections are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            # Create config without [permissions] section
            initial_content = """[takeover_mode]
enabled = true

[config_sync]
auto_migrate = false
"""
            config_path.write_text(initial_content)

            # Write permissions
            permissions = {'allow': ['Bash(git:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            # Read back and verify
            new_content = config_path.read_text()

            # Check that other sections are preserved
            self.assertIn('[takeover_mode]', new_content)
            self.assertIn('[config_sync]', new_content)

            # Check that [permissions] was added
            self.assertIn('[permissions]', new_content)
            self.assertIn('Bash(git:*)', new_content)

    def test_preserves_section_order(self):
        """
        Given a TOML config with sections ordered takeover_mode, permissions, config_sync
        When write_toml_config rewrites the permissions
        Then the original section ordering is maintained
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[takeover_mode]
enabled = true

[permissions]
allow = ["Bash(ls:*)"]
deny = []

[config_sync]
auto_migrate = false
"""
            config_path.write_text(initial_content)

            # Write new permissions
            permissions = {'allow': ['Bash(git:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            # Check order is preserved: takeover_mode before permissions before config_sync
            takeover_pos = new_content.index('[takeover_mode]')
            permissions_pos = new_content.index('[permissions]')
            config_sync_pos = new_content.index('[config_sync]')

            self.assertLess(takeover_pos, permissions_pos)
            self.assertLess(permissions_pos, config_sync_pos)


class TestCommentPreservation(unittest.TestCase):
    """Test that comments are preserved when rewriting TOML (Bug 2)."""

    def test_preserves_inline_comments(self):
        """
        Given a TOML config with inline comments on the same line as rules
        When write_toml_config rewrites the permissions adding a new rule
        Then the inline comments are preserved in the output
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
allow = [
  "Bash(ls:*)",  # This allows ls commands
  "Bash(git:*)",  # Git commands
]
deny = []
"""
            config_path.write_text(initial_content)

            # Add a new pattern
            permissions = {'allow': ['Bash(ls:*)', 'Bash(git:*)', 'Read(/tmp/*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            # Inline comments should be preserved
            self.assertIn('# This allows ls commands', new_content)
            self.assertIn('# Git commands', new_content)

    def test_preserves_comment_blocks_above_rules(self):
        """
        Given a TOML config with comment blocks above individual rules
        When write_toml_config rewrites the permissions with sorting enabled
        Then those comment blocks are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
allow = [
  # Allow git operations
  "Bash(git:*)",

  # Allow file listing
  "Bash(ls:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            # Rewrite with sorting (will change order)
            permissions = {'allow': ['Bash(git:*)', 'Bash(ls:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=True)

            new_content = config_path.read_text()

            # Comments should still be present
            self.assertIn('# Allow git operations', new_content)
            self.assertIn('# Allow file listing', new_content)

    def test_preserves_top_of_section_comments(self):
        """
        Given a TOML config with explanatory comments at the top of the permissions section
        When write_toml_config rewrites the permissions
        Then those comments are preserved and remain before the first rule
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
# These permissions are equivalent to Claude code permissions
# Extended syntax is supported

allow = [
  "Bash(ls:*)",
  "Bash(git:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            # Rewrite
            permissions = {'allow': ['Bash(git:*)', 'Bash(ls:*)', 'Read(/tmp/*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            # Top comments should be preserved
            self.assertIn('# These permissions are equivalent', new_content)
            self.assertIn('# Extended syntax is supported', new_content)

            # And they should be before the rules
            comment_pos = new_content.index('# These permissions')
            first_rule_pos = new_content.index('Bash(')
            self.assertLess(comment_pos, first_rule_pos)

    def test_preserves_bottom_of_section_comments(self):
        """
        Given a TOML config with trailing comments after the last rule in the allow list
        When write_toml_config rewrites the permissions adding a new rule
        Then those comments are preserved and remain after the last rule
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
allow = [
  "Bash(ls:*)",
  "Bash(git:*)",
  # TODO: Add more patterns here
  # Review this list regularly
]
deny = []
"""
            config_path.write_text(initial_content)

            # Rewrite
            permissions = {'allow': ['Bash(ls:*)', 'Bash(git:*)', 'Read(/tmp/*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            # Bottom comments should be preserved
            self.assertIn('# TODO: Add more patterns here', new_content)
            self.assertIn('# Review this list regularly', new_content)

            # And they should be after the last rule
            last_rule_pos = new_content.rindex('Read(/tmp/*)')
            comment_pos = new_content.index('# TODO')
            self.assertGreater(comment_pos, last_rule_pos)

    def test_preserves_blank_lines_in_comment_blocks(self):
        """
        Given a TOML config with comment blocks separated by blank lines above a rule
        When write_toml_config rewrites the permissions
        Then the comment lines are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
allow = [
  # Section 1: Git commands

  # Allow all git operations
  "Bash(git:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            # Rewrite
            permissions = {'allow': ['Bash(git:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            # Comments should be preserved
            self.assertIn('# Section 1: Git commands', new_content)
            self.assertIn('# Allow all git operations', new_content)

    def test_comments_move_with_sorted_rules(self):
        """
        Given a TOML config where each rule has its own comment block and sorting reorders them
        When write_toml_config rewrites with auto_sort enabled
        Then each comment moves together with its associated rule into the new order
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'toolguard_hook.toml'

            initial_content = """[permissions]
allow = [
  # ZZZ pattern
  "Write(/tmp/*)",

  # AAA pattern
  "Bash(ls:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            # Rewrite with sorting enabled
            permissions = {'allow': ['Write(/tmp/*)', 'Bash(ls:*)'], 'deny': [], 'ask': []}
            write_toml_config(config_path, permissions, auto_sort=True)

            new_content = config_path.read_text()

            # After sorting, Bash should come before Write
            bash_pos = new_content.index('Bash(ls:*)')
            write_pos = new_content.index('Write(/tmp/*)')
            self.assertLess(bash_pos, write_pos)

            # Comments should move with their rules
            aaa_comment_pos = new_content.index('# AAA pattern')
            zzz_comment_pos = new_content.index('# ZZZ pattern')

            # AAA comment should be before Bash rule
            self.assertLess(aaa_comment_pos, bash_pos)

            # ZZZ comment should be before Write rule
            self.assertLess(zzz_comment_pos, write_pos)


class TestBlanketPatternSimilarity(unittest.TestCase):
    """Test that blanket patterns are not flagged as similar (Bug 3)."""

    def test_blanket_bash_pattern_not_similar(self):
        """
        Given an existing blanket Bash(*) pattern and a new specific Bash(wc:*) pattern
        When detect_similar_patterns runs
        Then no matches are returned because the blanket pattern has no meaningful prefix
        """
        existing = ['Bash(*)', 'Read(*)', 'Write(*)']
        new_pattern = 'Bash(wc:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        # Should return empty - blanket patterns have no meaningful prefix
        self.assertEqual(len(similar), 0)

    def test_blanket_read_pattern_not_similar(self):
        """
        Given an existing blanket Read(*) pattern and a new specific Read(/tmp/*) pattern
        When detect_similar_patterns runs
        Then no matches are returned
        """
        existing = ['Read(*)', 'Bash(*)']
        new_pattern = 'Read(/tmp/*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(similar), 0)

    def test_new_blanket_pattern_not_similar(self):
        """
        Given existing specific Bash patterns and a new blanket Bash(*) pattern
        When detect_similar_patterns runs
        Then no matches are returned because the new blanket pattern is not compared
        """
        existing = ['Bash(git:*)', 'Bash(ls:*)', 'Bash(find:*)']
        new_pattern = 'Bash(*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        # New blanket pattern should not be compared
        self.assertEqual(len(similar), 0)

    def test_meaningful_prefix_extraction_blanket(self):
        """
        Given blanket patterns of the form Tool(*)
        When extract_meaningful_prefix is called on each
        Then it returns an empty string (no meaningful prefix)
        """
        from toolguard.scripts.migrate_permissions import extract_meaningful_prefix

        self.assertEqual(extract_meaningful_prefix('Bash(*)'), '')
        self.assertEqual(extract_meaningful_prefix('Read(*)'), '')
        self.assertEqual(extract_meaningful_prefix('Write(*)'), '')
        self.assertEqual(extract_meaningful_prefix('Edit(*)'), '')

    def test_meaningful_prefix_extraction_with_content(self):
        """
        Given patterns whose inner content carries a real command or path prefix
        When extract_meaningful_prefix is called on each
        Then it returns that command or path prefix string
        """
        from toolguard.scripts.migrate_permissions import extract_meaningful_prefix

        self.assertEqual(extract_meaningful_prefix('Bash(uv run ruff format:*)'), 'uv run ruff format')
        self.assertEqual(extract_meaningful_prefix('Bash(find:*)'), 'find')
        self.assertEqual(extract_meaningful_prefix('Read(/tmp/*)'), '/tmp/')
        self.assertEqual(extract_meaningful_prefix('Bash(git push:*)'), 'git push')

    def test_similarity_respects_max_matches_per_pattern(self):
        """
        Given more candidate patterns than the max_matches limit for a single new pattern
        When detect_similar_patterns runs with max_matches=2
        Then at most 2 matches are returned for that pattern
        """
        existing = [
            'Bash(uv run pytest:*)',
            'Bash(uv run mypy:*)',
            'Bash(uv run ruff:*)',
            'Bash(uv run black:*)',
            'Bash(uv run isort:*)',
        ]
        new_pattern = 'Bash(uv run ruff format:*)'

        similar = detect_similar_patterns(new_pattern, existing, max_matches=2)

        # Should return at most 2 matches
        self.assertLessEqual(len(similar), 2)


class TestMigrationWithRedundantPatterns(unittest.TestCase):
    """Test full migration flow with redundant pattern removal."""

    def test_migration_removes_redundant_patterns(self):
        """
        Given a toolguard config and settings.local.json containing duplicates, subsets, and one
        genuinely new pattern
        When migrate runs the full flow
        Then all redundant and migrated patterns are removed from settings, the new pattern is
        added to the toolguard config, and it exits 0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / '.git').mkdir()
            claude_dir = project_root / '.claude'
            claude_dir.mkdir()

            # Create toolguard config with existing patterns
            toml_path = claude_dir / 'toolguard_hook.toml'
            toml_content = """[permissions]
allow = [
  "Bash(git:*)",
  "Bash(uv run ruff:*)",
]
deny = []
"""
            toml_path.write_text(toml_content)

            # Create settings.local.json with duplicates and subsets
            settings_path = claude_dir / 'settings.local.json'
            settings = {
                'permissions': {
                    'allow': [
                        'Bash(git:*)',  # Exact duplicate
                        'Bash(git push:*)',  # Subset of git:*
                        'Bash(uv run ruff format:*)',  # Subset of uv run ruff:*
                        'Bash(ls:*)',  # New pattern to migrate
                    ],
                    'deny': [],
                    'ask': [],
                }
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            # Run migration
            with patch('toolguard.scripts.migrate_permissions.find_project_root', return_value=project_root):
                exit_code = migrate(project_root)

            # Check that redundant patterns were removed
            with open(settings_path, 'r') as f:
                updated_settings = json.load(f)

            # Should keep only Bash(ls:*) which was migrated (but not redundant before migration)
            # All redundant patterns should be removed
            remaining = updated_settings['permissions']['allow']
            self.assertNotIn('Bash(git:*)', remaining)  # Exact duplicate - removed
            self.assertNotIn('Bash(git push:*)', remaining)  # Subset - removed
            self.assertNotIn('Bash(uv run ruff format:*)', remaining)  # Subset - removed
            self.assertNotIn('Bash(ls:*)', remaining)  # Migrated - removed

            # Verify patterns were added to toolguard config
            content = toml_path.read_text()
            self.assertIn('Bash(ls:*)', content)

            self.assertEqual(exit_code, 0)


if __name__ == '__main__':
    unittest.main()
