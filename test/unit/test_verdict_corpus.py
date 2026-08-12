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
from unittest.mock import patch

from test.verdict_corpus.fixture_loader import (
    CASES_PATH,
    E2E_CASES_PATH,
    E2E_GOLDENS_PATH,
    GOLDENS_PATH,
    ComparisonResult,
    E2EComparisonResult,
    build_hook_payload,
    compare_e2e_goldens,
    compare_goldens,
    generate_e2e_goldens_in_memory,
    generate_goldens_in_memory,
    read_jsonl,
)
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


if __name__ == "__main__":
    unittest.main()
