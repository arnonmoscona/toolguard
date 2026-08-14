"""
Unit tests for toolguard.tools.recommended_protections.

Covers the curated [hard_deny] "Sensitive files" pattern set that
``toolguard-install seed-hard-deny`` writes verbatim -- the single source of
truth, so an agent never composes ``[hard_deny]`` TOML by hand (see
docs/security.md "Recommended deny patterns" -> "Sensitive files").

The table is checked three ways: against an independent copy of the canonical
list (below), against docs/security.md itself, and -- because a pattern that
looks right but matches nothing is worse than none, since it is trusted --
through the REAL decision engine (toolguard.api.decide).
"""

import dataclasses
import re
import unittest
from pathlib import Path
from types import MappingProxyType

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.file_matching import check_file_path_hard_deny
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
    "Write(**/.env.*)",
    "Write(**/.aws/**)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)",
    "Edit(**/.env.*)",
    "Edit(**/.aws/**)",
    "Edit(**/.ssh/**)",
    "Read(~/.env)",
    "Read(~/.env.*)",
    "Read(~/.aws/**)",
    "Read(~/.ssh/**)",
    "Write(~/.env)",
    "Write(~/.env.*)",
    "Write(~/.aws/**)",
    "Write(~/.ssh/**)",
    "Edit(~/.env)",
    "Edit(~/.env.*)",
    "Edit(~/.aws/**)",
    "Edit(~/.ssh/**)",
)

#: parents[0]=test/unit, parents[1]=test, parents[2]=repo root.
_SECURITY_DOC = Path(__file__).resolve().parents[2] / "docs" / "security.md"

_QUOTED_PATTERN = re.compile(r'"([^"]+)"')


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
        project root by file_matching._anchor_file_pattern) is inspected
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
        self.assertTrue(patterns, "empty table: the comparison below is 0 == 0")
        self.assertEqual(len(patterns), len(set(patterns)))

    def test_every_entry_has_a_nonempty_rationale(self):
        """
        Given the required hard-deny protection table
        When each entry's rationale is inspected
        Then it is a non-empty, human-readable RecommendedProtection.rationale string
        """
        protections = required_hard_deny_patterns()
        self.assertTrue(protections, "empty table: the loop below checks nothing")
        for index, protection in enumerate(protections):
            with self.subTest(index=index):
                self.assertIsInstance(protection, RecommendedProtection)
                self.assertTrue(
                    protection.rationale.strip(), f"empty rationale at index {index}"
                )

    def test_entries_are_frozen_dataclass_instances(self):
        """
        Given every required hard-deny protection entry
        When an attempt is made to mutate its pattern
        Then it raises FrozenInstanceError specifically and the value is
        unchanged -- a bare Exception would also be satisfied by an unrelated
        error, and a frozen dataclass raises the same error for a field that
        does not exist, so the field name is checked separately
        """
        protections = required_hard_deny_patterns()
        self.assertTrue(protections, "empty table: the loop below checks nothing")
        # Indexed rather than labelled by pattern: reading .pattern to build the
        # label would turn a renamed field into an error instead of a failure.
        for index, protection in enumerate(protections):
            with self.subTest(index=index):
                field_names = {f.name for f in dataclasses.fields(protection)}
                self.assertIn("pattern", field_names)
                original = protection.pattern
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    protection.pattern = "Read(**/.env.other)"
                # The table is a module-level singleton: a mutation that landed
                # would leak into every later test in the process.
                self.assertEqual(protection.pattern, original)


class TestCanonicalSetMatchesTheSecurityDoc(unittest.TestCase):
    """The table and docs/security.md are the same list, in the same order."""

    def test_the_sixteen_patterns_appear_in_order_in_docs_security_md(self):
        """
        Given docs/security.md's "Recommended deny patterns" TOML block, which
        the module docstring and seed-hard-deny's help both name as the set
        this table mirrors
        When the quoted patterns in that block are read in document order
        Then the 16 canonical patterns appear in it as one contiguous run in
        table order -- so extending or trimming the table without touching the
        doc (or the reverse) fails here instead of drifting silently
        """
        self.assertTrue(_SECURITY_DOC.is_file(), f"missing doc: {_SECURITY_DOC}")
        doc = _SECURITY_DOC.read_text(encoding="utf-8")
        section = doc.split("## Recommended deny patterns", 1)
        self.assertEqual(len(section), 2, "doc section heading not found")
        block = section[1].split("```", 2)
        self.assertEqual(len(block), 3, "fenced TOML block not found in the section")
        documented = _QUOTED_PATTERN.findall(block[1])
        self.assertIn(
            _EXPECTED_PATTERNS[0], documented, "the canonical set is not in the block"
        )
        start = documented.index(_EXPECTED_PATTERNS[0])
        self.assertEqual(
            tuple(documented[start : start + len(_EXPECTED_PATTERNS)]),
            _EXPECTED_PATTERNS,
        )


def _hard_deny_config(deny_patterns, extra_layers=()):
    """
    Build a Configuration whose only deny source is a ``[hard_deny]`` pool.

    The normal cascade allows everything under the project root AND under home
    (``**`` is anchored to the project root, so it does not reach home), which
    makes the negative case reachable: a path the hard-deny pool misses comes
    back ``allow``, never ``ask``, so a dropped or narrowed pattern shows up as
    a decision flip rather than as an unrelated fallback.
    """
    layer = ConfigLayer(
        Provenance(
            "user",
            "toolguard_hook",
            "toml",
            Path("/isolated/home/.claude/toolguard_hook.toml"),
            10,
        ),
        MappingProxyType(
            {
                "governed_tools": ["Read", "Write", "Edit"],
                "permissions": {
                    "allow": [
                        "Read(**)",
                        "Write(**)",
                        "Edit(**)",
                        "Read(~/**)",
                        "Write(~/**)",
                        "Edit(~/**)",
                    ],
                    "deny": [],
                    "ask": [],
                },
                "hard_deny": {"deny": list(deny_patterns)},
            }
        ),
    )
    return Configuration(layers=tuple(extra_layers) + (layer,))


class TestRecommendedProtectionsBehavior(ConfigIsolationMixin, unittest.TestCase):
    """
    End-to-end through the live decision engine: what the canonical patterns
    actually block, and what they leave alone.
    """

    def setUp(self):
        self.home, self.project = self.isolate_config_environment()
        self.patterns = [p.pattern for p in required_hard_deny_patterns()]
        self.config = _hard_deny_config(self.patterns)

    def assert_hard_denied(self, tool, path, expected_pattern):
        """
        Assert the path is denied BY the named hard-deny pattern.

        The verdict alone does not say which rule denied: unlike the Bash path,
        resolve_file_path_permission_detailed deliberately leaves
        ``matched_rule`` None on a hard-deny, so the deciding pattern survives
        only in the prose reason -- or, as here, by asking the same production
        function the resolver itself calls.
        """
        verdict = decide(self.config, tool, str(path))
        self.assertEqual(verdict.decision, "deny", f"{tool} {path}")
        matched = check_file_path_hard_deny(tool, str(path), self.config, True)
        self.assertIsNotNone(matched, f"no hard_deny matched for {tool} {path}")
        self.assertEqual(matched.matched_pattern, expected_pattern)

    def assert_allowed(self, tool, path, expected_rule):
        """Assert the path is allowed by the fixture's own allow rule, not merely un-denied."""
        verdict = decide(self.config, tool, str(path))
        self.assertEqual(verdict.decision, "allow", f"{tool} {path}")
        self.assertEqual(verdict.matched_rule, expected_rule)

    def test_the_isolated_home_and_project_root_are_what_the_engine_resolves(self):
        """
        Given the isolation fixture's temporary home and project root
        When Path.home() and the Configuration's project root are read back
        Then both are the isolated directories -- every assertion below is
        anchored to them, so a patch that failed to take effect would silently
        measure the developer's real home instead
        """
        self.assertEqual(Path.home(), self.home)
        self.assertEqual(self.config.project_root, self.project)

    def test_every_home_anchored_pattern_denies_the_file_it_names(self):
        """
        Given the eight home-anchored (~/...) canonical patterns
        When a real secret path under the isolated home is evaluated for each
        Then it is denied, and denied by that exact pattern -- so removing or
        narrowing any one of the eight fails here
        """
        cases = [
            ("Read", self.home / ".env", "~/.env"),
            ("Read", self.home / ".env.production", "~/.env.*"),
            ("Read", self.home / ".aws" / "credentials", "~/.aws/**"),
            ("Read", self.home / ".ssh" / "id_rsa", "~/.ssh/**"),
            ("Write", self.home / ".env", "~/.env"),
            ("Write", self.home / ".aws" / "credentials", "~/.aws/**"),
            ("Write", self.home / ".ssh" / "id_rsa", "~/.ssh/**"),
            ("Edit", self.home / ".env", "~/.env"),
        ]
        for tool, path, expected in cases:
            with self.subTest(tool=tool, path=str(path)):
                self.assert_hard_denied(tool, path, expected)

    def test_every_relative_pattern_denies_the_file_it_names_inside_the_project(self):
        """
        Given the eight relative (**/...) canonical patterns, anchored to the
        active project root
        When a secret path inside the isolated project is evaluated for each
        Then it is denied by that exact pattern, both at the project root and
        in a nested directory
        """
        cases = [
            ("Read", self.project / ".env", "**/.env"),
            ("Read", self.project / "sub" / "deep" / ".env", "**/.env"),
            ("Read", self.project / ".env.local", "**/.env.*"),
            ("Read", self.project / ".aws" / "credentials", "**/.aws/**"),
            ("Read", self.project / "vendor" / ".ssh" / "id_rsa", "**/.ssh/**"),
            ("Write", self.project / ".env", "**/.env"),
            ("Write", self.project / ".aws" / "credentials", "**/.aws/**"),
            ("Write", self.project / ".ssh" / "id_rsa", "**/.ssh/**"),
            ("Edit", self.project / ".env", "**/.env"),
        ]
        for tool, path, expected in cases:
            with self.subTest(tool=tool, path=str(path)):
                self.assert_hard_denied(tool, path, expected)

    def test_the_family_patterns_cover_more_than_the_one_file_probed_above(self):
        """
        Given the six patterns that name a whole family rather than one file --
        ``.ssh/**``, ``.aws/**`` and ``.env.*``, in both anchoring forms
        When a SECOND member of each family is evaluated, differing from the
        probe above in both name and depth
        Then it is denied by that same pattern.

        Measured, not speculative: the two probes above pin each family with
        exactly one witness, so narrowing both forms together -- ``.ssh/**`` to
        ``.ssh/id_rsa``, or ``**`` to ``*`` -- leaves every one of them passing
        and hands a user a config that no longer protects the rest of the
        directory. Six such mutants survived the module before this test.
        """
        cases = [
            ("Read", self.home / ".ssh" / "nested" / "id_ed25519", "~/.ssh/**"),
            ("Write", self.home / ".ssh" / "nested" / "id_ed25519", "~/.ssh/**"),
            ("Read", self.home / ".aws" / "sso" / "cache" / "tok.json", "~/.aws/**"),
            ("Write", self.home / ".aws" / "sso" / "cache" / "tok.json", "~/.aws/**"),
            ("Read", self.home / ".env.staging", "~/.env.*"),
            ("Read", self.project / ".ssh" / "nested" / "id_ed25519", "**/.ssh/**"),
            ("Write", self.project / ".ssh" / "nested" / "id_ed25519", "**/.ssh/**"),
            (
                "Read",
                self.project / ".aws" / "sso" / "cache" / "tok.json",
                "**/.aws/**",
            ),
            (
                "Write",
                self.project / ".aws" / "sso" / "cache" / "tok.json",
                "**/.aws/**",
            ),
            ("Read", self.project / ".env.production", "**/.env.*"),
        ]
        for tool, path, expected in cases:
            with self.subTest(tool=tool, path=str(path)):
                self.assert_hard_denied(tool, path, expected)

    def test_an_unexpanded_tilde_target_is_denied_too(self):
        """
        Given a target written as '~/.ssh/id_rsa' rather than as an absolute path
        When it is evaluated
        Then it is denied by ~/.ssh/** -- the path side is tilde-expanded, so a
        caller passing the short form is not a way around the pattern
        """
        self.assert_hard_denied("Read", "~/.ssh/id_rsa", "~/.ssh/**")

    def test_unrelated_files_are_left_alone(self):
        """
        Given files that are not secrets -- a source file in the project, a note
        in home, and '.envelope', which a sloppy '.env*' pattern would swallow
        When each is evaluated
        Then each is ALLOWED by the fixture's own allow rule, so a pattern
        broadened to everything (or a '.env.*' written as '.env*') fails here
        """
        cases = [
            ("Read", self.project / "src" / "main.py", "**"),
            ("Read", self.home / "notes.txt", "~/**"),
            ("Read", self.home / ".envelope", "~/**"),
            ("Write", self.project / "README.md", "**"),
        ]
        for tool, path, expected_rule in cases:
            with self.subTest(tool=tool, path=str(path)):
                self.assert_allowed(tool, path, expected_rule)

    def test_a_more_specific_allow_does_not_override_the_hard_deny(self):
        """
        Given a project-level layer that explicitly ALLOWS ~/.ssh/** -- more
        specific than the user layer carrying the hard_deny
        When the SSH key is evaluated
        Then it is still denied by ~/.ssh/**: the hard_deny pool is checked
        before the cascade, which is the property the whole set relies on
        """
        project_layer = ConfigLayer(
            Provenance(
                "project",
                "toolguard_hook",
                "toml",
                self.project / ".claude" / "toolguard_hook.toml",
                0,
            ),
            MappingProxyType(
                {
                    "governed_tools": ["Read", "Write", "Edit"],
                    "permissions": {
                        "allow": ["Read(~/.ssh/**)"],
                        "deny": [],
                        "ask": [],
                    },
                }
            ),
        )
        self.config = _hard_deny_config(self.patterns, extra_layers=(project_layer,))
        self.assertEqual(len(self.config.layers), 2)
        self.assert_hard_denied("Read", self.home / ".ssh" / "id_rsa", "~/.ssh/**")

    def test_the_relative_patterns_alone_leave_the_real_home_unprotected(self):
        """
        Given only the eight relative patterns seeded -- the mistake
        docs/security.md records having been made for real ("an install once
        added only the relative patterns at user scope and ~/.ssh/id_rsa was
        not denied until the home-anchored patterns were added by hand")
        When a key under home and one inside the project are both evaluated
        Then the project copy is denied and ~/.ssh/id_rsa is ALLOWED -- this is
        the measured reason the table carries both forms, not a defect in the
        anchoring rule
        """
        relative_only = [p for p in self.patterns if "(**/" in p]
        self.assertEqual(len(relative_only), 12)
        self.config = _hard_deny_config(relative_only)
        self.assert_hard_denied("Read", self.project / ".ssh" / "id_rsa", "**/.ssh/**")
        self.assert_allowed("Read", self.home / ".ssh" / "id_rsa", "~/**")


class TestGapsInTheCanonicalSet(ConfigIsolationMixin, unittest.TestCase):
    """
    RED. Two sensitive-file exposures the canonical set does not cover today.

    Both are measured, not inferred: no pattern in the set matches, so the paths
    below fall through to the normal cascade -- 'allow' under this fixture's
    blanket allows, and 'ask' (measured) under a config that has none. Either
    way the outcome is whatever the surrounding config or the agent decides in
    the moment, which is the thing [hard_deny] exists so a protection does not
    depend on. Closing either one means adding patterns to
    recommended_protections.py, to _EXPECTED_PATTERNS above, and to
    docs/security.md in the same reviewed change.
    """

    def setUp(self):
        self.home, self.project = self.isolate_config_environment()
        self.config = _hard_deny_config(
            [p.pattern for p in required_hard_deny_patterns()]
        )

    def assert_denied(self, tool, path):
        """Assert the path is denied by some hard-deny pattern in the pool."""
        verdict = decide(self.config, tool, str(path))
        matched = check_file_path_hard_deny(tool, str(path), self.config, True)
        self.assertEqual(verdict.decision, "deny", f"{tool} {path}")
        self.assertIsNotNone(matched)

    def test_edit_is_denied_wherever_write_is_denied(self):
        """
        Given that Write of ~/.ssh/** and ~/.aws/** is hard-denied
        When the same files are evaluated for Edit -- a different tool name for
        the same capability, modifying the file in place
        Then they are hard-denied too: Edit is covered only for .env today, so
        appending a key to ~/.ssh/authorized_keys is not blocked by the set
        """
        for path in (
            self.home / ".ssh" / "authorized_keys",
            self.home / ".aws" / "credentials",
        ):
            with self.subTest(path=str(path)):
                self.assert_denied("Edit", path)

    def test_env_variants_are_write_protected_as_well_as_read_protected(self):
        """
        Given that reading .env.local / .env.production is hard-denied by the
        .env.* patterns, and that Write(.env) exists to stop a command
        "silently planting or altering secrets"
        When a write to ~/.env.local is evaluated
        Then it is hard-denied: only the exact .env name is write-protected
        today, so the same secret under a variant name can be planted freely
        """
        self.assert_denied("Write", self.home / ".env.local")


if __name__ == "__main__":
    unittest.main()
