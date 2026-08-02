"""
Unit tests for toolguard.tools.environment_audit (TOO-19).

Covers the PYTHONPATH-shadowing finding: silent in the normal case (no
PYTHONPATH, or one with no shadowing entry) and a single HIGH finding when a
shadowing entry is present, following the same "silent unless the specific
loosened condition is measured" pattern as
test_tools_takeover_audit.py's loose-undecidable-fallback coverage.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.tools.danger import Severity
from toolguard.tools.environment_audit import audit_environment


class TestAuditEnvironment(unittest.TestCase):
    """audit_environment() -- the PYTHONPATH-shadow security-audit finding."""

    def test_no_pythonpath_is_silent(self):
        """
        Given PYTHONPATH is unset
        When audit_environment runs
        Then it returns no findings -- the normal case must never nag
        """
        self.assertEqual(audit_environment({}), [])

    def test_pythonpath_with_no_shadow_entry_is_silent(self):
        """
        Given PYTHONPATH is set but contains no directory with its own
        toolguard/ package
        When audit_environment runs
        Then it returns no findings
        """
        with TemporaryDirectory() as d:
            self.assertEqual(audit_environment({"PYTHONPATH": d}), [])

    def test_shadowing_entry_produces_one_high_finding(self):
        """
        Given PYTHONPATH contains a directory holding its own toolguard/ package
        When audit_environment runs
        Then it returns exactly one HIGH finding naming that entry, with a
        stable finding_id and non-empty remediation
        """
        with TemporaryDirectory() as d:
            pkg = Path(d) / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")

            findings = audit_environment({"PYTHONPATH": d})

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.finding_id, "pythonpath-shadows-hook")
        self.assertEqual(finding.severity, Severity.HIGH)
        self.assertIn(d, finding.description)
        self.assertTrue(finding.remediation)
        self.assertTrue(finding.impact)

    def test_defaults_to_os_environ_when_env_not_given(self):
        """
        Given no explicit env mapping is passed and PYTHONPATH is unset in
        the real environment
        When audit_environment runs
        Then it delegates to os.environ and returns no findings
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(audit_environment(), [])


if __name__ == "__main__":
    unittest.main()
