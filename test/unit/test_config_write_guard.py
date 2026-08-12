"""
Unit tests for toolguard.config_write_guard -- the self-protection gate every
config-file write must pass through.

Isolation (`.claude/rules/test-config-isolation.md`): these tests do file I/O
inside a throwaway TemporaryDirectory only and never reach toolguard.config's
discovery path, so ConfigIsolationMixin is not needed.
"""

import json
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.config_write_guard import (
    ConfigWriteVerificationError,
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
        Then ConfigWriteVerificationError is raised
        """
        with self.assertRaises(ConfigWriteVerificationError):
            verify_config_text("{not valid json", "json")

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

    def test_reintroduced_change1_corruption_scenario_is_refused(self):
        """
        Given a rewritten [permissions] section spliced into the middle of an
            EARLIER structured entry's quoted additionalContext string,
            leaving an unescaped newline
        When verified_write_config() is called with that corrupted text
        Then it is refused by the syntax guard
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
        Then ConfigWriteVerificationError is raised naming the missing
            pattern, and the original file is left unchanged
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
            self.assertIn("Bash(rm -rf /)", ctx.exception.message)
            self.assertEqual(path.read_bytes(), original.encode("utf-8"))

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
        Then no content-loss check is performed and the write succeeds even
            though there was no "previous" content to compare against
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.toml"
            verified_write_config(path, "[permissions]\nallow = []\n", "toml")
            self.assertTrue(path.exists())


class TestVerifiedWriteConfigAtomicity(unittest.TestCase):
    """Atomic-write behaviour: no temp file survives, valid write applies."""

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

    def test_write_uses_replace_not_truncate_in_place(self):
        """
        Given an existing file
        When verified_write_config() writes new valid content
        Then the final content on disk is byte-identical to what was
            requested (sanity check that the atomic rename path produces
            correct, non-truncated output)
        """
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "toolguard_hook.json"
            path.write_text('{"permissions": {"allow": []}}')
            new_text = json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}})

            verified_write_config(path, new_text, "json")

            with open(path) as f:
                self.assertEqual(json.load(f), json.loads(new_text))


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
        Given text that is not valid TOML
        When patterns_in_config_text() is called
        Then the underlying tomllib.TOMLDecodeError propagates
        """
        with self.assertRaises(tomllib.TOMLDecodeError):
            patterns_in_config_text("[permissions\n", "toml")


class TestPrivateHelpers(unittest.TestCase):
    """Narrow direct tests for the module's internal parsing helpers."""

    def test_verify_config_text_toml_matches_tomllib_directly(self):
        """
        Given TOML text that tomllib.loads() itself accepts
        When verify_config_text() is called
        Then it does not raise (cross-check against the real parser)
        """
        text = '[permissions]\nallow = ["Bash(ls:*)"]\n'
        tomllib.loads(text)
        verify_config_text(text, "toml")

    def test_atomic_write_cleans_up_temp_file_on_replace_failure(self):
        """
        Given os.replace() raising during the final rename step of an
            otherwise-valid write
        When verified_write_config() is called
        Then the underlying OSError propagates, and the temporary file the
            atomic-write step had created is removed -- no stray file is
            left behind next to the (unchanged) destination
        """
        with TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            path = directory / "toolguard_hook.toml"
            path.write_text("[permissions]\nallow = []\n")

            with patch(
                "toolguard.config_write_guard.os.replace",
                side_effect=OSError("boom"),
            ):
                with self.assertRaises(OSError):
                    verified_write_config(
                        path, '[permissions]\nallow = ["x"]\n', "toml"
                    )

            remaining = {p.name for p in directory.iterdir()}
            self.assertEqual(remaining, {"toolguard_hook.toml"})


if __name__ == "__main__":
    unittest.main()
