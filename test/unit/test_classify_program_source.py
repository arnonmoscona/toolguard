"""Tests for the program-source classifier.

``classify_program_source`` (in :mod:`toolguard.parser.command_extractor`)
answers a binary visibility question for a leaf command: is its executable
material a file, or not (TOO-28 spec 4.3). It is the classifier a rule's
``program_source`` guard consumes; :mod:`test_rule_entry` and
:mod:`test_permission_resolution` cover the guard itself.
"""

import unittest

from toolguard.constants import PROGRAM_SOURCE_FILE, PROGRAM_SOURCE_NOT_FILE
from toolguard.parser.command_extractor import classify_program_source


class TestClassifyProgramSourceFile(unittest.TestCase):
    """Commands whose executable material is a file, across interpreter families."""

    def test_python_positional_script_is_a_file(self):
        """
        Given `python script.py`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(
            classify_program_source("python script.py"), PROGRAM_SOURCE_FILE
        )

    def test_python_value_letters_flag_is_stepped_over_before_the_positional(self):
        """
        Given `python -X foo script.py`, where -X's value ('foo') is a
            separate token that must be stepped over
        When classify_program_source inspects it
        Then the positional script.py is still correctly read as a file,
            not misread as the value of -X
        """
        self.assertEqual(
            classify_program_source("python -X foo script.py"), PROGRAM_SOURCE_FILE
        )

    def test_awk_program_file_flag_is_a_file(self):
        """
        Given `awk -f script.awk`
        When classify_program_source inspects it
        Then the material is a file, via program_file_letters
        """
        self.assertEqual(
            classify_program_source("awk -f script.awk"), PROGRAM_SOURCE_FILE
        )

    def test_awk_redirected_from_a_file_is_a_file(self):
        """
        Given `awk < script.awk`, a redirect rather than a -f flag
        When classify_program_source inspects it
        Then the material is still a file -- the question is where the
            material is, not how it arrived, and this takes priority over
            awk's bare_program positional rule
        """
        self.assertEqual(
            classify_program_source("awk < script.awk"), PROGRAM_SOURCE_FILE
        )

    def test_php_program_file_flag_is_a_file(self):
        """
        Given `php -f script.php`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(
            classify_program_source("php -f script.php"), PROGRAM_SOURCE_FILE
        )

    def test_bash_positional_script_is_a_file(self):
        """
        Given `bash script.sh`, a bash-family member with no flag at all
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(classify_program_source("bash script.sh"), PROGRAM_SOURCE_FILE)

    def test_bash_dash_e_is_a_file_not_inline(self):
        """
        Given `bash -e script.sh`, where -e is bash's real exit-on-error
            flag, not an inline-code flag
        When classify_program_source inspects it
        Then the material is a file -- misreading -e via the broad default
            executor flags (which use 'cer' as inline_letters) would
            wrongly call this not_file
        """
        self.assertEqual(
            classify_program_source("bash -e script.sh"), PROGRAM_SOURCE_FILE
        )

    def test_node_positional_script_is_a_file(self):
        """
        Given `node script.js`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(classify_program_source("node script.js"), PROGRAM_SOURCE_FILE)

    def test_perl_positional_script_is_a_file(self):
        """
        Given `perl script.pl`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(classify_program_source("perl script.pl"), PROGRAM_SOURCE_FILE)

    def test_ruby_positional_script_is_a_file(self):
        """
        Given `ruby script.rb`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(classify_program_source("ruby script.rb"), PROGRAM_SOURCE_FILE)

    def test_rscript_positional_script_is_a_file(self):
        """
        Given `Rscript script.R`
        When classify_program_source inspects it
        Then the material is a file
        """
        self.assertEqual(
            classify_program_source("Rscript script.R"), PROGRAM_SOURCE_FILE
        )


class TestClassifyProgramSourceNotFile(unittest.TestCase):
    """Commands whose executable material is inline, stdin, or unrecognized -- the negative direction that gives the file cases meaning."""

    def test_python_dash_c_is_not_a_file(self):
        """
        Given `python -c "print(1)"`
        When classify_program_source inspects it
        Then the material is not a file -- a file-requiring guard must NOT
            fire here
        """
        self.assertEqual(
            classify_program_source('python -c "print(1)"'), PROGRAM_SOURCE_NOT_FILE
        )

    def test_python_value_letters_flag_then_inline_flag_is_not_a_file(self):
        """
        Given `python -X foo -c "print(1)"`
        When classify_program_source inspects it
        Then the material is not a file -- stepping over -X's value must not
            prevent -c from being seen
        """
        self.assertEqual(
            classify_program_source('python -X foo -c "print(1)"'),
            PROGRAM_SOURCE_NOT_FILE,
        )

    def test_awk_inline_program_is_not_a_file(self):
        """
        Given `awk 'BEGIN{print 1}'`, awk's bare_program positional
        When classify_program_source inspects it
        Then the material is not a file
        """
        self.assertEqual(
            classify_program_source("awk 'BEGIN{print 1}'"), PROGRAM_SOURCE_NOT_FILE
        )

    def test_bash_dash_c_is_not_a_file(self):
        """
        Given `bash -c "echo hi"`
        When classify_program_source inspects it
        Then the material is not a file
        """
        self.assertEqual(
            classify_program_source('bash -c "echo hi"'), PROGRAM_SOURCE_NOT_FILE
        )

    def test_no_positional_is_not_a_file(self):
        """
        Given `python` alone, with no positional at all (REPL/stdin)
        When classify_program_source inspects it
        Then the material is not a file
        """
        self.assertEqual(classify_program_source("python"), PROGRAM_SOURCE_NOT_FILE)

    def test_dash_alone_is_not_a_file(self):
        """
        Given `python -`, the conventional "read from stdin" marker
        When classify_program_source inspects it
        Then the material is not a file
        """
        self.assertEqual(classify_program_source("python -"), PROGRAM_SOURCE_NOT_FILE)

    def test_unrecognized_executor_is_not_a_file(self):
        """
        Given a command with no recognized foreign executor at all
        When classify_program_source inspects it
        Then it defaults to not_file, matching the ask-floor's existing bias
            toward treating unresolvable material as visible
        """
        self.assertEqual(
            classify_program_source("grep python -c file"), PROGRAM_SOURCE_NOT_FILE
        )


if __name__ == "__main__":
    unittest.main()
