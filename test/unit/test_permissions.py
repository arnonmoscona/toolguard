"""
Unit tests for toolguard permission checking logic.

Tests the permission checking, pattern matching, and configuration loading
functionality of the toolguard pre-tool-use hook.
"""

import unittest

from toolguard.permissions import (
    normalize_path_in_command,
    contains_path_component,
    match_command,
    check_permission,
)


class TestNormalizePathInCommand(unittest.TestCase):
    """Test path normalization in commands."""

    def test_normalize_adds_prefix_to_relative_path(self):
        """
        Given a command with a bare relative path argument
        When normalize_path_in_command processes it
        Then the relative path argument gains a ./ prefix
        """
        self.assertEqual(normalize_path_in_command('cat file.txt'), 'cat ./file.txt')
        self.assertEqual(normalize_path_in_command('ls mydir'), 'ls ./mydir')

    def test_normalize_preserves_dot_paths(self):
        """
        Given a command whose path argument already starts with ./ or ../
        When normalize_path_in_command processes it
        Then the path argument is left unchanged
        """
        self.assertEqual(normalize_path_in_command('cat ./file.txt'), 'cat ./file.txt')
        self.assertEqual(normalize_path_in_command('cat ../file.txt'), 'cat ../file.txt')

    def test_normalize_preserves_absolute_paths(self):
        """
        Given a command with an absolute path argument
        When normalize_path_in_command processes it
        Then the absolute path is left unchanged
        """
        self.assertEqual(normalize_path_in_command('cat /etc/hosts'), 'cat /etc/hosts')
        self.assertEqual(normalize_path_in_command('ls /usr/bin'), 'ls /usr/bin')

    def test_normalize_preserves_flags(self):
        """
        Given a command whose arguments are flags starting with - or --
        When normalize_path_in_command processes it
        Then the flags are left unchanged (not treated as paths)
        """
        self.assertEqual(normalize_path_in_command('ls -la'), 'ls -la')
        self.assertEqual(normalize_path_in_command('git --version'), 'git --version')

    def test_normalize_preserves_tilde_paths(self):
        """
        Given a command with a ~/ home-relative path argument
        When normalize_path_in_command processes it
        Then the tilde path is left unchanged
        """
        self.assertEqual(normalize_path_in_command('cat ~/file.txt'), 'cat ~/file.txt')

    def test_normalize_command_only_unchanged(self):
        """
        Given a command with no arguments
        When normalize_path_in_command processes it
        Then the command is returned unchanged
        """
        self.assertEqual(normalize_path_in_command('git'), 'git')
        self.assertEqual(normalize_path_in_command('ls'), 'ls')


class TestContainsPathComponent(unittest.TestCase):
    """Test path component detection in commands."""

    def test_exact_match(self):
        """
        Given a command whose argument is exactly the target path component
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component('cat .env', '.env'))
        self.assertTrue(contains_path_component('vim test.py', 'test.py'))

    def test_component_after_slash(self):
        """
        Given a command where the target component appears after a slash in a path
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component('cat dir/.env', '.env'))
        self.assertTrue(contains_path_component('cat /path/to/.env', '.env'))

    def test_component_before_slash(self):
        """
        Given a command where the target component appears before a slash in a path
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component('cat .env/file', '.env'))

    def test_component_in_middle(self):
        """
        Given a command where the target component sits between slashes in a path
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component('cat dir/.env/file', '.env'))

    def test_no_match(self):
        """
        Given a command that does not contain the target path component
        When contains_path_component checks for that component
        Then it reports no match
        """
        self.assertFalse(contains_path_component('cat file.txt', '.env'))
        self.assertFalse(contains_path_component('git status', '.env'))

    def test_command_only_no_match(self):
        """
        Given a command with no arguments
        When contains_path_component checks for a component
        Then it reports no match
        """
        self.assertFalse(contains_path_component('ls', 'file'))


class TestMatchCommand(unittest.TestCase):
    """Test command pattern matching."""

    def test_simple_wildcard_match(self):
        """
        Given a pattern list with a trailing wildcard pattern (e.g. 'git *')
        When match_command checks a command with that prefix
        Then it matches and returns the matching pattern
        """
        patterns = ['git *']
        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git *')

    def test_command_args_pattern_match(self):
        """
        Given a command:args pattern (e.g. 'git log:*')
        When match_command checks a command with those args
        Then it matches and returns the pattern
        """
        patterns = ['git log:*']
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git log:*')

    def test_path_component_pattern_match(self):
        """
        Given a path-component pattern (e.g. '**/.env/**')
        When match_command checks commands referencing that component directly or nested
        Then both the direct and nested references match
        """
        patterns = ['**/.env/**']
        matched, pattern = match_command('cat .env', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '**/.env/**')

        matched, pattern = match_command('cat dir/.env/file', patterns)
        self.assertTrue(matched)

    def test_normalized_path_matching(self):
        """
        Given a pattern expecting a ./-prefixed path (e.g. 'cat ./*:*')
        When match_command checks a command with a bare relative path
        Then path normalization makes it match the pattern
        """
        patterns = ['cat ./*:*']
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'cat ./*:*')

    def test_no_match(self):
        """
        Given a pattern list none of whose entries cover the command
        When match_command checks the command
        Then it reports no match and returns None for the pattern
        """
        patterns = ['git *', 'ls *']
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_empty_patterns(self):
        """
        Given an empty pattern list
        When match_command checks any command
        Then it reports no match and returns None for the pattern
        """
        patterns = []
        matched, pattern = match_command('git status', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_double_star_normalization(self):
        """
        Given a pattern using ** (e.g. 'git **')
        When match_command checks a command with extra arguments
        Then ** is normalized to * for fnmatch and the command matches
        """
        patterns = ['git **']
        matched, pattern = match_command('git status --short', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git **')

    def test_relative_path_command_matches_dotslash_pattern(self):
        """
        Given a pattern with a ./-prefixed script path (e.g. './bin/X:*')
        When match_command checks a command using the equivalent bare path 'bin/X'
        Then they are treated as equivalent and the command matches, with or without args
        """
        patterns = ['./bin/precommit_checks.sh:*']

        matched, pattern = match_command('bin/precommit_checks.sh', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, './bin/precommit_checks.sh:*')

        matched, _ = match_command('bin/precommit_checks.sh --dry-run', patterns)
        self.assertTrue(matched)

    def test_dotslash_command_matches_relative_pattern(self):
        """
        Given a pattern with a bare relative script path (e.g. 'bin/X:*')
        When match_command checks a command using the ./-prefixed path './bin/X'
        Then they are treated as equivalent and the command matches, with or without args
        """
        patterns = ['bin/precommit_checks.sh:*']

        matched, pattern = match_command('./bin/precommit_checks.sh', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'bin/precommit_checks.sh:*')

        matched, _ = match_command('./bin/precommit_checks.sh --flag', patterns)
        self.assertTrue(matched)

    def test_relative_path_no_false_positive(self):
        """
        Given a pattern for a specific relative script path (e.g. './bin/precommit_checks.sh:*')
        When match_command checks commands with a different directory or different script
        Then normalization does not cause a false match
        """
        patterns = ['./bin/precommit_checks.sh:*']

        matched, _ = match_command('other/precommit_checks.sh', patterns)
        self.assertFalse(matched)

        matched, _ = match_command('bin/other_script.sh', patterns)
        self.assertFalse(matched)


class TestCheckPermission(unittest.TestCase):
    """Test permission checking logic."""

    def test_allow_pattern_match(self):
        """
        Given a command matching an allow pattern and no deny patterns
        When check_permission evaluates it
        Then the decision is 'allow' and the reason cites an allow pattern
        """
        allow_patterns = ['git *', 'ls *']
        deny_patterns = []
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')
        self.assertIn('allow pattern', reason.lower())

    def test_deny_pattern_match(self):
        """
        Given a command matching a deny pattern
        When check_permission evaluates it
        Then the decision is 'deny' and the reason cites a deny pattern
        """
        allow_patterns = ['git *']
        deny_patterns = ['git push:*']
        decision, reason = check_permission('git push origin', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('deny pattern', reason.lower())

    def test_deny_takes_precedence(self):
        """
        Given a command matching both an allow and a deny pattern
        When check_permission evaluates it
        Then deny wins and the decision is 'deny'
        """
        allow_patterns = ['git *']
        deny_patterns = ['git *']
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

    def test_not_in_allow_list(self):
        """
        Given a command that matches no allow pattern and no deny pattern
        When check_permission evaluates it
        Then the decision is 'deny' and the reason notes it does not match
        """
        allow_patterns = ['git *']
        deny_patterns = []
        decision, reason = check_permission('rm -rf /', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('does not match', reason.lower())

    def test_empty_allow_list(self):
        """
        Given empty allow and deny lists
        When check_permission evaluates any command
        Then the decision is 'deny' because nothing is allowed
        """
        allow_patterns = []
        deny_patterns = []
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')


class TestExtendedPatterns(unittest.TestCase):
    """Test extended pattern matching (REGEX and GLOB)."""

    def test_regex_pattern_in_allow_list(self):
        """
        Given an allow list containing a [regex] pattern with an alternation
        When match_command checks commands inside and outside the alternation
        Then matching commands match (returning the regex pattern) and others do not
        """
        patterns = ['[regex]^git (log|diff|status).*']

        # Should match
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git (log|diff|status).*')

        matched, pattern = match_command('git diff HEAD~1', patterns)
        self.assertTrue(matched)

        matched, pattern = match_command('git status --short', patterns)
        self.assertTrue(matched)

        # Should not match
        matched, pattern = match_command('git push origin', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        matched, pattern = match_command('ls -la', patterns)
        self.assertFalse(matched)

    def test_regex_pattern_in_deny_list(self):
        """
        Given an allow list of 'git *' and a deny list with a [regex] for git push
        When check_permission evaluates a push command versus a status command
        Then the push command is denied (citing the regex) and status is allowed
        """
        allow_patterns = ['git *']
        deny_patterns = ['[regex]^git push.*']

        # Should be denied by regex pattern
        decision, reason = check_permission('git push origin main', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('[regex]^git push.*', reason)

        # Should be allowed
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_glob_pattern_in_allow_list(self):
        """
        Given an allow list with a [glob] pattern matching the whole command string
        When match_command checks commands with matching and mismatching paths/extensions
        Then only commands matching the full glob match
        """
        # GLOB patterns match the entire command string, so we need to include the command
        patterns = ['[glob]cat /Users/*/projects/**/*.py']

        # Should match
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.py', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[glob]cat /Users/*/projects/**/*.py')

        # Should not match - different user path
        matched, pattern = match_command('vim /Users/bob/projects/myapp/src/app.py', patterns)
        self.assertFalse(matched)

        # Should not match - wrong path
        matched, pattern = match_command('cat /Users/arnon/documents/file.py', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        # Should not match - wrong extension
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.txt', patterns)
        self.assertFalse(matched)

    def test_glob_pattern_in_deny_list(self):
        """
        Given an allow list of 'cat *' and deny [glob] patterns targeting .env files
        When check_permission evaluates commands reading .env files versus a normal file
        Then the .env commands are denied and the normal file is allowed
        """
        allow_patterns = ['cat *']
        deny_patterns = ['[glob]cat *.env*', '[glob]cat*/**/.env*']

        # Should be denied by glob pattern - simple case
        decision, reason = check_permission('cat .env', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('.env', reason)

        # Should be denied by glob pattern - recursive path with **
        decision, reason = check_permission('cat /path/to/.env.production', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

        # Should be allowed
        decision, reason = check_permission('cat normal_file.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_mixed_pattern_types(self):
        """
        Given a pattern list mixing DEFAULT, [regex], and [glob] entries
        When match_command checks commands targeting each pattern type
        Then each command matches its corresponding pattern and an unrelated command matches none
        """
        patterns = [
            'git status:*',  # DEFAULT
            '[regex]^git (log|diff).*',  # REGEX
            '[glob]cat /Users/*/projects/**/*.py',  # GLOB
        ]

        # DEFAULT pattern should match
        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git status:*')

        # REGEX pattern should match
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git (log|diff).*')

        # GLOB pattern should match
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.py', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[glob]cat /Users/*/projects/**/*.py')

        # None should match
        matched, pattern = match_command('rm -rf /', patterns)
        self.assertFalse(matched)

    def test_invalid_regex_no_match(self):
        """
        Given an allow list with a malformed [regex] pattern
        When match_command checks a command against it
        Then it reports no match and returns None instead of raising
        """
        patterns = ['[regex]^git (unclosed']  # Invalid regex - unclosed parenthesis

        # Should not match (invalid regex returns False)
        matched, pattern = match_command('git anything', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_regex_bypasses_normalization(self):
        """
        Given [regex] patterns that anchor on the literal command (with or without ./)
        When match_command checks commands with and without a ./ prefix
        Then matching is literal with no path normalization applied
        """
        # Pattern that matches exactly "cat file.txt"
        patterns = ['[regex]^cat file\\.txt$']

        # SHOULD match - regex matches the literal command string
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match with ./ prefix
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertFalse(matched)

        # Pattern that explicitly requires ./ prefix
        patterns = ['[regex]^cat \\./file\\.txt$']
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match without the ./ prefix
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertFalse(matched)

    def test_regex_ignores_colon_syntax(self):
        """
        Given a [regex] pattern containing a literal colon (e.g. '^git log:.*')
        When match_command checks commands with and without that colon
        Then the colon is treated as part of the regex, not a command:args separator
        """
        # Colon in regex is part of the pattern, not a separator
        patterns = ['[regex]^git log:.*']

        # Should match "git log:" literally
        matched, pattern = match_command('git log:something', patterns)
        self.assertTrue(matched)

        # Should NOT match "git log" without colon
        matched, pattern = match_command('git log something', patterns)
        self.assertFalse(matched)

    def test_glob_bypasses_normalization(self):
        """
        Given a [glob] pattern for a literal command (e.g. 'cat file.txt')
        When match_command checks the command with and without a ./ prefix
        Then matching is literal and the ./-prefixed command does not match
        """
        patterns = ['[glob]cat file.txt']

        # Should match exactly
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match with ./ prefix (glob is literal)
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertFalse(matched)

    def test_glob_ignores_colon_syntax(self):
        """
        Given a [glob] pattern containing a literal colon (e.g. 'git log:*')
        When match_command checks a command with that colon versus a spaced command
        Then the colon is matched literally, so only the colon form matches
        """
        patterns = ['[glob]git log:*']

        # Should match "git log:" literally with glob wildcard
        matched, pattern = match_command('git log:something', patterns)
        self.assertTrue(matched)

        # Should NOT match "git log " (space instead of colon)
        matched, pattern = match_command('git log something', patterns)
        self.assertFalse(matched)

    def test_first_match_wins(self):
        """
        Given a pattern list where two patterns of different types both match a command
        When match_command evaluates them in order
        Then the first matching pattern in the list is the one returned
        """
        patterns = [
            '[regex]^git .*',  # This should match first
            'git status:*',  # This would also match but comes second
        ]

        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git .*')  # First pattern wins

    def test_env_special_handling_only_for_default(self):
        """
        Given the same 'cat .env' command checked against DEFAULT, [regex], and [glob] patterns
        When match_command evaluates each
        Then the **/.env/** path-component special handling applies only to DEFAULT patterns,
        while regex and glob must match the full command literally
        """
        # DEFAULT pattern with special handling
        default_patterns = ['**/.env/**']
        matched, pattern = match_command('cat .env', default_patterns)
        self.assertTrue(matched)  # Special handling applies

        # REGEX pattern - no special handling (must match full command literally)
        regex_patterns = ['[regex].*\\.env.*']
        matched, pattern = match_command('cat .env', regex_patterns)
        self.assertTrue(matched)  # Regex matches, but no path component special handling

        # GLOB pattern - no special handling, must match the full command string
        glob_patterns = ['[glob]cat .env']
        matched, pattern = match_command('cat .env', glob_patterns)
        self.assertTrue(matched)  # Exact glob match

        # GLOB with wildcard
        glob_patterns = ['[glob]* .env']
        matched, pattern = match_command('cat .env', glob_patterns)
        self.assertTrue(matched)  # Glob wildcard matches

    def test_native_pattern_uses_native_semantics(self):
        """
        Given an allow list with a [native] pattern (e.g. '[native]git * main')
        When match_command checks commands ending in the trailing word versus not
        Then word-level NATIVE segment matching is used: matching commands match and others do not
        """
        patterns = ['[native]git * main']

        matched, pattern = match_command('git checkout main', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[native]git * main')

        matched, pattern = match_command('git merge main', patterns)
        self.assertTrue(matched)

        # "git * main" should NOT match commands where 'main' is not the final token
        # position in an expected-order-sequence way via NATIVE semantics
        matched, pattern = match_command('git checkout develop', patterns)
        self.assertFalse(matched)

    def test_native_pattern_in_deny_list(self):
        """
        Given an allow list of 'git *' and a deny list with '[native]git push *'
        When check_permission evaluates a git push command versus git status
        Then the push command is denied (citing the native pattern) and status is allowed
        """
        allow_patterns = ['git *']
        deny_patterns = ['[native]git push *']

        decision, reason = check_permission('git push origin main', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('[native]git push *', reason)

        # git status is allowed because only "git push *" is denied
        decision, _ = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')


if __name__ == '__main__':
    unittest.main()
