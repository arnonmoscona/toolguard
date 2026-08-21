"""
Unit tests for permission migration script.
"""

import json
import os
import tomllib
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from test.unit._subprocess_harness import release_barrier_when_ready, run_child
from toolguard import file_lock
from toolguard import permission_migration as permission_migration_module
from toolguard.config_write_guard import (
    ConfigWriteVerificationError,
    verified_write_config,
)
from toolguard.permission_migration import (
    MigrationOutcome,
    create_backup,
    detect_similar_patterns,
    extract_pattern_key,
    find_redundant_patterns,
    is_superset,
    migrate,
    update_settings_file,
    write_json_config,
    write_toml_config,
)
from toolguard.rule_entry import RuleEntry, normalize_entries_preserving, real_patterns
from toolguard.rule_sort import get_tool_priority, sort_patterns
from toolguard.scripts import migrate_permissions as migrate_permissions_module


class TestBackupCreation(unittest.TestCase):
    """Test backup file creation with correct naming."""

    def test_backup_with_extension(self):
        """
        Given a source file with an extension (settings.local.json)
        When create_backup copies it into a backup directory
        Then a timestamped backup is created in that directory, keeping the extension and content
        """
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "settings.local.json"
            source_file.write_text('{"test": true}')

            backup_dir = Path(tmpdir) / "backups"
            backup_path = create_backup(source_file, backup_dir)

            self.assertTrue(backup_path.exists())

            self.assertTrue(backup_path.name.startswith("settings.local."))
            self.assertTrue(backup_path.name.endswith(".json"))

            self.assertEqual(backup_path.read_text(), '{"test": true}')

            self.assertEqual(backup_path.parent, backup_dir)

    def test_backup_without_extension(self):
        """
        Given a source file with no extension (configfile)
        When create_backup copies it into a backup directory
        Then a timestamped backup named 'configfile.<timestamp>' is created with the same content
        """
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "configfile"
            source_file.write_text("test content")

            backup_dir = Path(tmpdir) / "backups"
            backup_path = create_backup(source_file, backup_dir)

            self.assertTrue(backup_path.exists())

            self.assertTrue(backup_path.name.startswith("configfile."))

            self.assertEqual(backup_path.read_text(), "test content")

    def test_backup_creates_directory(self):
        """
        Given a backup directory path with nested parents that do not yet exist
        When create_backup runs
        Then the full backup directory tree is created
        """
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "test.json"
            source_file.write_text("{}")

            backup_dir = Path(tmpdir) / "deep" / "nested" / "backups"
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
            source_file = Path(tmpdir) / "nonexistent.json"
            backup_dir = Path(tmpdir) / "backups"

            with self.assertRaises(FileNotFoundError):
                create_backup(source_file, backup_dir)

    def test_colliding_timestamp_does_not_overwrite_earlier_backup(self):
        """
        Given create_backup is called twice for the same source file, with
        datetime.now() forced to return the identical second-granularity
        timestamp both times (simulating two backups landing in the same
        wall-clock second)
        When the second call runs
        Then it writes to a DISTINCT backup file rather than overwriting the
        first, and the first backup's original content survives untouched
        (this is the actual data-loss regression: a naive implementation
        would silently clobber the first backup's bytes)
        """
        fixed_now = datetime(2026, 2, 5, 14, 30, 22)
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "settings.local.json"
            backup_dir = Path(tmpdir) / "backups"

            with patch("toolguard.permission_migration.datetime") as mock_datetime:
                mock_datetime.now.return_value = fixed_now

                source_file.write_text('{"version": 1}')
                first_backup = create_backup(source_file, backup_dir)

                source_file.write_text('{"version": 2}')
                second_backup = create_backup(source_file, backup_dir)

            # Proves the patched clock is the one create_backup reads: without
            # this the test passes on real timestamps that merely happened to
            # collide, which is not the scenario the Given describes.
            self.assertEqual(mock_datetime.now.call_count, 2)

            self.assertNotEqual(first_backup, second_backup)
            self.assertTrue(first_backup.exists())
            self.assertTrue(second_backup.exists())

            self.assertEqual(first_backup.read_text(), '{"version": 1}')
            self.assertEqual(second_backup.read_text(), '{"version": 2}')

    def test_third_collision_on_same_timestamp_gets_its_own_file(self):
        """
        Given two backups already exist for the same colliding timestamp
        When a third create_backup call happens with datetime.now() forced to
        the same timestamp again
        Then a third, distinct backup file is created (proving the
        disambiguator keeps incrementing rather than only handling exactly
        two collisions) and all three earlier backups remain intact
        """
        fixed_now = datetime(2026, 2, 5, 14, 30, 22)
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "settings.local.json"
            backup_dir = Path(tmpdir) / "backups"

            with patch("toolguard.permission_migration.datetime") as mock_datetime:
                mock_datetime.now.return_value = fixed_now

                source_file.write_text('{"version": 1}')
                first_backup = create_backup(source_file, backup_dir)

                source_file.write_text('{"version": 2}')
                second_backup = create_backup(source_file, backup_dir)

                source_file.write_text('{"version": 3}')
                third_backup = create_backup(source_file, backup_dir)

            self.assertEqual(mock_datetime.now.call_count, 3)

            all_backups = {first_backup, second_backup, third_backup}
            self.assertEqual(len(all_backups), 3, "all three paths must be distinct")

            self.assertEqual(first_backup.read_text(), '{"version": 1}')
            self.assertEqual(second_backup.read_text(), '{"version": 2}')
            self.assertEqual(third_backup.read_text(), '{"version": 3}')

    def test_no_collision_case_keeps_current_filename_shape(self):
        """
        Given a single create_backup call with no pre-existing file at the
        candidate backup path (the common, non-colliding case)
        When create_backup runs
        Then the backup filename is exactly the plain
        '{stem}.{timestamp}{suffix}' shape, with no disambiguator suffix
        appended (no regression in the common path)
        """
        fixed_now = datetime(2026, 2, 5, 14, 30, 22)
        with TemporaryDirectory() as tmpdir:
            source_file = Path(tmpdir) / "settings.local.json"
            source_file.write_text('{"test": true}')
            backup_dir = Path(tmpdir) / "backups"

            with patch("toolguard.permission_migration.datetime") as mock_datetime:
                mock_datetime.now.return_value = fixed_now
                backup_path = create_backup(source_file, backup_dir)

            self.assertEqual(mock_datetime.now.call_count, 1)
            self.assertEqual(backup_path.name, "settings.local.2026-02-05-143022.json")


class TestPatternKeyExtraction(unittest.TestCase):
    """Test pattern key extraction for similarity detection."""

    def test_bash_command_with_args(self):
        """
        Given a Bash pattern with command arguments (e.g. 'Bash(git push:*)')
        When extract_pattern_key parses it
        Then the key is the tool plus the leading command word ('Bash', 'git')
        """
        key = extract_pattern_key("Bash(git push:*)")
        self.assertEqual(key, ("Bash", "git"))

    def test_bash_command_simple(self):
        """
        Given a simple Bash pattern (e.g. 'Bash(git:*)')
        When extract_pattern_key parses it
        Then the key is ('Bash', 'git')
        """
        key = extract_pattern_key("Bash(git:*)")
        self.assertEqual(key, ("Bash", "git"))

    def test_read_path_with_subdirs(self):
        """
        Given a Read pattern with subdirectories (e.g. 'Read(/tmp/foo/*)')
        When extract_pattern_key parses it
        Then the key is the tool plus the leading path segment ('Read', '/tmp/')
        """
        key = extract_pattern_key("Read(/tmp/foo/*)")
        self.assertEqual(key, ("Read", "/tmp/"))

    def test_read_path_simple(self):
        """
        Given a simple Read path pattern (e.g. 'Read(/tmp/*)')
        When extract_pattern_key parses it
        Then the key is ('Read', '/tmp/')
        """
        key = extract_pattern_key("Read(/tmp/*)")
        self.assertEqual(key, ("Read", "/tmp/"))

    def test_wildcard_only(self):
        """
        Given a wildcard-only pattern (e.g. 'Write(*)')
        When extract_pattern_key parses it
        Then the key is the tool plus '*' ('Write', '*')
        """
        key = extract_pattern_key("Write(*)")
        self.assertEqual(key, ("Write", "*"))

    def test_no_delimiters(self):
        """
        Given a pattern with no colon or path delimiters (e.g. 'Bash(ls)')
        When extract_pattern_key parses it
        Then the key is the tool plus the whole inner token ('Bash', 'ls')
        """
        key = extract_pattern_key("Bash(ls)")
        self.assertEqual(key, ("Bash", "ls"))


class TestSimilarPatternDetection(unittest.TestCase):
    """Test detection of similar patterns."""

    def test_detect_similar_git_commands(self):
        """
        Given existing git and ls patterns and a new 'git push --force' pattern
        When detect_similar_patterns runs
        Then the related git pattern is flagged as similar and the unrelated ls pattern is not
        """
        existing = ["Bash(git push:*)", "Bash(ls:*)"]
        new_pattern = "Bash(git push --force:*)"

        similar = detect_similar_patterns(new_pattern, existing)

        similar_patterns = [p for p, _, _ in similar]
        self.assertIn("Bash(git push:*)", similar_patterns)
        self.assertNotIn("Bash(ls:*)", similar_patterns)

    def test_detect_similar_paths(self):
        """
        Given existing Read path patterns and a new 'Read(/tmp/foo/*)' pattern
        When detect_similar_patterns runs
        Then the matching '/tmp/' path pattern is flagged as similar and unrelated paths are not
        """
        existing = ["Read(/tmp/*)", "Read(/var/*)", "Read(/home/*)"]
        new_pattern = "Read(/tmp/foo/*)"

        similar = detect_similar_patterns(new_pattern, existing)

        similar_patterns = [p for p, _, _ in similar]
        self.assertIn("Read(/tmp/*)", similar_patterns)
        self.assertNotIn("Read(/var/*)", similar_patterns)

    def test_identical_pattern_is_reported_as_a_perfect_non_superset_match(self):
        """
        Given an existing pattern and a new pattern identical to it
        When detect_similar_patterns runs
        Then exactly that one pattern comes back, with a similarity of 1.0 and
             the superset flag False (a pattern is not a superset of itself --
             see test_not_superset_for_identical_patterns), and the unrelated
             pattern is not reported
        """
        existing = ["Bash(git:*)", "Bash(ls:*)"]
        new_pattern = "Bash(git:*)"

        similar = detect_similar_patterns(new_pattern, existing)

        self.assertEqual(similar, [("Bash(git:*)", 1.0, False)])

    def test_no_similar_patterns(self):
        """
        Given existing patterns that are all very different from the new pattern
        When detect_similar_patterns runs
        Then no similar patterns are returned (empty result)
        """
        existing = ["Read(/var/log/*)", "Write(/home/user/docs/*)", "Edit(/etc/config)"]
        new_pattern = "Bash(git:*)"

        similar = detect_similar_patterns(new_pattern, existing)

        self.assertEqual(len(similar), 0)

    def test_broader_pattern_is_similar(self):
        """
        Given an existing broad pattern 'Bash(git:*)' and a new specific 'Bash(git push:*)'
        When detect_similar_patterns runs
        Then the broader existing pattern is flagged as similar to the specific one
        """
        existing = ["Bash(git:*)"]
        new_pattern = "Bash(git push:*)"

        similar = detect_similar_patterns(new_pattern, existing)

        similar_patterns = [p for p, _, _ in similar]
        self.assertIn("Bash(git:*)", similar_patterns)


class TestPatternSorting(unittest.TestCase):
    """Test pattern sorting behavior."""

    def test_sort_by_tool_priority(self):
        """
        Given an unordered list of patterns across several tool types
        When sort_patterns sorts them
        Then they are ordered by tool priority: Bash, Read, Write, Edit, then others
        """
        patterns = [
            "Edit(/tmp/*)",
            "Write(/tmp/*)",
            "Read(/tmp/*)",
            "Bash(ls:*)",
            "Grep(pattern)",
        ]

        sorted_patterns = sort_patterns(patterns)

        tools = [p.split("(")[0] for p in sorted_patterns]
        self.assertEqual(tools[0], "Bash")
        self.assertEqual(tools[1], "Read")
        self.assertEqual(tools[2], "Write")
        self.assertEqual(tools[3], "Edit")
        self.assertEqual(tools[4], "Grep")

    def test_sort_alphabetically_within_tool(self):
        """
        Given several Bash patterns in arbitrary order
        When sort_patterns sorts them
        Then patterns of the same tool are ordered alphabetically by command
        """
        patterns = [
            "Bash(rm:*)",
            "Bash(git:*)",
            "Bash(ls:*)",
            "Bash(cat:*)",
        ]

        sorted_patterns = sort_patterns(patterns)

        self.assertEqual(
            sorted_patterns,
            [
                "Bash(cat:*)",
                "Bash(git:*)",
                "Bash(ls:*)",
                "Bash(rm:*)",
            ],
        )

    def test_sort_case_insensitive(self):
        """
        Given Bash patterns with mixed-case commands
        When sort_patterns sorts them
        Then ordering uses case-insensitive comparison (abc, def, XYZ, Zsh)
        """
        patterns = [
            "Bash(Zsh:*)",
            "Bash(abc:*)",
            "Bash(XYZ:*)",
            "Bash(def:*)",
        ]

        sorted_patterns = sort_patterns(patterns)

        expected_order = ["abc", "def", "XYZ", "Zsh"]
        actual_order = [p.split("(")[1].split(":")[0] for p in sorted_patterns]
        self.assertEqual(actual_order, expected_order)

    def test_get_tool_priority(self):
        """
        Given patterns for Bash, Read, Write, Edit, and another tool
        When get_tool_priority is called on each
        Then it returns the priority index (0-4) paired with the lowercased pattern as sort key
        """
        self.assertEqual(get_tool_priority("Bash(ls:*)"), (0, "bash(ls:*)"))
        self.assertEqual(get_tool_priority("Read(/tmp/*)"), (1, "read(/tmp/*)"))
        self.assertEqual(get_tool_priority("Write(/tmp/*)"), (2, "write(/tmp/*)"))
        self.assertEqual(get_tool_priority("Edit(/tmp/*)"), (3, "edit(/tmp/*)"))
        self.assertEqual(get_tool_priority("Grep(pattern)"), (4, "grep(pattern)"))

    def test_sort_patterns_tolerates_structured_entry_without_raising(self):
        """
        Given a list mixing a structured RuleEntry (metadata, not a raw dict)
             and plain string patterns
        When sort_patterns() sorts the list
        Then it does not raise (regression guard for the confirmed
             "TypeError: unhashable type: 'dict'" defect in get_tool_priority)
             and orders purely by .pattern, ignoring metadata
        """
        structured = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"additionalContext": "be careful"}),
            raw={"match": "Bash(git *)", "additionalContext": "be careful"},
        )
        entries = ["Write(/tmp/*)", structured, "Read(/tmp/*)"]

        result = sort_patterns(entries)

        self.assertIs(result[0], structured)
        self.assertEqual(result[1], "Read(/tmp/*)")
        self.assertEqual(result[2], "Write(/tmp/*)")

    def test_get_tool_priority_ignores_ruleentry_metadata(self):
        """
        Given two RuleEntry with the same pattern but different metadata
        When get_tool_priority() computes each one's sort key
        Then both keys are identical -- metadata never affects ordering
        """
        a = RuleEntry(
            pattern="Bash(git *)", metadata=MappingProxyType({"additionalContext": "x"})
        )
        b = RuleEntry(
            pattern="Bash(git *)", metadata=MappingProxyType({"additionalContext": "y"})
        )
        self.assertEqual(get_tool_priority(a), get_tool_priority(b))
        self.assertEqual(get_tool_priority(a), (0, "bash(git *)"))


class TestTOMLConfigWriting(unittest.TestCase):
    """Test writing TOML configuration files."""

    def test_write_toml_with_sorting(self):
        """
        Given unsorted allow permissions and auto_sort enabled
        When write_toml_config writes the TOML file
        Then the rules appear sorted by tool priority (Bash before Read before Write)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            permissions = {
                "allow": ["Write(/tmp/*)", "Bash(ls:*)", "Read(/tmp/*)"],
                "deny": ["Bash(rm:*)"],
                "ask": [],
            }

            write_toml_config(config_path, permissions, auto_sort=True)

            content = config_path.read_text()

            self.assertIn("[permissions]", content)
            bash_pos = content.index("Bash(ls:*)")
            read_pos = content.index("Read(/tmp/*)")
            write_pos = content.index("Write(/tmp/*)")
            self.assertLess(bash_pos, read_pos)
            self.assertLess(read_pos, write_pos)

    def test_write_toml_without_sorting(self):
        """
        Given allow permissions in a given order and auto_sort disabled
        When write_toml_config writes the TOML file
        Then the original input order is preserved (Write before Bash)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            permissions = {
                "allow": ["Write(/tmp/*)", "Bash(ls:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }

            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()

            write_pos = content.index("Write(/tmp/*)")
            bash_pos = content.index("Bash(ls:*)")
            self.assertLess(write_pos, bash_pos)

    def test_toml_escapes_special_chars(self):
        """
        Given a permission pattern containing double quotes
        When write_toml_config writes the TOML file
        Then the embedded quotes are escaped in the output
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            permissions = {
                "allow": ['Bash(echo "test":*)'],
                "deny": [],
                "ask": [],
            }

            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()

            self.assertIn('echo \\"test\\"', content)

    def test_newline_in_additional_context_still_produces_a_writable_config(self):
        """
        Given a structured entry whose additionalContext contains a literal
            newline -- reachable from any JSON config, e.g.
            {"additionalContext": "line1\\nline2"}
        When write_toml_config writes it
        Then the file is written and re-parses with the newline intact.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            entry = RuleEntry(
                pattern="Bash(git push:*)",
                metadata=MappingProxyType({"additionalContext": "line1\nline2"}),
            )
            permissions = {"allow": [entry], "deny": [], "ask": []}

            write_toml_config(config_path, permissions, auto_sort=False)

            written = tomllib.loads(config_path.read_text())["permissions"]["allow"]
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0]["match"], "Bash(git push:*)")
            self.assertEqual(written[0]["additionalContext"], "line1\nline2")

    def test_same_pattern_different_metadata_both_survive_write_round_trip(self):
        """
        Given an existing TOML file with two structured entries sharing the
            same pattern but different additionalContext values (the shape
            merge_entries's case-3 contradiction handling deliberately
            preserves side-by-side)
        When write_toml_config() re-writes the file with both entries kept
            unchanged, in the same relative order
        Then BOTH entries' distinct additionalContext values are present in
            the rewritten file -- previously the writer's rule_lines/
            rule_comments dicts were keyed by pattern alone, so the second
            entry's text silently overwrote the first's on write
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                "[permissions]\n"
                "allow = [\n"
                '  { match = "Bash(git push:*)", additionalContext = "first note" },\n'
                '  { match = "Bash(git push:*)", additionalContext = "second note" },\n'
                "]\n"
            )
            config_path.write_text(original)

            first_entry = RuleEntry(
                pattern="Bash(git push:*)",
                metadata=MappingProxyType({"additionalContext": "first note"}),
                raw={
                    "match": "Bash(git push:*)",
                    "additionalContext": "first note",
                },
            )
            second_entry = RuleEntry(
                pattern="Bash(git push:*)",
                metadata=MappingProxyType({"additionalContext": "second note"}),
                raw={
                    "match": "Bash(git push:*)",
                    "additionalContext": "second note",
                },
            )
            permissions = {
                "allow": [first_entry, second_entry],
                "deny": [],
                "ask": [],
            }

            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()
            self.assertIn("first note", content)
            self.assertIn("second note", content)
            self.assertIn(
                '{ match = "Bash(git push:*)", additionalContext = "first note" },',
                content,
            )
            self.assertIn(
                '{ match = "Bash(git push:*)", additionalContext = "second note" },',
                content,
            )
            self.assertLess(content.index("first note"), content.index("second note"))


class TestJSONConfigWriting(unittest.TestCase):
    """Test writing JSON configuration files."""

    def test_write_json_with_sorting(self):
        """
        Given unsorted allow permissions and auto_sort enabled
        When write_json_config writes the JSON file
        Then the allow list is stored sorted by tool priority (Bash, Read, Write)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.json"

            permissions = {
                "allow": ["Write(/tmp/*)", "Bash(ls:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }

            write_json_config(config_path, permissions, auto_sort=True)

            with open(config_path, "r") as f:
                config = json.load(f)

            allow_patterns = config["permissions"]["allow"]

            self.assertEqual(allow_patterns[0], "Bash(ls:*)")
            self.assertEqual(allow_patterns[1], "Read(/tmp/*)")
            self.assertEqual(allow_patterns[2], "Write(/tmp/*)")

    def test_write_json_preserves_other_config(self):
        """
        Given an existing JSON config with unrelated keys (governed_tools, other_setting)
        When write_json_config writes new permissions into it
        Then the unrelated keys are preserved and the permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.json"

            initial_config = {
                "governed_tools": ["Bash", "Read"],
                "other_setting": "value",
            }
            with open(config_path, "w") as f:
                json.dump(initial_config, f)

            permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
            write_json_config(config_path, permissions, auto_sort=False)

            with open(config_path, "r") as f:
                config = json.load(f)

            self.assertEqual(config["governed_tools"], ["Bash", "Read"])
            self.assertEqual(config["other_setting"], "value")
            self.assertEqual(config["permissions"]["allow"], ["Bash(ls:*)"])

    def test_write_json_config_preserves_structured_entry_without_raising(self):
        """
        Given a permissions dict whose allow list mixes a structured RuleEntry
             and a plain string, with auto_sort enabled
        When write_json_config() writes the JSON file
        Then it does not raise (the same TypeError sort defect also reaches the
             JSON write path via sort_patterns), the structured entry is
             emitted as a genuine JSON object (never a stringified dict), and
             it sorts ahead of the plain string per its Bash pattern
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.json"

            structured = RuleEntry(
                pattern="Bash(git *)",
                metadata=MappingProxyType({"additionalContext": "be careful"}),
            )
            permissions = {
                "allow": ["Read(/tmp/*)", structured],
                "deny": [],
                "ask": [],
            }

            write_json_config(config_path, permissions, auto_sort=True)

            with open(config_path, "r") as f:
                config = json.load(f)

            allow = config["permissions"]["allow"]
            self.assertEqual(len(allow), 2)
            self.assertIsInstance(allow[0], dict)
            self.assertEqual(allow[0]["match"], "Bash(git *)")
            self.assertEqual(allow[0]["additionalContext"], "be careful")
            self.assertEqual(allow[1], "Read(/tmp/*)")


class TestWriteConfigRoutesThroughVerificationGuard(unittest.TestCase):
    """write_toml_config()/write_json_config() write only via verified_write_config(), never a raw file write."""

    def test_write_toml_config_new_file_calls_verified_write_config(self):
        """
        Given a config_path that does not yet exist (the "new file" branch)
        When write_toml_config() is called
        Then toolguard.config_write_guard.verified_write_config() is invoked
            with file_format="toml" and expected_patterns covering every
            pattern in the permissions being written
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            permissions = {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)"], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config"
            ) as mock_write:
                write_toml_config(config_path, permissions, auto_sort=True)

            mock_write.assert_called_once()
            args, kwargs = mock_write.call_args
            self.assertEqual(args[0], config_path)
            self.assertEqual(args[2], "toml")
            self.assertEqual(
                set(kwargs["expected_patterns"]), {"Bash(ls:*)", "Bash(rm:*)"}
            )

    def test_write_toml_config_section_replace_calls_verified_write_config(self):
        """
        Given an existing TOML file with a [permissions] section (the
            "replace existing section" branch)
        When write_toml_config() is called
        Then verified_write_config() is invoked with file_format="toml" and
            expected_patterns covering the newly-written permissions
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            config_path.write_text('[permissions]\nallow = ["Bash(ls:*)"]\n')
            permissions = {"allow": ["Bash(git:*)"], "deny": [], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config"
            ) as mock_write:
                write_toml_config(config_path, permissions, auto_sort=True)

            mock_write.assert_called_once()
            _args, kwargs = mock_write.call_args
            self.assertEqual(set(kwargs["expected_patterns"]), {"Bash(git:*)"})

    def test_write_toml_config_append_branch_calls_verified_write_config(self):
        """
        Given an existing TOML file with NO [permissions] section (the
            "append at end" branch)
        When write_toml_config() is called
        Then verified_write_config() is invoked with file_format="toml"
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            config_path.write_text("[hard_deny]\ndeny = []\n")
            permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config"
            ) as mock_write:
                write_toml_config(config_path, permissions, auto_sort=True)

            mock_write.assert_called_once()
            args, kwargs = mock_write.call_args
            self.assertEqual(args[2], "toml")
            self.assertEqual(set(kwargs["expected_patterns"]), {"Bash(ls:*)"})

    def test_write_json_config_calls_verified_write_config(self):
        """
        Given a permissions dict to write to a JSON config file
        When write_json_config() is called
        Then verified_write_config() is invoked with file_format="json" and
            expected_patterns covering the newly-written permissions
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.json"
            permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config"
            ) as mock_write:
                write_json_config(config_path, permissions, auto_sort=True)

            mock_write.assert_called_once()
            args, kwargs = mock_write.call_args
            self.assertEqual(args[0], config_path)
            self.assertEqual(args[2], "json")
            self.assertEqual(set(kwargs["expected_patterns"]), {"Bash(ls:*)"})

    def test_write_toml_config_refuses_when_guard_raises(self):
        """
        Given verified_write_config() raising ConfigWriteVerificationError
            (simulating a would-be corrupting write)
        When write_toml_config() is called
        Then the error propagates out of write_toml_config() unmodified, and
            (since the mock never actually touches disk) no file is created
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config",
                side_effect=ConfigWriteVerificationError(
                    config_path, "invalid TOML", "boom"
                ),
            ):
                with self.assertRaises(ConfigWriteVerificationError):
                    write_toml_config(config_path, permissions, auto_sort=True)

            self.assertFalse(config_path.exists())


class TestWriteConfigToleratesMalformedEntries(unittest.TestCase):
    """A malformed structured entry must never block writing the rest of the file; exercises the real (unmocked) verified_write_config path."""

    def test_toml_write_survives_a_malformed_structured_entry(self):
        """
        Given an existing TOML file whose [permissions] allow list contains
            one valid string entry and one structured entry MISSING its
            "match" key, normalized via normalize_entries_preserving() (the
            write-path chokepoint) and handed straight back to
            write_toml_config()
        When write_toml_config() is called
        Then the write succeeds (no ConfigWriteVerificationError) and the
            malformed entry round-trips verbatim in the file
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(ls)",\n'
                '  { additionalContext = "oops" },\n'
                "]\n"
            )
            config_path.write_text(original)

            existing = tomllib.loads(original)["permissions"]
            entries = {
                perm_type: list(
                    normalize_entries_preserving(
                        existing.get(perm_type, []), is_native=False
                    )
                )
                for perm_type in ("allow", "deny", "ask")
            }

            write_toml_config(config_path, entries, auto_sort=False)

            written = tomllib.loads(config_path.read_text())["permissions"]["allow"]
            self.assertIn("Bash(ls)", written)
            self.assertIn({"additionalContext": "oops"}, written)

    def test_json_write_survives_a_non_string_element(self):
        """
        Given an existing JSON config whose allow list contains a valid
            string entry and a non-string element (a bare int), normalized
            via normalize_entries_preserving() and handed back to
            write_json_config()
        When write_json_config() is called
        Then the write succeeds and the non-string element round-trips
            verbatim
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.json"
            existing = {"allow": ["Bash(ls)", 42], "deny": [], "ask": []}
            entries = {
                perm_type: list(
                    normalize_entries_preserving(
                        existing.get(perm_type, []), is_native=False
                    )
                )
                for perm_type in ("allow", "deny", "ask")
            }

            write_json_config(config_path, entries, auto_sort=False)

            written = json.loads(config_path.read_text())["permissions"]["allow"]
            self.assertIn("Bash(ls)", written)
            self.assertIn(42, written)

    def test_write_still_refused_when_a_real_pattern_is_genuinely_dropped(self):
        """
        Given entries that include BOTH a malformed (synthesized-pattern)
            entry AND a real pattern, but the file's parsed structure has a
            duplicate-pattern collision that causes the writer to actually
            drop that real pattern's text (simulated directly at the
            verified_write_config layer, since real_patterns() only affects
            which patterns are EXCLUDED as synthetic -- it must never affect
            whether a genuinely-missing REAL pattern is still caught)
        When verified_write_config() is called with the real pattern in
            expected_patterns but text that omits it
        Then ConfigWriteVerificationError is still raised -- confirming the
            synthesized-pattern exclusion fix does not weaken the
            content-loss guard's actual safety net (see
            test_config_write_guard.TestVerifiedWriteConfigContentLossGuard
            for the guard's own direct coverage of this)
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\nallow = ["Bash(ls)", "Bash(git status)"]\n'
            config_path.write_text(original)

            entries = normalize_entries_preserving(
                ["Bash(ls)", {"nope": "malformed"}], is_native=False
            )
            self.assertEqual(real_patterns(entries), ["Bash(ls)"])

            new_text = '[permissions]\nallow = ["Bash(ls)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(
                    config_path,
                    new_text,
                    "toml",
                    expected_patterns=real_patterns(entries) + ["Bash(git status)"],
                )
            self.assertEqual(config_path.read_text(), original)


class TestSettingsFileUpdate(unittest.TestCase):
    """Test updating settings.local.json after migration."""

    def test_remove_migrated_patterns(self):
        """
        Given a settings file and a set of migrated patterns that overlap some of its entries
        When update_settings_file runs
        Then the migrated patterns are removed from the settings, leaving only non-migrated ones
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            settings = {
                "permissions": {
                    "allow": ["Bash(ls:*)", "Bash(git:*)", "Read(/tmp/*)"],
                    "deny": ["Bash(rm:*)"],
                    "ask": [],
                }
            }
            with open(settings_path, "w") as f:
                json.dump(settings, f)

            migrated = {
                "allow": ["Bash(git:*)", "Read(/tmp/*)"],
                "deny": ["Bash(rm:*)"],
                "ask": [],
            }

            update_settings_file(settings_path, migrated)

            with open(settings_path, "r") as f:
                updated = json.load(f)

            self.assertEqual(updated["permissions"]["allow"], ["Bash(ls:*)"])
            self.assertEqual(updated["permissions"]["deny"], [])

    def test_keep_empty_permissions_structure(self):
        """
        Given a settings file whose only pattern is migrated away
        When update_settings_file runs
        Then the permissions structure remains with empty allow, deny, and ask lists
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            settings = {
                "permissions": {
                    "allow": ["Bash(ls:*)"],
                    "deny": [],
                    "ask": [],
                }
            }
            with open(settings_path, "w") as f:
                json.dump(settings, f)

            migrated = {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }

            update_settings_file(settings_path, migrated)

            with open(settings_path, "r") as f:
                updated = json.load(f)

            self.assertIn("permissions", updated)
            self.assertEqual(updated["permissions"]["allow"], [])
            self.assertEqual(updated["permissions"]["deny"], [])
            self.assertEqual(updated["permissions"]["ask"], [])

    def test_surviving_patterns_are_handed_to_the_write_guard(self):
        """
        Given a settings file where only some patterns are being removed
        When update_settings_file runs
        Then it writes through verified_write_config with exactly the SURVIVING
             patterns as expected_patterns -- the content-loss guard for the
             user's native settings file. Deleting that argument list is
             otherwise undetectable: it only ever fires when some other defect
             drops a survivor, so nothing observes it from behaviour alone.
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings = {
                "permissions": {
                    "allow": ["Bash(ls:*)", "Bash(git:*)"],
                    "deny": ["Bash(rm:*)"],
                    "ask": ["Bash(curl:*)"],
                }
            }
            settings_path.write_text(json.dumps(settings))

            migrated = {"allow": ["Bash(git:*)"], "deny": [], "ask": []}
            redundant = {"allow": [], "deny": ["Bash(rm:*)"], "ask": []}

            with patch(
                "toolguard.permission_migration.verified_write_config"
            ) as mock_write:
                update_settings_file(settings_path, migrated, redundant)

            mock_write.assert_called_once()
            args, kwargs = mock_write.call_args
            self.assertEqual(args[0], settings_path)
            self.assertEqual(args[2], "json")
            self.assertEqual(
                set(kwargs["expected_patterns"]), {"Bash(ls:*)", "Bash(curl:*)"}
            )


class TestMigration(ConfigIsolationMixin, unittest.TestCase):
    """Full migration process. Isolates Path.home() because load_configuration()'s aggregated toolguard_perms still reads it even though write-target selection is already restricted to project_root's own .claude directory."""

    def test_dry_run_mode(self):
        """
        Given a project with a settings.local.json containing patterns
        When migrate runs with dry_run=True
        Then no files are changed, no TOML config is created, and it exits 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)", "Bash(git:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root, dry_run=True)

        with open(settings_path, "r") as f:
            after_settings = json.load(f)

        self.assertEqual(after_settings, settings)
        self.assertFalse((claude_dir / "toolguard_hook.toml").exists())
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_migration_creates_new_toml_config(self):
        """
        Given a project with settings.local.json patterns and no existing toolguard_hook.toml
        When migrate runs
        Then a new toolguard_hook.toml is created with the patterns, the settings allow list is
        emptied, and it exits 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)", "Bash(git:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        toml_path = claude_dir / "toolguard_hook.toml"
        self.assertTrue(toml_path.exists())

        # Assert against the PARSED structure, not a substring of the file: a
        # pattern written into the wrong list, or into a comment, satisfies
        # assertIn on the raw text just as well as a correct write does.
        written = tomllib.loads(toml_path.read_text())["permissions"]
        self.assertEqual(sorted(written["allow"]), ["Bash(git:*)", "Bash(ls:*)"])
        self.assertEqual(written.get("deny", []), [])
        self.assertEqual(written.get("ask", []), [])

        with open(settings_path, "r") as f:
            updated_settings = json.load(f)

        self.assertEqual(updated_settings["permissions"]["allow"], [])
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_migrate_puts_each_native_list_in_the_matching_toolguard_list(self):
        """
        Given settings.local.json with a divergent pattern in EACH of allow,
            deny and ask
        When migrate runs
        Then each pattern lands in the toolguard config list of the same name,
             and in no other list -- placement, not mere presence. The suite's
             other migrate tests assert `assertIn(pattern, file_text)`, which
             a rule moved from allow into deny satisfies unchanged; that
             inversion is the single most dangerous edit a config writer can
             make (proposed ticket 39).
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_path.write_text(
            '[permissions]\nallow = ["Bash(ls:*)"]\ndeny = []\nask = []\n'
        )

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(git:*)"],
                "deny": ["Bash(rm -rf /:*)"],
                "ask": ["Bash(curl:*)"],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

        written = tomllib.loads(toml_path.read_text())["permissions"]
        self.assertEqual(sorted(written["allow"]), ["Bash(git:*)", "Bash(ls:*)"])
        self.assertEqual(written["deny"], ["Bash(rm -rf /:*)"])
        self.assertEqual(written["ask"], ["Bash(curl:*)"])

    def test_existing_hard_deny_section_survives_a_migration(self):
        """
        Given a toolguard config with a [hard_deny] section and a migration
            that rewrites [permissions]
        When migrate runs
        Then the hard deny is still in hard_deny.deny afterwards and has NOT
             appeared in permissions.allow -- the write guard's content-loss
             check compares a flat set of pattern strings and so cannot see a
             pattern that moved between lists (proposed ticket 39), which
             leaves this end-to-end assertion as the only thing watching it.
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_path.write_text(
            "[hard_deny]\n"
            'deny = ["Bash(rm -rf /)"]\n'
            "\n"
            "[permissions]\n"
            'allow = ["Bash(ls:*)"]\n'
            "deny = []\n"
        )

        settings_path = claude_dir / "settings.local.json"
        with open(settings_path, "w") as f:
            json.dump(
                {"permissions": {"allow": ["Bash(git:*)"], "deny": [], "ask": []}}, f
            )

        outcome = migrate(project_root)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

        reparsed = tomllib.loads(toml_path.read_text())
        self.assertEqual(reparsed["hard_deny"]["deny"], ["Bash(rm -rf /)"])
        self.assertNotIn("Bash(rm -rf /)", reparsed["permissions"]["allow"])

    def test_a_rule_for_an_ungoverned_tool_stays_in_settings(self):
        """
        Given settings.local.json holding a rule for a tool toolguard does not
            govern (WebFetch) alongside a governed Bash rule
        When migrate runs
        Then the WebFetch rule is still in settings.local.json and was NOT
             written into the toolguard config -- migrating it would remove it
             from Claude's own settings while toolguard ignores it, leaving the
             rule enforced by nobody
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_path.write_text('[permissions]\nallow = ["Bash(ls:*)"]\ndeny = []\n')

        settings_path = claude_dir / "settings.local.json"
        with open(settings_path, "w") as f:
            json.dump(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", "WebFetch(domain:example.com)"],
                        "deny": [],
                        "ask": [],
                    }
                },
                f,
            )

        outcome = migrate(project_root)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

        with open(settings_path) as f:
            remaining = json.load(f)["permissions"]["allow"]
        self.assertEqual(remaining, ["WebFetch(domain:example.com)"])

        written = tomllib.loads(toml_path.read_text())["permissions"]["allow"]
        self.assertEqual(sorted(written), ["Bash(git:*)", "Bash(ls:*)"])

    def test_a_refused_config_write_fails_the_migration_and_loses_no_rule(self):
        """
        Given the config write guard refusing the toolguard config write
            (standing in for any text this project could not parse back)
        When migrate runs
        Then it returns MigrationOutcome.FAILED, the target config keeps its
             original bytes, and settings.local.json still holds every pattern
             it started with -- a failed migration must not be a migration that
             removed the rules from one file without adding them to the other
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        original_toml = '[permissions]\nallow = ["Bash(ls:*)"]\ndeny = []\n'
        toml_path.write_text(original_toml)

        settings_path = claude_dir / "settings.local.json"
        original_settings = {
            "permissions": {"allow": ["Bash(git:*)"], "deny": [], "ask": []}
        }
        with open(settings_path, "w") as f:
            json.dump(original_settings, f)

        with patch.object(
            permission_migration_module,
            "verified_write_config",
            side_effect=ConfigWriteVerificationError(toml_path, "invalid TOML", "boom"),
        ) as mock_write:
            outcome = migrate(project_root)

        mock_write.assert_called()
        self.assertEqual(outcome, MigrationOutcome.FAILED)
        self.assertEqual(toml_path.read_text(), original_toml)
        with open(settings_path) as f:
            self.assertEqual(json.load(f), original_settings)

    def test_migration_adds_to_existing_toml(self):
        """
        Given an existing toolguard_hook.toml and settings.local.json with extra patterns
        When migrate runs
        Then the new patterns are added to the TOML and all settings patterns (migrated or
        redundant) are removed, exiting 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        # Migration only moves rules for governed tools, so this config
        # must govern Read for the Read pattern below to be eligible.
        toml_path = claude_dir / "toolguard_hook.toml"
        toml_content = """governed_tools = ["Bash", "Read"]

[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
        toml_path.write_text(toml_content)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)", "Bash(git:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        written = tomllib.loads(toml_path.read_text())["permissions"]
        self.assertEqual(
            sorted(written["allow"]),
            ["Bash(git:*)", "Bash(ls:*)", "Read(/tmp/*)"],
        )
        self.assertEqual(written.get("deny", []), [])

        with open(settings_path, "r") as f:
            updated_settings = json.load(f)

        self.assertEqual(updated_settings["permissions"]["allow"], [])
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_structured_entry_round_trips_byte_identical_through_migrate(self):
        """
        Given an existing toolguard_hook.toml whose allow list has ONE structured
        entry ({match=..., additionalContext=...}) with its own leading comment,
        plus settings.local.json with one genuinely new (divergent) native pattern
        When migrate() runs (not dry-run)
        Then the structured entry's original line AND its leading comment survive
             byte-identical, it keeps its sorted position ahead of the newly
             migrated pattern, and the file still parses as valid TOML with the
             entry's metadata intact.
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            "  # review this rule carefully\n"
            '  { match = "Bash(git *)", additionalContext = "review carefully" },\n'
            '  "Bash(ls *)",\n'
            "]\n"
            "deny = []\n"
            "ask = []\n"
        )
        toml_path.write_text(toml_content)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(pwd)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

        content = toml_path.read_text()

        self.assertIn(
            "  # review this rule carefully\n"
            '  { match = "Bash(git *)", additionalContext = "review carefully" },\n',
            content,
        )

        git_pos = content.index('match = "Bash(git *)"')
        ls_pos = content.index('"Bash(ls *)"')
        pwd_pos = content.index('"Bash(pwd)"')
        self.assertLess(git_pos, ls_pos)
        self.assertLess(ls_pos, pwd_pos)

        reparsed = tomllib.loads(content)
        allow = reparsed["permissions"]["allow"]
        structured = [e for e in allow if isinstance(e, dict)]
        self.assertEqual(len(structured), 1)
        self.assertEqual(structured[0]["match"], "Bash(git *)")
        self.assertEqual(structured[0]["additionalContext"], "review carefully")

    def test_migration_skips_identical_patterns(self):
        """
        Given a toolguard_hook.toml and settings.local.json that share an identical pattern
        When migrate runs
        Then the shared pattern appears only once in the TOML (no duplication), exiting 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_content = """[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
        toml_path.write_text(toml_content)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        content = toml_path.read_text()
        occurrences = content.count("Bash(ls:*)")

        self.assertEqual(occurrences, 1)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_no_migration_when_no_new_patterns(self):
        """
        Given a toolguard_hook.toml and settings.local.json with the same single pattern
        When migrate runs with nothing new to migrate
        Then it reports success and exits 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_content = """[permissions]
allow = [
  "Bash(ls:*)",
]
deny = []
"""
        toml_path.write_text(toml_content)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_migration_creates_backups(self):
        """
        Given a project with settings.local.json and a configured backup directory
        When migrate runs with that backup_dir
        Then a single timestamped settings.local.*.json backup is created and it exits 0
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(git:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        backup_dir = project_root / "logs" / "config-backups"

        outcome = migrate(project_root, backup_dir=backup_dir)

        self.assertTrue(backup_dir.exists())

        backups = list(backup_dir.glob("settings.local.*.json"))
        self.assertEqual(len(backups), 1)

        backup_name = backups[0].name
        self.assertTrue(backup_name.startswith("settings.local."))
        self.assertTrue(backup_name.endswith(".json"))

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)


class TestMigrationLocking(ConfigIsolationMixin, unittest.TestCase):
    """migrate()'s cross-process exclusion, in-process behaviour only -- see TestMigrationLockingAcrossProcesses for the genuine multi-process cases."""

    def test_dry_run_never_takes_the_lock(self):
        """
        Given a project with divergent patterns to preview
        When migrate runs with dry_run=True
        Then file_lock.exclusive is never called -- a dry run performs no
             write and needs no exclusion
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}}
            )
        )

        with patch.object(
            permission_migration_module.file_lock,
            "exclusive",
            side_effect=AssertionError("dry run must not take the lock"),
        ):
            outcome = migrate(project_root, dry_run=True)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_declines_with_named_code_when_lock_already_held(self):
        """
        Given this project's migration lock already held (by this test,
            standing in for another process) and a short lock_timeout_seconds
            passed explicitly so the test doesn't wait the real default
        When migrate runs (not a dry run)
        Then it returns MigrationOutcome.DECLINED_LOCKED (not SUCCEEDED, not
             FAILED) without touching settings.local.json, and reports the
             decline via error_reporter.report_warning
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        original_settings = {
            "permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
        }
        settings_path.write_text(json.dumps(original_settings))

        lock_path = permission_migration_module._migration_lock_path(project_root)

        with patch.object(
            permission_migration_module, "report_warning"
        ) as mock_warning:
            with file_lock.exclusive(lock_path, timeout_seconds=5):
                outcome = migrate(project_root, dry_run=False, lock_timeout_seconds=0.2)

        self.assertEqual(outcome, MigrationOutcome.DECLINED_LOCKED)
        mock_warning.assert_called_once()
        with open(settings_path) as f:
            self.assertEqual(json.load(f), original_settings)

    def test_declined_message_names_the_real_reason_for_a_non_timeout_decline(self):
        """
        Given exclusive() raises LockUnavailable for a reason OTHER than
            REASON_TIMEOUT (e.g. no OS lock primitive on this platform)
        When migrate runs (not a dry run)
        Then the reported message does not assert "another migration is
             already in progress" -- that claim is only true for
             REASON_TIMEOUT -- and instead names the real reason
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}}
            )
        )

        with patch.object(
            permission_migration_module.file_lock,
            "exclusive",
            side_effect=file_lock.LockUnavailable(
                Path("/some/lock"), file_lock.REASON_NO_PRIMITIVE
            ),
        ):
            with patch.object(
                permission_migration_module, "report_warning"
            ) as mock_warning:
                outcome = migrate(project_root, dry_run=False)

        self.assertEqual(outcome, MigrationOutcome.DECLINED_UNAVAILABLE)
        message = mock_warning.call_args[0][0]
        self.assertNotIn("already in progress", message)
        self.assertIn(file_lock.REASON_NO_PRIMITIVE, message)

    def test_every_non_timeout_reason_declines_as_unavailable_not_locked(self):
        """
        Given exclusive() raises LockUnavailable for each reason OTHER than
            REASON_TIMEOUT in turn (no lock primitive, lock directory
            unavailable, lock file unavailable)
        When migrate runs (not a dry run)
        Then every one of them returns DECLINED_UNAVAILABLE, never
             DECLINED_LOCKED -- that member is reserved for REASON_TIMEOUT,
             where another migration really is racing this one -- and
             settings.local.json is left untouched
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        original_settings = {
            "permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
        }
        settings_path.write_text(json.dumps(original_settings))

        non_timeout_reasons = (
            file_lock.REASON_NO_PRIMITIVE,
            file_lock.REASON_DIRECTORY_UNAVAILABLE,
            file_lock.REASON_FILE_UNAVAILABLE,
        )
        for reason in non_timeout_reasons:
            with self.subTest(reason=reason):
                with patch.object(
                    permission_migration_module.file_lock,
                    "exclusive",
                    side_effect=file_lock.LockUnavailable(Path("/some/lock"), reason),
                ):
                    with patch.object(permission_migration_module, "report_warning"):
                        outcome = migrate(project_root, dry_run=False)

                self.assertEqual(outcome, MigrationOutcome.DECLINED_UNAVAILABLE)

        with open(settings_path) as f:
            self.assertEqual(json.load(f), original_settings)

    def test_lock_key_is_based_on_the_resolved_project_root(self):
        """
        Given two Path spellings of the SAME directory (one via a symlink)
        When _migration_lock_path is built for each
        Then both resolve to the SAME lock file -- unlike
             once_per_store._project_key (str(project), no .resolve()),
             mutual exclusion here is about the real directory
        """
        _home, project_root = self.isolate_config_environment()
        alias = project_root.parent / "alias"
        try:
            alias.symlink_to(project_root)
        except OSError:
            self.skipTest("symlinks not supported in this environment")

        direct = permission_migration_module._migration_lock_path(project_root)
        via_alias = permission_migration_module._migration_lock_path(alias)

        self.assertEqual(direct, via_alias)


class TestMigrationLockingAcrossProcesses(unittest.TestCase):
    """Real concurrent OS processes racing migrate() on the same project -- see test_file_lock.py for the lock primitive's own cross-process tests; these exercise migrate()'s use of it."""

    @staticmethod
    def _isolated_env(home: Path) -> dict:
        """A minimal, clean child-process environment isolated to *home*."""
        return {"HOME": str(home), "PATH": os.environ.get("PATH", "")}

    def test_two_concurrent_migrations_of_different_patterns_lose_neither(self):
        """
        Given two processes concurrently migrating the SAME project, each
            intending to move a DIFFERENT divergent pattern (find_divergent_
            patterns/find_redundant_patterns are stubbed per-process so each
            genuinely computes a different result, standing in for two
            sessions that each added a different new permission -- with
            identical inputs the two would trivially converge, which is not
            a real exercise of the lock; see the ticket's own severity note)
        When both run at nearly the same instant, synchronized via a barrier
            that is only released once BOTH children have signalled they
            reached their wait loop -- not a guessed sleep, which can let a
            slow-to-start child degrade this to a sequential run that still
            passes
        Then the target toolguard config ends up with BOTH patterns and
             settings.local.json ends up with NEITHER -- no lost update,
             regardless of which process's lock wait wins
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir()
            project_root = Path(tmpdir) / "project"
            claude_dir = project_root / ".claude"
            claude_dir.mkdir(parents=True)
            settings_path = claude_dir / "settings.local.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": ["Bash(p1:*)", "Bash(p2:*)"],
                            "deny": [],
                            "ask": [],
                        }
                    }
                )
            )
            barrier = Path(tmpdir) / "go"
            patterns = ("Bash(p1:*)", "Bash(p2:*)")
            ready_markers = [Path(tmpdir) / f"ready_{i}" for i in range(len(patterns))]

            script = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                "from toolguard import permission_migration as pm\n"
                "project_root = Path(sys.argv[1])\n"
                "pattern = sys.argv[2]\n"
                "barrier = Path(sys.argv[3])\n"
                "Path(sys.argv[4]).touch()\n"
                "fake_divergent = {'allow': [pattern], 'deny': [], 'ask': []}\n"
                "fake_redundant = {'allow': [], 'deny': [], 'ask': []}\n"
                "deadline = time.monotonic() + 10\n"
                "while not barrier.exists() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "with patch.object(pm, 'find_divergent_patterns', return_value=fake_divergent):\n"
                "    with patch.object(pm, 'find_redundant_patterns', return_value=fake_redundant):\n"
                "        outcome = pm.migrate(project_root, dry_run=False)\n"
                "print(outcome.exit_code)\n"
            )

            env = self._isolated_env(home)
            procs = [
                run_child(
                    script,
                    str(project_root),
                    pattern,
                    str(barrier),
                    str(ready),
                    env=env,
                )
                for pattern, ready in zip(patterns, ready_markers)
            ]

            self.assertTrue(
                release_barrier_when_ready(barrier, ready_markers, timeout=10),
                "children never reached the barrier wait loop",
            )

            outputs = []
            for proc in procs:
                stdout, stderr = proc.communicate(timeout=20)
                self.assertEqual(proc.returncode, 0, msg=stderr)
                # migrate() prints progress to stdout; the exit code this
                # script prints is always its last line.
                outputs.append(stdout.strip().splitlines()[-1])

            self.assertEqual(outputs, ["0", "0"])

            toml_content = (claude_dir / "toolguard_hook.toml").read_text()
            self.assertIn("Bash(p1:*)", toml_content)
            self.assertIn("Bash(p2:*)", toml_content)

            with open(settings_path) as f:
                after_settings = json.load(f)
            self.assertEqual(after_settings["permissions"]["allow"], [])

    def test_second_process_declines_while_first_holds_the_lock(self):
        """
        Given one process holding this project's migration lock directly
            (standing in for a slow migration already in progress) and a
            marker file signalling once it holds it
        When a second process calls the real migrate() against the same
            project, with a short lock_timeout_seconds passed explicitly so
            the test doesn't wait the real default
        Then the second process's migrate() call returns
             MigrationOutcome.DECLINED_LOCKED -- observed here via its
             .exit_code, since the call happens in a child process and only
             the printed exit code crosses the process boundary -- without
             modifying settings.local.json
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir()
            project_root = Path(tmpdir) / "project"
            claude_dir = project_root / ".claude"
            claude_dir.mkdir(parents=True)
            settings_path = claude_dir / "settings.local.json"
            original_settings = {
                "permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
            }
            settings_path.write_text(json.dumps(original_settings))
            marker = Path(tmpdir) / "holding"

            holder_script = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from toolguard import file_lock, permission_migration as pm\n"
                "project_root = Path(sys.argv[1])\n"
                "marker = Path(sys.argv[2])\n"
                "lock_path = pm._migration_lock_path(project_root)\n"
                "with file_lock.exclusive(lock_path, timeout_seconds=5):\n"
                "    marker.touch()\n"
                "    time.sleep(1.5)\n"
                "print('released')\n"
            )
            contender_script = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from toolguard import permission_migration as pm\n"
                "project_root = Path(sys.argv[1])\n"
                "marker = Path(sys.argv[2])\n"
                "deadline = time.monotonic() + 10\n"
                "while not marker.exists() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "print(pm.migrate(project_root, dry_run=False, lock_timeout_seconds=0.3).exit_code)\n"
            )

            env = self._isolated_env(home)
            holder = run_child(holder_script, str(project_root), str(marker), env=env)
            contender = run_child(
                contender_script, str(project_root), str(marker), env=env
            )

            holder_out, holder_err = holder.communicate(timeout=20)
            contender_out, contender_err = contender.communicate(timeout=20)

            self.assertEqual(holder.returncode, 0, msg=holder_err)
            self.assertEqual(contender.returncode, 0, msg=contender_err)
            self.assertEqual(holder_out.strip(), "released")
            self.assertEqual(
                contender_out.strip(), str(MigrationOutcome.DECLINED_LOCKED.exit_code)
            )

            with open(settings_path) as f:
                self.assertEqual(json.load(f), original_settings)


class TestMigrationOutcomeExitCodes(unittest.TestCase):
    """Pins the mapping between MigrationOutcome and the shell exit code migrate_permissions.main() exposes."""

    def test_exit_code_mapping(self):
        """
        Given each MigrationOutcome member
        When .exit_code is read
        Then it matches the documented, stable contract: 0 success, 1
             failure, 3 declined-because-locked (not 2 -- that's argparse's
             own usage-error code in the same CLI)
        """
        self.assertEqual(MigrationOutcome.SUCCEEDED.exit_code, 0)
        self.assertEqual(MigrationOutcome.FAILED.exit_code, 1)
        self.assertEqual(MigrationOutcome.DECLINED_LOCKED.exit_code, 3)
        self.assertEqual(MigrationOutcome.DECLINED_UNAVAILABLE.exit_code, 4)

    def test_every_member_has_an_exit_code(self):
        """
        Given every member currently defined on MigrationOutcome
        When .exit_code is read
        Then none raises KeyError -- a member added without a matching
             _EXIT_CODES entry would blow up the first time a caller reads
             it, rather than at definition time
        """
        for outcome in MigrationOutcome:
            with self.subTest(outcome=outcome):
                outcome.exit_code


class TestMigratePermissionsMainExitCodes(unittest.TestCase):
    """End-to-end check that migrate_permissions.main() returns a plain int exit code, even though migrate() itself returns a MigrationOutcome."""

    def _main_with_mocked_migrate(self, outcome: MigrationOutcome) -> int:
        """
        Run main() with find_project_root and migrate() both mocked, asserting
        both mocks were consulted -- a mis-targeted find_project_root patch
        would otherwise let main() resolve the real repository root and every
        test here would still pass.
        """
        with (
            patch.object(
                migrate_permissions_module,
                "find_project_root",
                return_value=Path("/irrelevant"),
            ) as mock_root,
            patch.object(
                migrate_permissions_module, "migrate", return_value=outcome
            ) as mock_migrate,
            patch.object(migrate_permissions_module.sys, "argv", ["toolguard-migrate"]),
        ):
            exit_code = migrate_permissions_module.main()

        mock_root.assert_called_once()
        mock_migrate.assert_called_once()
        self.assertEqual(
            mock_migrate.call_args.kwargs["project_root"], Path("/irrelevant")
        )
        return exit_code

    def test_success_exits_zero(self):
        """
        Given migrate() returns MigrationOutcome.SUCCEEDED
        When main() runs
        Then it returns the int 0
        """
        self.assertEqual(self._main_with_mocked_migrate(MigrationOutcome.SUCCEEDED), 0)

    def test_failure_exits_one(self):
        """
        Given migrate() returns MigrationOutcome.FAILED
        When main() runs
        Then it returns the int 1
        """
        self.assertEqual(self._main_with_mocked_migrate(MigrationOutcome.FAILED), 1)

    def test_declined_locked_exits_three(self):
        """
        Given migrate() returns MigrationOutcome.DECLINED_LOCKED
        When main() runs
        Then it returns the int 3 -- distinct from argparse's own usage-error
             code 2 in the same CLI
        """
        self.assertEqual(
            self._main_with_mocked_migrate(MigrationOutcome.DECLINED_LOCKED), 3
        )

    def test_declined_unavailable_exits_four(self):
        """
        Given migrate() returns MigrationOutcome.DECLINED_UNAVAILABLE
        When main() runs
        Then it returns the int 4 -- distinct from DECLINED_LOCKED's 3, since
             a script branching on the exit code should be able to tell a
             lock race apart from access being unavailable altogether
        """
        self.assertEqual(
            self._main_with_mocked_migrate(MigrationOutcome.DECLINED_UNAVAILABLE), 4
        )


class TestSupersetDetection(unittest.TestCase):
    """Test superset detection for :*) patterns."""

    def test_superset_with_colon_star_pattern(self):
        """
        Given two :*) patterns where one's command is a prefix of the other's
        When is_superset compares the broader pattern against the narrower one
        Then it reports True (the broader pattern is a superset)
        """
        self.assertTrue(
            is_superset("Bash(uv run ruff:*)", "Bash(uv run ruff format:*)")
        )
        self.assertTrue(is_superset("Bash(git:*)", "Bash(git push:*)"))

    def test_not_superset_when_no_prefix_match(self):
        """
        Given two :*) patterns where neither command is a true word-prefix of the other
        When is_superset compares them
        Then it reports False
        """
        self.assertFalse(is_superset("Bash(ruff:*)", "Bash(ruffle:*)"))
        self.assertFalse(is_superset("Bash(git:*)", "Bash(ls:*)"))

    def test_not_superset_for_identical_patterns(self):
        """
        Given two identical patterns
        When is_superset compares them
        Then it reports False (a pattern is not a superset of itself)
        """
        self.assertFalse(is_superset("Bash(git:*)", "Bash(git:*)"))

    def test_extended_syntax_not_detected_as_superset(self):
        """
        Given patterns using extended syntax prefixes ([regex], [glob], [native])
        When is_superset is called with one of them involved
        Then it reports False because extended-syntax patterns are skipped
        """
        self.assertFalse(is_superset("[regex]^git", "Bash(git push:*)"))
        self.assertFalse(is_superset("Bash(git:*)", "[glob]git:*"))
        self.assertFalse(is_superset("[native]git *", "Bash(git push:*)"))

    def test_non_colon_star_patterns_not_superset(self):
        """
        Given patterns that lack the :*) postfix (plain or trailing-* forms)
        When is_superset compares them
        Then it reports False because only :*) patterns are handled
        """
        self.assertFalse(is_superset("Bash(git)", "Bash(git push)"))
        self.assertFalse(is_superset("Bash(git*)", "Bash(git push*)"))


class TestRedundantPatternDetection(unittest.TestCase):
    """Test detection of redundant patterns."""

    def test_find_exact_duplicates(self):
        """
        Given native permissions that exactly duplicate some toolguard permissions
        When find_redundant_patterns compares them
        Then the exact duplicates are reported as redundant and unique patterns are not
        """
        native_perms = {
            "allow": ["Bash(git:*)", "Bash(ls:*)", "Bash(uv run pytest:*)"],
            "deny": [],
            "ask": [],
        }
        toolguard_perms = {
            "allow": ["Bash(git:*)", "Bash(uv run pytest:*)"],
            "deny": [],
            "ask": [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertIn("Bash(git:*)", redundant["allow"])
        self.assertIn("Bash(uv run pytest:*)", redundant["allow"])
        self.assertNotIn("Bash(ls:*)", redundant["allow"])

    def test_find_subsets_covered_by_supersets(self):
        """
        Given native permissions that are narrower subsets of broader toolguard permissions
        When find_redundant_patterns compares them
        Then the subset patterns are reported as redundant (covered by the supersets)
        """
        native_perms = {
            "allow": ["Bash(uv run ruff format:*)", "Bash(git push:*)"],
            "deny": [],
            "ask": [],
        }
        toolguard_perms = {
            "allow": ["Bash(uv run ruff:*)", "Bash(git:*)"],
            "deny": [],
            "ask": [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertIn("Bash(uv run ruff format:*)", redundant["allow"])
        self.assertIn("Bash(git push:*)", redundant["allow"])

    def test_no_redundant_patterns(self):
        """
        Given native permissions that neither duplicate nor are subsets of toolguard permissions
        When find_redundant_patterns compares them
        Then no patterns are reported as redundant (empty allow result)
        """
        native_perms = {
            "allow": ["Bash(ls:*)", "Bash(cat:*)"],
            "deny": [],
            "ask": [],
        }
        toolguard_perms = {
            "allow": ["Bash(git:*)"],
            "deny": [],
            "ask": [],
        }

        redundant = find_redundant_patterns(native_perms, toolguard_perms)

        self.assertEqual(len(redundant["allow"]), 0)


class TestImprovedSimilarityDetection(unittest.TestCase):
    """Test improved similarity detection with difflib."""

    def test_similarity_uses_difflib(self):
        """
        Given an existing pattern that differs from the new one only by a single space
        When detect_similar_patterns runs
        Then it finds that close match with a high similarity score (> 0.9)
        """
        existing = [
            "Bash(~/bin/open_note_by_title.sh :*)",
            "Bash(git:*)",
            "Bash(ls:*)",
        ]
        new_pattern = "Bash(~/bin/open_note_by_title.sh:*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertTrue(len(similar) > 0)
        pattern, score, _ = similar[0]
        self.assertEqual(pattern, "Bash(~/bin/open_note_by_title.sh :*)")
        self.assertGreater(score, 0.9)

    def test_similarity_returns_ranked_results(self):
        """
        Given existing patterns of which TWO are close enough to the new
             pattern to be reported (the previous three-pattern fixture
             produced a single match, so the descending-score loop below ran
             zero times and the ranking this test is named for was never
             checked)
        When detect_similar_patterns runs
        Then two matches come back, the closest one first, with scores in
             descending order
        """
        existing = [
            "Bash(uv run ruff:*)",
            "Bash(uv run ruff format --diff:*)",
            "Bash(uv run mypy:*)",
        ]
        new_pattern = "Bash(uv run ruff format:*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(
            [pattern for pattern, _score, _superset in similar],
            ["Bash(uv run ruff format --diff:*)", "Bash(uv run ruff:*)"],
        )
        scores = [score for _pattern, score, _superset in similar]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_similarity_identifies_supersets(self):
        """
        Given an existing broad pattern that is a superset of the new specific pattern
        When detect_similar_patterns runs
        Then the match is returned with its superset flag set True
        """
        existing = ["Bash(uv run ruff:*)"]
        new_pattern = "Bash(uv run ruff format:*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertTrue(len(similar) > 0)
        pattern, score, is_superset_match = similar[0]
        self.assertEqual(pattern, "Bash(uv run ruff:*)")
        self.assertTrue(is_superset_match)

    def test_max_similar_matches_limit(self):
        """
        Given three candidate patterns that ALL qualify as similar
        When detect_similar_patterns runs with max_matches=2 and again with 3
        Then exactly 2 come back for 2 and exactly 3 for 3, and the two are the
             top of the same ranking. The previous fixture produced a single
             match whatever the limit, so `assertLessEqual(len(similar), 2)`
             held for any implementation of the cap, including none.
        """
        existing = [
            "Bash(uv run ruff formatter:*)",
            "Bash(uv run ruff format --diff:*)",
            "Bash(uv run ruff format --check:*)",
        ]
        new_pattern = "Bash(uv run ruff format:*)"

        capped = detect_similar_patterns(new_pattern, existing, max_matches=2)
        uncapped = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(capped), 2)
        self.assertEqual(len(uncapped), 3)
        self.assertEqual(capped, uncapped[:2])

    def test_common_prefix_not_flagged_as_similar(self):
        """
        Given many existing patterns that all share the same long prefix
        When detect_similar_patterns runs against a new same-prefix pattern
        Then no matches are returned because the shared prefix is not discriminating
        """
        existing = [f"Bash(uv run tool{i}:*)" for i in range(20)]
        new_pattern = "Bash(uv run tool99:*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(similar), 0)


class TestTOMLSectionPreservation(unittest.TestCase):
    """Test that write_toml_config preserves other sections."""

    def test_preserves_takeover_mode_section(self):
        """
        Given a TOML config with [takeover_mode] and [config_sync] sections plus permissions
        When write_toml_config writes new permissions
        Then the other sections and their values are preserved and permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {
                "allow": ["Bash(git:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("[takeover_mode]", new_content)
            self.assertIn("enabled = true", new_content)
            self.assertIn("[config_sync]", new_content)
            self.assertIn("auto_migrate = false", new_content)

            self.assertIn("Bash(git:*)", new_content)
            self.assertIn("Read(/tmp/*)", new_content)

    def test_preserves_top_level_keys(self):
        """
        Given a TOML config with top-level keys (governed_tools, additional_supported_tools)
        When write_toml_config writes new permissions
        Then those top-level keys are preserved and the permissions are updated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("governed_tools", new_content)
            self.assertIn("additional_supported_tools", new_content)
            self.assertIn("mcp__local-tools__checked_bash", new_content)

            self.assertIn("Bash(ls:*)", new_content)

    def test_creates_permissions_section_when_missing(self):
        """
        Given a TOML config with other sections but no [permissions] section
        When write_toml_config writes permissions
        Then a [permissions] section is added while the existing sections are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            initial_content = """[takeover_mode]
enabled = true

[config_sync]
auto_migrate = false
"""
            config_path.write_text(initial_content)

            permissions = {"allow": ["Bash(git:*)"], "deny": [], "ask": []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("[takeover_mode]", new_content)
            self.assertIn("[config_sync]", new_content)

            self.assertIn("[permissions]", new_content)
            self.assertIn("Bash(git:*)", new_content)

    def test_preserves_section_order(self):
        """
        Given a TOML config with sections ordered takeover_mode, permissions, config_sync
        When write_toml_config rewrites the permissions
        Then the original section ordering is maintained
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            initial_content = """[takeover_mode]
enabled = true

[permissions]
allow = ["Bash(ls:*)"]
deny = []

[config_sync]
auto_migrate = false
"""
            config_path.write_text(initial_content)

            permissions = {"allow": ["Bash(git:*)"], "deny": [], "ask": []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            takeover_pos = new_content.index("[takeover_mode]")
            permissions_pos = new_content.index("[permissions]")
            config_sync_pos = new_content.index("[config_sync]")

            self.assertLess(takeover_pos, permissions_pos)
            self.assertLess(permissions_pos, config_sync_pos)


class TestStructuredEntryFallbackRendering(unittest.TestCase):
    """reassemble_permissions_section's synthesize-from-scratch fallback: a new structured entry must render as a valid single-line TOML inline table, never a stringified dict."""

    def test_new_structured_entry_renders_as_valid_inline_table(self):
        """
        Given an existing TOML config with a [permissions] section containing
             only plain-string rules, and a NEW structured RuleEntry (no
             matching original line) added to the allow list passed to
             write_toml_config
        When write_toml_config rewrites the file
        Then the new entry is emitted as a single-line TOML inline table
             (not a Python-repr'd dict), and the resulting file re-parses with
             tomllib into the same match/metadata values
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"
            config_path.write_text(
                '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\ndeny = []\n'
            )

            new_entry = RuleEntry(
                pattern="Bash(git *)",
                metadata=MappingProxyType({"additionalContext": "review carefully"}),
            )
            permissions = {
                "allow": [
                    RuleEntry(pattern="Bash(ls:*)", raw="Bash(ls:*)"),
                    new_entry,
                ],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=False)

            content = config_path.read_text()

            self.assertNotIn("RuleEntry(", content)
            self.assertIn(
                '{ match = "Bash(git *)", additionalContext = "review carefully" }',
                content,
            )

            reparsed = tomllib.loads(content)
            allow = reparsed["permissions"]["allow"]
            structured = [e for e in allow if isinstance(e, dict)]
            self.assertEqual(len(structured), 1)
            self.assertEqual(structured[0]["match"], "Bash(git *)")
            self.assertEqual(structured[0]["additionalContext"], "review carefully")


class TestCommentPreservation(unittest.TestCase):
    """Test that comments are preserved when rewriting TOML (Bug 2)."""

    def test_preserves_inline_comments(self):
        """
        Given a TOML config with inline comments on the same line as rules
        When write_toml_config rewrites the permissions adding a new rule
        Then the inline comments are preserved in the output
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            initial_content = """[permissions]
allow = [
  "Bash(ls:*)",  # This allows ls commands
  "Bash(git:*)",  # Git commands
]
deny = []
"""
            config_path.write_text(initial_content)

            permissions = {
                "allow": ["Bash(ls:*)", "Bash(git:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("# This allows ls commands", new_content)
            self.assertIn("# Git commands", new_content)

    def test_preserves_single_quoted_literal_rules(self):
        """
        Given a TOML config whose allow list uses a single-quoted LITERAL string
              for a rule that contains backslashes (e.g. a [regex] find guard)
        When write_toml_config rewrites the permissions (adding an unrelated rule)
        Then the single-quoted literal rule is preserved verbatim and is NOT
             dropped or regenerated into an escaped double-quoted form.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            initial_content = (
                "[permissions]\n"
                "allow = [\n"
                "  # find guard\n"
                "  'Bash([regex]\\bfind\\b(?!.*-exec))',\n"
                '  "Bash(ls:*)",\n'
                "]\n"
            )
            config_path.write_text(initial_content)

            permissions = {
                "allow": [
                    "Bash([regex]\\bfind\\b(?!.*-exec))",
                    "Bash(ls:*)",
                    "Bash(git status:*)",
                ],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=True)

            new_content = config_path.read_text()
            self.assertIn("'Bash([regex]\\bfind\\b(?!.*-exec))',", new_content)
            self.assertIn("# find guard", new_content)
            self.assertIn('"Bash(git status:*)"', new_content)

    def test_preserves_comment_blocks_above_rules(self):
        """
        Given a TOML config with comment blocks above individual rules
        When write_toml_config rewrites the permissions with sorting enabled
        Then those comment blocks are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {
                "allow": ["Bash(git:*)", "Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=True)

            new_content = config_path.read_text()

            self.assertIn("# Allow git operations", new_content)
            self.assertIn("# Allow file listing", new_content)

    def test_preserves_top_of_section_comments(self):
        """
        Given a TOML config with explanatory comments at the top of the permissions section
        When write_toml_config rewrites the permissions
        Then those comments are preserved and remain before the first rule
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {
                "allow": ["Bash(git:*)", "Bash(ls:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("# These permissions are equivalent", new_content)
            self.assertIn("# Extended syntax is supported", new_content)

            comment_pos = new_content.index("# These permissions")
            first_rule_pos = new_content.index("Bash(")
            self.assertLess(comment_pos, first_rule_pos)

    def test_preserves_bottom_of_section_comments(self):
        """
        Given a TOML config with trailing comments after the last rule in the allow list
        When write_toml_config rewrites the permissions adding a new rule
        Then those comments are preserved and remain after the last rule
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {
                "allow": ["Bash(ls:*)", "Bash(git:*)", "Read(/tmp/*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("# TODO: Add more patterns here", new_content)
            self.assertIn("# Review this list regularly", new_content)

            last_rule_pos = new_content.rindex("Read(/tmp/*)")
            comment_pos = new_content.index("# TODO")
            self.assertGreater(comment_pos, last_rule_pos)

    def test_preserves_blank_lines_in_comment_blocks(self):
        """
        Given a TOML config with comment blocks separated by blank lines above a rule
        When write_toml_config rewrites the permissions
        Then the comment lines are preserved
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

            initial_content = """[permissions]
allow = [
  # Section 1: Git commands

  # Allow all git operations
  "Bash(git:*)",
]
deny = []
"""
            config_path.write_text(initial_content)

            permissions = {"allow": ["Bash(git:*)"], "deny": [], "ask": []}
            write_toml_config(config_path, permissions, auto_sort=False)

            new_content = config_path.read_text()

            self.assertIn("# Section 1: Git commands", new_content)
            self.assertIn("# Allow all git operations", new_content)

    def test_comments_move_with_sorted_rules(self):
        """
        Given a TOML config where each rule has its own comment block and sorting reorders them
        When write_toml_config rewrites with auto_sort enabled
        Then each comment moves together with its associated rule into the new order
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "toolguard_hook.toml"

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

            permissions = {
                "allow": ["Write(/tmp/*)", "Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
            write_toml_config(config_path, permissions, auto_sort=True)

            new_content = config_path.read_text()

            bash_pos = new_content.index("Bash(ls:*)")
            write_pos = new_content.index("Write(/tmp/*)")
            self.assertLess(bash_pos, write_pos)

            aaa_comment_pos = new_content.index("# AAA pattern")
            zzz_comment_pos = new_content.index("# ZZZ pattern")

            self.assertLess(aaa_comment_pos, bash_pos)

            self.assertLess(zzz_comment_pos, write_pos)


class TestBlanketPatternSimilarity(unittest.TestCase):
    """Test that blanket patterns are not flagged as similar."""

    def test_blanket_bash_pattern_not_similar(self):
        """
        Given an existing blanket Bash(*) pattern and a new specific Bash(wc:*) pattern
        When detect_similar_patterns runs
        Then no matches are returned because the blanket pattern has no meaningful prefix
        """
        existing = ["Bash(*)", "Read(*)", "Write(*)"]
        new_pattern = "Bash(wc:*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(similar), 0)

    def test_blanket_read_pattern_not_similar(self):
        """
        Given an existing blanket Read(*) pattern and a new specific Read(/tmp/*) pattern
        When detect_similar_patterns runs
        Then no matches are returned
        """
        existing = ["Read(*)", "Bash(*)"]
        new_pattern = "Read(/tmp/*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(similar), 0)

    def test_new_blanket_pattern_not_similar(self):
        """
        Given existing specific Bash patterns and a new blanket Bash(*) pattern
        When detect_similar_patterns runs
        Then no matches are returned because the new blanket pattern is not compared
        """
        existing = ["Bash(git:*)", "Bash(ls:*)", "Bash(find:*)"]
        new_pattern = "Bash(*)"

        similar = detect_similar_patterns(new_pattern, existing, max_matches=3)

        self.assertEqual(len(similar), 0)

    def test_meaningful_prefix_extraction_blanket(self):
        """
        Given blanket patterns of the form Tool(*)
        When extract_meaningful_prefix is called on each
        Then it returns an empty string (no meaningful prefix)
        """
        from toolguard.permission_migration import extract_meaningful_prefix

        self.assertEqual(extract_meaningful_prefix("Bash(*)"), "")
        self.assertEqual(extract_meaningful_prefix("Read(*)"), "")
        self.assertEqual(extract_meaningful_prefix("Write(*)"), "")
        self.assertEqual(extract_meaningful_prefix("Edit(*)"), "")

    def test_meaningful_prefix_extraction_with_content(self):
        """
        Given patterns whose inner content carries a real command or path prefix
        When extract_meaningful_prefix is called on each
        Then it returns that command or path prefix string
        """
        from toolguard.permission_migration import extract_meaningful_prefix

        self.assertEqual(
            extract_meaningful_prefix("Bash(uv run ruff format:*)"),
            "uv run ruff format",
        )
        self.assertEqual(extract_meaningful_prefix("Bash(find:*)"), "find")
        self.assertEqual(extract_meaningful_prefix("Read(/tmp/*)"), "/tmp/")
        self.assertEqual(extract_meaningful_prefix("Bash(git push:*)"), "git push")

    def test_lowering_max_matches_can_suppress_every_match(self):
        """
        Given five same-prefix candidates, exactly one of which is reported as
            similar at max_matches=2
        When detect_similar_patterns runs with max_matches=1 instead
        Then NOTHING is reported -- max_matches is not only a display cap, it
             also scales the "this prefix isn't discriminating" suppression at
             permission_migration.py:464-470, so asking for fewer matches can
             drop the superset warning entirely rather than truncate it.
             Characterization of measured behaviour that contradicts the
             parameter's own docstring ("Maximum number of similar patterns to
             return"). Previously this was a duplicate of
             test_max_similar_matches_limit, on a fixture neither could fail on.
        """
        existing = [
            "Bash(uv run pytest:*)",
            "Bash(uv run mypy:*)",
            "Bash(uv run ruff:*)",
            "Bash(uv run black:*)",
            "Bash(uv run isort:*)",
        ]
        new_pattern = "Bash(uv run ruff format:*)"

        self.assertEqual(
            len(detect_similar_patterns(new_pattern, existing, max_matches=2)), 1
        )
        self.assertEqual(
            detect_similar_patterns(new_pattern, existing, max_matches=1), []
        )


class TestMigrationWithRedundantPatterns(ConfigIsolationMixin, unittest.TestCase):
    """Test full migration flow with redundant pattern removal."""

    def test_migration_removes_redundant_patterns(self):
        """
        Given a toolguard config and settings.local.json containing duplicates, subsets, and one
        genuinely new pattern
        When migrate runs the full flow
        Then all redundant and migrated patterns are removed from settings and
        it exits 0 -- and the toolguard config ends up holding the patterns
        just reported as redundant TOO, not only the genuinely new one.
        Characterization, not endorsement: divergent and redundant are computed
        independently, so a pattern reported as "COVERED BY" a superset is
        still written. The previous Then claimed only the new pattern was
        added, which the file contradicts.
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_content = """[permissions]
allow = [
  "Bash(git:*)",
  "Bash(uv run ruff:*)",
]
deny = []
"""
        toml_path.write_text(toml_content)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": [
                    "Bash(git:*)",
                    "Bash(git push:*)",
                    "Bash(uv run ruff format:*)",
                    "Bash(ls:*)",
                ],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        with open(settings_path, "r") as f:
            updated_settings = json.load(f)

        remaining = updated_settings["permissions"]["allow"]
        self.assertNotIn("Bash(git:*)", remaining)
        self.assertNotIn("Bash(git push:*)", remaining)
        self.assertNotIn("Bash(uv run ruff format:*)", remaining)
        self.assertNotIn("Bash(ls:*)", remaining)

        written = tomllib.loads(toml_path.read_text())["permissions"]
        self.assertEqual(
            sorted(written["allow"]),
            [
                "Bash(git push:*)",
                "Bash(git:*)",
                "Bash(ls:*)",
                "Bash(uv run ruff format:*)",
                "Bash(uv run ruff:*)",
            ],
        )
        self.assertEqual(written.get("deny", []), [])

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)


class TestMigrationTargetLevel(ConfigIsolationMixin, unittest.TestCase):
    """
    migrate() always writes to project_root's OWN .claude directory, never
    falling through to a toolguard_hook file discover_config_files() found at
    a less-specific level (e.g. the user's home ~/.claude). migrate() does
    not call find_project_root() itself, but discover_config_files() does --
    so project_root here is always the mixin's own isolated project.
    """

    def test_migration_targets_project_own_existing_config_not_user_level(self):
        """
        Given a project with its OWN existing toolguard_hook.toml AND a DIFFERENT,
        distinct user-level toolguard_hook.toml also present
        When migrate runs
        Then the new pattern is added to the PROJECT's own toolguard_hook.toml and the
        user-level file is left completely unchanged
        """
        home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        project_toml_path = claude_dir / "toolguard_hook.toml"
        project_toml_path.write_text(
            '[permissions]\nallow = [\n  "Bash(git:*)",\n]\ndeny = []\n'
        )

        home_claude_dir = home / ".claude"
        home_claude_dir.mkdir()
        user_toml_path = home_claude_dir / "toolguard_hook.toml"
        user_toml_original = (
            '[permissions]\nallow = [\n  "Bash(other:*)",\n]\ndeny = []\n'
        )
        user_toml_path.write_text(user_toml_original)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(git:*)", "Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        project_written = tomllib.loads(project_toml_path.read_text())["permissions"]
        self.assertEqual(
            sorted(project_written["allow"]), ["Bash(git:*)", "Bash(ls:*)"]
        )

        user_content = user_toml_path.read_text()
        self.assertNotIn("Bash(ls:*)", user_content)
        self.assertEqual(user_content, user_toml_original)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_a_pattern_already_allowed_at_the_user_level_is_not_migrated(self):
        """
        Given a pattern present in the USER-level ~/.claude/toolguard_hook.toml
            and in the project's settings.local.json, with the project having
            its own toolguard config that does NOT contain it
        When migrate runs
        Then the pattern is not written into the project config -- toolguard
             already allows it through the user level, so migrating it would
             duplicate the rule. Without this, nothing here distinguishes
             "the user level was read" from "the user level was ignored":
             deleting the ~/.claude candidates from discover_config_files
             leaves the rest of this module green.
        """
        home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        project_toml_path = claude_dir / "toolguard_hook.toml"
        project_toml_path.write_text(
            '[permissions]\nallow = ["Bash(git:*)"]\ndeny = []\n'
        )

        home_claude_dir = home / ".claude"
        home_claude_dir.mkdir()
        (home_claude_dir / "toolguard_hook.toml").write_text(
            '[permissions]\nallow = ["Bash(user-level:*)"]\ndeny = []\n'
        )

        settings_path = claude_dir / "settings.local.json"
        with open(settings_path, "w") as f:
            json.dump(
                {
                    "permissions": {
                        "allow": ["Bash(user-level:*)", "Bash(ls:*)"],
                        "deny": [],
                        "ask": [],
                    }
                },
                f,
            )

        outcome = migrate(project_root)
        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

        project_written = tomllib.loads(project_toml_path.read_text())["permissions"]
        self.assertEqual(
            sorted(project_written["allow"]), ["Bash(git:*)", "Bash(ls:*)"]
        )
        self.assertNotIn("Bash(user-level:*)", project_written["allow"])

    def test_migration_creates_project_config_instead_of_using_user_level(self):
        """
        Given a project with NO toolguard_hook config of its own, but a user-level
        ~/.claude/toolguard_hook.toml DOES exist
        When migrate runs
        Then it CREATES project_root/.claude/toolguard_hook.toml and adds the new
        pattern there, WITHOUT touching the existing user-level file
        """
        home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        home_claude_dir = home / ".claude"
        home_claude_dir.mkdir()
        user_toml_path = home_claude_dir / "toolguard_hook.toml"
        user_toml_original = (
            '[permissions]\nallow = [\n  "Bash(other:*)",\n]\ndeny = []\n'
        )
        user_toml_path.write_text(user_toml_original)

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        project_toml_path = claude_dir / "toolguard_hook.toml"
        self.assertTrue(
            project_toml_path.exists(),
            "migrate() must create a project-level toolguard_hook.toml "
            "rather than silently writing into the user-level config",
        )
        project_content = project_toml_path.read_text()
        self.assertIn("Bash(ls:*)", project_content)

        user_content = user_toml_path.read_text()
        self.assertNotIn("Bash(ls:*)", user_content)
        self.assertEqual(user_content, user_toml_original)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_migration_project_root_equal_to_home_targets_the_shared_config(self):
        """
        Given project_root itself resolves to the home directory (project and user
        level collapse to the same .claude directory), with an existing
        toolguard_hook.toml there
        When migrate runs
        Then the new pattern is added to that single shared toolguard_hook.toml (the
        project-vs-user distinction naturally collapses, no special-casing needed)
        """
        home, _project = self.isolate_config_environment()
        project_root = home
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        toml_path = claude_dir / "toolguard_hook.toml"
        toml_path.write_text(
            '[permissions]\nallow = [\n  "Bash(git:*)",\n]\ndeny = []\n'
        )

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        # project_root IS home here; the mixin's default project is home's
        # sibling, so find_project_root must be re-pointed for this test.
        self.enterContext(
            patch("toolguard.config.find_project_root", return_value=project_root)
        )
        outcome = migrate(project_root)

        content = toml_path.read_text()
        self.assertIn("Bash(ls:*)", content)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)

    def test_migration_creates_project_config_when_neither_level_has_one(self):
        """
        Given neither the project nor the user level has an existing toolguard_hook
        config anywhere
        When migrate runs
        Then it creates project_root/.claude/toolguard_hook.toml with the new pattern
        """
        _home, project_root = self.isolate_config_environment()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        settings_path = claude_dir / "settings.local.json"
        settings = {
            "permissions": {
                "allow": ["Bash(ls:*)"],
                "deny": [],
                "ask": [],
            }
        }
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        outcome = migrate(project_root)

        project_toml_path = claude_dir / "toolguard_hook.toml"
        self.assertTrue(project_toml_path.exists())
        content = project_toml_path.read_text()
        self.assertIn("Bash(ls:*)", content)

        self.assertEqual(outcome, MigrationOutcome.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
