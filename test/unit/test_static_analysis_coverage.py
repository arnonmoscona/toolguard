"""
Guards that `pyscn` can actually read this repository's source.

`pyscn analyze` drops a file it cannot parse from every metric it computes,
warns once on stderr, and still exits 0 with a summary that looks complete.
That happened for real: one ``except A, B, C:`` clause silently reduced a
whole-package health score to 58 of 59 modules, and pointing pyscn at such a
file on its own still reports a health score for it.

Two guards, deliberately different in kind:

* an AST scan for the clause form itself, over every tracked `.py` file. It
  needs no tools, so it cannot go quiet on a machine without pyscn, and it
  cannot be fooled by the clause appearing in a string or a comment.
* the pyscn run itself, which is what the pre-push checklist executes. Its
  hazard is the opposite one: pyscn exits nonzero and prints no parse-failure
  line when it analysed nothing at all, so a run over an absent, empty or
  fully-excluded tree looks exactly like a clean one unless the return code
  and the score are checked too.
"""

import ast
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYSCN_CONFIG = REPO_ROOT / ".pyscn.toml"

#: The one file deliberately kept away from pyscn: the canopy-generated PEG
#: parser. Measured 2026-08-14 on pyscn 1.24.3 -- analysing it does not crash,
#: it does not terminate: killed at six minutes with no output.
SANCTIONED_EXCLUSION = "**/bash_parser.py"

#: Ceiling on a pyscn run. The whole package takes under a second, so this is
#: not a performance allowance -- it is the bound that turns the generated
#: parser's non-termination into a failure instead of a stalled suite.
PYSCN_TIMEOUT_SECONDS = 120

#: The whole of `.pyscn.toml`'s exclude list, pinned. Broadening it is the
#: quiet way to make every guard in this file pass over nothing.
EXPECTED_EXCLUSIONS = (
    "**/*.pyc",
    "**/*_test.py",
    "**/.pytest_cache/",
    "**/__pycache__/*",
    "**/bash_parser.py",
    "**/migrations/**",
    "**/test_*.py",
    ".env/",
    ".tox/",
    ".venv/",
    "env/",
    "venv/",
)

#: Trees that must be represented in the scan. The scan itself covers every
#: tracked `.py` file rather than a list of directories, so its scope cannot
#: be narrowed by editing a constant; this is only a sanity floor. `tools/`
#: and `test/` are in scope even though the pre-push `pyscn` step is not run
#: over them -- an instrument nothing can analyse is worse placed there than
#: in the package.
REQUIRED_TREES = ("toolguard", "tools", "test")

#: Names in an unparenthesised `except` tuple, at or above which pyscn's
#: grammar gives up on the whole file. Two parses fine and is used throughout
#: on purpose -- `ruff format` strips the parentheses off a two-name tuple.
BLINDING_ARITY = 3

#: Substrings pyscn uses to announce that it skipped a file.
PARSE_FAILURE_MARKERS = ("Failed to parse", "syntax errors found")

#: Present only when pyscn got as far as scoring something.
ANALYSIS_COMPLETED_MARKER = "Health Score"

#: pyscn's refusal when the paths it was given yield no analysable file.
NOTHING_TO_ANALYSE_MARKER = "no Python files found"


def _unparenthesised_except_tuples(source: str) -> list[tuple[int, int]]:
    """
    `(line, name count)` for each `except A, B:` clause written without
    parentheses, found by AST -- so the same text in a string or a comment
    cannot match, and a line continuation cannot hide one.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        clause = node.type
        if not isinstance(clause, ast.Tuple):
            continue
        segment = ast.get_source_segment(source, clause) or ""
        if not segment.startswith("("):
            found.append((clause.lineno, len(clause.elts)))
    return found


def _tracked_python_sources() -> list[Path]:
    """
    Every `.py` file git tracks in this repository, sorted. Asking git rather
    than naming directories is deliberate: it means a new top-level package is
    covered the day it is added, and the scan's scope cannot be narrowed by
    shortening a list.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "*.py"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    paths = (REPO_ROOT / name for name in listing.stdout.split("\0") if name)
    return sorted(p for p in paths if p.is_file())


def _run_pyscn(pyscn: str, *targets: Path) -> subprocess.CompletedProcess:
    """
    Run `pyscn analyze` over *targets* against the repo's real config, from a
    throwaway cwd -- pyscn writes a ~112 KB HTML report beside its working
    directory, and these tests are not entitled to leave one in the repo.
    """
    with tempfile.TemporaryDirectory() as workdir:
        return subprocess.run(
            [pyscn, "analyze", "-c", str(PYSCN_CONFIG), *(str(t) for t in targets)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=PYSCN_TIMEOUT_SECONDS,
        )


class TestNoSourceIsUnreadableToAnAnalyser(unittest.TestCase):
    """No file may carry the clause form that makes an analyser skip it."""

    def test_no_source_file_carries_a_blinding_except_clause(self):
        """
        Given every Python source git tracks in this repository
        When each file's except clauses are read from its AST
        Then none writes three or more exception names without parentheses,
             the form that makes pyscn skip a file while still scoring it
        """
        sources = _tracked_python_sources()
        covered = {path.relative_to(REPO_ROOT).parts[0] for path in sources}
        for tree in REQUIRED_TREES:
            self.assertIn(
                tree,
                covered,
                f"No tracked Python file under {tree}/ reached this scan, so "
                f"whatever it reports says nothing about that tree. A guard "
                f"that passes over an absent subject is the failure this "
                f"module exists to catch.",
            )

        offenders = []
        for path in sources:
            text = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(REPO_ROOT)}:{line} ({names} names)"
                for line, names in _unparenthesised_except_tuples(text)
                if names >= BLINDING_ARITY
            )

        self.assertEqual(
            offenders,
            [],
            "These clauses are valid Python and make pyscn skip the ENTIRE "
            "file, while still reporting a health score for it -- so the file "
            "silently leaves static analysis. Note the fix is not the obvious "
            "one: `ruff format` strips the parentheses back off a plain "
            "`except (A, B, C):`, measured on ruff 0.15.14. What survives a "
            "format run is a parenthesised tuple with a magic trailing comma, "
            "or the tuple hoisted to a named constant. "
            f"Offending clauses: {offenders}",
        )

    def test_the_scan_sees_every_shape_of_the_clause_and_no_lookalike(self):
        """
        Given planted sources carrying the clause plainly, nested in a class
             and a function, split over a line continuation, and as `except*`
        When each is scanned, alongside lookalikes that must not match
        Then every real clause is found, and no parenthesised tuple, single
             name, string or comment is mistaken for one
        """
        must_match = {
            "plain": "try:\n    pass\nexcept A, B, C:\n    pass\n",
            "continuation": "try:\n    pass\nexcept A, \\\n    B, C:\n    pass\n",
            "nested": (
                "class K:\n"
                "    def m(self):\n"
                "        def inner():\n"
                "            try:\n"
                "                pass\n"
                "            except A, B, C:\n"
                "                pass\n"
            ),
            "except_star": "try:\n    pass\nexcept* A, B, C:\n    pass\n",
        }
        for name, source in must_match.items():
            with self.subTest(shape=name):
                found = _unparenthesised_except_tuples(source)
                self.assertEqual(
                    [names for _, names in found],
                    [3],
                    f"The {name} shape of an unparenthesised three-name except "
                    f"clause was not detected, so a file carrying it would "
                    f"leave static analysis without failing this module.",
                )

        must_not_match = {
            "parenthesised": "try:\n    pass\nexcept (A, B, C):\n    pass\n",
            "parenthesised_exploded": (
                "try:\n    pass\nexcept (\n    A,\n    B,\n    C,\n):\n    pass\n"
            ),
            "with_as": "try:\n    pass\nexcept (A, B, C) as e:\n    pass\n",
            "single_name": "try:\n    pass\nexcept A:\n    pass\n",
            "inside_a_string": 'S = """\nexcept A, B, C:\n"""\n',
            "inside_a_comment": "# except A, B, C:\nx = 1\n",
        }
        for name, source in must_not_match.items():
            with self.subTest(shape=name):
                self.assertEqual(
                    [
                        names
                        for _, names in _unparenthesised_except_tuples(source)
                        if names >= BLINDING_ARITY
                    ],
                    [],
                    f"The {name} shape was reported as a blinding clause. It "
                    f"is not one, and a false positive here makes the guard "
                    f"unfixable and therefore ignorable.",
                )

    def test_two_names_are_reported_but_below_the_blinding_arity(self):
        """
        Given the two-name form, which is used deliberately across the package
             because `ruff format` strips its parentheses
        When it is scanned
        Then it is seen as an unparenthesised tuple but counted below
             BLINDING_ARITY, so the threshold is doing the work rather than
             the scan failing to see it
        """
        found = _unparenthesised_except_tuples(
            "try:\n    pass\nexcept A, B:\n    pass\n"
        )
        self.assertEqual(
            [names for _, names in found],
            [2],
            "The two-name form was not seen as an unparenthesised tuple at "
            "all, so the scan is passing it for the wrong reason and raising "
            "BLINDING_ARITY would not be what keeps it quiet.",
        )


class TestPyscnStillBehavesAsThisModuleAssumes(unittest.TestCase):
    """The hazard, and pyscn's announcement of it, must both still be real."""

    def setUp(self):
        self.pyscn = shutil.which("pyscn")
        if self.pyscn is None:
            self.skipTest(
                "pyscn not installed (dev-only tool, not a runtime dependency)"
            )
        self.workdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.workdir, True)

    def _analyse(self, name: str, source: str) -> str:
        """Write *source* to `name` under the fixture and return pyscn's output."""
        target = self.workdir / name
        target.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [self.pyscn, "analyze", target.name],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=PYSCN_TIMEOUT_SECONDS,
        )
        return result.stdout + result.stderr

    @staticmethod
    def _clause_of_arity(arity: int) -> str:
        """A module whose only except clause names *arity* exceptions, bare."""
        names = ", ".join(f"E{i}" for i in range(arity))
        return f"def f():\n    try:\n        pass\n    except {names}:\n        pass\n"

    def test_blinding_arity_is_the_boundary_pyscn_actually_has(self):
        """
        Given one planted file whose bare except clause names BLINDING_ARITY
             exceptions and one naming a single name fewer
        When pyscn analyses each
        Then only the first draws a parse-failure warning, so the constant is
             the measured boundary rather than a remembered one, and the
             strings this module greps for are still the strings pyscn prints
        """
        blinding = self._analyse("blinding.py", self._clause_of_arity(BLINDING_ARITY))
        benign = self._analyse("benign.py", self._clause_of_arity(BLINDING_ARITY - 1))

        for marker in PARSE_FAILURE_MARKERS:
            self.assertIn(
                marker,
                blinding,
                f"pyscn no longer announces a skipped file with {marker!r}. "
                f"test_pyscn_reports_no_parse_failures greps for exactly these "
                f"strings, so it has gone silent rather than gone green.",
            )
        for marker in PARSE_FAILURE_MARKERS:
            self.assertNotIn(
                marker,
                benign,
                f"pyscn now rejects a bare {BLINDING_ARITY - 1}-name except "
                f"clause too, so BLINDING_ARITY is set too high and the AST "
                f"scan is letting real blind spots through. That form is used "
                f"throughout the package because `ruff format` strips its "
                f"parentheses, so this is a repo-wide problem, not a test one.",
            )


class TestPyscnAnalysesEveryModule(unittest.TestCase):
    """pyscn must not silently drop a module from its metrics."""

    def test_pyscn_reports_no_parse_failures(self):
        """
        Given the toolguard package and pyscn's configured exclusions
        When `pyscn analyze` runs over the package
        Then it completes, reports a score, and reports no parse failures, so
             its metrics cover every non-excluded module rather than an
             unannounced subset
        """
        pyscn = shutil.which("pyscn")
        if pyscn is None:
            self.skipTest(
                "pyscn not installed (dev-only tool, not a runtime dependency)"
            )

        package = REPO_ROOT / "toolguard"
        result = _run_pyscn(pyscn, package)
        combined = result.stdout + result.stderr

        # pyscn exits 1 and prints no summary when it analysed nothing at all
        # -- a missing tree, an empty one, or an exclude pattern that swallowed
        # the package. Without these two the parse-failure check below is
        # trivially satisfied by a run that read no files.
        self.assertEqual(
            result.returncode,
            0,
            f"pyscn did not complete over {package}, so the parse-failure "
            f"check below examined the output of a run that may have analysed "
            f"nothing. Output: {combined}",
        )
        self.assertIn(
            ANALYSIS_COMPLETED_MARKER,
            combined,
            f"pyscn exited 0 but printed no score, so nothing was measured. "
            f"Output: {combined}",
        )

        offending = [
            line.strip()
            for line in combined.splitlines()
            if any(marker in line for marker in PARSE_FAILURE_MARKERS)
        ]
        self.assertEqual(
            offending,
            [],
            "pyscn could not parse one or more files and EXCLUDED them from every "
            "metric it reports, while still exiting 0 and printing a summary that "
            "looks complete. Either make the file parseable (a tuple with a magic "
            "trailing comma survives `ruff format`; a bare parenthesised one does "
            "not), or -- if it genuinely should not be analysed -- add it to "
            "`.pyscn.toml`'s exclude_patterns WITH a reason and pin it in "
            f"EXPECTED_EXCLUSIONS, so the omission is visible instead of silent. "
            f"Offending output: {offending}",
        )

    def test_pointing_pyscn_at_nothing_is_not_a_clean_run(self):
        """
        Given a directory holding no Python file
        When pyscn is pointed at it
        Then it does not complete, which is what makes the return-code check in
             the guard above able to tell a clean package from an absent one
        """
        pyscn = shutil.which("pyscn")
        if pyscn is None:
            self.skipTest(
                "pyscn not installed (dev-only tool, not a runtime dependency)"
            )

        with tempfile.TemporaryDirectory() as empty:
            result = _run_pyscn(pyscn, Path(empty))
            combined = result.stdout + result.stderr

        self.assertNotEqual(
            result.returncode,
            0,
            "pyscn now reports success over a tree with no Python files, so "
            "the guard above can no longer distinguish an analysed package "
            "from a missing one and needs a positive count of files instead.",
        )
        self.assertNotIn(ANALYSIS_COMPLETED_MARKER, combined)


class TestSanctionedPyscnExclusion(unittest.TestCase):
    """The deliberate exclusions must stay deliberate and stay visible."""

    def setUp(self):
        config = tomllib.loads(PYSCN_CONFIG.read_text(encoding="utf-8"))
        self.patterns = config["analysis"]["exclude_patterns"]

    def test_the_exclusion_list_is_exactly_what_is_pinned_here(self):
        """
        Given `.pyscn.toml`'s exclude_patterns
        When they are compared against EXPECTED_EXCLUSIONS
        Then they match exactly, so widening the list -- the quiet way to make
             every guard in this file pass over nothing -- fails here
        """
        self.assertEqual(
            sorted(self.patterns),
            sorted(EXPECTED_EXCLUSIONS),
            "`.pyscn.toml`'s exclude_patterns changed. A pattern removed may "
            "crash the analyser; a pattern added removes files from every "
            "metric with no other signal, and a broad enough one leaves pyscn "
            "nothing to analyse at all. Update EXPECTED_EXCLUSIONS in the same "
            "change, with the reason in `.pyscn.toml` beside the pattern.",
        )

    def test_generated_parser_is_still_excluded(self):
        """
        Given the canopy-generated PEG parser, which pyscn cannot analyse
        When `.pyscn.toml`'s exclude_patterns are read
        Then the generated parser is still listed, so a future edit that drops
             it fails here rather than crashing an analysis run
        """
        self.assertIn(
            SANCTIONED_EXCLUSION,
            self.patterns,
            "The canopy-generated PEG parser is no longer excluded from pyscn. "
            "It is generated code, meaningless against the style and debt "
            "questions pyscn is used for here, and it has crashed the tool. "
            "Restore the exclusion, or if pyscn has since fixed the crash, "
            "remove this test in the same change and say so.",
        )

    def test_the_exclusion_is_honoured_and_not_merely_declared(self):
        """
        Given the excluded generated parser and an ordinary package module
        When pyscn is pointed at each file BY NAME
        Then the excluded one yields nothing to analyse while the ordinary one
             is scored, so the exclusion is shown taking effect rather than
             only being present in the config
        """
        pyscn = shutil.which("pyscn")
        if pyscn is None:
            self.skipTest(
                "pyscn not installed (dev-only tool, not a runtime dependency)"
            )

        excluded = REPO_ROOT / "toolguard" / "parser" / "bash_parser.py"
        ordinary = REPO_ROOT / "toolguard" / "patterns.py"
        for path in (excluded, ordinary):
            self.assertTrue(path.is_file(), f"{path} has moved; this test is stale.")

        excluded_run = _run_pyscn(pyscn, excluded)
        self.assertIn(
            NOTHING_TO_ANALYSE_MARKER,
            excluded_run.stdout + excluded_run.stderr,
            f"pyscn analysed {excluded.name} even though it is named in "
            f"exclude_patterns, so the exclusion is declared but not applied.",
        )

        # Without this control the assertion above would also pass if pyscn had
        # simply stopped accepting a file path.
        ordinary_run = _run_pyscn(pyscn, ordinary)
        self.assertIn(
            ANALYSIS_COMPLETED_MARKER,
            ordinary_run.stdout + ordinary_run.stderr,
            f"pyscn produced no score for {ordinary.name} either, so the "
            f"exclusion check above proves nothing about the exclusion.",
        )


if __name__ == "__main__":
    unittest.main()
