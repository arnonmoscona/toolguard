"""
Unit tests for extended pattern matching in toolguard.

Tests GLOB globstar support and NATIVE pattern matching.
"""

import unittest
from toolguard.patterns import PatternType, parse_pattern, match_pattern


class TestParsePattern(unittest.TestCase):
    """Test pattern parsing and type detection."""

    def test_parse_regex_pattern(self):
        """
        Given a pattern string prefixed with [regex]
        When parse_pattern parses it
        Then the type is REGEX and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern("[regex]^git .*")
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, "^git .*")

    def test_parse_glob_pattern(self):
        """
        Given a pattern string prefixed with [glob]
        When parse_pattern parses it
        Then the type is GLOB and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern("[glob]/tmp/**/*.txt")
        self.assertEqual(pattern_type, PatternType.GLOB)
        self.assertEqual(pattern, "/tmp/**/*.txt")

    def test_parse_native_pattern(self):
        """
        Given a pattern string prefixed with [native]
        When parse_pattern parses it
        Then the type is NATIVE and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern("[native]git * main")
        self.assertEqual(pattern_type, PatternType.NATIVE)
        self.assertEqual(pattern, "git * main")

    def test_parse_default_pattern(self):
        """
        Given a pattern string with no type prefix
        When parse_pattern parses it
        Then the type is DEFAULT and the pattern is returned unchanged
        """
        pattern_type, pattern = parse_pattern("git *")
        self.assertEqual(pattern_type, PatternType.DEFAULT)
        self.assertEqual(pattern, "git *")

    def test_parse_with_whitespace(self):
        """
        Given a [native] pattern with leading and trailing whitespace
        When parse_pattern parses it
        Then the type is NATIVE and surrounding whitespace is stripped
        """
        pattern_type, pattern = parse_pattern("  [native]npm *  ")
        self.assertEqual(pattern_type, PatternType.NATIVE)
        self.assertEqual(pattern, "npm *")


class TestGlobGlobstar(unittest.TestCase):
    """Test GLOB pattern globstar support (** vs *)."""

    def test_single_star_no_recursion(self):
        """
        Given a GLOB pattern using a single * between path segments
        When matched against a command path spanning multiple directory levels
        Then it does not match, because * covers only one level
        """
        # Pattern with single * should NOT match multiple directory levels
        self.assertFalse(
            match_pattern(
                PatternType.GLOB, "~/projects/*/*.py", "~/projects/a/b/c/file.py"
            )
        )

    def test_double_star_recursion(self):
        """
        Given a GLOB pattern using ** between path segments
        When matched against a command path spanning multiple directory levels
        Then it matches, because ** recurses across levels
        """
        # Pattern with ** should match multiple directory levels
        self.assertTrue(
            match_pattern(
                PatternType.GLOB, "~/projects/**/*.py", "~/projects/a/b/c/file.py"
            )
        )

    def test_single_star_single_level_match(self):
        """
        Given a GLOB pattern with a single * file wildcard at one directory level
        When matched against a same-level path and against a deeper path
        Then the same-level path matches and the deeper path does not
        """
        self.assertTrue(match_pattern(PatternType.GLOB, "/tmp/*.txt", "/tmp/file.txt"))
        self.assertFalse(
            match_pattern(PatternType.GLOB, "/tmp/*.txt", "/tmp/a/file.txt")
        )

    def test_double_star_all_levels_match(self):
        """
        Given a GLOB pattern with ** before a file wildcard
        When matched against paths at zero, one, and two directory levels deep
        Then all of them match
        """
        self.assertTrue(
            match_pattern(PatternType.GLOB, "/tmp/**/*.txt", "/tmp/file.txt")
        )
        self.assertTrue(
            match_pattern(PatternType.GLOB, "/tmp/**/*.txt", "/tmp/a/file.txt")
        )
        self.assertTrue(
            match_pattern(PatternType.GLOB, "/tmp/**/*.txt", "/tmp/a/b/file.txt")
        )

    def test_glob_exact_match(self):
        """
        Given a GLOB pattern with no wildcards
        When matched against an identical command and a different command
        Then the identical command matches and the different one does not
        """
        self.assertTrue(match_pattern(PatternType.GLOB, "cat file.txt", "cat file.txt"))
        self.assertFalse(
            match_pattern(PatternType.GLOB, "cat file.txt", "cat other.txt")
        )

    def test_glob_with_tilde_expansion(self):
        """
        Given a GLOB pattern starting with ~ and a command using the expanded home path
        When match_pattern compares them
        Then the ~ is expanded to the home directory and the path matches
        """
        import os

        home = os.path.expanduser("~")
        pattern = "~/test/*.txt"
        command = f"{home}/test/file.txt"
        self.assertTrue(match_pattern(PatternType.GLOB, pattern, command))

    def test_glob_wildcard_in_command(self):
        """
        Given GLOB patterns whose wildcard covers the filename part of a command
        When matched against commands with arbitrary filenames
        Then the wildcard matches both extensioned and extensionless filenames
        """
        self.assertTrue(
            match_pattern(PatternType.GLOB, "cat /tmp/*.txt", "cat /tmp/anything.txt")
        )
        self.assertTrue(
            match_pattern(
                PatternType.GLOB, "cat /tmp/*", "cat /tmp/file_without_extension"
            )
        )

    def test_glob_multiple_components(self):
        """
        Given a GLOB pattern with a single * for one intermediate path component
        When matched against a path with one level there versus two levels
        Then the single-level path matches and the two-level path does not
        """
        # Single star - should match only one level per star
        self.assertTrue(
            match_pattern(PatternType.GLOB, "/a/*/c/*.txt", "/a/b/c/file.txt")
        )
        self.assertFalse(
            match_pattern(PatternType.GLOB, "/a/*/c/*.txt", "/a/b1/b2/c/file.txt")
        )

    def test_glob_double_star_middle(self):
        """
        Given a GLOB pattern with ** between fixed path components (e.g. /projects/**/src/*.py)
        When matched against paths with varying depth between the components
        Then matching paths with the required trailing component match and others do not
        """
        self.assertTrue(
            match_pattern(
                PatternType.GLOB, "/projects/**/src/*.py", "/projects/myapp/src/main.py"
            )
        )
        self.assertTrue(
            match_pattern(
                PatternType.GLOB,
                "/projects/**/src/*.py",
                "/projects/a/b/c/src/main.py",
            )
        )
        self.assertFalse(
            match_pattern(
                PatternType.GLOB,
                "/projects/**/src/*.py",
                "/projects/myapp/lib/main.py",
            )
        )


class TestNativePattern(unittest.TestCase):
    """Test NATIVE pattern matching (word-level wildcards)."""

    def test_native_middle_wildcard(self):
        """
        Given a NATIVE pattern with * between two fixed words (e.g. 'git * main')
        When matched against commands ending in the trailing word
        Then commands with the bracketing words match and those ending differently do not
        """
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * main", "git checkout main")
        )
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * main", "git merge main")
        )
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * main", "git pull origin main")
        )
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "git * main", "git checkout develop")
        )

    def test_native_leading_wildcard(self):
        """
        Given a NATIVE pattern starting with * followed by a word (e.g. '* install')
        When matched against various commands ending in that word
        Then commands ending with the word match and ones with a different word do not
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "* install", "npm install"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "* install", "pip install"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "* install", "yarn install"))
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "* install", "npm uninstall")
        )

    def test_native_trailing_wildcard(self):
        """
        Given a NATIVE pattern ending with * after a word (e.g. 'npm *')
        When matched against commands starting with that word
        Then commands beginning with the word match and ones with a different word do not
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "npm *", "npm install"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "npm *", "npm run build"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "npm *", "npm test"))
        self.assertFalse(match_pattern(PatternType.NATIVE, "npm *", "yarn install"))

    def test_native_multiple_wildcards(self):
        """
        Given a NATIVE pattern with two * separating words (e.g. 'git * * main')
        When matched against commands with two intervening words versus fewer
        Then commands supplying both wildcard words match and shorter commands do not
        """
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * * main", "git push origin main")
        )
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * * main", "git pull upstream main")
        )
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "git * * main", "git checkout main")
        )

    def test_native_exact_match(self):
        """
        Given a NATIVE pattern with no wildcards
        When matched against an identical command and against longer or prefixed commands
        Then only the exact command matches
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "exact match", "exact match"))
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "exact match", "exact matches")
        )
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "exact match", "not exact match")
        )

    def test_native_all_wildcard(self):
        """
        Given a NATIVE pattern consisting solely of *
        When matched against any command
        Then it matches every command, including multi-word ones
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "*", "anything"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "*", "multiple words here"))

    def test_native_surrounding_wildcards(self):
        """
        Given a NATIVE pattern with * on both sides of a word (e.g. '* log *')
        When matched against commands containing that word in the middle
        Then commands containing the word match and ones without it do not
        """
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "* log *", "git log --oneline")
        )
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "* log *", "docker log container")
        )
        self.assertFalse(match_pattern(PatternType.NATIVE, "* log *", "git status"))

    def test_native_adjacent_wildcards(self):
        """
        Given a NATIVE pattern with adjacent ** between words (e.g. 'git ** main')
        When matched against commands with a single intervening word
        Then the adjacent wildcards behave like a single wildcard and match
        """
        # Adjacent wildcards should work like single wildcard
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git ** main", "git checkout main")
        )
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git ** main", "git merge main")
        )

    def test_native_segments_must_be_in_order(self):
        """
        Given a NATIVE pattern 'git * main'
        When matched against a command with the words in the correct order versus reversed
        Then the in-order command matches and the reversed command does not
        """
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "git * main", "git checkout main")
        )
        # "main" appears before "git" - should not match
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "git * main", "main checkout git")
        )

    def test_native_case_sensitive(self):
        """
        Given a NATIVE pattern with a capitalized word (e.g. 'Git * main')
        When matched against commands with matching versus differing case
        Then only the case-matching command matches
        """
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "Git * main", "Git checkout main")
        )
        self.assertFalse(
            match_pattern(PatternType.NATIVE, "Git * main", "git checkout main")
        )

    def test_native_partial_segment_match(self):
        """
        Given NATIVE patterns where a literal segment may sit inside or beside a word
        When matched against commands, including patterns with and without surrounding spaces
        Then a segment without a space can match within a word, while a spaced segment
        requires a matching space in the command
        """
        # This should match because "log" is found in the command
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "* log *", "git log --oneline")
        )
        # This should match - "log" segment with space matches " log" in command
        self.assertTrue(match_pattern(PatternType.NATIVE, "cat *log", "cat app.log"))
        # With space in pattern, it requires space in command
        self.assertFalse(match_pattern(PatternType.NATIVE, "cat * log", "cat app.log"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "cat * log", "cat error log"))

    def test_native_empty_pattern(self):
        """
        Given an empty NATIVE pattern
        When matched against an empty command and a non-empty command
        Then it matches only the empty command
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "", ""))
        self.assertFalse(match_pattern(PatternType.NATIVE, "", "something"))

    def test_native_only_wildcards(self):
        """
        Given NATIVE patterns consisting only of multiple wildcards (** or ***)
        When matched against any command
        Then they match every command
        """
        self.assertTrue(match_pattern(PatternType.NATIVE, "**", "any command here"))
        self.assertTrue(match_pattern(PatternType.NATIVE, "***", "any command here"))


class TestPatternTypeComparison(unittest.TestCase):
    """Test differences between pattern types on the same inputs."""

    def test_glob_vs_native_wildcard_semantics(self):
        """
        Given the same wildcard pattern interpreted as GLOB versus NATIVE
        When matched against commands containing spaces in the wildcard region
        Then GLOB's * spans spaces within a component while NATIVE finds the segments in order
        """
        # GLOB: * matches any characters including spaces within path component
        self.assertTrue(
            match_pattern(PatternType.GLOB, "cat *.txt", "cat file name.txt")
        )

        # NATIVE: * matches non-whitespace sequences
        # "cat *.txt" would try to find "cat " then ".txt" in sequence
        self.assertTrue(match_pattern(PatternType.NATIVE, "cat *.txt", "cat file.txt"))
        # This should also match because we find "cat " and then ".txt" exists
        self.assertTrue(
            match_pattern(PatternType.NATIVE, "cat *.txt", "cat file name.txt")
        )

    def test_glob_requires_full_match_native_finds_segments(self):
        """
        Given a command and patterns under both GLOB and NATIVE semantics
        When a bare-word pattern and a wildcard pattern are matched
        Then GLOB requires the pattern to span the whole command, while NATIVE with
        wildcards locates ordered segments but still requires exact match without wildcards
        """
        command = "git log --oneline"

        # GLOB: Must match entire command
        self.assertTrue(match_pattern(PatternType.GLOB, "git log *", command))
        self.assertFalse(
            match_pattern(PatternType.GLOB, "log", command)
        )  # Doesn't match full string

        # NATIVE with wildcards: Finds segments in order
        self.assertTrue(match_pattern(PatternType.NATIVE, "git * --oneline", command))
        # Without wildcards, NATIVE requires exact match
        self.assertFalse(match_pattern(PatternType.NATIVE, "log", command))


if __name__ == "__main__":
    unittest.main()
