"""Unit tests for toolguard permission checking logic."""

import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import ambient
from toolguard.permissions import (
    normalize_path_in_command,
    contains_path_component,
    match_command,
    check_permission,
    _command_variants,
)


def _passwd_lookup(directory):
    """A pwd.getpwnam replacement resolving only the names *directory* maps to a home."""

    def getpwnam(name):
        if name in directory:
            return SimpleNamespace(pw_dir=directory[name])
        raise KeyError(f"getpwnam(): name not found: {name!r}")

    return getpwnam


class TestNormalizePathInCommand(unittest.TestCase):
    """Test path normalization in commands."""

    def test_normalize_adds_prefix_to_relative_path(self):
        """
        Given a command with a bare relative path argument
        When normalize_path_in_command processes it
        Then the relative path argument gains a ./ prefix
        """
        self.assertEqual(normalize_path_in_command("cat file.txt"), "cat ./file.txt")
        self.assertEqual(normalize_path_in_command("ls mydir"), "ls ./mydir")

    def test_normalize_preserves_dot_paths(self):
        """
        Given a command whose path argument already starts with ./ or ../
        When normalize_path_in_command processes it
        Then the path argument is left unchanged
        """
        self.assertEqual(normalize_path_in_command("cat ./file.txt"), "cat ./file.txt")
        self.assertEqual(
            normalize_path_in_command("cat ../file.txt"), "cat ../file.txt"
        )

    def test_normalize_preserves_absolute_paths(self):
        """
        Given a command with an absolute path argument
        When normalize_path_in_command processes it
        Then the absolute path is left unchanged
        """
        self.assertEqual(normalize_path_in_command("cat /etc/hosts"), "cat /etc/hosts")
        self.assertEqual(normalize_path_in_command("ls /usr/bin"), "ls /usr/bin")

    def test_normalize_preserves_flags(self):
        """
        Given a command whose arguments are flags starting with - or --
        When normalize_path_in_command processes it
        Then the flags are left unchanged (not treated as paths)
        """
        self.assertEqual(normalize_path_in_command("ls -la"), "ls -la")
        self.assertEqual(normalize_path_in_command("git --version"), "git --version")

    def test_normalize_preserves_tilde_paths(self):
        """
        Given a command with a ~/ home-relative path argument
        When normalize_path_in_command processes it
        Then the tilde path is left unchanged
        """
        self.assertEqual(normalize_path_in_command("cat ~/file.txt"), "cat ~/file.txt")

    def test_normalize_command_only_unchanged(self):
        """
        Given a command with no arguments
        When normalize_path_in_command processes it
        Then the command is returned unchanged
        """
        self.assertEqual(normalize_path_in_command("git"), "git")
        self.assertEqual(normalize_path_in_command("ls"), "ls")


class TestContainsPathComponent(unittest.TestCase):
    """Test path component detection in commands."""

    def test_exact_match(self):
        """
        Given a command whose argument is exactly the target path component
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component("cat .env", ".env"))
        self.assertTrue(contains_path_component("vim test.py", "test.py"))

    def test_component_after_slash(self):
        """
        Given a command where the target component appears after a / or \\ separator
        When contains_path_component checks for that component
        Then it reports a match, backslash being treated as a separator too
        """
        self.assertTrue(contains_path_component("cat dir/.env", ".env"))
        self.assertTrue(contains_path_component("cat /path/to/.env", ".env"))
        self.assertTrue(contains_path_component("cat dir\\.env", ".env"))

    def test_component_before_slash(self):
        """
        Given a command where the target component appears before a slash in a path
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component("cat .env/file", ".env"))

    def test_component_in_middle(self):
        """
        Given a command where the target component sits between slashes in a path
        When contains_path_component checks for that component
        Then it reports a match
        """
        self.assertTrue(contains_path_component("cat dir/.env/file", ".env"))

    def test_no_match(self):
        """
        Given a command that does not contain the target as a whole path segment
        When contains_path_component checks for that component
        Then it reports no match, including when the component is only a substring
        of a longer segment
        """
        self.assertFalse(contains_path_component("cat file.txt", ".env"))
        self.assertFalse(contains_path_component("git status", ".env"))
        self.assertFalse(contains_path_component("cat .environment", ".env"))
        self.assertFalse(contains_path_component("cat env/.envfile", ".env"))

    def test_command_only_no_match(self):
        """
        Given a command with no arguments
        When contains_path_component checks for a component
        Then it reports no match
        """
        self.assertFalse(contains_path_component("ls", "file"))


class TestMatchCommand(unittest.TestCase):
    """Test command pattern matching."""

    def test_simple_wildcard_match(self):
        """
        Given a pattern list with a trailing wildcard pattern (e.g. 'git *')
        When match_command checks a command with that prefix
        Then it matches and returns the matching pattern
        """
        patterns = ["git *"]
        matched, pattern = match_command("git status", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "git *")

    def test_command_args_pattern_match(self):
        """
        Given a command:args pattern (e.g. 'git log:*')
        When match_command checks a command with those args
        Then it matches and returns the pattern
        """
        patterns = ["git log:*"]
        matched, pattern = match_command("git log --oneline", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "git log:*")

    def test_path_component_pattern_match(self):
        """
        Given a path-component pattern (e.g. '**/.env/**')
        When match_command checks commands referencing that component directly or nested
        Then both the direct and nested references match
        """
        patterns = ["**/.env/**"]
        matched, pattern = match_command("cat .env", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "**/.env/**")

        matched, pattern = match_command("cat dir/.env/file", patterns)
        self.assertTrue(matched)

    def test_normalized_path_matching(self):
        """
        Given a pattern expecting a ./-prefixed path (e.g. 'cat ./*:*')
        When match_command checks a command with a bare relative path
        Then path normalization makes it match the pattern
        """
        patterns = ["cat ./*:*"]
        matched, pattern = match_command("cat file.txt", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "cat ./*:*")

    def test_no_match(self):
        """
        Given a pattern list none of whose entries cover the command
        When match_command checks the command
        Then it reports no match and returns None for the pattern
        """
        patterns = ["git *", "ls *"]
        matched, pattern = match_command("cat file.txt", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_empty_patterns(self):
        """
        Given an empty pattern list
        When match_command checks any command
        Then it reports no match and returns None for the pattern
        """
        patterns = []
        matched, pattern = match_command("git status", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_double_star_normalization(self):
        """
        Given a DEFAULT pattern using ** (e.g. 'git **')
        When match_command checks commands with extra arguments and with a path argument
        Then ** behaves as a DEFAULT *: it matches the extra arguments and, unlike a
        [glob] wildcard, spans path separators
        """
        patterns = ["git **"]
        matched, pattern = match_command("git status --short", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "git **")

        matched, _ = match_command("git log docs/a/b.md", patterns)
        self.assertTrue(matched)

    def test_relative_path_command_matches_dotslash_pattern(self):
        """
        Given a pattern with a ./-prefixed script path (e.g. './bin/X:*')
        When match_command checks a command using the equivalent bare path 'bin/X'
        Then they are treated as equivalent and the command matches, with or without args
        """
        patterns = ["./bin/precommit_checks.sh:*"]

        matched, pattern = match_command("bin/precommit_checks.sh", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "./bin/precommit_checks.sh:*")

        matched, _ = match_command("bin/precommit_checks.sh --dry-run", patterns)
        self.assertTrue(matched)

    def test_dotslash_command_matches_relative_pattern(self):
        """
        Given a pattern with a bare relative script path (e.g. 'bin/X:*')
        When match_command checks a command using the ./-prefixed path './bin/X'
        Then they are treated as equivalent and the command matches, with or without args
        """
        patterns = ["bin/precommit_checks.sh:*"]

        matched, pattern = match_command("./bin/precommit_checks.sh", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "bin/precommit_checks.sh:*")

        matched, _ = match_command("./bin/precommit_checks.sh --flag", patterns)
        self.assertTrue(matched)

    def test_relative_path_no_false_positive(self):
        """
        Given a pattern for a specific relative script path (e.g. './bin/precommit_checks.sh:*')
        When match_command checks commands with a different directory or different script
        Then normalization does not cause a false match
        """
        patterns = ["./bin/precommit_checks.sh:*"]

        matched, _ = match_command("other/precommit_checks.sh", patterns)
        self.assertFalse(matched)

        matched, _ = match_command("bin/other_script.sh", patterns)
        self.assertFalse(matched)


class TestMatchCommandTokenBoundary(unittest.TestCase):
    """
    ``Bash(x:*)`` == ``Bash(x *)``: a trailing wildcard after ``:`` requires the
    prefix to be followed by a space or end-of-string, not merely a shared substring.
    """

    def test_colon_star_matches_the_bare_command_and_its_arguments(self):
        """
        Given the pattern 'ls:*'
        When match_command checks 'ls' and 'ls -la'
        Then both match
        """
        patterns = ["ls:*"]
        self.assertTrue(match_command("ls", patterns)[0])
        self.assertTrue(match_command("ls -la", patterns)[0])

    def test_colon_star_does_not_match_a_longer_command_name(self):
        """
        Given the pattern 'ls:*'
        When match_command checks 'lsof'
        Then it does not match -- 'lsof' shares a prefix with 'ls' but is a
        different program, and the boundary fix exists precisely for this case
        """
        matched, pattern = match_command("lsof", ["ls:*"])
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_colon_star_boundary_excludes_a_path_separator(self):
        """
        Given the pattern 'rm -rf /tmp:*'
        When match_command checks 'rm -rf /tmp', 'rm -rf /tmp -f', and 'rm -rf /tmp/foo'
        Then the bare and flagged forms match but the path-suffixed form does not --
        '/' is not a space or end-of-string, so it does not close the boundary
        """
        patterns = ["rm -rf /tmp:*"]
        self.assertTrue(match_command("rm -rf /tmp", patterns)[0])
        self.assertTrue(match_command("rm -rf /tmp -f", patterns)[0])
        matched, pattern = match_command("rm -rf /tmp/foo", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_colon_star_boundary_applies_to_a_multi_token_prefix(self):
        """
        Given the pattern 'git log:*'
        When match_command checks 'git log --oneline' and 'git logfoo'
        Then the first matches and the second does not
        """
        patterns = ["git log:*"]
        self.assertTrue(match_command("git log --oneline", patterns)[0])
        matched, pattern = match_command("git logfoo", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_colon_star_boundary_witness_shapes_a_person_would_not_write_by_hand(self):
        """
        Given multi-token ':*' prefixes whose base command has a same-prefixed sibling
            ('git commit' / 'git commit-tree', 'uv run alembic' / 'uv run alembicfoo')
        When match_command checks the sibling command against each pattern
        Then none of the siblings match -- found by brute-forcing the matcher rather
        than by hand, since these shapes are not ones a person thinks to write. Pins
        the pre-existing token-boundary check itself, not this ticket's ':*'-at-end
        recognition change (all four cases pass unchanged on either side of it).
        """
        cases = [
            ("git commit:*", "git commit-tree abc"),
            ("git commit:*", "git commitfoo -x"),
            ("uv run alembic:*", "uv run alembicfoo upgrade"),
            ("uv run:**", "uv runx"),
        ]
        for pattern, command in cases:
            with self.subTest(pattern=pattern, command=command):
                matched, matched_pattern = match_command(command, [pattern])
                self.assertFalse(matched)
                self.assertIsNone(matched_pattern)

    def test_a_bare_trailing_star_with_no_colon_is_a_plain_prefix(self):
        """
        Given the pattern 'ls*', written with no space or colon before the '*'
        When match_command checks 'lsof'
        Then it matches -- unlike the ':*' form, a bare trailing '*' enforces
        no word boundary
        """
        matched, pattern = match_command("lsof", ["ls*"])
        self.assertTrue(matched)
        self.assertEqual(pattern, "ls*")

    def test_a_pattern_that_is_only_a_colon_star_does_not_raise(self):
        """
        Given a pattern with no command part at all before the trailing wildcard
        (':*' or ':**')
        When match_command checks an ordinary command with no leading space
        Then it returns a plain (False, None) rather than raising -- an empty
        cmd_pattern used to index the empty split() result and raise IndexError.
        See test_a_bare_colon_star_matches_empty_or_leading_space_commands for
        the two input shapes this does NOT hold for.
        """
        for pattern in (":*", ":**"):
            with self.subTest(pattern=pattern):
                matched, matched_pattern = match_command("ls -la", [pattern])
                self.assertFalse(matched)
                self.assertIsNone(matched_pattern)

    def test_a_bare_colon_star_matches_empty_or_leading_space_commands(self):
        """
        Given a pattern with no command part at all before the trailing wildcard
        (':*' or ':**')
        When match_command checks an empty command, or one starting with a space
        Then it matches -- a silent fail-open on those two shapes rather than
        "matches nothing". Harmless in production: the command extractor
        upstream strips leading whitespace and never emits an empty leaf, so
        match_command never sees either shape from a real Bash invocation.
        """
        for pattern in (":*", ":**"):
            with self.subTest(pattern=pattern):
                matched, matched_pattern = match_command("", [pattern])
                self.assertTrue(matched)
                self.assertEqual(matched_pattern, pattern)

                matched, matched_pattern = match_command(" ls", [pattern])
                self.assertTrue(matched)
                self.assertEqual(matched_pattern, pattern)


class TestMatchCommandColonOnlyRecognisedAtPatternEnd(unittest.TestCase):
    """
    Claude Code's own rule: ':*' is recognised only when it is the pattern's literal
    end. A ':' anywhere else -- mid-pattern, or inside a URL -- is a literal character,
    not a cmd:args separator.
    """

    def test_mid_pattern_colon_star_does_not_act_as_a_wildcard(self):
        """
        Given the pattern 'git:* push', whose ':*' is not at the pattern's end
        When match_command checks 'git checkout push'
        Then it does not match -- the ':' is literal, so this is not the same as
        'git * push'
        """
        matched, pattern = match_command("git checkout push", ["git:* push"])
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_mid_pattern_colon_star_matches_its_own_literal_text(self):
        """
        Given the pattern 'git:* push'
        When match_command checks the literal string 'git:* push'
        Then it matches -- the '*' is a plain fnmatch wildcard that can match the
        single '*' character in the command too
        """
        matched, pattern = match_command("git:* push", ["git:* push"])
        self.assertTrue(matched)
        self.assertEqual(pattern, "git:* push")

    def test_a_colon_inside_a_url_does_not_split_the_pattern(self):
        """
        Given the pattern 'curl http://ex.com/*', whose only ':' sits inside a URL
        When match_command checks 'curl http://ex.com/x'
        Then it matches as a plain trailing-wildcard pattern -- the ':' is not
        treated as a cmd:args separator
        """
        matched, pattern = match_command(
            "curl http://ex.com/x", ["curl http://ex.com/*"]
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "curl http://ex.com/*")


class TestMatchCommandExplicitArgsAfterColonNoLongerSplit(unittest.TestCase):
    """
    Before this ticket, a pattern with literal text after a non-trailing ':'
    (e.g. 'git commit:-m *') split there and matched the literal text as a second
    fnmatch against the command's remainder. Claude Code recognises ':*' only at a
    pattern's literal end (see TestMatchCommandColonOnlyRecognisedAtPatternEnd), so
    this shape no longer splits -- a semantic narrowing, pinned here on a deny rule
    since that is the direction where losing reach matters.
    """

    def test_explicit_args_after_colon_no_longer_match_the_command_they_used_to(self):
        """
        Given patterns whose ':' is followed by literal args text, not a bare '*'
        When match_command checks a command with the same base but different args
        Then none of them match -- the ':' is a literal character now, not a
        cmd:args separator
        """
        cases = [
            ("git commit:-m *", "git commit -m x"),
            ("git push:--force *", "git push --force origin"),
            ("rm:-rf /tmp/*", "rm -rf /tmp/foo"),
            ("docker run:--privileged *", "docker run --privileged ubuntu"),
            ("npm run:test", "npm run test"),
            ("git commit: *", "git commit -m x"),
        ]
        for pattern, command in cases:
            with self.subTest(pattern=pattern, command=command):
                matched, matched_pattern = match_command(command, [pattern])
                self.assertFalse(matched)
                self.assertIsNone(matched_pattern)

    def test_explicit_args_pattern_still_matches_its_own_literal_text(self):
        """
        Given a pattern of this shape
        When match_command checks the command that names the pattern's ':' verbatim
        Then it matches -- the pattern still means something: a whole-string
        fnmatch treating the ':' as a literal character
        """
        matched, matched_pattern = match_command("git commit:-m x", ["git commit:-m *"])
        self.assertTrue(matched)
        self.assertEqual(matched_pattern, "git commit:-m *")

    def test_a_deny_rule_of_this_shape_no_longer_blocks_the_command_it_named(self):
        """
        Given a deny pattern of this shape, and an allow pattern that would
            otherwise let the command through
        When check_permission evaluates the command the deny pattern used to name
        Then the decision is 'allow' -- pinning the loss of reach a deny-rule
        author relying on the old split would experience
        """
        decision, _ = check_permission(
            "git push --force origin main",
            allow_patterns=["git *"],
            deny_patterns=["git push:--force *"],
        )
        self.assertEqual(decision, "allow")


class TestMatchCommandColonPrefixWithOwnColonNowMatches(unittest.TestCase):
    """
    Before this ticket, a pattern like 'curl http://localhost:*' split at the FIRST
    ':' -- the one inside the URL -- so its base command became 'curl http' and it
    matched almost nothing. Restricting ':*' recognition to the pattern's literal
    end (TestMatchCommandColonOnlyRecognisedAtPatternEnd) makes it an ordinary
    boundary-checked prefix instead: the same change that narrows
    TestMatchCommandExplicitArgsAfterColonNoLongerSplit's shape WIDENS this one.
    Native-faithful (row 18 in docs/native-pattern-reference.md), but the silent
    and permissive direction, so it is pinned on its own.
    """

    def test_a_colon_in_the_prefix_no_longer_blocks_the_trailing_colon_star(self):
        """
        Given patterns whose prefix itself contains a ':' before the trailing ':*'
        When match_command checks a command with extra arguments after the prefix
        Then each now matches -- all were False before this ticket
        """
        cases = [
            ("curl http://localhost:*", "curl http://localhost"),
            ("curl http://localhost:*", "curl http://localhost -o /etc/shadow"),
            (
                "curl http://localhost:*",
                "curl http://localhost http://evil.example/steal",
            ),
            ("curl http://127.0.0.1:*", "curl http://127.0.0.1 -o /etc/shadow"),
            ("psql postgres://u@h/db:*", "psql postgres://u@h/db -c x"),
            ("scp x user@host:/tmp:*", "scp x user@host:/tmp -o extra"),
        ]
        for pattern, command in cases:
            with self.subTest(pattern=pattern, command=command):
                matched, matched_pattern = match_command(command, [pattern])
                self.assertTrue(matched)
                self.assertEqual(matched_pattern, pattern)


class TestCheckPermission(unittest.TestCase):
    """Test permission checking logic."""

    def test_allow_pattern_match(self):
        """
        Given a command matching an allow pattern and no deny patterns
        When check_permission evaluates it
        Then the decision is 'allow' and the reason names the allow pattern that matched
        """
        allow_patterns = ["git *", "ls *"]
        deny_patterns = []
        decision, reason = check_permission("git status", allow_patterns, deny_patterns)
        self.assertEqual(decision, "allow")
        self.assertIn("allow pattern", reason.lower())
        self.assertIn("git *", reason)

    def test_deny_pattern_match(self):
        """
        Given a command matching a deny pattern
        When check_permission evaluates it
        Then the decision is 'deny' and the reason names the deny pattern that matched
        """
        allow_patterns = ["git *"]
        deny_patterns = ["git push:*"]
        decision, reason = check_permission(
            "git push origin", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("deny pattern", reason.lower())
        self.assertIn("git push:*", reason)

    def test_deny_takes_precedence(self):
        """
        Given a command matching both an allow and a deny pattern
        When check_permission evaluates it
        Then deny wins and the decision is 'deny' by a deny match, not by fail-closed
        fallthrough
        """
        allow_patterns = ["git *"]
        deny_patterns = ["git *"]
        decision, reason = check_permission("git status", allow_patterns, deny_patterns)
        self.assertEqual(decision, "deny")
        self.assertIn("deny pattern", reason.lower())

    def test_not_in_allow_list(self):
        """
        Given a command that matches no allow pattern and no deny pattern
        When check_permission evaluates it
        Then the decision is 'deny' and the reason notes it does not match
        """
        allow_patterns = ["git *"]
        deny_patterns = []
        decision, reason = check_permission("rm -rf /", allow_patterns, deny_patterns)
        self.assertEqual(decision, "deny")
        self.assertIn("does not match", reason.lower())

    def test_empty_allow_list(self):
        """
        Given empty allow and deny lists
        When check_permission evaluates any command
        Then the decision is 'deny' because nothing is allowed
        """
        allow_patterns = []
        deny_patterns = []
        decision, reason = check_permission("git status", allow_patterns, deny_patterns)
        self.assertEqual(decision, "deny")


class TestExtendedPatterns(unittest.TestCase):
    """Test extended pattern matching ([regex], [glob] and [native])."""

    def test_regex_pattern_in_allow_list(self):
        """
        Given an allow list containing a [regex] pattern with an alternation
        When match_command checks commands inside and outside the alternation
        Then matching commands match (returning the regex pattern) and others do not
        """
        patterns = ["[regex]^git (log|diff|status).*"]

        matched, pattern = match_command("git log --oneline", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "[regex]^git (log|diff|status).*")

        matched, pattern = match_command("git diff HEAD~1", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git status --short", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git push origin", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        matched, pattern = match_command("ls -la", patterns)
        self.assertFalse(matched)

    def test_regex_pattern_in_deny_list(self):
        """
        Given an allow list of 'git *' and a deny list with a [regex] for git push
        When check_permission evaluates a push command versus a status command
        Then the push command is denied (citing the regex) and status is allowed
        """
        allow_patterns = ["git *"]
        deny_patterns = ["[regex]^git push.*"]

        decision, reason = check_permission(
            "git push origin main", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("[regex]^git push.*", reason)

        decision, reason = check_permission("git status", allow_patterns, deny_patterns)
        self.assertEqual(decision, "allow")

    def test_glob_pattern_in_allow_list(self):
        """
        Given an allow list with a [glob] pattern matching the whole command string
        When match_command checks commands with matching and mismatching paths/extensions
        Then only commands matching the full glob match, a single * covering exactly one
        path component (unlike a DEFAULT pattern's *, which spans separators)
        """
        patterns = ["[glob]cat /Users/*/projects/**/*.py"]

        matched, pattern = match_command(
            "cat /Users/arnon/projects/flowers/main.py", patterns
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "[glob]cat /Users/*/projects/**/*.py")

        matched, pattern = match_command(
            "cat /Users/arnon/dev/projects/flowers/main.py", patterns
        )
        self.assertFalse(matched)

        matched, pattern = match_command(
            "vim /Users/bob/projects/myapp/src/app.py", patterns
        )
        self.assertFalse(matched)

        matched, pattern = match_command("cat /Users/arnon/documents/file.py", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        matched, pattern = match_command(
            "cat /Users/arnon/projects/flowers/main.txt", patterns
        )
        self.assertFalse(matched)

    def test_glob_pattern_in_deny_list(self):
        """
        Given an allow list of 'cat *' and deny [glob] patterns targeting .env files
        When check_permission evaluates commands reading .env files versus a normal file
        Then the .env commands are denied and the normal file is allowed
        """
        allow_patterns = ["cat *"]
        deny_patterns = ["[glob]cat *.env*", "[glob]cat*/**/.env*"]

        decision, reason = check_permission("cat .env", allow_patterns, deny_patterns)
        self.assertEqual(decision, "deny")
        self.assertIn(".env", reason)

        decision, reason = check_permission(
            "cat /path/to/.env.production", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

        decision, reason = check_permission(
            "cat normal_file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_mixed_pattern_types(self):
        """
        Given a pattern list mixing DEFAULT, [regex], and [glob] entries
        When match_command checks commands targeting each pattern type
        Then each command matches its corresponding pattern and an unrelated command matches none
        """
        patterns = [
            "git status:*",
            "[regex]^git (log|diff).*",
            "[glob]cat /Users/*/projects/**/*.py",
        ]

        matched, pattern = match_command("git status", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "git status:*")

        matched, pattern = match_command("git log --oneline", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "[regex]^git (log|diff).*")

        matched, pattern = match_command(
            "cat /Users/arnon/projects/flowers/main.py", patterns
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "[glob]cat /Users/*/projects/**/*.py")

        matched, pattern = match_command("rm -rf /", patterns)
        self.assertFalse(matched)

    def test_invalid_regex_no_match(self):
        """
        Given an allow list with a malformed [regex] pattern
        When match_command checks a command against it
        Then it reports no match and returns None instead of raising
        """
        patterns = ["[regex]^git (unclosed"]

        matched, pattern = match_command("git anything", patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_regex_bypasses_normalization(self):
        """
        Given [regex] patterns that anchor on the literal command (with or without ./)
        When match_command checks commands with and without a ./ prefix
        Then matching is literal with no path normalization applied
        """
        patterns = ["[regex]^cat file\\.txt$"]

        matched, pattern = match_command("cat file.txt", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("cat ./file.txt", patterns)
        self.assertFalse(matched)

        patterns = ["[regex]^cat \\./file\\.txt$"]
        matched, pattern = match_command("cat ./file.txt", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("cat file.txt", patterns)
        self.assertFalse(matched)

    def test_regex_ignores_colon_syntax(self):
        """
        Given a [regex] pattern containing a literal colon (e.g. '^git log:.*')
        When match_command checks commands with and without that colon
        Then the colon is treated as part of the regex, not a command:args separator
        """
        patterns = ["[regex]^git log:.*"]

        matched, pattern = match_command("git log:something", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git log something", patterns)
        self.assertFalse(matched)

    def test_glob_bypasses_normalization(self):
        """
        Given a [glob] pattern for a literal command (e.g. 'cat file.txt')
        When match_command checks the command with and without a ./ prefix
        Then matching is literal and the ./-prefixed command does not match
        """
        patterns = ["[glob]cat file.txt"]

        matched, pattern = match_command("cat file.txt", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("cat ./file.txt", patterns)
        self.assertFalse(matched)

    def test_glob_ignores_colon_syntax(self):
        """
        Given a [glob] pattern containing a literal colon (e.g. 'git log:*')
        When match_command checks a command with that colon versus a spaced command
        Then the colon is matched literally, so only the colon form matches
        """
        patterns = ["[glob]git log:*"]

        matched, pattern = match_command("git log:something", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git log something", patterns)
        self.assertFalse(matched)

    def test_first_match_wins(self):
        """
        Given a pattern list where two patterns of different types both match a command
        When match_command evaluates them in order
        Then the first matching pattern in the list is the one returned
        """
        patterns = [
            "[regex]^git .*",
            "git status:*",
        ]

        matched, pattern = match_command("git status", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "[regex]^git .*")

    def test_env_special_handling_only_for_default(self):
        """
        Given the same 'cat .env' command checked against DEFAULT, [regex], and [glob] patterns
        When match_command evaluates each
        Then the **/.env/** path-component special handling applies only to DEFAULT patterns,
        while regex and glob must match the full command literally
        """
        default_patterns = ["**/.env/**"]
        matched, pattern = match_command("cat .env", default_patterns)
        self.assertTrue(matched)

        regex_patterns = ["[regex].*\\.env.*"]
        matched, pattern = match_command("cat .env", regex_patterns)
        self.assertTrue(matched)

        glob_patterns = ["[glob]cat .env"]
        matched, pattern = match_command("cat .env", glob_patterns)
        self.assertTrue(matched)

        glob_patterns = ["[glob]* .env"]
        matched, pattern = match_command("cat .env", glob_patterns)
        self.assertTrue(matched)

        # The same **/<component>/** spelling, prefixed: no special handling, so it is
        # matched as an ordinary glob/regex against the command and does not match.
        matched, pattern = match_command("cat .env", ["[glob]**/.env/**"])
        self.assertFalse(matched)

        matched, pattern = match_command("cat .env", ["[regex]**/.env/**"])
        self.assertFalse(matched)

    def test_native_pattern_uses_native_semantics(self):
        """
        Given an allow list with a [native] pattern (e.g. '[native]git * main')
        When match_command checks commands that only NATIVE semantics decide correctly
        Then NATIVE's own segment matching is used, not [glob]'s or DEFAULT's: * spans any
        run of characters including a path separator, and ? is a literal character
        """
        patterns = ["[native]git * main"]

        matched, pattern = match_command("git checkout main", patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, "[native]git * main")

        matched, pattern = match_command("git merge main", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git checkout develop", patterns)
        self.assertFalse(matched)

        # [glob] would refuse this: its * does not cross '/'.
        matched, pattern = match_command("git checkout feature/x main", patterns)
        self.assertTrue(matched)

        # DEFAULT (fnmatch) and [glob] both treat '?' as a single-character wildcard;
        # NATIVE's only metacharacter is *, so '?' must match itself.
        literal_patterns = ["[native]git * ?"]

        matched, pattern = match_command("git checkout ?", literal_patterns)
        self.assertTrue(matched)

        matched, pattern = match_command("git checkout x", literal_patterns)
        self.assertFalse(matched)

    def test_native_pattern_in_deny_list(self):
        """
        Given an allow list of 'git *' and a deny list with '[native]git push *'
        When check_permission evaluates a git push command versus git status
        Then the push command is denied (citing the native pattern) and status is allowed
        """
        allow_patterns = ["git *"]
        deny_patterns = ["[native]git push *"]

        decision, reason = check_permission(
            "git push origin main", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("[native]git push *", reason)

        decision, _ = check_permission("git status", allow_patterns, deny_patterns)
        self.assertEqual(decision, "allow")

        # NATIVE's * spans the '/', so the deny still covers a path-bearing argument;
        # under [glob] semantics this command would fall through to the 'git *' allow.
        decision, reason = check_permission(
            "git push a/b", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("[native]git push *", reason)

    def test_extended_syntax_disabled_treats_prefix_as_literal(self):
        """
        Given a [regex] pattern and a command the regex would match
        When match_command is called with extended_syntax=False
        Then the prefix is not recognised, the pattern is matched as DEFAULT and the
        command does not match, while a plain DEFAULT pattern still matches
        """
        patterns = ["[regex]^git .*"]

        matched, pattern = match_command("git anything", patterns)
        self.assertTrue(matched)

        matched, pattern = match_command(
            "git anything", patterns, extended_syntax=False
        )
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        matched, _ = match_command("git anything", ["git *"], extended_syntax=False)
        self.assertTrue(matched)


class TestMatchCommandUnderASymlinkedHomeDirectory(unittest.TestCase):
    """
    A rule keeps matching whichever spelling of a symlinked location it was written in.

    Isolation exception (`.claude/rules/test-config-isolation.md`): match_command never
    reaches toolguard.config's discovery path, so ConfigIsolationMixin does not apply;
    the only anchor here is Path.home(), read by normalization.
    """

    def setUp(self):
        """Build home/.claude as a symlink into home/store/claude, holding one file."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.store = self.home / "store" / "claude"
        self.store.mkdir(parents=True)
        (self.store / "settings.json").write_text("{}", encoding="utf-8")
        (self.home / ".claude").symlink_to(self.store)
        patcher = patch.object(Path, "home", staticmethod(lambda: self.home))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_rule_naming_the_link_matches_the_absolute_command(self):
        """
        Given a deny rule written as '~/.claude/settings.json', where '.claude' is a
        symlink, and a command naming the same file by absolute path
        When match_command evaluates it
        Then it matches -- resolving the symlink must not discard the spelling the
        rule author wrote, or every deny rule in that spelling silently fails open
        """
        matched, pattern = match_command(
            f"cat {self.home}/.claude/settings.json",
            ["cat ~/.claude/settings.json"],
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "cat ~/.claude/settings.json")

    def test_a_rule_naming_the_symlink_target_matches_the_command_too(self):
        """
        Given a deny rule written against the link's TARGET, '~/store/claude/...'
        When the same command -- which names the link, not the target -- is evaluated
        Then it still matches: the resolved spelling is carried alongside the others,
        so a symlink is not a way around a rule written against what it points at
        """
        matched, pattern = match_command(
            f"cat {self.home}/.claude/settings.json",
            ["cat ~/store/claude/settings.json"],
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "cat ~/store/claude/settings.json")

    def test_an_unrelated_file_under_the_link_is_not_matched(self):
        """
        Given the same two rules
        When a command names a DIFFERENT file in the symlinked directory
        Then neither matches -- carrying extra spellings widens the set of names for
        one location, not the set of locations
        """
        for rule in ("cat ~/.claude/settings.json", "cat ~/store/claude/settings.json"):
            with self.subTest(rule=rule):
                matched, _ = match_command(
                    f"cat {self.home}/.claude/other.json", [rule]
                )
                self.assertFalse(matched)


class TestMatchCommandAcrossTheTwoHomeSpellings(unittest.TestCase):
    """
    A DEFAULT rule meets its command whichever of '~' and the absolute path each was
    written in. The sibling class below covers the other three pattern types, which
    cross in one direction only.

    Isolation exception (`.claude/rules/test-config-isolation.md`): match_command never
    reaches toolguard.config's discovery path, so ConfigIsolationMixin does not apply;
    the only anchor is the home directory, bound here through toolguard.ambient.
    """

    HOME = Path("/home/testuser")
    USER = "testuser"

    def setUp(self):
        """Bind a fixed home, and make USER resolve to it through a patched passwd
        lookup, so no spelling depends on the machine."""
        self.enterContext(
            ambient.active(ambient.AmbientFacts(home=self.HOME, cwd=self.HOME, env={}))
        )
        self.enterContext(
            patch(
                "pwd.getpwnam", side_effect=_passwd_lookup({self.USER: str(self.HOME)})
            )
        )

    def test_an_absolutely_spelled_rule_fires_on_the_tilde_spelling(self):
        """
        Given a deny rule naming a file by its absolute path under home
        When a command names that same file with '~'
        Then it matches -- an absolute path is the natural spelling for a deny rule,
        and leaving '~' unexpanded lets the very command it names walk past it
        """
        matched, pattern = match_command(
            "cat ~/.ssh/id_rsa", [f"cat {self.HOME}/.ssh/id_rsa"]
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, f"cat {self.HOME}/.ssh/id_rsa")

    def test_a_tilde_spelled_rule_still_fires_on_the_absolute_spelling(self):
        """
        Given a deny rule written with '~'
        When a command names the same file by absolute path
        Then it matches, as before: the expanded spelling joins the others rather
        than replacing the home-collapsed one that answers this direction
        """
        matched, pattern = match_command(
            f"cat {self.HOME}/.ssh/id_rsa", ["cat ~/.ssh/id_rsa"]
        )
        self.assertTrue(matched)
        self.assertEqual(pattern, "cat ~/.ssh/id_rsa")

    def test_command_variants_does_not_itself_expand_tilde(self):
        """
        Given a command written with '~', passed straight to _command_variants
        When it builds the deduplicated path-normalization list
        Then no variant has the leading '~' expanded -- that spelling is added earlier,
        by match_command's own spellings loop, so a future edit that makes the tilde
        spelling load-bearing again has somewhere to add it instead of reintroducing it
        here as dead weight
        """
        self.assertEqual(_command_variants("cat ~/notes.txt"), ["cat ~/notes.txt"])

    def test_either_spelling_of_a_default_rule_matches_either_command_spelling(self):
        """
        Given a DEFAULT rule and a command differing only in how home is written
        When all four combinations are evaluated
        Then every one matches
        """
        spellings = ("cat ~/notes.txt", f"cat {self.HOME}/notes.txt")
        for rule in spellings:
            for command in spellings:
                with self.subTest(rule=rule, command=command):
                    matched, _ = match_command(command, [rule])
                    self.assertTrue(matched)

    def test_an_unknown_name_is_not_read_as_this_home(self):
        """
        Given a rule naming a file under THIS home
        When a command names the same suffix under '~root', a name the passwd stub
            does not know
        Then it does not match: an unresolved '~root' names a different file than the
        rule -- expanding it against this home would report a hit the command never named
        """
        matched, _ = match_command(
            "cat ~root/.ssh/id_rsa", [f"cat {self.HOME}/.ssh/id_rsa"]
        )
        self.assertFalse(matched)

    def test_a_named_user_is_read_as_the_home_the_passwd_lookup_gives_it(self):
        """
        Given a rule naming a file by its absolute path under home
        When a command names that same file as '~<name>/...' for a name the passwd
            lookup resolves to this same home
        Then it matches: a name spells its passwd home as surely as '~' does,
        so a rule blind to it could be walked past by writing it that way
        """
        matched, _ = match_command(
            f"cat ~{self.USER}/.ssh/id_rsa", [f"cat {self.HOME}/.ssh/id_rsa"]
        )
        self.assertTrue(matched)

    def test_a_deny_rule_reaches_a_named_user_resolving_to_this_home(self):
        """
        Given an absolutely-spelled deny rule and a blanket allow
        When the command spells the denied file '~<name>/...' for a name the passwd
            lookup resolves to this same home
        Then the decision is deny -- the restricting direction the expansion is for
        """
        decision, _ = check_permission(
            f"cat ~{self.USER}/.ssh/id_rsa", ["*"], [f"cat {self.HOME}/.ssh/id_rsa"]
        )
        self.assertEqual(decision, "deny")

    def test_an_unrelated_file_under_home_is_not_matched(self):
        """
        Given the same absolute rule
        When a command names a DIFFERENT file under home
        Then it does not match -- the extra spelling widens the names one location
        answers to, not the set of locations
        """
        matched, _ = match_command(
            "cat ~/.ssh/known_hosts", [f"cat {self.HOME}/.ssh/id_rsa"]
        )
        self.assertFalse(matched)

    def test_an_unresolvable_home_does_not_raise_out_of_the_matcher(self):
        """
        Given a machine where the home directory cannot be resolved at all
        When a '~'-spelled command is matched against both rule spellings
        Then the matcher returns a verdict instead of raising: the expanded spelling
        is simply unavailable, and the spellings that survive still decide
        """
        # patch.object(Path, "home") rather than ConfigIsolationMixin: the subject is a
        # home that resolves to nothing at all, which the mixin's layout cannot build.
        homeless = ambient.AmbientFacts(home=None, cwd=Path("/tmp"), env={})
        with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
            with ambient.active(homeless):
                absolute_rule, _ = match_command(
                    "cat ~/.ssh/id_rsa", [f"cat {self.HOME}/.ssh/id_rsa"]
                )
                tilde_rule, _ = match_command(
                    "cat ~/.ssh/id_rsa", ["cat ~/.ssh/id_rsa"]
                )
        self.assertFalse(absolute_rule)
        self.assertTrue(tilde_rule)


class TestEveryPatternTypeCrossesTheTwoHomeSpellings(unittest.TestCase):
    """
    An absolutely-spelled rule reaches a '~'-spelled command under [regex], [glob] and
    [native] too, not only DEFAULT, and for granting rules as well as restricting ones.

    Isolation exception (`.claude/rules/test-config-isolation.md`): match_command never
    reaches toolguard.config's discovery path, so ConfigIsolationMixin does not apply;
    the only anchor is the home directory, bound here through toolguard.ambient.
    """

    HOME = Path("/home/testuser")
    USER = "testuser"

    def setUp(self):
        """Bind a fixed home, and make USER resolve to it through a patched passwd
        lookup, so no spelling depends on the machine."""
        self.enterContext(
            ambient.active(ambient.AmbientFacts(home=self.HOME, cwd=self.HOME, env={}))
        )
        self.enterContext(
            patch(
                "pwd.getpwnam", side_effect=_passwd_lookup({self.USER: str(self.HOME)})
            )
        )

    def _one_rule_per_pattern_type(self, command):
        """*command*, spelled as a rule of each pattern type, keyed by type name."""
        return {
            "DEFAULT": command,
            "[glob]": f"[glob]{command}",
            "[regex]": "[regex]" + re.escape(command),
            "[native]": f"[native]{command}",
        }

    def test_every_pattern_type_sees_the_tilde_spelling(self):
        """
        Given a rule naming a file by its absolute path under home
        When the same file is named with '~' by the command
        Then every pattern type matches -- offering the expanded spelling to DEFAULT
        alone leaves the same deny bypassable by writing it as [regex]/[glob]/[native]
        """
        rules = self._one_rule_per_pattern_type(f"cat {self.HOME}/.ssh/id_rsa")
        for type_name, rule in rules.items():
            with self.subTest(pattern_type=type_name):
                matched, _ = match_command("cat ~/.ssh/id_rsa", [rule])
                self.assertTrue(matched)

    def test_a_deny_rule_reaches_the_tilde_spelling(self):
        """
        Given an absolutely-spelled [regex] deny rule and a blanket allow
        When a '~'-spelled command names the denied file
        Then the decision is deny -- the restricting direction this exists for
        """
        decision, _ = check_permission(
            "cat ~/.ssh/id_rsa",
            ["*"],
            ["[regex]" + re.escape(f"cat {self.HOME}/.ssh/id_rsa")],
        )
        self.assertEqual(decision, "deny")

    def test_an_allow_rule_reaches_it_on_the_same_terms(self):
        """
        Given an absolutely-spelled [regex] ALLOW rule
        When a '~'-spelled command names the same file
        Then it is allowed: unlike looking past a 'NAME=value' prefix, expanding '~'
        discards nothing -- the two spellings name one file -- so the granting side
        gets the spelling on the same terms as the restricting side
        """
        decision, _ = check_permission(
            "cat ~/notes.txt",
            ["[regex]" + re.escape(f"cat {self.HOME}/notes.txt")],
            [],
        )
        self.assertEqual(decision, "allow")

    def test_a_further_spelling_is_expanded_too(self):
        """
        Given a command whose leading assignment is looked past by a further spelling
        When that further spelling is the one carrying the '~'
        Then it is expanded as well, so the two accommodations compose rather than
        each hiding the command from the other
        """
        matched, _ = match_command(
            "TG_X=1 cat ~/notes.txt",
            ["[regex]" + re.escape(f"cat {self.HOME}/notes.txt")],
            also_spelled=("cat ~/notes.txt",),
        )
        self.assertTrue(matched)

    def test_a_component_pattern_now_answers_to_the_home_path_segments(self):
        """
        Given a '**/<component>/**' rule naming a segment of the home path itself
        When a '~'-spelled command is matched
        Then it matches, where before the expansion it did not: '~/x' IS
        '/home/testuser/x', so 'testuser' genuinely is one of its path segments
        """
        matched, _ = match_command("cat ~/notes.txt", ["**/testuser/**"])
        self.assertTrue(matched)

    def test_an_unknown_name_is_not_expanded_under_any_pattern_type(self):
        """
        Given a rule naming a file under THIS home
        When a command names the same suffix under '~root', a name the passwd stub
            does not know
        Then no pattern type matches: an unresolved '~root' names a different file than
        the rule
        """
        rules = self._one_rule_per_pattern_type(f"cat {self.HOME}/.ssh/id_rsa")
        for type_name, rule in rules.items():
            with self.subTest(pattern_type=type_name):
                matched, _ = match_command("cat ~root/.ssh/id_rsa", [rule])
                self.assertFalse(matched)

    def test_a_named_user_is_expanded_under_every_pattern_type(self):
        """
        Given a rule naming a file by its absolute path under home
        When a command names that same file as '~<name>/...' for a name the passwd
            lookup resolves to this same home
        Then every pattern type matches, on the same terms as a bare '~'
        """
        rules = self._one_rule_per_pattern_type(f"cat {self.HOME}/.ssh/id_rsa")
        for type_name, rule in rules.items():
            with self.subTest(pattern_type=type_name):
                matched, _ = match_command(f"cat ~{self.USER}/.ssh/id_rsa", [rule])
                self.assertTrue(matched)

    def test_an_unrelated_file_under_home_is_not_matched_under_any_pattern_type(self):
        """
        Given the same absolute rule
        When a command names a DIFFERENT file under home
        Then no pattern type matches -- the extra spelling widens the names one
        location answers to, not the set of locations
        """
        rules = self._one_rule_per_pattern_type(f"cat {self.HOME}/.ssh/id_rsa")
        for type_name, rule in rules.items():
            with self.subTest(pattern_type=type_name):
                matched, _ = match_command("cat ~/.ssh/known_hosts", [rule])
                self.assertFalse(matched)

    def test_an_unresolvable_home_does_not_raise_out_of_any_pattern_type(self):
        """
        Given a machine where the home directory cannot be resolved at all
        When a '~'-spelled command is matched under each pattern type
        Then each returns a verdict instead of raising: the expanded spelling is
        simply unavailable, and the raw spelling still decides
        """
        # patch.object(Path, "home") rather than ConfigIsolationMixin: the subject is a
        # home that resolves to nothing at all, which the mixin's layout cannot build.
        homeless = ambient.AmbientFacts(home=None, cwd=Path("/tmp"), env={})
        rules = self._one_rule_per_pattern_type(f"cat {self.HOME}/.ssh/id_rsa")
        with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
            with ambient.active(homeless):
                for type_name, rule in rules.items():
                    with self.subTest(pattern_type=type_name):
                        matched, _ = match_command("cat ~/.ssh/id_rsa", [rule])
                        self.assertFalse(matched)


if __name__ == "__main__":
    unittest.main()
