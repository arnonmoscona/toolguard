"""Unit tests for toolguard permission checking logic."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
