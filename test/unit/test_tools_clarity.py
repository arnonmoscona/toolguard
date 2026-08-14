"""
Unit tests for the rule-interaction clarity analyzer (toolguard.tools.clarity):
the same-layer pairwise and multi-section detectors and the cross-layer one, each
checked for the finding it produces and for the cases it must not flag; plus the
deterministic ordering of the returned list and the scoping of a run to one tool.

Every negative case carries a positive control in the same fixture, so "no
confusing interaction here" is distinguishable from "nothing was examined".
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions


def _make_provenance(
    specificity: int = 0, name: str = "hook", native: bool = False
) -> Provenance:
    """
    Build a Provenance for tests, distinct in ``path`` for every (name, specificity).

    The distinct path is load-bearing, not cosmetic: ``Provenance`` is a frozen
    dataclass and ``config_access.per_layer_rules`` keys a dict by it, so two
    fixture layers sharing one provenance silently collapse into the later one
    and the earlier layer's rules never reach the analyzer.

    Args:
        specificity: Hierarchy distance from the project root (0 = most specific).
        name: Distinguishes layers at the same specificity.
        native: Build a native Claude settings layer instead of a toolguard one.
    """
    if native:
        return Provenance(
            level="project",
            source_type="claude",
            file_format="json",
            path=Path(f"/fake/{name}-{specificity}/.claude/settings.json"),
            specificity=specificity,
        )
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(f"/fake/{name}-{specificity}/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _make_raw_layer(
    provenance: Provenance,
    allow: List[str],
    deny: List[str],
    ask: List[str],
) -> ConfigLayer:
    """Build a ConfigLayer from already-wrapped ``Tool(body)`` patterns."""
    return ConfigLayer(
        provenance=provenance,
        content=MappingProxyType(
            {"permissions": {"allow": allow, "deny": deny, "ask": ask}}
        ),
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """Build a ConfigLayer with wrapped allow/deny/ask bodies for ``tool``."""
    prefix = f"{tool}("
    return _make_raw_layer(
        provenance or _make_provenance(),
        [f"{prefix}{p})" for p in (allow or [])],
        [f"{prefix}{p})" for p in (deny or [])],
        [f"{prefix}{p})" for p in (ask or [])],
    )


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

    def test_only_the_overlapping_pair_of_a_mixed_layer_is_flagged(self):
        """
        Given one layer holding an overlapping allow/deny pair ('uv run alembic:*'
            under 'uv run:*') alongside an allow and a deny that overlap nothing
        When find_confusing_interactions runs
        Then exactly the overlapping pair is reported -- the non-overlapping rules
            were examined and correctly produced nothing.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git diff:*", "uv run alembic:*"],
                deny=["npm install:*", "uv run:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.allow_pattern, f.guard_pattern) for f in findings],
            [("uv run alembic:*", "uv run:*")],
        )

    def test_non_default_guard_is_skipped_while_a_default_guard_is_flagged(self):
        """
        Given two allows in one layer, one guarded by a [glob] deny and the other
            by an equivalent DEFAULT deny
        When find_confusing_interactions runs
        Then only the DEFAULT pair is reported: a guard outside DEFAULT syntax has
            no prefix-comparable command-space and takes no part.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*", "npm ci install:*"],
                deny=["[glob]uv run:*", "npm ci:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.allow_pattern, f.guard_pattern) for f in findings],
            [("npm ci install:*", "npm ci:*")],
        )

    def test_args_bearing_guard_is_skipped_while_a_prefix_guard_is_flagged(self):
        """
        Given two allows in one layer, one guarded by a deny carrying an args part
            ('uv run:-x *') and the other by a bare-prefix deny
        When find_confusing_interactions runs
        Then only the bare-prefix pair is reported: a guard whose args part is
            anything but '*'/'**' is not a command prefix.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*", "npm ci install:*"],
                deny=["uv run:-x *", "npm ci:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.allow_pattern, f.guard_pattern) for f in findings],
            [("npm ci install:*", "npm ci:*")],
        )

    def test_only_the_requested_tools_rules_are_examined(self):
        """
        Given one layer holding an overlapping allow/deny pair for Bash and a
            different overlapping pair for a governed MCP tool
        When find_confusing_interactions runs for each tool in turn
        Then each run reports only its own tool's pair. The analyzer is scoped by
            its argument, not to the first-party built-ins.
        """
        mcp_tool = "mcp__jetbrains__execute_terminal_command"
        config = _make_config(
            _make_raw_layer(
                _make_provenance(),
                allow=["Bash(git:*)", f"{mcp_tool}(uv run alembic:*)"],
                deny=["Bash(git push:*)", f"{mcp_tool}(uv run:*)"],
                ask=[],
            )
        )
        self.assertEqual(
            [
                (f.tool, f.allow_pattern, f.guard_pattern)
                for f in find_confusing_interactions(config, "Bash")
            ],
            [("Bash", "git:*", "git push:*")],
        )
        self.assertEqual(
            [
                (f.tool, f.allow_pattern, f.guard_pattern)
                for f in find_confusing_interactions(config, mcp_tool)
            ],
            [(mcp_tool, "uv run alembic:*", "uv run:*")],
        )


class TestNativeLayerInteractions(unittest.TestCase):
    """A native Claude settings layer's rules must be analyzed like any other."""

    def test_native_deny_overlapping_a_native_allow_is_flagged(self):
        """
        Given a native settings layer whose allow 'git push origin:*' is overlapped
            by its own deny 'git push:*'
        When find_confusing_interactions runs for Bash
        Then a 'deny-shadows-allow' finding is produced -- the control showing a
            native layer does reach the analyzer.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git push origin:*"],
                deny=["git push:*"],
                provenance=_make_provenance(native=True),
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.kind, f.guard_pattern) for f in findings],
            [("deny-shadows-allow", "git push:*")],
        )

    def test_native_ask_overlapping_a_native_allow_is_flagged(self):
        """
        Given a native settings layer whose allow 'git push origin:*' is overlapped
            by its own ask 'git push:*'
        When find_confusing_interactions runs for Bash
        Then an 'ask-overlaps-allow' finding is produced. Claude's settings.json
            has an ask list and the resolver decides on it, so an ask there is as
            capable of confusing a reader as one in a toolguard file.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git push origin:*"],
                ask=["git push:*"],
                provenance=_make_provenance(native=True),
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.kind, f.guard_pattern) for f in findings],
            [("ask-overlaps-allow", "git push:*")],
        )


class TestMultiSectionInteraction(unittest.TestCase):
    """An allow overlapping BOTH a deny and an ask in one file is called out."""

    def test_allow_overlapping_deny_and_ask_flags_multi_section(self):
        """
        Given a same-file allow 'git:*' overlapping both deny 'git push:*' and ask
            'git commit:*'
        When find_confusing_interactions runs for Bash
        Then a 'multi-section-interaction' finding is produced (alongside the
            pairwise findings) whose explanation names both guards
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git:*"],
                deny=["git push:*"],
                ask=["git commit:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        kinds = {f.kind for f in findings}
        self.assertIn("multi-section-interaction", kinds)
        ms = next(f for f in findings if f.kind == "multi-section-interaction")
        self.assertEqual(ms.guard_section, "deny+ask")
        self.assertIn("git push:*", ms.explanation)
        self.assertIn("git commit:*", ms.explanation)

    def test_allow_overlapping_only_one_section_has_no_multi_section(self):
        """
        Given an allow overlapping only a deny (no ask overlap)
        When find_confusing_interactions runs
        Then the pairwise deny finding is produced and no
            'multi-section-interaction' finding is
        """
        config = _make_config(_make_layer("Bash", allow=["git:*"], deny=["git push:*"]))
        kinds = {f.kind for f in find_confusing_interactions(config, "Bash")}
        self.assertIn("deny-shadows-allow", kinds)
        self.assertNotIn("multi-section-interaction", kinds)

    def test_one_multi_section_finding_per_allow_however_many_guards(self):
        """
        Given an allow 'git:*' overlapping two denies and two asks in its layer
        When find_confusing_interactions runs
        Then all four pairwise findings are produced but the multi-section summary
            appears once -- it summarises the allow, not each guard pair.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git:*"],
                deny=["git push:*", "git reset:*"],
                ask=["git commit:*", "git rebase:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        kinds = [f.kind for f in findings]
        self.assertEqual(kinds.count("deny-shadows-allow"), 2)
        self.assertEqual(kinds.count("ask-overlaps-allow"), 2)
        self.assertEqual(kinds.count("multi-section-interaction"), 1)


class TestCrossLayerInteraction(unittest.TestCase):
    """An allow whose verdict depends on a guard in another layer is flagged."""

    def _two_layer(self, project_kwargs, user_kwargs):
        """Build a project (specificity 0) over user (specificity 1) config."""

        def mk(spec, kw):
            """Build one Bash layer at ``spec`` from an allow/deny/ask kwargs dict."""
            return _make_layer(
                "Bash",
                kw.get("allow", []),
                deny=kw.get("deny"),
                ask=kw.get("ask"),
                provenance=_make_provenance(spec),
            )

        return _make_config(mk(0, project_kwargs), mk(1, user_kwargs))

    def _cross_layer(self, config):
        """Return only the 'cross-layer-dependent' findings for Bash."""
        return [
            f
            for f in find_confusing_interactions(config, "Bash")
            if f.kind == "cross-layer-dependent"
        ]

    def test_more_specific_allow_overrides_broader_deny_across_layers(self):
        """
        Given a project allow 'git:*' and a broader user deny 'git push:*'
        When find_confusing_interactions runs
        Then a 'cross-layer-dependent' finding says the more-specific allow OVERRIDES
            the broader deny, and carries the deny's layer as guard_provenance
        """
        config = self._two_layer({"allow": ["git:*"]}, {"deny": ["git push:*"]})
        findings = self._cross_layer(config)
        self.assertEqual(len(findings), 1)
        self.assertIn("OVERRIDES", findings[0].explanation)
        self.assertEqual(findings[0].guard_section, "deny")
        self.assertEqual(findings[0].guard_provenance.specificity, 1)

    def test_more_specific_deny_wins_over_broader_allow_across_layers(self):
        """
        Given a project deny 'git push:*' and a broader user allow 'git:*'
        When find_confusing_interactions runs
        Then a 'cross-layer-dependent' finding says the more-specific deny WINS
        """
        config = self._two_layer({"deny": ["git push:*"]}, {"allow": ["git:*"]})
        findings = self._cross_layer(config)
        self.assertEqual(len(findings), 1)
        self.assertIn("WINS", findings[0].explanation)

    def test_more_specific_ask_gates_broader_allow_across_layers(self):
        """
        Given a project ask 'git push:*' and a broader user allow 'git:*'
        When find_confusing_interactions runs
        Then a 'cross-layer-dependent' finding says the more-specific ask GATES the
            allow into a prompt
        """
        config = self._two_layer({"ask": ["git push:*"]}, {"allow": ["git:*"]})
        findings = self._cross_layer(config)
        self.assertEqual(len(findings), 1)
        self.assertIn("GATES", findings[0].explanation)

    def test_more_specific_allow_bypasses_broader_ask_across_layers(self):
        """
        Given a project allow 'git:*' and a broader user ask 'git push:*'
        When find_confusing_interactions runs
        Then a 'cross-layer-dependent' finding says the more-specific allow BYPASSES
            the broader ask
        """
        config = self._two_layer({"allow": ["git:*"]}, {"ask": ["git push:*"]})
        findings = self._cross_layer(config)
        self.assertEqual(len(findings), 1)
        self.assertIn("BYPASSES", findings[0].explanation)

    def test_same_specificity_layers_are_not_cross_layer(self):
        """
        Given two layers of the SAME specificity in different files, the first
            holding an allow 'git:*' and its own deny 'git rebase:*', the second an
            overlapping deny 'git push:*'
        When find_confusing_interactions runs
        Then the first layer's own overlap is reported and no
            'cross-layer-dependent' finding is: same-specificity layers resolve as
            one level, not as a cross-level dependency.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                ["git:*"],
                deny=["git rebase:*"],
                provenance=_make_provenance(0, "a"),
            ),
            _make_layer(
                "Bash", [], deny=["git push:*"], provenance=_make_provenance(0, "b")
            ),
        )
        kinds = {f.kind for f in find_confusing_interactions(config, "Bash")}
        self.assertIn("deny-shadows-allow", kinds)
        self.assertEqual(self._cross_layer(config), [])


class TestFindingOrder(unittest.TestCase):
    """
    The returned list is ordered by kind, then allow pattern, then guard pattern,
    then the allow's layer, then the guard's layer.

    Every fixture here is built so that INSERTION order does not already satisfy
    the assertion -- otherwise a deleted or constant sort key passes.
    """

    def test_findings_are_ordered_by_kind(self):
        """
        Given a configuration producing one finding of each of the four kinds, in
            an insertion order (deny, ask, multi-section, cross-layer) that is not
            the sorted one
        When find_confusing_interactions runs
        Then the findings come back ordered by kind.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git:*"],
                deny=["git push:*"],
                ask=["git commit:*"],
                provenance=_make_provenance(0, "project"),
            ),
            _make_layer(
                "Bash",
                [],
                deny=["git rebase:*"],
                provenance=_make_provenance(1, "user"),
            ),
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [f.kind for f in findings],
            [
                "ask-overlaps-allow",
                "cross-layer-dependent",
                "deny-shadows-allow",
                "multi-section-interaction",
            ],
        )

    def test_findings_of_one_kind_are_ordered_by_allow_then_guard_pattern(self):
        """
        Given one layer whose two allows and two denies produce three
            'deny-shadows-allow' findings, inserted guard-major
        When find_confusing_interactions runs
        Then they come back ordered by allow pattern and, within an allow, by
            guard pattern.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git:*", "git push origin:*"],
                deny=["git push:*", "git checkout:*"],
            )
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [(f.allow_pattern, f.guard_pattern) for f in findings],
            [
                ("git push origin:*", "git push:*"),
                ("git:*", "git checkout:*"),
                ("git:*", "git push:*"),
            ],
        )

    def test_findings_alike_but_for_their_layer_are_ordered_by_provenance(self):
        """
        Given two same-specificity layers carrying identical rules, the
            alphabetically LATER file first
        When find_confusing_interactions runs
        Then the two otherwise-identical findings come back ordered by the layer
            that holds the allow.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["npm:*"],
                deny=["npm run:*"],
                provenance=_make_provenance(0, "zeta"),
            ),
            _make_layer(
                "Bash",
                allow=["npm:*"],
                deny=["npm run:*"],
                provenance=_make_provenance(0, "alpha"),
            ),
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [f.provenance.path.as_posix() for f in findings],
            [
                "/fake/alpha-0/.claude/toolguard_hook.toml",
                "/fake/zeta-0/.claude/toolguard_hook.toml",
            ],
        )

    def test_cross_layer_findings_are_ordered_by_guard_provenance(self):
        """
        Given one allow overlapped by the SAME guard pattern in two less-specific
            layers, the alphabetically later file first
        When find_confusing_interactions runs
        Then the two cross-layer findings -- identical but for which layer holds
            the guard -- come back ordered by guard provenance.
        """
        config = _make_config(
            _make_layer("Bash", allow=["pip:*"], provenance=_make_provenance(0, "p")),
            _make_layer(
                "Bash",
                [],
                deny=["pip install:*"],
                provenance=_make_provenance(2, "zeta"),
            ),
            _make_layer(
                "Bash",
                [],
                deny=["pip install:*"],
                provenance=_make_provenance(1, "alpha"),
            ),
        )
        findings = find_confusing_interactions(config, "Bash")
        self.assertEqual(
            [f.guard_provenance.path.as_posix() for f in findings],
            [
                "/fake/alpha-1/.claude/toolguard_hook.toml",
                "/fake/zeta-2/.claude/toolguard_hook.toml",
            ],
        )


if __name__ == "__main__":
    unittest.main()
