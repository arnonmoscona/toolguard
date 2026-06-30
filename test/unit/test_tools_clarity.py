"""
Unit tests for the rule-interaction clarity analyzer (toolguard.tools.clarity).

These verify the first detector: a DEFAULT allow rule whose command-space
overlaps a deny or ask rule in the same config layer is flagged with a calibrated
explanation, while non-overlapping or non-DEFAULT rules are not.
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions


def _make_provenance(specificity: int = 0) -> Provenance:
    """Build a minimal project-level Provenance for tests."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """Build a ConfigLayer with wrapped allow/deny/ask bodies for ``tool``."""
    provenance = provenance or _make_provenance()
    prefix = f"{tool}("
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"{prefix}{p})" for p in (allow or [])],
                "deny": [f"{prefix}{p})" for p in (deny or [])],
                "ask": [f"{prefix}{p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=provenance, content=content)


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


class TestFindConfusingInteractions(unittest.TestCase):
    """Detection of confusing same-file allow/guard overlaps."""

    def test_deny_overlapping_allow_is_flagged(self):
        """
        Given a same-file allow 'uv run alembic upgrade:*' and a broader deny
            'uv run:*' whose command-space overlaps it
        When find_confusing_interactions runs for Bash
        Then a 'deny-shadows-allow' finding names both rules and its explanation
            states the deny wins.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*"],
                deny=["uv run:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIsInstance(finding, InteractionFinding)
        self.assertEqual(finding.kind, "deny-shadows-allow")
        self.assertEqual(finding.guard_pattern, "uv run:*")
        self.assertEqual(finding.allow_pattern, "uv run alembic upgrade:*")
        self.assertIn("DENY wins", finding.explanation)

    def test_ask_overlapping_allow_is_flagged(self):
        """
        Given a same-file allow 'git push origin:*' and an ask 'git push:*' that
            overlaps it
        When find_confusing_interactions runs for Bash
        Then an 'ask-overlaps-allow' finding is produced for the pair.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git push origin:*"],
                ask=["git push:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "ask-overlaps-allow")
        self.assertEqual(findings[0].guard_section, "ask")

    def test_non_overlapping_rules_produce_no_finding(self):
        """
        Given an allow and a deny whose command prefixes do not overlap
            (different first command token)
        When find_confusing_interactions runs
        Then no interaction findings are produced.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git diff:*"],
                deny=["npm install:*"],
            )
        )
        self.assertEqual(find_confusing_interactions(config, "Bash"), [])

    def test_non_default_guard_is_skipped(self):
        """
        Given an allow and a deny expressed as a non-DEFAULT [regex] pattern
        When find_confusing_interactions runs
        Then the non-DEFAULT guard is not prefix-comparable and no finding is made.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*"],
                deny=["[regex]^uv run"],
            )
        )
        self.assertEqual(find_confusing_interactions(config, "Bash"), [])


if __name__ == "__main__":
    unittest.main()
