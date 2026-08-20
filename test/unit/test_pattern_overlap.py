"""Unit tests for toolguard.tools.pattern_overlap."""

import unittest

from toolguard.permissions import match_command
from toolguard.tools.pattern_overlap import (
    default_prefix_tokens,
    prefixes_overlap,
    split_default_body,
)


class TestSplitDefaultBody(unittest.TestCase):
    """split_default_body's cmd/args split, kept in step with match_command."""

    def test_trailing_colon_star_splits_into_tokens_and_args(self):
        """
        Given a DEFAULT body ending in ':*'
        When split_default_body splits it
        Then the command part is tokenized and the args part is '*'
        """
        self.assertEqual(split_default_body("git diff:*"), (["git", "diff"], "*"))

    def test_trailing_double_star_normalizes_like_a_single_star(self):
        """
        Given a DEFAULT body ending in ':**'
        When split_default_body splits it
        Then '**' normalizes to '*' the same way match_command does
        """
        self.assertEqual(split_default_body("uv run:**"), (["uv", "run"], "*"))

    def test_a_colon_not_at_the_end_is_not_a_separator(self):
        """
        Given a DEFAULT body whose only ':' sits inside a URL, not at the end
        When split_default_body splits it
        Then no split happens -- the whole body is the command part, no args part
        """
        self.assertEqual(
            split_default_body("curl http://ex.com/*"),
            (["curl", "http://ex.com/*"], ""),
        )

    def test_a_bare_pattern_with_no_colon_has_no_args_part(self):
        """
        Given a DEFAULT body with no ':' at all
        When split_default_body splits it
        Then the command part is the whole tokenized body and args part is empty
        """
        self.assertEqual(split_default_body("git status"), (["git", "status"], ""))

    def test_a_path_component_body_is_not_corrupted_by_star_normalization(self):
        """
        Given a '**/<component>/**' path-component body, which carries no ':' at all
        When split_default_body splits it
        Then the '**' is left untouched -- match_command matches this shape via
        contains_path_component before any '**' normalization runs, so collapsing
        it to '*/secrets/*' here would name a pattern match_command never sees
        """
        self.assertEqual(split_default_body("**/secrets/**"), (["**/secrets/**"], ""))


class TestDefaultPrefixTokens(unittest.TestCase):
    """default_prefix_tokens' DEFAULT/':*' gating."""

    def test_default_colon_star_pattern_yields_its_tokens(self):
        """
        Given a DEFAULT ':*'-suffixed pattern
        When default_prefix_tokens processes it
        Then it returns the command's token sequence
        """
        self.assertEqual(
            default_prefix_tokens("uv run alembic:*"), ["uv", "run", "alembic"]
        )

    def test_a_pattern_with_no_trailing_colon_star_yields_none(self):
        """
        Given a DEFAULT pattern with no trailing ':*' (a bare command, or one with a
            colon that is not the trailing separator)
        When default_prefix_tokens processes it
        Then it returns None. Not a differential against the pre-fix splitter: a
            first-colon split also gave None for the URL case, via a different
            (non-'*') args_part -- see TestMatchCommandColonOnlyRecognisedAtPatternEnd
            in test_permissions.py for the case that actually distinguishes the two.
        """
        self.assertIsNone(default_prefix_tokens("ls"))
        self.assertIsNone(default_prefix_tokens("curl http://ex.com/*"))

    def test_a_mid_pattern_colon_or_explicit_args_pattern_yields_none(self):
        """
        Given a DEFAULT pattern whose ':' is not the pattern's literal end -- a
            mid-pattern ':*' or explicit literal text after the ':'
        When default_prefix_tokens processes it
        Then it returns None -- these are no longer cmd:args prefixes at all
            (match_command matches them as a whole-string fnmatch), so
            prefixes_overlap-based analysis (clarity.py, consolidate.py) correctly
            never reasons about their command-space as a prefix
        """
        self.assertIsNone(default_prefix_tokens("git:* push"))
        self.assertIsNone(default_prefix_tokens("git commit:-m *"))
        self.assertIsNone(default_prefix_tokens("rm:-rf /tmp/*"))

    def test_a_non_default_pattern_yields_none(self):
        """
        Given a [regex]/[glob]/[native] pattern
        When default_prefix_tokens processes it
        Then it returns None -- their command-space is not prefix-comparable
        """
        self.assertIsNone(default_prefix_tokens("[regex]^git (log|diff)"))
        self.assertIsNone(default_prefix_tokens("[native]git * main"))


class TestPrefixesOverlap(unittest.TestCase):
    """prefixes_overlap's token-sequence prefix test."""

    def test_one_shorter_sequence_prefixing_a_longer_one_overlaps(self):
        """
        Given ['git'] and ['git', 'commit']
        When prefixes_overlap compares them
        Then they overlap -- the shorter is a prefix of the longer
        """
        self.assertTrue(prefixes_overlap(["git"], ["git", "commit"]))

    def test_diverging_sequences_do_not_overlap(self):
        """
        Given ['uv', 'run'] and ['uv', 'runx']
        When prefixes_overlap compares them
        Then they do not overlap -- 'run' and 'runx' diverge at the second token
        """
        self.assertFalse(prefixes_overlap(["uv", "run"], ["uv", "runx"]))


class TestPrefixesOverlapAgreesWithMatchCommand(unittest.TestCase):
    """
    The differential that found the original defect: prefixes_overlap's claim about
    two patterns' token sequences must agree with whether match_command can find a
    real command both patterns actually match. A fixed, small corpus rather than a
    randomized brute force, so the regression check is deterministic in CI.

    Every PATTERNS entry ends in ':*', so this guards the last-token boundary check,
    not the mid-pattern-colon / explicit-args narrowing -- those patterns yield None
    from default_prefix_tokens and so never reach a prefix-overlap claim at all; see
    TestSplitDefaultBody and test_permissions.py's
    TestMatchCommandColonOnlyRecognisedAtPatternEnd /
    TestMatchCommandExplicitArgsAfterColonNoLongerSplit for those shapes.
    """

    # Deliberately includes 'sibling' pairs that diverge only in a glued-on suffix or
    # a truncated last token -- the exact shape ('uv run:*' vs 'uv runx:*') the
    # original over-match was found in.
    PATTERNS = [
        "git:*",
        "git commit:*",
        "git commit-tree:*",
        "git commitfoo:*",
        "uv run:*",
        "uv runx:*",
        "uv run alembic:*",
        "uv run alembicfoo:*",
        "rm -rf /tmp:*",
        "rm -rf /tmpfoo:*",
        "ls:*",
        "lsof:*",
    ]

    WITNESS_COMMANDS = [
        "git status",
        "git commit -m x",
        "git commit-tree abc",
        "git commitfoo -x",
        "uv run pytest",
        "uv runx",
        "uv run alembic upgrade",
        "uv run alembicfoo upgrade",
        "rm -rf /tmp",
        "rm -rf /tmp/foo",
        "rm -rf /tmpfoo",
        "ls -la",
        "lsof -i",
    ]

    def test_prefixes_overlap_never_misses_a_shared_command(self):
        """
        Given every pair of PATTERNS above, all literal ':*' prefixes with no
            fnmatch wildcards in their tokens
        When prefixes_overlap's claim is compared against whether match_command
            finds a WITNESS_COMMANDS entry both patterns actually match
        Then no pair claims NO overlap while sharing a real match -- the direction
            the original over-match defect took (a false 'no overlap' claim on a
            pair that in fact shares a real match)
        """
        tokens = {p: default_prefix_tokens(p) for p in self.PATTERNS}
        matches = {
            p: {c for c in self.WITNESS_COMMANDS if match_command(c, [p])[0]}
            for p in self.PATTERNS
        }

        for i, a in enumerate(self.PATTERNS):
            for b in self.PATTERNS[i + 1 :]:
                shared = matches[a] & matches[b]
                claims_overlap = prefixes_overlap(tokens[a], tokens[b])
                if shared and not claims_overlap:
                    self.fail(
                        f"{a!r} and {b!r} share {shared!r} but prefixes_overlap "
                        "claims no overlap"
                    )
