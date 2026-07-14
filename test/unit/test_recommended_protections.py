"""
Unit tests for toolguard.tools.recommended_protections (TOO-15).

Covers the declarative, curated [hard_deny] "Sensitive files" pattern set that
``toolguard-install seed-hard-deny`` writes verbatim -- this module is the single
source of truth so an agent never composes ``[hard_deny]`` TOML by hand (see
docs/security.md "Recommended deny patterns" -> "Sensitive files").

RED-PHASE NOTE: as of this commit toolguard/tools/recommended_protections.py does
not exist yet. Every test in this module is expected to fail (ImportError at
collection time, surfacing as an error on every test) until the module is
implemented. This file defines the module's contract the implementation must
satisfy, mirroring test_tools_self_permission.py's shape for
toolguard.tools.self_permission.
"""

import unittest

from toolguard.tools.recommended_protections import (
    RecommendedProtection,
    required_hard_deny_patterns,
)


# The canonical "Sensitive files" set from docs/security.md's "Recommended deny
# patterns" section, copied verbatim -- this is the exact set the module must return,
# no more, no less. Includes both the relative (project-anchored) forms and their
# home-anchored (~/...) siblings; see docs/security.md's "Why both forms of the
# sensitive-file patterns are needed" for the rationale.
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
        docs/security.md's "Recommended deny patterns" section (the 8 original
        relative patterns plus their 8 home-anchored siblings), no more, no less
        """
        patterns = tuple(p.pattern for p in required_hard_deny_patterns())
        self.assertEqual(patterns, _EXPECTED_PATTERNS)

    def test_every_relative_pattern_has_a_home_anchored_sibling(self):
        """
        Given the required hard-deny protection table
        When every relative pattern (of the form ``Verb(**/...)``, anchored to the
        active project root by resolve.py's _anchor_file_pattern) is inspected
        Then its home-anchored sibling (``Verb(~/...)``, left unmodified by
        _anchor_file_pattern and always resolving to the real home directory) is
        also present in the table -- this is the structural "both forms" invariant
        that protects secrets regardless of which project is active, not just an
        artifact of the literal list matching docs/security.md
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
        Then it raises (the table is immutable, matching self_permission.py's
        SelfPermission pattern -- toolguard must never let this canonical set be
        mutated at runtime)
        """
        protection = required_hard_deny_patterns()[0]
        with self.assertRaises(Exception):
            protection.pattern = "Read(**/.env.other)"


if __name__ == "__main__":
    unittest.main()
