"""Tests for the compound/resolve seam: ``RuntimeVerdict.sub_matches`` content
and order, the ask-floor fallback matrix, and ``judge_unit``'s invariants."""

import unittest
from pathlib import Path
from types import MappingProxyType

from toolguard.compound import (
    CommandUnit,
    ResolveOneResult,
    _resolve_leaf,
    _unit_for,
    _unit_from_result,
    decompose,
    judge_unit,
)
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.parser.command_extractor import LeafCommand
from toolguard.resolve import resolve_bash_permission_detailed
from toolguard.rule_entry import ADDITIONAL_CONTEXT_KEY


def _make_config(layers_content):
    """Build a Configuration from ``(level, source_type, content_dict)`` tuples --
    index 0 is the MOST specific level."""
    layers = []
    for i, (level, source_type, content) in enumerate(layers_content):
        prov = Provenance(
            level=level,
            source_type=source_type,
            file_format="toml",
            path=Path(f"/fake/{level}/{source_type}"),
            specificity=i,
        )
        layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(layers), start_dir=None)


def _config(allow=(), deny=(), hard_deny=(), fallback="ask"):
    """Return a single-level Configuration with the given Bash patterns."""
    content = {
        "undecidable_fallback": fallback,
        "permissions": {
            "allow": [f"Bash({p})" for p in allow],
            "deny": [f"Bash({p})" for p in deny],
        },
        "hard_deny": {"deny": [f"Bash({p})" for p in hard_deny], "allow": []},
    }
    return _make_config([("project", "toolguard_hook", content)])


def _resolve(config, command):
    """Resolve *command* through :func:`resolve_bash_permission_detailed`."""
    hd_deny, hd_allow = config.hard_deny("Bash")
    return resolve_bash_permission_detailed(command, config, True, hd_deny, hd_allow)


def _shape(sub_match):
    """Project a UnitVerdict down to the four fields this module pins."""
    return (
        sub_match.sub_command,
        sub_match.decision,
        sub_match.matched_rule,
        sub_match.fallback_kind,
    )


class TestSubMatchesCharacterization(unittest.TestCase):
    """Pin ``RuntimeVerdict.sub_matches`` content and order."""

    def test_single_plain_command(self):
        """
        Given a single non-compound command matching an allow pattern
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has exactly one entry, the genuine rule match, and the
            verdict attributes that same rule -- 'allow' alone would also be
            produced by a no-rule fallback, which carries matched_rule None
        """
        config = _config(allow=["git *"])
        result = _resolve(config, "git status")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "git *")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [("git status", "allow", "git *", None)],
        )

    def test_multi_part_plain_leaf(self):
        """
        Given a '&&'-chained compound of two plain commands (decompose splits
            this into two separate 'plain' units, each with one part)
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has one entry per sub-command, in order
        """
        config = _config(allow=["git *", "ls*"])
        result = _resolve(config, "git status && ls")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [
                ("git status", "allow", "git *", None),
                ("ls", "allow", "ls*", None),
            ],
        )

    def test_multi_leaf_multi_line(self):
        """
        Given two newline-separated commands (two separate leaves)
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has one entry per leaf, in order
        """
        config = _config(allow=["git *", "ls*"])
        result = _resolve(config, "git status\nls -la")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [
                ("git status", "allow", "git *", None),
                ("ls -la", "allow", "ls*", None),
            ],
        )

    def test_ask_floor_leaf_under_each_fallback(self):
        """
        Given a foreign inline-code leaf resolved under each of the four
            undecidable_fallback values
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has exactly one entry, keyed to the leaf's real,
            full text (never the truncated outer-command stub), with
            matched_rule always None (an escape hatch, never a genuine
            attribution) and fallback_kind naming the escape hatch
        """
        command = 'python3 -c "import os"'
        expected = {
            "ask": ("ask", None, None),
            "deny": ("deny", None, "denied"),
            "allow_with_warning": ("allow", None, "warned"),
            "allow": ("allow", None, "silent"),
        }
        for fallback, (decision, matched_rule, fallback_kind) in expected.items():
            with self.subTest(fallback=fallback):
                config = _config(allow=["python3 -c:*"], fallback=fallback)
                result = _resolve(config, command)
                self.assertEqual(result.decision, decision)
                self.assertEqual(
                    [_shape(sm) for sm in result.sub_matches],
                    [(command, decision, matched_rule, fallback_kind)],
                )

    def test_undecidable_segment_plus_plain_leaf(self):
        """
        Given a command mixing an undecidable process-substitution segment
            with a plain trailing leaf, the segment deliberately longer than
            the 80-character slice judge_unit uses for its REASON text
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has TWO entries, in order: the judged undecidable
            segment -- keyed to its real, full text, never the 80-character
            display slice -- then the plain leaf's own genuine match
        """
        segment = "diff <(cat " + "a" * 100 + ") <(cat b)"
        self.assertGreater(len(segment), 80, "fixture must exceed the display slice")
        # No 'diff*' rule: an undecidable unit has no parts, so no rule is ever
        # consulted for it. Including one would imply it was evaluated and lost.
        config = _config(allow=["ls*"])
        result = _resolve(config, f"{segment} && ls -la")
        self.assertEqual(result.decision, "ask")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [
                (segment, "ask", None, None),
                ("ls -la", "allow", "ls*", None),
            ],
        )

    def test_hard_denied_sub_command(self):
        """
        Given a command matching the unoverridable hard_deny pool
        When resolve_bash_permission_detailed resolves it
        Then sub_matches has exactly one entry, a genuine attribution to the
            matched hard_deny PATTERN (not the command text, which shares the
            'rm -rf' prefix), and the verdict attributes that same pattern --
            'deny' alone is also what a total extraction failure produces,
            and that path carries matched_rule None
        """
        config = _config(hard_deny=["rm -rf*"])
        result = _resolve(config, "rm -rf /")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "rm -rf*")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [("rm -rf /", "deny", "rm -rf*", None)],
        )

    def test_ask_floor_leaf_does_not_leak_the_stubs_additional_context(self):
        """
        Given an ASK-floor leaf whose outer-command stub matches an allow rule
            carrying additionalContext
        When resolve_bash_permission_detailed floors the leaf to 'ask'
        Then neither the sub_match nor the verdict carries that enrichment --
            the floor decided, and the stub's rule never read the leaf's real
            content, so its explanatory text must not describe the outcome
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(python3 -c:*)",
                                    ADDITIONAL_CONTEXT_KEY: "stub context",
                                }
                            ],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = _resolve(config, 'python3 -c "import os"')
        self.assertEqual(result.decision, "ask")
        self.assertIsNone(result.additional_context)
        self.assertEqual(len(result.sub_matches), 1)
        self.assertIsNone(result.sub_matches[0].additional_context)

    def test_mixed_genuine_and_escape_hatch_allow_attributes_only_the_rule(self):
        """
        Given a compound whose first leaf allows by a genuine rule match and
            whose second is an ASK-floor leaf allowed by
            undecidable_fallback=allow (an escape hatch, not a rule)
        When resolve_bash_permission_detailed resolves it
        Then the verdict attributes the ONE genuine rule; the escape-hatch
            leaf is excluded from the search for a single decider, so it
            neither supplies an attribution nor cancels the genuine one
        """
        config = _config(allow=["ls*", "python3 -c:*"], fallback="allow")
        result = _resolve(config, 'ls -la && python3 -c "import os"')
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "ls*")
        self.assertEqual(
            [_shape(sm) for sm in result.sub_matches],
            [
                ("ls -la", "allow", "ls*", None),
                ('python3 -c "import os"', "allow", None, "silent"),
            ],
        )

    def test_while_loop_condition_reaches_sub_matches(self):
        """
        Given a 'while' loop whose CONDITION is a denied command
            ('while rm -rf /tmp/x; do :; done' under a Bash(rm *) deny rule)
        When resolve_bash_permission_detailed resolves it
        Then the condition appears in sub_matches and the compound is denied,
            exactly as the same command bare is denied
        """
        config = _config(allow=["*"], deny=["rm *"])
        result = _resolve(config, "while rm -rf /tmp/x; do :; done")
        self.assertIn("rm -rf /tmp/x", [sm.sub_command for sm in result.sub_matches])
        self.assertEqual(result.decision, "deny")


class TestAskFloorFallbackMatrix(unittest.TestCase):
    """Exhaustive {stub decision} x {undecidable_fallback} grid for an ask-floor
    leaf, against :func:`~toolguard.compound._apply_undecidable_floor`'s table."""

    _FALLBACKS = ("ask", "deny", "allow_with_warning", "allow")

    def _leaf(self, text='python -c "import os"'):
        """Return an ASK-floor LeafCommand for *text*."""
        return LeafCommand(text, ask_floor=True)

    def test_stub_deny_always_wins_regardless_of_fallback(self):
        """
        Given an ASK-floor leaf whose outer-command stub matches an explicit
            deny rule
        When _resolve_leaf resolves it under each undecidable_fallback value
        Then the decision is always 'deny', with the stub's own reason
             passed through unchanged (a genuine rule match, not floored)
        """

        def resolve_one(_cmd):
            return ResolveOneResult("deny", "matched deny pattern", None)

        for fallback in self._FALLBACKS:
            with self.subTest(fallback=fallback):
                verdict = _resolve_leaf(self._leaf(), resolve_one, fallback)
                self.assertEqual(verdict.decision, "deny")
                self.assertEqual(verdict.reason, "matched deny pattern")

    def test_stub_ask_under_each_fallback(self):
        """
        Given an ASK-floor leaf whose outer-command stub matches an explicit
            ask rule
        When _resolve_leaf resolves it under each undecidable_fallback value
        Then the decision follows _apply_undecidable_floor("ask", fallback)
             exactly -- 'ask' floors to 'deny' only under
             undecidable_fallback='deny'; every other value leaves the
             rule's own 'ask' unchanged (a floor can only ever raise
             strictness, and 'ask' already outranks 'allow')
        """
        expected = {
            "ask": "ask",
            "deny": "deny",
            "allow_with_warning": "ask",
            "allow": "ask",
        }

        def resolve_one(_cmd):
            return ResolveOneResult("ask", "matched ask pattern", None)

        for fallback, want in expected.items():
            with self.subTest(fallback=fallback):
                verdict = _resolve_leaf(self._leaf(), resolve_one, fallback)
                self.assertEqual(verdict.decision, want)
                if want == "ask":
                    self.assertEqual(verdict.reason, "matched ask pattern")
                else:
                    self.assertIn("undecidable_fallback=deny", verdict.reason)

    def test_stub_allow_under_each_fallback(self):
        """
        Given an ASK-floor leaf whose outer-command stub matches an explicit
            allow rule (or matches nothing)
        When _resolve_leaf resolves it under each undecidable_fallback value
        Then the decision follows _apply_undecidable_floor("allow", fallback)
             exactly, and the reason names the floor/escape-hatch that
             decided (never the stub's own rule match, which never verified
             the leaf's real content)
        """
        expected = {
            "ask": ("ask", "ASK floor applied"),
            "deny": ("deny", "undecidable_fallback=deny"),
            "allow_with_warning": ("allow", "Allowed with a warning"),
            "allow": ("allow", "Allowed with no warning"),
        }

        def resolve_one(_cmd):
            return ResolveOneResult("allow", "matched allow pattern", None)

        for fallback, (want_decision, want_substring) in expected.items():
            with self.subTest(fallback=fallback):
                verdict = _resolve_leaf(self._leaf(), resolve_one, fallback)
                self.assertEqual(verdict.decision, want_decision)
                self.assertIn(want_substring, verdict.reason)


class TestAskFloorStubOverrideNeverLeaks(unittest.TestCase):
    """An ask-floor leaf's outer-command-stub-level allow-over-deny override must
    produce ZERO entries in the compound's own ``RuntimeVerdict.overrides``."""

    def test_stub_override_does_not_leak_into_compound_overrides(self):
        """
        Given a more-specific level allowing 'python *' and a less-specific
            level denying 'python *', an ASK-floor leaf whose outer command
            stub is 'python -c' (matches both), and
            undecidable_fallback='allow' so the leaf resolves to 'allow'
        When resolve_bash_permission_detailed resolves the leaf
        Then the outer stub's own allow-over-deny override (a real
            ConflictOverride at the per-level layer) does NOT appear in the
            returned RuntimeVerdict.overrides -- the floor, not the stub's
            cascade result, decides this leaf, and the probe must stay
            invisible
        """
        # undecidable_fallback='allow' is load-bearing, not incidental. Under
        # the default 'ask' the verdict is non-allow, and resolve.py clears
        # overrides wholesale for any non-allow decision -- so the list would
        # be empty whether or not the audits_as_one gate exists, and this
        # test could not fail. Forcing 'allow' leaves the gate as the only
        # thing keeping it empty.
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": "allow",
                        "permissions": {"allow": ["Bash(python *)"], "deny": []},
                    },
                ),
                (
                    "user",
                    "toolguard_hook",
                    {"permissions": {"allow": [], "deny": ["Bash(python *)"]}},
                ),
            ]
        )
        result = _resolve(config, 'python -c "import os"')
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.overrides, [])


class TestUnitFromResult(unittest.TestCase):
    """``_unit_from_result``'s own unit tests.

    Superseded ``TestUnitFromTuple`` (TOO-45 ticket 38): the old class pinned
    ``_unit_from_tuple`` deriving ``fallback_kind`` by substring-matching
    canned reason text via the now-deleted ``fallback_kind_for_reason`` --
    exactly the prose-parsing anti-pattern the ticket removes. The
    replacement pins the new contract instead: ``fallback_kind`` is read
    from the caller-supplied :class:`ResolveOneResult` verbatim, never
    derived from *reason*.
    """

    def test_wraps_a_plain_allow_result(self):
        """
        Given an allow ResolveOneResult with no fallback_kind
        When _unit_from_result adapts it
        Then the resulting UnitVerdict carries the sub_command, decision,
             reason, and additional_context verbatim, with matched_rule,
             provenance, and fallback_kind all None
        """
        unit = _unit_from_result(
            "git status",
            ResolveOneResult("allow", "Command matches allow pattern: git *", "note"),
        )
        self.assertEqual(unit.sub_command, "git status")
        self.assertEqual(unit.decision, "allow")
        self.assertEqual(unit.reason, "Command matches allow pattern: git *")
        self.assertEqual(unit.additional_context, "note")
        self.assertIsNone(unit.matched_rule)
        self.assertIsNone(unit.provenance)
        self.assertIsNone(unit.fallback_kind)

    def test_fallback_kind_is_read_verbatim_never_derived_from_reason(self):
        """
        Given a ResolveOneResult whose fallback_kind is explicitly 'warned',
            but whose reason text names NO recognizable fallback wording at
            all (a reason a substring classifier could never have matched)
        When _unit_from_result adapts it
        Then fallback_kind is still 'warned' -- proving the value is read
            from the caller's own field, not re-derived from *reason*
        """
        unit = _unit_from_result(
            "rm -rf /tmp/x",
            ResolveOneResult("allow", "some arbitrary reason text", None, "warned"),
        )
        self.assertEqual(unit.fallback_kind, "warned")

    def test_fallback_kind_none_stays_none_even_with_matching_reason_text(self):
        """
        Given a ResolveOneResult whose reason text happens to contain the
            OLD marker substring the deleted classifier used to match, but
            whose fallback_kind field is None
        When _unit_from_result adapts it
        Then fallback_kind is None -- the reason text is never consulted
        """
        unit = _unit_from_result(
            "rm -rf /tmp/x",
            ResolveOneResult(
                "allow",
                "No allow pattern matched; allowed anyway "
                "(no_match_fallback=allow_with_warning)",
                None,
                None,
            ),
        )
        self.assertIsNone(unit.fallback_kind)


class TestJudgeUnitInvariants(unittest.TestCase):
    """``judge_unit``'s two failure modes -- a positional-length mismatch between
    ``part_verdicts`` and ``unit.parts``, and an unrecognized ``CommandUnit.kind``
    -- its two fail-closed defaults, and the ``_unit_for``/``decompose`` mapping
    that produces the units it judges."""

    def test_raises_on_part_verdicts_length_mismatch(self):
        """
        Given a 'plain' CommandUnit with two parts
        When judge_unit is called with only one part_verdict
        Then it raises ValueError rather than silently misattributing
        """
        unit = CommandUnit(
            text="git status && ls",
            kind="plain",
            parts=("git status", "ls"),
            audits_as_one=False,
        )
        only_one = [
            _unit_from_result("git status", ResolveOneResult("allow", "matched", None)),
        ]
        with self.assertRaises(ValueError):
            judge_unit(unit, only_one)

    def test_raises_on_unrecognized_kind(self):
        """
        Given a CommandUnit whose kind is not one of the four judge_unit
            recognizes
        When judge_unit is called
        Then it raises ValueError rather than falling through to a default
        """
        unit = CommandUnit(
            text="whatever", kind="mystery", parts=(), audits_as_one=False
        )
        with self.assertRaises(ValueError):
            judge_unit(unit, [])

    def test_empty_plain_unit_fails_closed_to_deny(self):
        """
        Given a 'plain' CommandUnit whose grammar extraction produced no parts
        When judge_unit judges it with no part_verdicts
        Then it denies -- a defensive fail-closed default, so a leaf nothing
            could be resolved for can never reach the shell unjudged
        """
        unit = CommandUnit(text="$(:)", kind="plain", parts=(), audits_as_one=False)
        verdict = judge_unit(unit, [])
        self.assertEqual(verdict.decision, "deny")
        self.assertEqual(verdict.reason, "No valid commands found in leaf")
        self.assertIsNone(verdict.matched_rule)
        self.assertIsNone(verdict.fallback_kind)

    def test_unknown_kind_unit_resolves_to_ask(self):
        """
        Given the defensive 'unknown' CommandUnit kind
        When judge_unit judges it
        Then it asks, with no rule attributed -- an extraction result of
            neither known type is never silently allowed
        """
        unit = CommandUnit(
            text="whatever", kind="unknown", parts=(), audits_as_one=False
        )
        verdict = judge_unit(unit, [])
        self.assertEqual(verdict.decision, "ask")
        self.assertEqual(verdict.reason, "Unknown extraction result; cannot verify")
        self.assertIsNone(verdict.matched_rule)

    def test_unit_for_maps_ask_floor_leaf_to_inline_code_with_untruncated_stub(self):
        """
        Given a LeafCommand with ask_floor=True and a long inline-code payload
        When _unit_for maps it via decompose's own mapping function
        Then kind is 'inline_code', audits_as_one is True, and parts holds
             exactly the UNTRUNCATED outer-command stub
        """
        leaf = LeafCommand('python -c "import os; ' + "x" * 200 + '"', ask_floor=True)
        unit = _unit_for(leaf)
        self.assertEqual(unit.kind, "inline_code")
        self.assertTrue(unit.audits_as_one)
        self.assertEqual(unit.parts, ("python -c",))
        self.assertEqual(unit.text, leaf.text)

    def test_unit_for_peg_splits_a_plain_leaf_into_multiple_parts(self):
        """
        Given a single LeafCommand whose own text is a '&&'-chained compound
            ('git status && ls'), exercising _unit_for's OWN PEG re-split
        When _unit_for maps it to a CommandUnit
        Then kind is 'plain', audits_as_one is False, and parts holds both
             PEG sub-commands in order
        """
        unit = _unit_for(LeafCommand("git status && ls", ask_floor=False))
        self.assertEqual(unit.kind, "plain")
        self.assertFalse(unit.audits_as_one)
        self.assertEqual(unit.parts, ("git status", "ls"))

    def test_decompose_splits_undecidable_and_plain_units(self):
        """
        Given a command mixing an undecidable process-substitution segment
            with a following plain leaf
        When decompose splits the command line
        Then it returns two units, in order: 'undecidable' (audits_as_one
             True, no parts) then 'plain' (audits_as_one False, one part)
        """
        units = decompose("diff <(cat a) <(cat b) && ls -la")
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].kind, "undecidable")
        self.assertTrue(units[0].audits_as_one)
        self.assertEqual(units[0].parts, ())
        self.assertEqual(units[1].kind, "plain")
        self.assertFalse(units[1].audits_as_one)
        self.assertEqual(units[1].parts, ("ls -la",))


if __name__ == "__main__":
    unittest.main()
