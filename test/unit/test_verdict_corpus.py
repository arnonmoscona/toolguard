"""
Replay tests for the verdict-equivalence corpus: a HARD tier that must never be
made to pass by regenerating a goldens file, and a TRACKED tier that may be.
Read ``test/verdict_corpus/README.md`` before touching anything here.

Two corpora, deliberately two ``TestCase`` classes so either can be run alone:
the fast in-process one through :func:`toolguard.api.decide`, and a small
end-to-end one through the REAL hook subprocess, which is the only one that
reaches :func:`toolguard.hook.create_hook_output`.

Isolation (`.claude/rules/test-config-isolation.md`): this module does NOT use
ConfigIsolationMixin. Fixtures come from
:mod:`test.verdict_corpus.fixture_loader`, which wraps
:func:`toolguard.testing.sandbox.experiment` -- the same function
``tools/corpus_build.py`` uses to generate the committed goldens, so a
difference these tests catch is never an artifact of divergent scaffolding.
"""

import os
import unittest
from collections import defaultdict
from unittest.mock import patch

from test.verdict_corpus.fixture_loader import (
    CASES_PATH,
    E2E_CASES_PATH,
    E2E_GOLDENS_PATH,
    FIXTURE_IDS,
    GOLDENS_PATH,
    ComparisonResult,
    CompoundBreakdownMismatch,
    E2EComparisonResult,
    ProseDiff,
    VerdictMismatch,
    build_hook_payload,
    compare_e2e_goldens,
    compare_goldens,
    generate_e2e_goldens_in_memory,
    generate_goldens_in_memory,
    load_fixture_configuration,
    read_jsonl,
)
from toolguard.constants import FILE_TOOLS
from toolguard.file_matching import check_file_path_hard_deny
from toolguard.tool_spec import ToolKind, ToolSpec

#: Set to "1" to acknowledge already-reviewed TRACKED-tier differences without
#: regenerating goldens.jsonl.
_ACCEPT_PROSE_ENV_VAR = "TOOLGUARD_CORPUS_ACCEPT_PROSE"


class TestVerdictCorpus(unittest.TestCase):
    """
    Replays every ``cases.jsonl`` case through :func:`toolguard.api.decide` and
    compares it to ``goldens.jsonl``, ONCE per class -- replaying is the
    expensive part, and every method below reuses that one comparison.
    """

    cases = None
    expected_goldens = None
    result: ComparisonResult = None

    @classmethod
    def setUpClass(cls):
        """
        Load the committed corpus and replay it exactly once.

        Given the committed ``cases.jsonl`` and ``goldens.jsonl``
        When the whole corpus is replayed through :func:`~toolguard.api.decide`
        Then a single :class:`~test.verdict_corpus.fixture_loader.ComparisonResult`
             is available to every test method in this class.
        """
        cls.cases = read_jsonl(CASES_PATH)
        cls.expected_goldens = read_jsonl(GOLDENS_PATH)
        if not cls.cases:
            raise unittest.SkipTest(
                f"No cases found at {CASES_PATH} -- run "
                "'uv run python tools/corpus_build.py --extract' first."
            )
        if not cls.expected_goldens:
            raise unittest.SkipTest(
                f"No goldens found at {GOLDENS_PATH} -- run "
                "'uv run python tools/corpus_build.py --generate' first."
            )
        actual_goldens = generate_goldens_in_memory(cls.cases)
        cls.result = compare_goldens(cls.expected_goldens, actual_goldens)

    def test_no_stale_or_missing_goldens(self):
        """
        Given the committed cases.jsonl and goldens.jsonl
        When every (fixture, tool, target) key is compared between the two files
        Then no case lacks a committed golden and no golden lacks a matching case
        """
        self.assertEqual(
            [],
            self.result.missing_goldens,
            "case(s) with no committed golden -- run "
            "'uv run python tools/corpus_build.py --generate'",
        )
        self.assertEqual(
            [],
            self.result.extra_goldens,
            "stale committed golden(s) with no matching case in cases.jsonl -- "
            "regenerate both files together",
        )

    def test_no_verdict_changed(self):
        """
        Given every corpus case, replayed right now through decide()
        When its verdict (allow/ask/deny) is compared to the committed golden's verdict
        Then no verdict differs -- the HARD invariant the corpus exists to guard
        """
        if not self.result.verdict_mismatches:
            return
        lines = [
            f"  [{m.fixture}] {m.tool}({m.target!r}): "
            f"expected={m.expected_verdict!r} actual={m.actual_verdict!r}"
            for m in self.result.verdict_mismatches
        ]
        self.fail(
            f"{len(self.result.verdict_mismatches)} verdict(s) changed -- STOP and "
            "investigate a real behaviour change. Do NOT regenerate goldens.jsonl to "
            "make this pass -- see test/verdict_corpus/README.md.\n" + "\n".join(lines)
        )

    def test_no_sub_command_breakdown_changed(self):
        """
        Given every corpus case, replayed right now through decide()
        When its sub_matches/overrides breakdown is compared to the committed
             golden
        Then neither differs for any case -- a second HARD invariant, same tier
             as :meth:`test_no_verdict_changed`
        """
        if not self.result.breakdown_mismatches:
            return
        lines = []
        for mismatch in self.result.breakdown_mismatches:
            lines.append(
                f"  [{mismatch.fixture}] {mismatch.tool}({mismatch.target!r}).{mismatch.field}:"
            )
            lines.append(f"    expected: {mismatch.expected!r}")
            lines.append(f"    actual  : {mismatch.actual!r}")
        self.fail(
            f"{len(self.result.breakdown_mismatches)} sub-command breakdown "
            "mismatch(es) -- STOP and investigate a real behaviour change. Do NOT "
            "regenerate goldens.jsonl to make this pass -- see "
            "test/verdict_corpus/README.md.\n" + "\n".join(lines)
        )

    def test_tracked_fields_unchanged_or_acknowledged(self):
        """
        Given every corpus case, replayed right now through decide()
        When its reason/additional_context/provenance/matched_rule are compared
             to the committed golden
        Then either nothing differs, or TOOLGUARD_CORPUS_ACCEPT_PROSE=1 explicitly
             acknowledges the (already reviewed) differences

        These fields are TRACKED, not frozen: a refactor may reword a reason
        string without changing behaviour. Reviewing the diff and regenerating
        goldens.jsonl, or setting the env var for one run, are the two
        acknowledgement paths; loosening this check is not one.
        """
        if not self.result.prose_diffs:
            return
        if os.environ.get(_ACCEPT_PROSE_ENV_VAR) == "1":
            return
        lines = []
        for diff in self.result.prose_diffs:
            lines.append(
                f"  [{diff.fixture}] {diff.tool}({diff.target!r}).{diff.field}:"
            )
            lines.append(f"    expected: {diff.expected!r}")
            lines.append(f"    actual  : {diff.actual!r}")
        self.fail(
            f"{len(self.result.prose_diffs)} tracked (reason/additional_context/"
            "provenance/matched_rule) difference(s) found. These are NOT verdict "
            "changes. Review them, then either regenerate goldens.jsonl (once the "
            f"change is confirmed legitimate) or set {_ACCEPT_PROSE_ENV_VAR}=1 to "
            "acknowledge without "
            "regenerating.\n" + "\n".join(lines)
        )


class TestVerdictCorpusEndToEnd(unittest.TestCase):
    """
    Replays every ``e2e_cases.jsonl`` case through the REAL hook binary (one
    subprocess each) and compares the full hook JSON response to
    ``e2e_goldens.jsonl``, ONCE per class. Small on purpose: subprocess startup
    dominates, and it exists to cover
    :func:`toolguard.hook.create_hook_output`, which ``decide()`` never reaches.
    """

    e2e_cases = None
    e2e_expected_goldens = None
    result: E2EComparisonResult = None

    @classmethod
    def setUpClass(cls):
        """
        Load the committed end-to-end corpus and replay it exactly once.

        Given the committed e2e_cases.jsonl and e2e_goldens.jsonl
        When the whole end-to-end corpus is replayed through the real hook subprocess
        Then a single E2EComparisonResult is available to every test method here
        """
        cls.e2e_cases = read_jsonl(E2E_CASES_PATH)
        cls.e2e_expected_goldens = read_jsonl(E2E_GOLDENS_PATH)
        if not cls.e2e_cases:
            raise unittest.SkipTest(
                f"No end-to-end cases found at {E2E_CASES_PATH} -- run "
                "'uv run python tools/corpus_build.py --extract' first."
            )
        if not cls.e2e_expected_goldens:
            raise unittest.SkipTest(
                f"No end-to-end goldens found at {E2E_GOLDENS_PATH} -- run "
                "'uv run python tools/corpus_build.py --generate' first."
            )
        actual_goldens = generate_e2e_goldens_in_memory(cls.e2e_cases)
        cls.result = compare_e2e_goldens(cls.e2e_expected_goldens, actual_goldens)

    def test_no_stale_or_missing_e2e_goldens(self):
        """
        Given the committed e2e_cases.jsonl and e2e_goldens.jsonl
        When every (fixture, tool, target) key is compared between the two files
        Then no case lacks a committed golden and no golden lacks a matching case
        """
        self.assertEqual(
            [],
            self.result.missing_goldens,
            "end-to-end case(s) with no committed golden -- run "
            "'uv run python tools/corpus_build.py --generate'",
        )
        self.assertEqual(
            [],
            self.result.extra_goldens,
            "stale committed end-to-end golden(s) with no matching case -- "
            "regenerate both files together",
        )

    def test_no_hard_output_changed(self):
        """
        Given every end-to-end case, replayed right now through the real hook subprocess
        When permissionDecision and additionalContext's PRESENCE (not its text) are
             compared to the committed golden
        Then neither differs for any case -- the HARD invariant this corpus
             exists to guard, in particular ``additionalContext`` silently
             disappearing from the hook's real JSON output
        """
        if not self.result.hard_mismatches:
            return
        lines = [
            f"  [{m.fixture}] {m.tool}({m.target!r}).{m.kind}: "
            f"expected={m.expected!r} actual={m.actual!r}"
            for m in self.result.hard_mismatches
        ]
        self.fail(
            f"{len(self.result.hard_mismatches)} end-to-end hard mismatch(es) -- STOP "
            "and investigate a real behaviour change. Do NOT regenerate "
            "e2e_goldens.jsonl to make this pass -- see test/verdict_corpus/README.md.\n"
            + "\n".join(lines)
        )

    def test_e2e_tracked_fields_unchanged_or_acknowledged(self):
        """
        Given every end-to-end case, replayed right now through the real hook subprocess
        When permissionDecisionReason's text, additionalContext's text (when
             present on both sides), and conflict_message's text (when both
             sides logged a conflict) are compared to the committed golden
        Then either nothing differs, or TOOLGUARD_CORPUS_ACCEPT_PROSE=1 explicitly
             acknowledges the (already reviewed) differences
        """
        if not self.result.prose_diffs:
            return
        if os.environ.get(_ACCEPT_PROSE_ENV_VAR) == "1":
            return
        lines = []
        for diff in self.result.prose_diffs:
            lines.append(
                f"  [{diff.fixture}] {diff.tool}({diff.target!r}).{diff.field}:"
            )
            lines.append(f"    expected: {diff.expected!r}")
            lines.append(f"    actual  : {diff.actual!r}")
        self.fail(
            f"{len(self.result.prose_diffs)} tracked end-to-end "
            "(reason/additionalContext/conflict_message text) difference(s) found. "
            "These are NOT hard-output changes. Review them, "
            "then either regenerate e2e_goldens.jsonl (once the change is confirmed "
            f"legitimate) or set {_ACCEPT_PROSE_ENV_VAR}=1 to acknowledge without "
            "regenerating.\n" + "\n".join(lines)
        )


class TestBuildHookPayloadPayloadKeySeam(unittest.TestCase):
    """``build_hook_payload`` dispatches through the tool_spec registry, not a hardcoded literal."""

    @patch.dict(
        "toolguard.tool_spec.TOOLS_BY_NAME",
        {
            "Read": ToolSpec(
                name="Read",
                kind=ToolKind.FILE,
                payload_key="target_path",
                is_builtin=True,
            )
        },
    )
    def test_payload_key_comes_from_the_registry(self):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When build_hook_payload builds a Read event
        Then the target is placed under 'target_path', not 'file_path'
        """
        self.assertEqual(
            build_hook_payload("Read", "/proj/readme.md"),
            {"tool_name": "Read", "tool_input": {"target_path": "/proj/readme.md"}},
        )

    def test_unregistered_tool_falls_back_to_command(self):
        """
        Given a tool with no registered ToolSpec
        When build_hook_payload builds an event
        Then the target is placed under 'command'
        """
        self.assertEqual(
            build_hook_payload("mcp__local-tools__checked_bash", "ls"),
            {
                "tool_name": "mcp__local-tools__checked_bash",
                "tool_input": {"command": "ls"},
            },
        )


#: Committed corpus population, as a FLOOR. Every check above compares
#: cases.jsonl against goldens.jsonl, so the two shrinking TOGETHER -- which is
#: what `--extract` followed by `--generate` does on a tree whose logs/ is
#: smaller or absent -- leaves both files mutually consistent and every other
#: test in this module green. Measured 2026-08-13: dropping both files to 3200
#: cases produced 4 passes and no skips. Raise these when the corpus grows;
#: lowering one is a reviewed decision, not a repair.
_MIN_CASES = 6401
_MIN_E2E_CASES = 61

#: Minimum surviving population per region of the decision space. A corpus that
#: kept its total but lost, say, every compound case would still be a green
#: regression net over nothing. Keys are ``"<kind>/<verdict>"`` plus the two
#: structural regions; values are the counts committed alongside _MIN_CASES.
_MIN_BY_REGION = {
    "bash/allow": 5351,
    "bash/ask": 129,
    "bash/deny": 151,
    "file_path/allow": 731,
    "file_path/ask": 35,
    "file_path/deny": 4,
    "compound": 1066,
    "override": 33,
}


def _regions(golden):
    """Yield every :data:`_MIN_BY_REGION` key the golden record belongs to."""
    kind = "file_path" if golden["tool"] in FILE_TOOLS else "bash"
    yield f"{kind}/{golden['verdict']}"
    if len(golden.get("sub_matches") or []) > 1:
        yield "compound"
    if golden.get("overrides"):
        yield "override"


class TestCorpusPopulation(unittest.TestCase):
    """
    Guards the corpus's SIZE and SPREAD, which every comparison above is blind
    to by construction: they check cases against goldens, and a case that
    exists in neither file is not a difference. Deliberately its own class with
    no ``setUpClass`` -- :class:`TestVerdictCorpus` SKIPS on an empty corpus,
    and a skip reports green.
    """

    def test_the_corpus_has_not_silently_shrunk(self):
        """
        Given the committed cases/goldens files for both corpora
        When their record counts are compared to the committed floors
        Then neither corpus has lost cases, and each still has one golden per case
        """
        cases = read_jsonl(CASES_PATH)
        goldens = read_jsonl(GOLDENS_PATH)
        e2e_cases = read_jsonl(E2E_CASES_PATH)
        e2e_goldens = read_jsonl(E2E_GOLDENS_PATH)
        self.assertGreaterEqual(
            len(cases),
            _MIN_CASES,
            f"in-process corpus shrank to {len(cases)} cases -- regenerating "
            "cases.jsonl and goldens.jsonl together hides this from every other "
            "test here. Confirm the loss is intended before raising/lowering "
            "_MIN_CASES.",
        )
        self.assertGreaterEqual(
            len(e2e_cases),
            _MIN_E2E_CASES,
            f"end-to-end corpus shrank to {len(e2e_cases)} cases -- see _MIN_E2E_CASES.",
        )
        self.assertEqual(
            len(cases), len(goldens), "cases.jsonl/goldens.jsonl differ in size"
        )
        self.assertEqual(
            len(e2e_cases), len(e2e_goldens), "e2e cases/goldens differ in size"
        )

    def test_every_declared_fixture_is_exercised(self):
        """
        Given the fixture ids the corpus declares in FIXTURE_IDS
        When each is looked for in cases.jsonl
        Then every one has at least one case -- a fixture nothing replays
             contributes no coverage while still reading as configured
        """
        exercised = {case["fixture"] for case in read_jsonl(CASES_PATH)}
        self.assertEqual(
            [],
            [fixture for fixture in FIXTURE_IDS if fixture not in exercised],
            "declared fixture(s) with no case in cases.jsonl",
        )

    def test_every_region_of_the_decision_space_is_still_populated(self):
        """
        Given every committed golden, bucketed by tool kind, verdict and shape
        When each bucket's size is compared to its committed floor
        Then no region of the decision space has been emptied out
        """
        populations = defaultdict(int)
        for golden in read_jsonl(GOLDENS_PATH):
            for region in _regions(golden):
                populations[region] += 1
        for region, minimum in sorted(_MIN_BY_REGION.items()):
            with self.subTest(region=region):
                self.assertGreaterEqual(
                    populations[region],
                    minimum,
                    f"corpus coverage of {region!r} fell from {minimum} to "
                    f"{populations[region]}",
                )


class TestProseAcknowledgementIsNarrow(unittest.TestCase):
    """
    ``TOOLGUARD_CORPUS_ACCEPT_PROSE=1`` must silence the TRACKED tier and
    nothing else. It is the one switch that can turn a check here green without
    a code change, and an exported one applies to every later run.
    """

    @staticmethod
    def _mismatch_in_every_tier():
        """A ComparisonResult carrying one difference of each tier."""
        return ComparisonResult(
            verdict_mismatches=[
                VerdictMismatch("f", "Bash", "rm -rf /", "deny", "allow")
            ],
            breakdown_mismatches=[
                CompoundBreakdownMismatch(
                    "f", "Bash", "a && b", "sub_matches", [{}], []
                )
            ],
            prose_diffs=[ProseDiff("f", "Bash", "ls", "matched_rule", "ls:*", None)],
        )

    def test_acknowledging_prose_does_not_silence_the_hard_tiers(self):
        """
        Given a comparison carrying a verdict, a breakdown AND a tracked difference
        When TOOLGUARD_CORPUS_ACCEPT_PROSE=1 is set
        Then both HARD checks still fail and only the tracked check goes quiet
        """
        with (
            patch.object(TestVerdictCorpus, "result", self._mismatch_in_every_tier()),
            patch.dict(os.environ, {_ACCEPT_PROSE_ENV_VAR: "1"}),
        ):
            case = TestVerdictCorpus("test_no_verdict_changed")
            with self.assertRaises(AssertionError):
                case.test_no_verdict_changed()
            with self.assertRaises(AssertionError):
                case.test_no_sub_command_breakdown_changed()
            case.test_tracked_fields_unchanged_or_acknowledged()

    def test_the_tracked_tier_fails_without_the_acknowledgement(self):
        """
        Given the same comparison, carrying a tracked difference
        When TOOLGUARD_CORPUS_ACCEPT_PROSE is absent from the environment
        Then the tracked check fails -- the acknowledgement above is what
             silenced it, not the fixture being unable to produce a failure
        """
        with (
            patch.object(TestVerdictCorpus, "result", self._mismatch_in_every_tier()),
            patch.dict(os.environ, {}, clear=True),
        ):
            case = TestVerdictCorpus("test_tracked_fields_unchanged_or_acknowledged")
            with self.assertRaises(AssertionError):
                case.test_tracked_fields_unchanged_or_acknowledged()


class TestFilePathHardDenyAttribution(unittest.TestCase):
    """
    A file-path hard-deny's deciding pattern must survive into the golden as
    DATA. ``resolve_file_path_permission_detailed`` sets ``matched_rule=None``
    on that branch, citing this corpus, so the pattern that refused the access
    exists only inside the prose ``reason`` -- the tier this corpus's own
    README says a refactor may legitimately reword.
    """

    def test_a_file_path_hard_deny_golden_records_the_deciding_pattern(self):
        """
        Given every committed golden that denies a file-path tool
        When the deciding hard-deny pattern is recomputed from its own fixture
        Then the golden's matched_rule carries that pattern rather than None
        """
        denied_by_fixture = defaultdict(list)
        for golden in read_jsonl(GOLDENS_PATH):
            if golden["tool"] in FILE_TOOLS and golden["verdict"] == "deny":
                denied_by_fixture[golden["fixture"]].append(golden)
        self.assertTrue(
            denied_by_fixture,
            "no file-path deny golden exists at all -- the corpus cannot see "
            "this branch, let alone justify a design constraint on it",
        )

        unattributed = []
        for fixture_id, goldens in sorted(denied_by_fixture.items()):
            with load_fixture_configuration(fixture_id) as (config, _sanitize):
                for golden in goldens:
                    hard = check_file_path_hard_deny(
                        golden["tool"], golden["target"], config, True
                    )
                    # None means the cascade denied instead; that branch does
                    # pass matched_rule through, so it is not this gap.
                    if (
                        hard is not None
                        and golden["matched_rule"] != hard.matched_pattern
                    ):
                        unattributed.append(
                            f"  [{fixture_id}] {golden['tool']}({golden['target']!r}): "
                            f"denied by {hard.matched_pattern!r}, golden records "
                            f"{golden['matched_rule']!r}"
                        )
        self.assertEqual(
            [],
            unattributed,
            "file-path hard-deny golden(s) do not record which pattern denied.\n"
            + "\n".join(unattributed),
        )


if __name__ == "__main__":
    unittest.main()
