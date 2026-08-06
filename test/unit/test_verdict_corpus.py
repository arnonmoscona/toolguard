"""
Replay tests for the TOO-45 verdict-equivalence corpus.

See ``test/verdict_corpus/README.md`` for what this corpus is for, how it is
built, and -- critically -- what to do when a test in this module fails. The
short version, repeated here because it is the single most important fact
about this file: a failing :meth:`TestVerdictCorpus.test_no_verdict_changed`
(or, for the end-to-end corpus,
:meth:`TestVerdictCorpusEndToEnd.test_no_hard_output_changed`) means STOP and
investigate a real behaviour change. Neither is ever fixed by regenerating a
goldens file.

Two test classes, two corpora, run independently
--------------------------------------------------
- :class:`TestVerdictCorpus` replays the fast, ~5,000-case in-process corpus
  through :func:`toolguard.tools.decision.decide` directly.
- :class:`TestVerdictCorpusEndToEnd` replays a small (~30-case), deliberately
  chosen end-to-end corpus through the REAL hook binary in a subprocess (via
  :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`). This exists because
  ``decide()`` stops at the decision itself and cannot see
  :func:`toolguard.hook.create_hook_output` -- the seam that turns a decision
  into the actual JSON Claude Code receives. A real defect once silently
  dropped ``additionalContext`` there, undetected by decision-level testing;
  this class is what closes that specific gap.

Kept as two separate ``TestCase`` classes (not two methods sharing one
``setUpClass``) precisely so either corpus can be run and diagnosed on its
own, e.g. ``python -m unittest test.unit.test_verdict_corpus.TestVerdictCorpusEndToEnd``.

Isolation note: this module deliberately does NOT use
``test.unit._config_isolation.ConfigIsolationMixin``. Every fixture's
Configuration (or sandbox, for the end-to-end class) is built by
:func:`test.verdict_corpus.fixture_loader.load_fixture_configuration` /
:func:`~test.verdict_corpus.fixture_loader.load_fixture_sandbox`, both of
which wrap :func:`toolguard.testing.sandbox.experiment` -- the SAME function
``tools/corpus_build.py`` uses to generate the committed goldens in the first
place. Sharing one isolation/loading path (rather than the test using
``ConfigIsolationMixin`` and the dev tool using something else) is what makes
``compare_goldens``/``compare_e2e_goldens`` meaningful: both sides are
guaranteed to build a fixture the same way, so any behaviour difference these
tests catch is a difference in the engine under test, never an artifact of
divergent test scaffolding. ``toolguard.testing.sandbox.experiment`` already
covers the same ground ``ConfigIsolationMixin`` does (``Path.home()``,
``find_project_root``, a cleared/rebuilt environment) plus a write tripwire
``ConfigIsolationMixin`` does not have.
"""

import os
import unittest

from test.verdict_corpus.fixture_loader import (
    CASES_PATH,
    E2E_CASES_PATH,
    E2E_GOLDENS_PATH,
    GOLDENS_PATH,
    ComparisonResult,
    E2EComparisonResult,
    compare_e2e_goldens,
    compare_goldens,
    generate_e2e_goldens_in_memory,
    generate_goldens_in_memory,
    read_jsonl,
)

#: Set to "1" to acknowledge reviewed reason/additional_context/provenance/
#: matched_rule differences without regenerating goldens.jsonl. See README.md.
_ACCEPT_PROSE_ENV_VAR = "TOOLGUARD_CORPUS_ACCEPT_PROSE"


class TestVerdictCorpus(unittest.TestCase):
    """
    Replays every ``(fixture, tool, target)`` case in ``cases.jsonl`` through
    :func:`toolguard.tools.decision.decide` and compares the result to the
    committed ``goldens.jsonl``, ONCE for the whole test class (replaying is
    the expensive part; every ``test_*`` method below reuses the same
    comparison rather than re-running it).
    """

    cases = None
    expected_goldens = None
    result: ComparisonResult = None

    @classmethod
    def setUpClass(cls):
        """
        Load the committed corpus and replay it exactly once.

        Given the committed ``cases.jsonl`` and ``goldens.jsonl``
        When the whole corpus is replayed through :func:`~toolguard.tools.decision.decide`
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

        A mismatch here means the two files were not regenerated together
        (e.g. a case was added/removed without re-running --generate) -- a
        corpus data-integrity problem, not a verdict-equivalence one, but
        still always a hard failure: the corpus cannot guard anything if its
        own two halves have drifted apart.
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
        Then no verdict differs

        This is the HARD invariant the whole corpus exists to guard (TOO-45).
        A failure here means STOP and investigate a real behaviour change --
        it is NEVER fixed by regenerating goldens.jsonl. See
        test/verdict_corpus/README.md.
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

    def test_tracked_fields_unchanged_or_acknowledged(self):
        """
        Given every corpus case, replayed right now through decide()
        When its reason/additional_context/provenance/matched_rule are compared
             to the committed golden
        Then either nothing differs, or TOOLGUARD_CORPUS_ACCEPT_PROSE=1 explicitly
             acknowledges the (already reviewed) differences

        Unlike verdict, these fields are TRACKED, not frozen: a legitimate
        refactor step may reword a reason string without changing behaviour.
        A single-tier golden would either block that legitimate rewording or
        hide a real regression inside it -- both expensive here -- so this is
        reported separately, fails by default (so a difference is never
        silently ignored), and has exactly one acknowledgement path: either
        regenerate goldens.jsonl after reviewing the diff (the normal case),
        or set TOOLGUARD_CORPUS_ACCEPT_PROSE=1 for a one-off run. Editing this
        test to loosen the check is not that path.
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
    Replays every ``(fixture, tool, target)`` case in ``e2e_cases.jsonl``
    through the REAL ``toolguard`` hook binary (one subprocess per case, via
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`) and compares the full
    hook JSON response to the committed ``e2e_goldens.jsonl``, ONCE for the
    whole test class.

    Deliberately separate from :class:`TestVerdictCorpus`: this corpus is
    small (subprocess startup dominates its cost) and exists for a different
    reason -- covering :func:`toolguard.hook.create_hook_output`, which the
    in-process corpus's entry point never reaches.
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
        Then neither differs for any case

        This is the HARD invariant this corpus exists to guard -- in particular
        the ``additionalContext`` key silently disappearing from the hook's
        real JSON output, which the in-process corpus cannot see at all (it
        never reaches ``toolguard.hook.create_hook_output``). A failure here
        means STOP and investigate a real behaviour change -- it is NEVER
        fixed by regenerating e2e_goldens.jsonl. See test/verdict_corpus/README.md.
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

        Same rationale as :meth:`TestVerdictCorpus.test_tracked_fields_unchanged_or_acknowledged`,
        applied to the end-to-end corpus's prose fields.
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


if __name__ == "__main__":
    unittest.main()
