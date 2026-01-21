"""
Unit tests for extended pattern matching in toolguard.

Tests GLOB globstar support and NATIVE pattern matching.
"""

import unittest
from toolguard.patterns import PatternType, parse_pattern, match_pattern


class TestParsePattern(unittest.TestCase):
    """Test pattern parsing and type detection."""

    def test_parse_regex_pattern(self):
        """Test parsing [regex] prefix."""
        pattern_type, pattern = parse_pattern('[regex]^git .*')
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, '^git .*')

    def test_parse_glob_pattern(self):
        """Test parsing [glob] prefix."""
        pattern_type, pattern = parse_pattern('[glob]/tmp/**/*.txt')
        self.assertEqual(pattern_type, PatternType.GLOB)
        self.assertEqual(pattern, '/tmp/**/*.txt')

    def test_parse_native_pattern(self):
        """Test parsing [native] prefix."""
        pattern_type, pattern = parse_pattern('[native]git * main')
        self.assertEqual(pattern_type, PatternType.NATIVE)
        self.assertEqual(pattern, 'git * main')

    def test_parse_default_pattern(self):
        """Test parsing pattern without prefix."""
        pattern_type, pattern = parse_pattern('git *')
        self.assertEqual(pattern_type, PatternType.DEFAULT)
        self.assertEqual(pattern, 'git *')

    def test_parse_with_whitespace(self):
        """Test parsing patterns with surrounding whitespace."""
        pattern_type, pattern = parse_pattern('  [native]npm *  ')
        self.assertEqual(pattern_type, PatternType.NATIVE)
        self.assertEqual(pattern, 'npm *')


class TestGlobGlobstar(unittest.TestCase):
    """Test GLOB pattern globstar support (** vs *)."""

    def test_single_star_no_recursion(self):
        """Test that * matches single directory level only."""
        # Pattern with single * should NOT match multiple directory levels
        self.assertFalse(match_pattern(PatternType.GLOB, '~/projects/*/*.py', '~/projects/a/b/c/file.py'))

    def test_double_star_recursion(self):
        """Test that ** matches multiple directory levels."""
        # Pattern with ** should match multiple directory levels
        self.assertTrue(match_pattern(PatternType.GLOB, '~/projects/**/*.py', '~/projects/a/b/c/file.py'))

    def test_single_star_single_level_match(self):
        """Test that * matches at single level."""
        self.assertTrue(match_pattern(PatternType.GLOB, '/tmp/*.txt', '/tmp/file.txt'))
        self.assertFalse(match_pattern(PatternType.GLOB, '/tmp/*.txt', '/tmp/a/file.txt'))

    def test_double_star_all_levels_match(self):
        """Test that ** matches at all levels."""
        self.assertTrue(match_pattern(PatternType.GLOB, '/tmp/**/*.txt', '/tmp/file.txt'))
        self.assertTrue(match_pattern(PatternType.GLOB, '/tmp/**/*.txt', '/tmp/a/file.txt'))
        self.assertTrue(match_pattern(PatternType.GLOB, '/tmp/**/*.txt', '/tmp/a/b/file.txt'))

    def test_glob_exact_match(self):
        """Test GLOB pattern exact matching."""
        self.assertTrue(match_pattern(PatternType.GLOB, 'cat file.txt', 'cat file.txt'))
        self.assertFalse(match_pattern(PatternType.GLOB, 'cat file.txt', 'cat other.txt'))

    def test_glob_with_tilde_expansion(self):
        """Test that ~ is expanded in GLOB patterns."""
        import os

        home = os.path.expanduser('~')
        pattern = '~/test/*.txt'
        command = f'{home}/test/file.txt'
        self.assertTrue(match_pattern(PatternType.GLOB, pattern, command))

    def test_glob_wildcard_in_command(self):
        """Test GLOB pattern with wildcards in command part."""
        self.assertTrue(match_pattern(PatternType.GLOB, 'cat /tmp/*.txt', 'cat /tmp/anything.txt'))
        self.assertTrue(match_pattern(PatternType.GLOB, 'cat /tmp/*', 'cat /tmp/file_without_extension'))

    def test_glob_multiple_components(self):
        """Test GLOB with multiple path components."""
        # Single star - should match only one level per star
        self.assertTrue(match_pattern(PatternType.GLOB, '/a/*/c/*.txt', '/a/b/c/file.txt'))
        self.assertFalse(match_pattern(PatternType.GLOB, '/a/*/c/*.txt', '/a/b1/b2/c/file.txt'))

    def test_glob_double_star_middle(self):
        """Test ** in the middle of a pattern."""
        self.assertTrue(match_pattern(PatternType.GLOB, '/projects/**/src/*.py', '/projects/myapp/src/main.py'))
        self.assertTrue(
            match_pattern(
                PatternType.GLOB,
                '/projects/**/src/*.py',
                '/projects/a/b/c/src/main.py',
            )
        )
        self.assertFalse(
            match_pattern(
                PatternType.GLOB,
                '/projects/**/src/*.py',
                '/projects/myapp/lib/main.py',
            )
        )


class TestNativePattern(unittest.TestCase):
    """Test NATIVE pattern matching (word-level wildcards)."""

    def test_native_middle_wildcard(self):
        """Test * in the middle of pattern."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * main', 'git checkout main'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * main', 'git merge main'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * main', 'git pull origin main'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'git * main', 'git checkout develop'))

    def test_native_leading_wildcard(self):
        """Test * at the beginning of pattern."""
        self.assertTrue(match_pattern(PatternType.NATIVE, '* install', 'npm install'))
        self.assertTrue(match_pattern(PatternType.NATIVE, '* install', 'pip install'))
        self.assertTrue(match_pattern(PatternType.NATIVE, '* install', 'yarn install'))
        self.assertFalse(match_pattern(PatternType.NATIVE, '* install', 'npm uninstall'))

    def test_native_trailing_wildcard(self):
        """Test * at the end of pattern."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'npm *', 'npm install'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'npm *', 'npm run build'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'npm *', 'npm test'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'npm *', 'yarn install'))

    def test_native_multiple_wildcards(self):
        """Test multiple * in pattern."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * * main', 'git push origin main'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * * main', 'git pull upstream main'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'git * * main', 'git checkout main'))

    def test_native_exact_match(self):
        """Test pattern without wildcards (exact match)."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'exact match', 'exact match'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'exact match', 'exact matches'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'exact match', 'not exact match'))

    def test_native_all_wildcard(self):
        """Test pattern that is just *."""
        self.assertTrue(match_pattern(PatternType.NATIVE, '*', 'anything'))
        self.assertTrue(match_pattern(PatternType.NATIVE, '*', 'multiple words here'))

    def test_native_surrounding_wildcards(self):
        """Test * at both beginning and end."""
        self.assertTrue(match_pattern(PatternType.NATIVE, '* log *', 'git log --oneline'))
        self.assertTrue(match_pattern(PatternType.NATIVE, '* log *', 'docker log container'))
        self.assertFalse(match_pattern(PatternType.NATIVE, '* log *', 'git status'))

    def test_native_adjacent_wildcards(self):
        """Test adjacent ** in pattern."""
        # Adjacent wildcards should work like single wildcard
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git ** main', 'git checkout main'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git ** main', 'git merge main'))

    def test_native_segments_must_be_in_order(self):
        """Test that segments must appear in order."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * main', 'git checkout main'))
        # "main" appears before "git" - should not match
        self.assertFalse(match_pattern(PatternType.NATIVE, 'git * main', 'main checkout git'))

    def test_native_case_sensitive(self):
        """Test that matching is case-sensitive."""
        self.assertTrue(match_pattern(PatternType.NATIVE, 'Git * main', 'Git checkout main'))
        self.assertFalse(match_pattern(PatternType.NATIVE, 'Git * main', 'git checkout main'))

    def test_native_partial_segment_match(self):
        """Test that segments can match within words."""
        # This should match because "log" is found in the command
        self.assertTrue(match_pattern(PatternType.NATIVE, '* log *', 'git log --oneline'))
        # This should match - "log" segment with space matches " log" in command
        self.assertTrue(match_pattern(PatternType.NATIVE, 'cat *log', 'cat app.log'))
        # With space in pattern, it requires space in command
        self.assertFalse(match_pattern(PatternType.NATIVE, 'cat * log', 'cat app.log'))
        self.assertTrue(match_pattern(PatternType.NATIVE, 'cat * log', 'cat error log'))

    def test_native_empty_pattern(self):
        """Test empty pattern."""
        self.assertTrue(match_pattern(PatternType.NATIVE, '', ''))
        self.assertFalse(match_pattern(PatternType.NATIVE, '', 'something'))

    def test_native_only_wildcards(self):
        """Test patterns with only wildcards."""
        self.assertTrue(match_pattern(PatternType.NATIVE, '**', 'any command here'))
        self.assertTrue(match_pattern(PatternType.NATIVE, '***', 'any command here'))


class TestPatternTypeComparison(unittest.TestCase):
    """Test differences between pattern types on the same inputs."""

    def test_glob_vs_native_wildcard_semantics(self):
        """Test that GLOB and NATIVE handle * differently."""
        # GLOB: * matches any characters including spaces within path component
        self.assertTrue(match_pattern(PatternType.GLOB, 'cat *.txt', 'cat file name.txt'))

        # NATIVE: * matches non-whitespace sequences
        # "cat *.txt" would try to find "cat " then ".txt" in sequence
        self.assertTrue(match_pattern(PatternType.NATIVE, 'cat *.txt', 'cat file.txt'))
        # This should also match because we find "cat " and then ".txt" exists
        self.assertTrue(match_pattern(PatternType.NATIVE, 'cat *.txt', 'cat file name.txt'))

    def test_glob_requires_full_match_native_finds_segments(self):
        """Test that GLOB requires full command match while NATIVE finds segments."""
        command = 'git log --oneline'

        # GLOB: Must match entire command
        self.assertTrue(match_pattern(PatternType.GLOB, 'git log *', command))
        self.assertFalse(match_pattern(PatternType.GLOB, 'log', command))  # Doesn't match full string

        # NATIVE with wildcards: Finds segments in order
        self.assertTrue(match_pattern(PatternType.NATIVE, 'git * --oneline', command))
        # Without wildcards, NATIVE requires exact match
        self.assertFalse(match_pattern(PatternType.NATIVE, 'log', command))


if __name__ == '__main__':
    unittest.main()
