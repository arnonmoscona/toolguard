"""
Unit tests for toolguard.tools.recommended_protections.

Covers the curated [hard_deny] "Sensitive files" pattern set that
``toolguard-install seed-hard-deny`` writes verbatim -- the single source of
truth, so an agent never composes ``[hard_deny]`` TOML by hand (see
docs/security.md "Recommended deny patterns" -> "Sensitive files").
"""

import unittest

from toolguard.tools.recommended_protections import (
    RecommendedProtection,
    required_hard_deny_patterns,
)


# The canonical "Sensitive files" set from docs/security.md, copied verbatim:
# the project-anchored forms and their home-anchored (~/...) siblings.
_EXPECTED_PATTERNS = (
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.aws/**)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.aws/**)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)",
    "Read(~/.env)",
    "Read(~/.env.*)",
    "Read(~/.aws/**)",
    "Read(~/.ssh/**)",
    "Write(~/.env)",
    "Write(~/.aws/**)",
    "Write(~/.ssh/**)",
    "Edit(~/.env)",
)


class TestRequiredHardDenyPatterns(unittest.TestCase):
    """The declarative canonical hard-deny pattern set matches docs/security.md exactly."""

    def test_contains_exactly_the_sixteen_canonical_patterns(self):
        """
        Given the required hard-deny protection table
        When it is inspected
        Then it contains exactly the 16 "Sensitive files" patterns from
        docs/security.md -- 8 relative plus their 8 home-anchored siblings,
        in that order, no more and no less
        """
        patterns = tuple(p.pattern for p in required_hard_deny_patterns())
        self.assertEqual(patterns, _EXPECTED_PATTERNS)

    def test_every_relative_pattern_has_a_home_anchored_sibling(self):
        """
        Given the required hard-deny protection table
        When every relative pattern (``Verb(**/...)``, anchored to the active
        project root by resolve.py's _anchor_file_pattern) is inspected
        Then its home-anchored sibling (``Verb(~/...)``, which _anchor_file_pattern
        leaves pointing at the real home directory) is also present -- secrets
        stay protected whichever project is active
        """
        patterns = {p.pattern for p in required_hard_deny_patterns()}
        relative_patterns = [p for p in patterns if "(**/" in p]
        self.assertTrue(
            relative_patterns, "expected at least one relative (**/) pattern"
        )
        for relative_pattern in relative_patterns:
            home_anchored_sibling = relative_pattern.replace("(**/", "(~/", 1)
            self.assertIn(
                home_anchored_sibling,
                patterns,
                f"missing home-anchored sibling {home_anchored_sibling!r} "
                f"for relative pattern {relative_pattern!r}",
            )

    def test_no_duplicate_patterns(self):
        """
        Given the required hard-deny protection table
        When the patterns are collected into a set
        Then no pattern is duplicated
        """
        patterns = [p.pattern for p in required_hard_deny_patterns()]
        self.assertEqual(len(patterns), len(set(patterns)))

    def test_every_entry_has_a_nonempty_rationale(self):
        """
        Given the required hard-deny protection table
        When each entry's rationale is inspected
        Then it is a non-empty, human-readable RecommendedProtection.rationale string
        """
        for protection in required_hard_deny_patterns():
            self.assertIsInstance(protection, RecommendedProtection)
            self.assertTrue(protection.rationale.strip())

    def test_entries_are_frozen_dataclass_instances(self):
        """
        Given one required hard-deny protection entry
        When an attempt is made to mutate its pattern
        Then it raises -- the canonical set cannot be mutated at runtime
        """
        protection = required_hard_deny_patterns()[0]
        with self.assertRaises(Exception):
            protection.pattern = "Read(**/.env.other)"


if __name__ == "__main__":
    unittest.main()
