"""Tests for foreign inline-code detection.

``_detect_foreign_inline_code`` (in :mod:`toolguard.parser.command_extractor`)
decides whether a leaf command gets the ``ask_floor`` security control --
forcing human review of foreign (non-bash) inline code such as
``python -c "..."``.
"""

import unittest

from toolguard.parser.command_extractor import (
    LeafCommand,
    _detect_foreign_inline_code,
)
from toolguard.parser.multiline import extract_structured


class TestForeignInlineCodeBaseline(unittest.TestCase):
    """Plain executor-then-flag forms, plus negative cases guarding over-detection."""

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

    def test_absolute_path_to_interpreter_detected(self):
        """
        Given `/usr/bin/python3 -c "code"` -- the interpreter named by an
            absolute path rather than by a bare name
        When _detect_foreign_inline_code inspects it
        Then the path is stripped to its basename and it is recognised (True)
        """
        self.assertTrue(_detect_foreign_inline_code('/usr/bin/python3 -c "import os"'))

    def test_versioned_interpreter_detected(self):
        """
        Given `python3.13 -c "code"` -- a version suffix on a known
            interpreter family, which no enumerated name matches
        When _detect_foreign_inline_code inspects it
        Then the family prefix is recognised (True), with no version list to maintain
        """
        self.assertTrue(_detect_foreign_inline_code('python3.13 -c "import os"'))

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

    def test_name_merely_starting_with_an_interpreter_name_not_flagged(self):
        """
        Given `pythonic -c foo` -- a command whose name only starts with a
            recognised interpreter family
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged (False): a family prefix must be followed by a
            non-letter, so the version-suffix rule cannot swallow other commands
        """
        self.assertFalse(_detect_foreign_inline_code("pythonic -c foo"))

    def test_inline_flag_of_a_different_executor_not_flagged(self):
        """
        Given `python -e "code"` -- an inline-code flag that belongs to node
            and perl, not to python
        When _detect_foreign_inline_code inspects it
        Then it is NOT flagged (False): the flag table is consulted per
            executor rather than as one pooled set of letters
        """
        self.assertFalse(_detect_foreign_inline_code('python -e "import os"'))


class TestForeignInlineCodeBypasses(unittest.TestCase):
    """Flag forms that hide the inline-code flag: intervening, attached and bundled."""

    def test_python_intervening_dash_u_flag(self):
        """
        Given `python -u -c "code"` (an intervening -u flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python -u -c "import os"'))

    def test_python_intervening_dash_capital_b_flag(self):
        """
        Given `python -B -c "code"` (an intervening -B flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python -B -c "import os"'))

    def test_python_intervening_dash_capital_i_flag(self):
        """
        Given `python -I -c "code"` (an intervening -I flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python -I -c "import os"'))

    def test_python3_intervening_dash_capital_o_flag(self):
        """
        Given `python3 -O -c "code"` (an intervening -O flag before -c)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python3 -O -c "import os"'))

    def test_node_intervening_long_flag(self):
        """
        Given `node --experimental-vm-modules -e "code"` (an intervening
            long-form flag before -e)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
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
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('perl -w -e "print 1"'))

    def test_ruby_intervening_dash_w_flag(self):
        """
        Given `ruby -w -e "code"` (an intervening -w flag before -e)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('ruby -w -e "puts 1"'))

    def test_python_attached_flag_no_space(self):
        """
        Given `python -cimport os` (the -c flag with the code attached
            directly, no separating space or quote)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code("python -cimport os"))

    def test_python_attached_flag_with_quote(self):
        """
        Given `python -c'import os'` (the -c flag with the code attached
            via a leading quote, no separating space)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code("python -c'import os'"))

    def test_python_combined_short_flags(self):
        """
        Given `python -uc "code"` (combined short flags: -u and -c bundled
            into a single token)
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('python -uc "import os"'))

    def test_node_attached_dash_e_flag(self):
        """
        Given `node -e'console.log(1)'` -- the attached form on an executor
            whose inline flag is -e rather than -c
        When _detect_foreign_inline_code inspects it
        Then it is recognised (True): the attached/bundled forms are not
            specific to -c
        """
        self.assertTrue(_detect_foreign_inline_code("node -e'console.log(1)'"))

    def test_perl_combined_short_flags(self):
        """
        Given `perl -we 'code'` (combined short flags -w and -e in one token)
        When _detect_foreign_inline_code inspects it
        Then it is recognised (True)
        """
        self.assertTrue(_detect_foreign_inline_code("perl -we 'print 1'"))

    def test_uv_run_python_intervening_flag(self):
        """
        Given `uv run python -u -c "code"` -- a wrapped executor AND an
            intervening flag, the form this repo's own `Bash(uv run *)` allow
            would otherwise let past the ASK floor
        When _detect_foreign_inline_code inspects it
        Then it is recognised as foreign inline code (True)
        """
        self.assertTrue(_detect_foreign_inline_code('uv run python -u -c "import os"'))


class TestForeignInlineCodeMissedForms(unittest.TestCase):
    """Commands that carry foreign inline code and are NOT floored.

    Every test here states the required behaviour and is expected to FAIL
    against current code. Each is a way to run inline code past the ASK floor.
    Do not weaken these to match what the detector does today.
    """

    def test_deep_short_flag_bundle(self):
        """
        Given `python -uBIc "code"` -- three short flags bundled ahead of -c,
            one more than the token pattern allows before the code letter
        When _detect_foreign_inline_code inspects it
        Then it must be recognised (True); bundle depth is not a security boundary
        """
        self.assertTrue(_detect_foreign_inline_code('python -uBIc "import os"'))

    def test_uppercase_inline_flag(self):
        """
        Given `perl -E 'say 1'` -- perl's other inline-code flag, which differs
            from -e only in case
        When _detect_foreign_inline_code inspects it
        Then it must be recognised (True); the code letters are matched
            case-sensitively today, so -E, php's -R and php's -B all escape
        """
        self.assertTrue(_detect_foreign_inline_code("perl -E 'say 1'"))

    def test_long_form_inline_flag(self):
        """
        Given `node --eval "code"` -- the long spelling of node's -e
        When _detect_foreign_inline_code inspects it
        Then it must be recognised (True); the flag table and its token pattern
            are short-form only, so `--eval` and node's -p escape as well
        """
        self.assertTrue(_detect_foreign_inline_code('node --eval "console.log(1)"'))

    def test_flag_taking_a_separate_value_token(self):
        """
        Given `python -X dev -c "code"`, where -X takes its value as a separate
            following token
        When _detect_foreign_inline_code inspects it
        Then it must be recognised (True); scanning stops at the first non-flag
            token, so any value-taking flag (-X, -W, node's -r, ruby's -E)
            hides the inline code behind it. Closing this needs a per-flag
            table of which flags consume a following token
        """
        self.assertTrue(_detect_foreign_inline_code('python -X dev -c "import os"'))

    def test_awk_inline_program(self):
        """
        Given `awk '{print $1}' f` -- awk's inline program, which is a bare
            argument rather than a flag value
        When _detect_foreign_inline_code inspects it
        Then it must be recognised (True). Detecting a bare program argument
            needs a rule the flag scan cannot express, so the fix direction is
            an open decision -- but the current answer is a false negative
        """
        self.assertTrue(_detect_foreign_inline_code("awk '{print $1}' f"))

    def test_awk_program_from_a_file_is_not_inline(self):
        """
        Given `awk -f prog.awk f` -- awk's -f, which reads the program FROM A
            FILE and is the opposite of inline code
        When _detect_foreign_inline_code inspects it
        Then it must NOT be flagged (False); the flag table maps awk to -f,
            which is inverted, and gawk silently disagrees with awk today
        """
        self.assertFalse(_detect_foreign_inline_code("awk -f prog.awk f"))

    def test_gawk_and_awk_agree(self):
        """
        Given the same `-f` program-file invocation spelled `awk` and `gawk`
        When _detect_foreign_inline_code inspects both
        Then they must agree; gawk is a recognised executor but has no flag
            table entry, so it takes a different path from awk
        """
        self.assertEqual(
            _detect_foreign_inline_code("awk -f prog.awk f"),
            _detect_foreign_inline_code("gawk -f prog.awk f"),
        )


class TestForeignInlineCodeOverDetection(unittest.TestCase):
    """The other direction: benign commands that must not be floored.

    The executor scan is unanchored so that a wrapped interpreter is still
    found. The wrapper cases below are what a fix for the first test must not
    break.
    """

    def test_interpreter_name_as_an_argument_not_flagged(self):
        """
        Given `grep python -c file` -- `python` is grep's search pattern and
            `-c` is grep's count flag; no interpreter runs
        When _detect_foreign_inline_code inspects it
        Then it must NOT be flagged (False). Every token is tested as an
            executor and the flag scan then runs over the rest of the line, so
            this benign command is floored today. Do not weaken this test; fix
            it without breaking the two wrapper cases below
        """
        self.assertFalse(_detect_foreign_inline_code("grep python -c file"))

    def test_wrapper_before_the_interpreter_still_flagged(self):
        """
        Given `timeout 5 python -c "code"` -- a wrapper command, its own
            argument, then the real interpreter
        When _detect_foreign_inline_code inspects it
        Then it is recognised (True)
        """
        self.assertTrue(_detect_foreign_inline_code('timeout 5 python -c "import os"'))

    def test_env_assignment_before_the_interpreter_still_flagged(self):
        """
        Given `env X=1 python -c "code"`
        When _detect_foreign_inline_code inspects it
        Then it is recognised (True)
        """
        self.assertTrue(_detect_foreign_inline_code('env X=1 python -c "import os"'))


class TestInlineCodeFloorReachesTheLeaf(unittest.TestCase):
    """The floor must survive the trip from detection to the emitted leaf.

    Detection is a predicate; what governs a command is ``LeafCommand.ask_floor``.
    These assert the exact leaf list, so an empty extraction or a parse failure
    is distinguishable from the floor firing.
    """

    def test_bare_inline_code_leaf_carries_the_floor(self):
        """
        Given `python -c "import os"` on its own
        When extract_structured decomposes it
        Then it yields exactly one leaf, whole, carrying ask_floor
        """
        self.assertEqual(
            extract_structured('python -c "import os"'),
            [LeafCommand(text='python -c "import os"', ask_floor=True)],
        )

    def test_inline_code_in_an_if_condition_keeps_the_floor(self):
        """
        Given `if python -c "import os"; then :; fi` -- inline code in the
            condition of an if
        When extract_structured decomposes it
        Then the condition leaf carries ask_floor, same as the bare command
        """
        self.assertEqual(
            extract_structured('if python -c "import os"; then :; fi'),
            [
                LeafCommand(text='python -c "import os"', ask_floor=True),
                LeafCommand(text=":", ask_floor=False),
            ],
        )


class TestInlineCodeInsideSubstitution(unittest.TestCase):
    """Foreign inline code inside ``$(...)``/backtick substitution must also floor.

    The floor is a whole-leaf property: the OUTER leaf (``echo $(python -c
    ...)``) carries ``ask_floor``, not a separate leaf for the substitution --
    the substitution's own sub-commands still come from
    :func:`~toolguard.compound.decompose` via ``extract_commands``, which
    already walked ``$(...)``/backticks before this fix. See
    :mod:`toolguard.parser.command_extractor`'s ``_substitution_carries_ask_floor``.
    """

    def test_dollar_paren_substitution_carries_the_floor(self):
        """
        Given `echo $(python -c "import os")` -- foreign inline code reachable
            only through a `$(...)` substitution
        When extract_structured decomposes it
        Then the single outer leaf carries ask_floor
        """
        self.assertEqual(
            extract_structured('echo $(python -c "import os")'),
            [LeafCommand(text='echo $(python -c "import os")', ask_floor=True)],
        )

    def test_backtick_substitution_carries_the_floor(self):
        """
        Given `` echo `python -c "import os"` `` -- the same shape spelled
            with backticks
        When extract_structured decomposes it
        Then the single outer leaf carries ask_floor
        """
        self.assertEqual(
            extract_structured('echo `python -c "import os"`'),
            [LeafCommand(text='echo `python -c "import os"`', ask_floor=True)],
        )

    def test_benign_substitution_does_not_carry_the_floor(self):
        """
        Given `echo $(ls -la)` -- a substitution with no foreign executor
        When extract_structured decomposes it
        Then the leaf is NOT floored: the floor follows the substitution's
            content, not merely the presence of `$(...)`
        """
        self.assertEqual(
            extract_structured("echo $(ls -la)"),
            [LeafCommand(text="echo $(ls -la)", ask_floor=False)],
        )

    def test_nested_substitution_foreign_code_carries_the_floor(self):
        """
        Given `echo $(echo $(python -c "import os"))` -- foreign inline code
            two substitution levels deep
        When extract_structured decomposes it
        Then the outer leaf still carries ask_floor -- descent is not capped
            at one level
        """
        self.assertEqual(
            extract_structured('echo $(echo $(python -c "import os"))'),
            [LeafCommand(text='echo $(echo $(python -c "import os"))', ask_floor=True)],
        )

    def test_leading_assignment_inside_substitution_still_carries_the_floor(self):
        """
        Given `echo $(FOO=1 python -c "import os")` -- the interpreter reached
            through a leading `NAME=value` assignment inside the substitution
        When extract_structured decomposes it
        Then the outer leaf still carries ask_floor
        """
        self.assertEqual(
            extract_structured('echo $(FOO=1 python -c "import os")'),
            [LeafCommand(text='echo $(FOO=1 python -c "import os")', ask_floor=True)],
        )

    def test_substitution_in_an_if_condition_is_a_known_residual_gap(self):
        """
        Given `if echo $(python -c "import os"); then :; fi` -- foreign inline
            code inside a substitution that is itself an if condition
        When extract_structured decomposes it
        Then the condition leaf is NOT floored. Known limitation: a control
            structure's condition is matched from flattened text
            (`ctrl_condition_text`), which carries no `cmd_substs`, so this
            case is not covered by this fix
        """
        self.assertEqual(
            extract_structured('if echo $(python -c "import os"); then :; fi'),
            [
                LeafCommand(text='echo $(python -c "import os")', ask_floor=False),
                LeafCommand(text=":", ask_floor=False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
