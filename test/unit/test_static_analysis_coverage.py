"""
Guards that `pyscn` actually analyses the whole package.

`pyscn analyze` reports a file it cannot parse as a WARNING on stderr and then
carries on, excluding that file from every metric it computes. The exit code
stays 0 and the summary looks complete. That is the failure this module exists
to make loud.

It was not hypothetical: a single ``except A, B, C:`` clause (Python 3.14's
parenthesis-free multi-exception form, with three names) made pyscn drop
``toolguard/install_provenance.py`` entirely, so a health score, a complexity
average and a duplication percentage were all computed over 58 of 59 modules
while presenting as a whole-package result. Nothing failed; one line of stderr
was the only signal.

The point is deliberately NOT "that syntax is banned". The next construct pyscn
cannot parse will be a different one, and this test does not need to know what
it is.
"""

import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYSCN_CONFIG = REPO_ROOT / ".pyscn.toml"

#: The one file the project deliberately keeps away from pyscn. It is the
#: canopy-generated PEG parser: meaningless against the style/debt questions
#: pyscn is used for here, and it has crashed the tool outright. The exclusion
#: lives in `.pyscn.toml`; this test only pins that it is still there, so that
#: removing it produces a failing test rather than a crashing analysis run.
SANCTIONED_EXCLUSION = "**/bash_parser.py"


class TestPyscnAnalysesEveryModule(unittest.TestCase):
    """pyscn must not silently drop a module from its metrics."""

    def test_pyscn_reports_no_parse_failures(self):
        """
        Given the toolguard package and pyscn's configured exclusions
        When `pyscn analyze toolguard` runs over the package
        Then it reports no parse failures, so its metrics cover every
             non-excluded module rather than an unannounced subset
        """
        pyscn = shutil.which("pyscn")
        if pyscn is None:
            self.skipTest(
                "pyscn not installed (dev-only tool, not a runtime dependency)"
            )

        result = subprocess.run(
            [pyscn, "analyze", "toolguard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr

        # Match on the behaviour, not on a specific message: any line naming a
        # file it could not read means that file left the analysis.
        offending = [
            line.strip()
            for line in combined.splitlines()
            if "Failed to parse" in line or "syntax errors found" in line
        ]
        self.assertEqual(
            offending,
            [],
            "pyscn could not parse one or more files and EXCLUDED them from every "
            "metric it reports, while still exiting 0 and printing a summary that "
            "looks complete. Either make the file parseable (a named tuple of "
            "exception types is one way to avoid syntax pyscn's grammar lacks), or "
            "-- if it genuinely should not be analysed -- add it to "
            "`.pyscn.toml`'s exclude_patterns WITH a reason, so the omission is "
            f"visible instead of silent. Offending output: {offending}",
        )


class TestSanctionedPyscnExclusion(unittest.TestCase):
    """The one deliberate exclusion must stay deliberate and stay visible."""

    def test_generated_parser_is_still_excluded(self):
        """
        Given the canopy-generated PEG parser, which pyscn cannot analyse
        When `.pyscn.toml`'s exclude_patterns are read
        Then the generated parser is still listed, so a future edit that drops
             it fails here rather than crashing an analysis run
        """
        config = tomllib.loads(PYSCN_CONFIG.read_text(encoding="utf-8"))
        patterns = config.get("analysis", {}).get("exclude_patterns", [])
        if not patterns:
            # The section name is pyscn's, not ours; find it wherever it lives
            # rather than hard-coding a path that a pyscn upgrade could move.
            for section in config.values():
                if isinstance(section, dict) and "exclude_patterns" in section:
                    patterns = section["exclude_patterns"]
                    break

        self.assertIn(
            SANCTIONED_EXCLUSION,
            patterns,
            "The canopy-generated PEG parser is no longer excluded from pyscn. "
            "It is generated code, meaningless against the style and debt "
            "questions pyscn is used for here, and it has crashed the tool. "
            "Restore the exclusion, or if pyscn has since fixed the crash, "
            "remove this test in the same change and say so.",
        )


if __name__ == "__main__":
    unittest.main()
