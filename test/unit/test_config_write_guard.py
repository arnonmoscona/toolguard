"""
Unit tests for toolguard.config_write_guard -- the self-protection gate every
config-file write must pass through.

Isolation (`.claude/rules/test-config-isolation.md`): these tests do file I/O
inside a throwaway TemporaryDirectory only and never reach toolguard.config's
discovery path, so ConfigIsolationMixin is not needed.

Atomicity is asserted by observing the rename, not by reading the file back: a
write-then-read test passes identically for an atomic write and a truncate in
place. See TestVerifiedWriteConfigAtomicity.
"""

import json
import os
import stat
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_write_guard import (
    ConfigWriteVerificationError,
    _ALLOW_LIST_TYPES,
    _HARD_DENY_RESTRICTING_LIST_TYPES,
    patterns_in_config_text,
    verified_write_config,
    verify_config_text,
)


class TestVerifyConfigText(unittest.TestCase):
    """Direct unit tests for the pure-syntax verify_config_text() check."""

    def test_valid_toml_text_raises_nothing(self):
        """
        Given syntactically valid TOML text
        When verify_config_text() is called with file_format="toml"
        Then it returns without raising
        """
        verify_config_text('[permissions]\nallow = ["Bash(ls:*)"]\n', "toml")

    def test_valid_json_text_raises_nothing(self):
        """
        Given syntactically valid JSON text
        When verify_config_text() is called with file_format="json"
        Then it returns without raising
        """
        verify_config_text('{"permissions": {"allow": []}}', "json")

    def test_invalid_toml_raises_config_write_verification_error(self):
        """
        Given TOML text with an illegal unescaped newline inside a string
        When verify_config_text() is called with file_format="toml"
        Then ConfigWriteVerificationError is raised, carrying the reason and
            the underlying parser's message
        """
        broken = 'additionalContext = "see [permissions]\ndocs"\n'
        with self.assertRaises(ConfigWriteVerificationError) as ctx:
            verify_config_text(broken, "toml")
        self.assertIn("TOML", ctx.exception.reason)
        self.assertTrue(ctx.exception.message)

    def test_invalid_json_raises_config_write_verification_error(self):
        """
        Given syntactically invalid JSON text
        When verify_config_text() is called with file_format="json"
        Then ConfigWriteVerificationError is raised, naming JSON in the reason
            and carrying the underlying parser's message
        """
        with self.assertRaises(ConfigWriteVerificationError) as ctx:
            verify_config_text("{not valid json", "json")
        self.assertIn("JSON", ctx.exception.reason)
        self.assertTrue(ctx.exception.message)

    def test_unknown_file_format_raises_value_error(self):
        """
        Given a file_format that is neither "toml" nor "json"
        When verify_config_text() is called
        Then ValueError is raised
        """
        with self.assertRaises(ValueError):
            verify_config_text("anything", "yaml")

    def test_error_carries_path_when_given(self):
        """
        Given invalid TOML text and an explicit path argument
        When verify_config_text() is called with that path
        Then the raised error's .path attribute is that same path, and the
            path appears in the exception's own message
        """
        with self.assertRaises(ConfigWriteVerificationError) as ctx:
            verify_config_text("bad = [", "toml", path=Path("/tmp/x.toml"))
        self.assertEqual(ctx.exception.path, Path("/tmp/x.toml"))
        self.assertIn("/tmp/x.toml", str(ctx.exception))

    def test_json_parsing_to_a_non_object_is_refused(self):
        """
        Given JSON text that parses cleanly but whose top level is not an
            object -- `null`, an array, a bare scalar
        When verify_config_text() is called, and when verified_write_config()
            is asked to write such text over an existing config file
        Then both are refused with ConfigWriteVerificationError and the file
            on disk is left unchanged

        FAILS AGAINST THE SHIPPED CODE ON PURPOSE. The guard checks only that
        the text parses. toolguard's own loader additionally requires a
        top-level table -- config.py's _parse_source_recording_failures raises
        `TypeError: expected a top-level object/table`, records a parse failure
        and clamps every governed decision to `ask`. So a `null` settings.json
        is a file this project cannot load, which is precisely the outcome this
        module exists to make impossible. (TOML cannot express a non-table top
        level, so this is a JSON-only shape.)
        """
        for text in ("null", "[]", "3", '"hello"'):
            with self.subTest(text=text):
                with self.assertRaises(ConfigWriteVerificationError):
                    verify_config_text(text, "json")

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            original = '{"permissions": {"allow": ["Bash(ls:*)"]}}'
            path.write_text(original)

            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(path, "null", "json")
            self.assertEqual(path.read_text(), original)


class TestVerifiedWriteConfigSyntaxGuard(unittest.TestCase):
    """verified_write_config()'s refusal on unparseable text, and file safety."""

    def test_corrupt_toml_write_is_refused_and_original_file_unchanged(self):
        """
        Given an existing valid TOML config file on disk
        When verified_write_config() is called with corrupt replacement text
        Then ConfigWriteVerificationError is raised naming the path, and the
            original file's bytes on disk are completely unchanged
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\nallow = ["Bash(ls:*)"]\n'
            path.write_bytes(original.encode("utf-8"))

            corrupt = 'additionalContext = "see [permissions]\ndocs"\n'
            with self.assertRaises(ConfigWriteVerificationError) as ctx:
                verified_write_config(path, corrupt, "toml")

            self.assertEqual(ctx.exception.path, path)
            self.assertEqual(path.read_bytes(), original.encode("utf-8"))

    def test_section_spliced_into_a_quoted_string_is_refused(self):
        """
        Given a rewritten [permissions] section spliced into the middle of an
            EARLIER structured entry's quoted additionalContext string,
            leaving an unescaped newline
        When verified_write_config() is called with that corrupted text
        Then it is refused by the syntax guard and the file is unchanged

        This is the on-disk shape a writer that fails to escape a newline
        inside additionalContext produces, so it is the case the guard is
        the last line of defence for.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                "[hard_deny]\n"
                "deny = [\n"
                '  { match = "Bash(rm -rf /)", additionalContext = "see [permissions] docs" },\n'
                "]\n"
                "\n"
                "[permissions]\n"
                'allow = ["Bash(ls *)"]\n'
            )
            path.write_bytes(original.encode("utf-8"))

            corrupted = (
                "[hard_deny]\n"
                "deny = [\n"
                '  { match = "Bash(rm -rf /)", additionalContext = "see [permissions]\n'
                "allow = [\n"
                '  "Bash(git status)",\n'
                "]\n"
                "\n"
                "[permissions]\n"
                'allow = ["Bash(ls *)"]\n'
            )

            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(path, corrupted, "toml")
            self.assertEqual(path.read_bytes(), original.encode("utf-8"))


class TestVerifiedWriteConfigContentLossGuard(unittest.TestCase):
    """verified_write_config()'s expected_patterns content-loss check."""

    def test_write_dropping_expected_pattern_is_refused(self):
        """
        Given valid (parseable) replacement TOML text that OMITS a pattern
            the caller expects to still be present
        When verified_write_config() is called with that pattern in
            expected_patterns
        Then ConfigWriteVerificationError is raised whose reason identifies a
            dropped rule and whose message names the missing pattern, and the
            original file is left unchanged
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\n\n'
                '[permissions]\nallow = ["Bash(ls *)"]\n'
            )
            path.write_bytes(original.encode("utf-8"))

            new_text = '[permissions]\nallow = ["Bash(ls *)"]\n'

            with self.assertRaises(ConfigWriteVerificationError) as ctx:
                verified_write_config(
                    path,
                    new_text,
                    "toml",
                    expected_patterns=["Bash(rm -rf /)", "Bash(ls *)"],
                )
            self.assertIn("drop", ctx.exception.reason)
            self.assertIn("Bash(rm -rf /)", ctx.exception.message)
            self.assertNotIn("Bash(ls *)", ctx.exception.message)
            self.assertEqual(path.read_bytes(), original.encode("utf-8"))

    def test_json_write_dropping_expected_pattern_is_refused(self):
        """
        Given an existing JSON config and replacement JSON text that omits one
            of its patterns
        When verified_write_config() is called with file_format="json" and
            expected_patterns computed from the original text
        Then the write is refused and the file is unchanged

        The TOML path is exercised above; before this test nothing anywhere
        drove the content-loss check with JSON, so _patterns_in_parsed was only
        ever fed a tomllib result.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            original = json.dumps(
                {"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)"]}}
            )
            path.write_text(original)

            expected = patterns_in_config_text(original, "json")
            self.assertEqual(expected, {"Bash(ls:*)", "Bash(rm:*)"})

            new_text = json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}})
            with self.assertRaises(ConfigWriteVerificationError) as ctx:
                verified_write_config(
                    path, new_text, "json", expected_patterns=expected
                )
            self.assertIn("Bash(rm:*)", ctx.exception.message)
            self.assertEqual(path.read_text(), original)

    def test_write_preserving_all_expected_patterns_succeeds(self):
        """
        Given replacement text that still contains every expected pattern,
            one as a plain string and one as a structured {match=...} entry
        When verified_write_config() is called with those patterns in
            expected_patterns
        Then the write succeeds and the file now contains the new text
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_bytes(b"[permissions]\nallow = []\n")

            new_text = (
                "[permissions]\n"
                'allow = ["Bash(ls *)", '
                '{ match = "Bash(git status)", additionalContext = "ro" }]\n'
            )
            verified_write_config(
                path,
                new_text,
                "toml",
                expected_patterns=["Bash(ls *)", "Bash(git status)"],
            )
            self.assertEqual(path.read_text(), new_text)

    def test_expected_patterns_none_skips_content_loss_check(self):
        """
        Given a brand-new file with expected_patterns left as None
        When verified_write_config() is called
        Then no content-loss check is performed and the file is written with
            exactly the requested text
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            text = "[permissions]\nallow = []\n"
            verified_write_config(path, text, "toml")
            self.assertEqual(path.read_text(), text)

    def test_empty_expected_patterns_verifies_nothing_and_accepts_an_empty_file(self):
        """
        Given expected_patterns=[] -- a caller asking for a content-loss check
            with zero patterns to check
        When verified_write_config() is called with text that drops every rule
            the file used to hold, and again with the empty string
        Then both writes succeed, including the one that leaves a zero-byte
            config file behind

        PINS SHIPPED BEHAVIOUR: the check reports success having verified
        nothing, and its caller cannot distinguish "12 patterns confirmed
        present" from "0 patterns checked". Refusing an empty set outright
        would be wrong -- a genuinely rule-free original yields an empty set
        legitimately -- so a fix here is a signal the caller can see, not a
        refusal. Do not read this test as a specification.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_text('[permissions]\nallow = ["Bash(ls *)"]\n')

            verified_write_config(
                path, "[permissions]\nallow = []\n", "toml", expected_patterns=[]
            )
            self.assertEqual(path.read_text(), "[permissions]\nallow = []\n")

            verified_write_config(path, "", "toml", expected_patterns=set())
            self.assertEqual(path.read_text(), "")

    def test_pattern_moved_out_of_hard_deny_into_allow_is_refused(self):
        """
        Given a config whose hard_deny.deny list holds "Bash(rm -rf /)" and
            replacement text that moves that same pattern into
            permissions.allow
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED and the file keeps its original bytes -- a
            hard deny inverted into an allow is a loss, even though the pattern
            string is still somewhere in the file
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\n\n[permissions]\nallow = []\n'
            )
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")
            self.assertEqual(expected, {"Bash(rm -rf /)"})

            inverted = '[permissions]\nallow = ["Bash(rm -rf /)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(
                    path, inverted, "toml", expected_patterns=expected
                )
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_hard_deny_deny_into_hard_deny_allow_is_refused(self):
        """
        Given a config whose hard_deny.deny list holds "Bash(rm -rf /)" and
            replacement text that moves that same pattern into
            hard_deny.allow, leaving hard_deny.deny empty
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED -- the pattern string never left the
            hard_deny table, but hard_deny.allow is a carve-out that exempts
            an otherwise-matched deny, so this is the same inversion as
            moving it out to permissions.allow, one level up
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            carved_out = '[hard_deny]\ndeny = []\nallow = ["Bash(rm -rf /)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(
                    path, carved_out, "toml", expected_patterns=expected
                )
            self.assertEqual(path.read_text(), original)

    def test_pattern_kept_in_hard_deny_deny_while_also_added_to_hard_deny_allow_is_refused(
        self,
    ):
        """
        Given a config whose hard_deny.deny list holds "Bash(rm -rf /)" and
            replacement text that ADDS that same pattern to hard_deny.allow
            too, while leaving it in hard_deny.deny
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED -- unlike permissions, where deny wins over
            allow at the same level, a hard_deny.allow carve-out wins over a
            same-pattern hard_deny.deny at match time, so the pattern string
            staying in deny does not mean protection was kept
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            redundant = (
                '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = ["Bash(rm -rf /)"]\n'
            )
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(
                    path, redundant, "toml", expected_patterns=expected
                )
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_deny_into_allow_is_refused(self):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)" and
            replacement text that moves that same pattern into
            permissions.allow, with permissions.deny left empty
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED, naming the moved pattern, and the file
            keeps its original bytes
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            inverted = '[permissions]\nallow = ["Bash(rm -rf /)"]\ndeny = []\n'
            with self.assertRaises(ConfigWriteVerificationError) as ctx:
                verified_write_config(
                    path, inverted, "toml", expected_patterns=expected
                )
            self.assertIn("Bash(rm -rf /)", ctx.exception.message)
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_ask_into_allow_is_refused(self):
        """
        Given a config whose permissions.ask list holds "Bash(git push:*)" and
            replacement text that moves that same pattern into
            permissions.allow, with permissions.ask left empty
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED and the file keeps its original bytes
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\nask = ["Bash(git push:*)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            inverted = '[permissions]\nallow = ["Bash(git push:*)"]\nask = []\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(
                    path, inverted, "toml", expected_patterns=expected
                )
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_deny_into_hard_deny_allow_is_refused(self):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)" and
            replacement text that removes it from permissions entirely and
            adds the same pattern to hard_deny.allow instead
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED -- hard_deny.allow is a carve-out, not a
            restriction, so the pattern ends up restricted nowhere even
            though its string is still present in the file
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            moved = '[hard_deny]\nallow = ["Bash(rm -rf /)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(path, moved, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_ask_into_hard_deny_allow_is_refused(self):
        """
        Given a config whose permissions.ask list holds "Bash(git push:*)" and
            replacement text that removes it from permissions entirely and
            adds the same pattern to hard_deny.allow instead
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED, the same class of loss as the
            permissions.deny case above
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\nask = ["Bash(git push:*)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            moved = '[hard_deny]\nallow = ["Bash(git push:*)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(path, moved, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_deny_into_unrecognised_hard_deny_sublist_is_refused(
        self,
    ):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)" and
            replacement text that removes it from permissions entirely and
            adds the same pattern to a hard_deny sub-list the runtime does
            not read (e.g. "quarantine")
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED -- the pattern's string survives somewhere
            in the file, but nowhere the runtime actually enforces it
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            moved = '[hard_deny]\nquarantine = ["Bash(rm -rf /)"]\n'
            with self.assertRaises(ConfigWriteVerificationError):
                verified_write_config(path, moved, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), original)

    def test_pattern_moved_from_permissions_deny_into_hard_deny_deny_is_not_refused(
        self,
    ):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)" and
            replacement text that removes it from permissions entirely and
            adds the same pattern to hard_deny.deny instead
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS -- hard_deny.deny is a strictly stronger
            restriction than permissions.deny, not a loss
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            moved = '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            verified_write_config(path, moved, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), moved)

    def test_pattern_dropped_from_expected_patterns_and_removed_entirely_is_not_refused(
        self,
    ):
        """
        Given a config whose permissions.deny list holds two patterns, and
            replacement text that removes ONE of them from the file entirely
        When verified_write_config() is called with expected_patterns that
            deliberately excludes the removed pattern (the caller does not
            require it to survive this write -- e.g. because a migration
            moved it to a different file)
        Then the write SUCCEEDS -- the placement checks are scoped to
            expected_patterns, the same set step 2 enforces, so a pattern
            the caller never asked this write to keep is not flagged just
            because it can no longer be found in this file
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = (
                '[permissions]\ndeny = ["Bash(rm -rf /)", "Bash(x)"]\nallow = []\n'
            )
            path.write_text(original)

            dropped = '[permissions]\ndeny = ["Bash(x)"]\nallow = []\n'
            verified_write_config(path, dropped, "toml", expected_patterns=["Bash(x)"])
            self.assertEqual(path.read_text(), dropped)

    def test_pattern_moved_between_deny_and_ask_is_not_refused(self):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)" and
            replacement text that moves that same pattern into permissions.ask
            instead, with no permissions.allow entry added
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS -- deny -> ask is a deliberately accepted
            weakening (ask is still an enforced gate under toolguard); only
            arrival in permissions.allow, where enforcement disappears
            entirely, is refused
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            moved = '[permissions]\nask = ["Bash(rm -rf /)"]\nallow = []\ndeny = []\n'
            verified_write_config(path, moved, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), moved)

    def test_pattern_kept_in_deny_while_also_added_to_allow_is_not_refused(self):
        """
        Given a config whose permissions.deny list holds "Bash(rm -rf /)"
        When verified_write_config() is called with replacement text that adds
            the SAME pattern to permissions.allow too, while leaving it in
            permissions.deny
        Then the write SUCCEEDS -- deny still wins over allow at the same
            level, so the pattern remains just as restricted as before
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            redundant = (
                '[permissions]\ndeny = ["Bash(rm -rf /)"]\nallow = ["Bash(rm -rf /)"]\n'
            )
            verified_write_config(path, redundant, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), redundant)

    def test_pattern_moved_from_hard_deny_deny_into_an_unrecognised_sublist_is_refused(
        self,
    ):
        """
        Given a config whose hard_deny.deny list holds "Bash(rm -rf /)" and
            replacement text that renames that list to a key the runtime does
            not read (e.g. "quarantine"), leaving the pattern's string still
            present somewhere under hard_deny
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write is REFUSED -- Configuration._pool_hard_deny_entries
            reads only hard_deny.deny/hard_deny.allow, so a pattern under any
            other key is no longer actually enforced, even though its string
            has not left the hard_deny table
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            renamed = '[hard_deny]\nquarantine = ["Bash(rm -rf /)"]\nallow = []\n'
            with self.assertRaises(ConfigWriteVerificationError) as ctx:
                verified_write_config(path, renamed, "toml", expected_patterns=expected)
            self.assertIn("Bash(rm -rf /)", ctx.exception.message)
            self.assertEqual(path.read_text(), original)

    def test_hard_deny_allow_non_list_value_does_not_crash_the_guard(self):
        """
        Given an on-disk config whose hard_deny.allow is a scalar rather than
            a list, and replacement text adding a second hard_deny.deny
            pattern while leaving hard_deny.allow as the same scalar
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS -- the malformed allow value contributes no
            carve-out patterns rather than crashing the guard
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(x)"]\nallow = 5\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            new_text = '[hard_deny]\ndeny = ["Bash(x)", "Bash(y)"]\nallow = 5\n'
            verified_write_config(path, new_text, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), new_text)

    def test_permissions_deny_non_list_value_does_not_crash_the_guard(self):
        """
        Given an on-disk config whose permissions.deny is a scalar rather
            than a list, and replacement text adding a permissions.allow
            pattern while leaving permissions.deny as the same scalar
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS -- the malformed deny value contributes no
            patterns rather than crashing the guard
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = "[permissions]\ndeny = 5\nallow = []\n"
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            new_text = '[permissions]\ndeny = 5\nallow = ["Bash(ls *)"]\n'
            verified_write_config(path, new_text, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), new_text)

    def test_broader_hard_deny_allow_carve_out_is_not_caught(self):
        """
        Given a config whose hard_deny.deny list holds
            "Bash(curl http://evil:*)", and replacement text that keeps that
            exact pattern in hard_deny.deny but adds a DIFFERENT, broader
            hard_deny.allow entry ("Bash(curl:*)") that also matches it
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS

        RECORDS AN ACCEPTED LIMITATION, not a bug: the placement check
        compares pattern STRINGS, so a same-string carve-out is caught (see
        test_pattern_kept_in_hard_deny_deny_while_also_added_to_hard_deny_allow_is_refused)
        but a broader carve-out that neutralises the same command through
        different rule syntax is not -- detecting that needs the matcher,
        which this module deliberately does not invoke.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(curl http://evil:*)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            broadened = (
                '[hard_deny]\ndeny = ["Bash(curl http://evil:*)"]\n'
                'allow = ["Bash(curl:*)"]\n'
            )
            verified_write_config(path, broadened, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), broadened)

    def test_broader_permissions_allow_for_an_ask_pattern_is_not_caught(self):
        """
        Given a config whose permissions.ask list holds "Bash(git push:*)",
            and replacement text that keeps that exact pattern in
            permissions.ask but adds a DIFFERENT, more specific
            permissions.allow entry ("Bash(git push origin:*)")
        When verified_write_config() is called with expected_patterns computed
            from the original file
        Then the write SUCCEEDS

        RECORDS AN ACCEPTED LIMITATION, the same class as the hard_deny one
        above: the ask pattern's string never left permissions.ask, so the
        placement check sees no downgrade, even though the more specific
        allow entry shadows it at match time for the commands it covers.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[permissions]\nask = ["Bash(git push:*)"]\nallow = []\n'
            path.write_text(original)

            expected = patterns_in_config_text(original, "toml")

            narrowed = (
                '[permissions]\nask = ["Bash(git push:*)"]\n'
                'allow = ["Bash(git push origin:*)"]\n'
            )
            verified_write_config(path, narrowed, "toml", expected_patterns=expected)
            self.assertEqual(path.read_text(), narrowed)

    def test_expected_patterns_none_skips_placement_checks_even_over_a_parseable_original(
        self,
    ):
        """
        Given an on-disk config whose hard_deny.deny list holds
            "Bash(rm -rf /)" -- valid, parseable TOML
        When verified_write_config() is called with replacement text that
            drops hard_deny.deny entirely and expected_patterns=None
        Then the write SUCCEEDS -- expected_patterns=None opts out of BOTH
            the content-loss check and the placement checks, not just the
            former; a parseable, existing original does not put the
            placement checks back on their own

        tools/installer.py's cmd_write_config relies on exactly this: it
        always writes a fresh, rule-free file, even over an existing one
        under --force, and takes its own backup before doing so rather than
        asking this guard to preserve the old rule set.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            original = '[hard_deny]\ndeny = ["Bash(rm -rf /)"]\nallow = []\n'
            path.write_text(original)

            dropped = "[hard_deny]\ndeny = []\nallow = []\n"
            verified_write_config(path, dropped, "toml", expected_patterns=None)
            self.assertEqual(path.read_text(), dropped)

    def test_write_over_unparseable_original_skips_placement_checks(self):
        """
        Given an on-disk config file that is not valid TOML
        When verified_write_config() is called with valid replacement text
            that moves a pattern from permissions.deny to permissions.allow,
            and expected_patterns that happens to include that pattern
        Then the write SUCCEEDS -- an original the guard cannot parse cannot
            be compared against, so a broken file must stay writable rather
            than becoming permanently stuck
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_text("[permissions\ndeny = [\n")

            new_text = '[permissions]\nallow = ["Bash(rm -rf /)"]\n'
            verified_write_config(
                path, new_text, "toml", expected_patterns=["Bash(rm -rf /)"]
            )
            self.assertEqual(path.read_text(), new_text)

    def test_write_over_non_utf8_original_skips_placement_checks(self):
        """
        Given an on-disk config file whose bytes are not valid UTF-8
        When verified_write_config() is called with valid replacement text
            that moves a pattern from permissions.deny to permissions.allow,
            and expected_patterns that happens to include that pattern
        Then the write SUCCEEDS rather than raising UnicodeDecodeError -- a
            non-UTF-8 original is exactly as broken as an unparseable one and
            must stay writable for the same reason
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_bytes(b"\xff\xfe not valid utf-8")

            new_text = '[permissions]\nallow = ["Bash(rm -rf /)"]\n'
            verified_write_config(
                path, new_text, "toml", expected_patterns=["Bash(rm -rf /)"]
            )
            self.assertEqual(path.read_text(), new_text)

    def test_expected_pattern_no_text_can_contain_blocks_every_write(self):
        """
        Given an expected_patterns member that no parsed config text can ever
            produce -- the repr() stand-in rule_entry synthesizes for a
            structured entry with no usable "match" key
        When verified_write_config() is called with otherwise-valid text that
            preserves every real pattern
        Then the write is refused, and refused again for any replacement text,
            so the file can never be written while that caller keeps computing
            expected_patterns the same way

        RECORDS CURRENT BEHAVIOUR, not a specification, and characterises the
        failure mode rule_entry.real_patterns() exists to prevent
        (rule_entry.py's PATTERN_KEY notes): the guard has no notion of an
        unsatisfiable expectation, so a caller-side mistake becomes a permanent
        write block rather than a one-off refusal. Left as-is because the
        refusal is fail-closed and whether the guard should validate
        expected_patterns' shape is undecided.
        """
        synthesized = "{'additionalContext': 'x'}"
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_text('[permissions]\nallow = ["Bash(ls *)"]\n')

            for text in (
                '[permissions]\nallow = ["Bash(ls *)"]\n',
                '[permissions]\nallow = ["Bash(ls *)", "Bash(git status)"]\n',
            ):
                with self.subTest(text=text):
                    with self.assertRaises(ConfigWriteVerificationError) as ctx:
                        verified_write_config(
                            path,
                            text,
                            "toml",
                            expected_patterns=["Bash(ls *)", synthesized],
                        )
                    self.assertIn(synthesized, ctx.exception.message)
            self.assertEqual(
                path.read_text(), '[permissions]\nallow = ["Bash(ls *)"]\n'
            )


class TestVerifiedWriteConfigAtomicity(unittest.TestCase):
    """
    The write is atomic -- observed at the rename, not inferred from a read-back.

    A test that writes and then reads the file cannot tell an atomic write from
    a truncate in place: both end with the right bytes on disk. These tests
    watch os.replace and os.fsync instead, so the invariant that actually
    matters -- the destination holds its old content until one atomic rename
    swaps in a fully-written, flushed file -- is the thing asserted.
    """

    def test_valid_write_succeeds_and_no_temp_file_survives(self):
        """
        Given a valid write with no expected_patterns
        When verified_write_config() is called
        Then the destination file contains the new text and no stray
            temporary file is left behind in the same directory
        """
        with TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            path = directory / "toolguard_hook.toml"
            new_text = '[permissions]\nallow = ["Bash(ls:*)"]\n'

            verified_write_config(path, new_text, "toml")

            self.assertEqual(path.read_text(), new_text)
            remaining = {p.name for p in directory.iterdir()}
            self.assertEqual(remaining, {"toolguard_hook.toml"})

    def test_destination_is_intact_until_one_rename_from_a_sibling_temp_file(self):
        """
        Given an existing config file with known bytes on disk
        When verified_write_config() writes new valid content
        Then exactly one os.replace() happens; its source is a temp file in the
            destination's OWN directory and is not the destination itself; the
            destination still holds its original bytes at the moment the rename
            fires; and afterwards it holds the requested bytes exactly
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.json"
            original = b'{"permissions": {"allow": []}}'
            path.write_bytes(original)
            new_text = json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}})

            renames = []
            real_replace = os.replace

            def spy(src, dst, *args, **kwargs):
                renames.append((Path(src), Path(dst), Path(dst).read_bytes()))
                return real_replace(src, dst, *args, **kwargs)

            with patch("toolguard.config_write_guard.os.replace", spy):
                verified_write_config(path, new_text, "json")

            self.assertEqual(len(renames), 1)
            src, dst, dest_bytes_at_rename = renames[0]
            self.assertEqual(dst, path)
            self.assertNotEqual(src, dst)
            self.assertEqual(src.parent, path.parent)
            self.assertEqual(dest_bytes_at_rename, original)
            self.assertEqual(path.read_bytes(), new_text.encode("utf-8"))

    def test_new_content_is_fsynced_before_the_rename(self):
        """
        Given a valid write
        When verified_write_config() is called
        Then os.fsync() is called at least once and the LAST fsync happens
            before the os.replace() that publishes the file -- a rename that
            beats the flush can publish a file the OS has not yet written
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_text("[permissions]\nallow = []\n")

            events = []
            real_fsync, real_replace = os.fsync, os.replace

            def fsync_spy(fd):
                events.append("fsync")
                return real_fsync(fd)

            def replace_spy(src, dst, *args, **kwargs):
                events.append("replace")
                return real_replace(src, dst, *args, **kwargs)

            with (
                patch("toolguard.config_write_guard.os.fsync", fsync_spy),
                patch("toolguard.config_write_guard.os.replace", replace_spy),
            ):
                verified_write_config(
                    path, '[permissions]\nallow = ["Bash(ls:*)"]\n', "toml"
                )

            self.assertIn("fsync", events)
            self.assertEqual(events[-1], "replace")

    def test_temp_file_is_cleaned_up_and_destination_untouched_on_rename_failure(self):
        """
        Given os.replace() raising during the final rename step of an
            otherwise-valid write
        When verified_write_config() is called
        Then the underlying OSError propagates, the destination still holds its
            ORIGINAL content, and the temporary file the atomic-write step had
            created is removed -- no stray file left beside it
        """
        with TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            path = directory / "toolguard_hook.toml"
            original = "[permissions]\nallow = []\n"
            path.write_text(original)

            with patch(
                "toolguard.config_write_guard.os.replace",
                side_effect=OSError("boom"),
            ):
                with self.assertRaises(OSError):
                    verified_write_config(
                        path, '[permissions]\nallow = ["x"]\n', "toml"
                    )

            self.assertEqual(path.read_text(), original)
            remaining = {p.name for p in directory.iterdir()}
            self.assertEqual(remaining, {"toolguard_hook.toml"})

    def test_write_replaces_the_destination_mode_with_0600(self):
        """
        Given an existing config file whose mode is 0644
        When verified_write_config() rewrites it
        Then the file's mode is 0600 afterwards -- the temp file's mkstemp mode
            replaces the destination's, it is not copied across

        PINS SHIPPED BEHAVIOUR, and the behaviour is a side effect of using
        mkstemp rather than a reviewed decision: the rename carries the temp
        file's ownership and permissions onto the destination. Recorded because
        it is invisible to git (which tracks only the executable bit) and so
        would otherwise change silently. Not a claim that 0600 is wrong.
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            path.write_text("[permissions]\nallow = []\n")
            os.chmod(path, 0o644)

            verified_write_config(path, '[permissions]\nallow = ["a"]\n', "toml")

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class TestVerifiedWriteConfigCreatesParentDirectory(unittest.TestCase):
    """The atomic write must create a not-yet-existing destination directory."""

    def test_write_creates_missing_parent_directory(self):
        """
        Given a destination path whose parent directory does not exist yet
        When verified_write_config() is called
        Then the parent directory is created and the file is written inside it
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "not-yet-created" / "toolguard_hook.toml"
            text = '[permissions]\nallow = ["Bash(ls:*)"]\n'

            verified_write_config(path, text, "toml")

            self.assertEqual(path.read_text(), text)


class TestPatternsInConfigText(unittest.TestCase):
    """:func:`patterns_in_config_text`, the helper that computes ``expected_patterns``."""

    def test_collects_permissions_and_hard_deny_patterns(self):
        """
        Given TOML text with patterns under permissions.allow/deny/ask and
            hard_deny.deny/hard_deny.allow
        When patterns_in_config_text() is called
        Then every pattern from all five lists is present in the returned set
        """
        text = (
            "[permissions]\n"
            'allow = ["Bash(ls:*)"]\n'
            'deny = ["Bash(rm:*)"]\n'
            'ask = ["Bash(git push:*)"]\n'
            "[hard_deny]\n"
            'deny = ["Read(**/.env)"]\n'
            'allow = ["Read(**/.env.example)"]\n'
        )

        patterns = patterns_in_config_text(text, "toml")

        self.assertEqual(
            patterns,
            {
                "Bash(ls:*)",
                "Bash(rm:*)",
                "Bash(git push:*)",
                "Read(**/.env)",
                "Read(**/.env.example)",
            },
        )

    def test_hard_deny_list_under_an_unrecognised_key_is_collected(self):
        """
        Given a hard_deny table holding a list under a key that is neither
            "deny" nor "allow", alongside a non-list value
        When patterns_in_config_text() is called
        Then the unrecognised list's patterns are collected anyway and the
            non-list value is ignored

        hard_deny is scanned generically by key so a future hard_deny list is
        covered without a change to the guard; nothing pinned that until now,
        so hardcoding the two known keys was a silent no-op.
        """
        text = (
            "[hard_deny]\n"
            "enabled = true\n"
            'deny = ["Bash(rm:*)"]\n'
            'ask = ["Bash(curl:*)"]\n'
        )

        self.assertEqual(
            patterns_in_config_text(text, "toml"), {"Bash(rm:*)", "Bash(curl:*)"}
        )

    def test_json_text_is_scanned_the_same_way_as_toml(self):
        """
        Given the same config expressed as JSON, with plain and structured
            entries under permissions and hard_deny
        When patterns_in_config_text() is called with file_format="json"
        Then it returns the same pattern set the TOML form would
        """
        text = json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(ls:*)", {"match": "Bash(git status)"}],
                    "ask": ["Bash(git push:*)"],
                },
                "hard_deny": {"deny": ["Read(**/.env)"]},
            }
        )

        self.assertEqual(
            patterns_in_config_text(text, "json"),
            {
                "Bash(ls:*)",
                "Bash(git status)",
                "Bash(git push:*)",
                "Read(**/.env)",
            },
        )

    def test_null_valued_permission_list_is_treated_as_empty(self):
        """
        Given JSON whose permissions.allow is null rather than a list
        When patterns_in_config_text() is called
        Then the remaining lists are still collected and the null one
            contributes nothing, rather than raising
        """
        text = json.dumps({"permissions": {"allow": None, "deny": ["Bash(rm:*)"]}})

        self.assertEqual(patterns_in_config_text(text, "json"), {"Bash(rm:*)"})

    def test_text_parsing_to_a_non_object_yields_empty_set(self):
        """
        Given JSON text that parses to a list rather than an object
        When patterns_in_config_text() is called
        Then it returns an empty set rather than raising
        """
        self.assertEqual(patterns_in_config_text('["Bash(ls:*)"]', "json"), set())

    def test_structured_entry_without_a_match_key_contributes_no_pattern(self):
        """
        Given entries that are structured tables with no usable "match" -- one
            missing the key entirely, one whose "match" is not a string
        When patterns_in_config_text() is called
        Then only the well-formed entries' patterns are returned, and no
            stand-in string is invented for the malformed ones

        A stand-in here would reach a caller's expected_patterns and, since no
        parsed text can ever reproduce it, block every future write of the file
        (see test_expected_pattern_no_text_can_contain_blocks_every_write).
        """
        text = json.dumps(
            {
                "permissions": {
                    "allow": [
                        "Bash(ls:*)",
                        {"additionalContext": "no match key"},
                        {"match": 42},
                        123,
                    ]
                }
            }
        )

        self.assertEqual(patterns_in_config_text(text, "json"), {"Bash(ls:*)"})

    def test_empty_config_yields_empty_set(self):
        """
        Given TOML text with neither a permissions nor a hard_deny table
        When patterns_in_config_text() is called
        Then it returns an empty set rather than raising
        """
        self.assertEqual(
            patterns_in_config_text("governed_tools = []\n", "toml"), set()
        )

    def test_invalid_text_propagates_parse_error(self):
        """
        Given text that is not valid TOML, and text that is not valid JSON
        When patterns_in_config_text() is called
        Then the underlying parser's own decode error propagates unwrapped --
            this helper does not convert failures into an empty set
        """
        with self.assertRaises(tomllib.TOMLDecodeError):
            patterns_in_config_text("[permissions\n", "toml")
        with self.assertRaises(json.JSONDecodeError):
            patterns_in_config_text("{not valid json", "json")


class TestHardDenyListTypeConstantsMatchRuntime(unittest.TestCase):
    """
    Pins _HARD_DENY_RESTRICTING_LIST_TYPES / _ALLOW_LIST_TYPES against the
    literal keys Configuration._pool_hard_deny_entries actually reads --
    nothing else in the codebase catches the two drifting independently.
    """

    def test_restricting_and_allow_list_types_match_configuration_pooling(self):
        """
        Given a hard_deny table whose sub-lists are named exactly the values
            in _HARD_DENY_RESTRICTING_LIST_TYPES and _ALLOW_LIST_TYPES
        When Configuration.hard_deny() pools that table
        Then the restricting sub-list's pattern lands in the pooled DENY
            tuple and the allow sub-list's pattern lands in the pooled
            ALLOW tuple
        """
        (restricting_key,) = _HARD_DENY_RESTRICTING_LIST_TYPES
        (allow_key,) = _ALLOW_LIST_TYPES
        prov = Provenance("project", "toolguard_hook", "toml", Path("/fake/0.toml"), 0)
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "hard_deny": {
                        restricting_key: ["Bash(rm -rf /)"],
                        allow_key: ["Bash(rm -rf /tmp)"],
                    }
                }
            ),
        )
        config = Configuration(layers=(layer,))
        deny, allow = config.hard_deny("Bash")
        self.assertIn("rm -rf /", deny)
        self.assertIn("rm -rf /tmp", allow)


if __name__ == "__main__":
    unittest.main()
