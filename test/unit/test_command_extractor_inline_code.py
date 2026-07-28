"""Characterization and regression tests for foreign inline-code detection.

TOO-19: ``_detect_foreign_inline_code`` (in
:mod:`toolguard.parser.command_extractor`) decides whether a leaf command
gets the ``ask_floor`` security control -- forcing human review of foreign
(non-bash) inline code such as ``python -c "..."``. Before this ticket the
function had ZERO direct test coverage and only inspected the single token
immediately following the executor, which allowed several trivial bypasses
(an intervening flag, an attached/bundled flag) to slip through with no
ASK floor at all.

This file is organised in two parts:

- ``TestForeignInlineCodeBaseline`` -- forms that already worked correctly
  before the fix, plus the negative cases that must stay ``False`` both
  before and after the fix (guards against over-detection).
- ``TestForeignInlineCodeBypasses`` -- the confirmed bypasses from the
  ticket. These assert the CORRECT (post-fix) behaviour and are expected to
  FAIL before the fix is applied and PASS after.
"""

import unittest

from toolguard.parser.command_extractor import _detect_foreign_inline_code


class TestForeignInlineCodeBaseline(unittest.TestCase):
    """Forms that already worked, plus negative cases guarding over-detection."""

    def test_python_dash_c_detected(self):
        """
        Given a plain `python -c "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python -c "print(1)"'))

    def test_python3_dash_c_detected(self):
        """
        Given a plain `python3 -c "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python3 -c "print(1)"'))

    def test_node_dash_e_detected(self):
        """
        Given a plain `node -e "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('node -e "console.log(1)"'))

    def test_perl_dash_e_detected(self):
        """
        Given a plain `perl -e "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('perl -e "print 1"'))

    def test_ruby_dash_e_detected(self):
        """
        Given a plain `ruby -e "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('ruby -e "puts 1"'))

    def test_php_dash_r_detected(self):
        """
        Given a plain `php -r "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('php -r "echo 1;"'))

    def test_rscript_dash_e_detected(self):
        """
        Given a plain `Rscript -e "code"` command
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('Rscript -e "print(1)"'))

    def test_uv_run_python_dash_c_detected(self):
        """
        Given `uv run python -c "code"` (executor not in first token position)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('uv run python -c "print(1)"'))

    # --- Negative cases: must stay False (guard against over-detection) ---

    def test_python_script_file_not_flagged(self):
        """
        Given `python script.py` (no inline code flag at all)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged as inline code (False)
        """
        self.assertFalse(_detect_foreign_inline_code("python script.py"))

    def test_python_script_with_dash_c_as_script_arg_not_flagged(self):
        """
        Given `python script.py -c foo` where `-c` is an argument TO THE SCRIPT
            (script.py is the first non-flag token, so anything after it
            belongs to the script, not to the python interpreter)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged as inline code (False)
        """
        self.assertFalse(_detect_foreign_inline_code("python script.py -c foo"))

    def test_python_dash_m_module_with_dash_c_arg_not_flagged(self):
        """
        Given `python -m mymod -c foo` where `-c` is an argument to the
            MODULE (mymod is a non-flag token following -m, so scanning
            must stop there)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged as inline code (False)
        """
        self.assertFalse(_detect_foreign_inline_code("python -m mymod -c foo"))

    def test_ls_dash_c_not_a_foreign_executor(self):
        """
        Given `ls -c` (not a foreign interpreter at all)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged as inline code (False)
        """
        self.assertFalse(_detect_foreign_inline_code("ls -c"))

    def test_git_commit_message_not_flagged(self):
        """
        Given `git commit -m "x"` (not a foreign interpreter)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged as inline code (False)
        """
        self.assertFalse(_detect_foreign_inline_code('git commit -m "x"'))


class TestForeignInlineCodeBypasses(unittest.TestCase):
    """Confirmed bypasses from the TOO-19 ticket -- must be True post-fix."""

    def test_python_intervening_dash_u_flag(self):
        """
        Given `python -u -c "code"` (an intervening -u flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('python -u -c "import os"'))

    def test_python_intervening_dash_capital_b_flag(self):
        """
        Given `python -B -c "code"` (an intervening -B flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('python -B -c "import os"'))

    def test_python_intervening_dash_capital_i_flag(self):
        """
        Given `python -I -c "code"` (an intervening -I flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('python -I -c "import os"'))

    def test_python3_intervening_dash_capital_o_flag(self):
        """
        Given `python3 -O -c "code"` (an intervening -O flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('python3 -O -c "import os"'))

    def test_node_intervening_long_flag(self):
        """
        Given `node --experimental-vm-modules -e "code"` (an intervening
            long-form flag before -e)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(
            _detect_foreign_inline_code(
                'node --experimental-vm-modules -e "console.log(1)"'
            )
        )

    def test_perl_intervening_dash_w_flag(self):
        """
        Given `perl -w -e "code"` (an intervening -w flag before -e)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('perl -w -e "print 1"'))

    def test_ruby_intervening_dash_w_flag(self):
        """
        Given `ruby -w -e "code"` (an intervening -w flag before -e)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('ruby -w -e "puts 1"'))

    def test_python_attached_flag_no_space(self):
        """
        Given `python -cimport os` (the -c flag with the code attached
            directly, no separating space or quote)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code("python -cimport os"))

    def test_python_attached_flag_with_quote(self):
        """
        Given `python -c'import os'` (the -c flag with the code attached
            via a leading quote, no separating space)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code("python -c'import os'"))

    def test_python_combined_short_flags(self):
        """
        Given `python -uc "code"` (combined short flags: -u and -c bundled
            into a single token)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('python -uc "import os"'))

    def test_uv_run_python_intervening_flag(self):
        """
        Given `uv run python -u -c "code"` (the real-world case: this repo's
            own live config allows `Bash(uv run *)`, so this combination was a
            complete, silent security-control bypass)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True) -- previously a bypass
        """
        self.assertTrue(_detect_foreign_inline_code('uv run python -u -c "import os"'))

    def test_python_dash_capital_x_dev_dash_c_KNOWN_LIMITATION(self):
        """
        Given `python -X dev -c "code"` (the -X flag takes its VALUE ("dev")
            as a separate, following token -- structurally indistinguishable,
            under the "stop scanning at the first non-flag token" rule
            mandated for -m, from `python -m mymod -c foo` where the token
            after the flag must NOT be treated as part of the interpreter
            invocation)
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged (False) -- this is a KNOWN, REPORTED residual
            gap, not a silent regression. See the TOO-19 implementation report
            for the full analysis: distinguishing "-X dev" from "-m mymod"
            requires a per-flag table of which flags consume a following
            value-token without changing execution context, which was judged
            out of scope for this fix (flagged for the user to decide).
        """
        self.assertFalse(_detect_foreign_inline_code('python -X dev -c "import os"'))


if __name__ == "__main__":
    unittest.main()
