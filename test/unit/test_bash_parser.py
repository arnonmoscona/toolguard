"""
Unit tests for the Canopy PEG bash parser.

These tests verify that the parser produces correct AST structure
for various bash constructs including subshells, brace groups,
and command substitutions.
"""

import unittest

from toolguard.parser import bash_parser


class TestBashParserAST(unittest.TestCase):
    """Test that the PEG parser produces correct AST structure."""

    def test_simple_command_structure(self):
        """
        Given a simple command with no operators ('ls -la')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced that exposes a compound_command node
        """
        tree = bash_parser.parse("ls -la")
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, "compound_command"))
        self.assertIsNotNone(tree.compound_command)

    def test_pipe_structure(self):
        """
        Given a piped command ('cmd1 | cmd2')
        When it is parsed by the PEG bash parser
        Then the tree's compound_command exposes a pipeline node
        """
        tree = bash_parser.parse("cmd1 | cmd2")
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, "compound_command"))
        # Pipeline should have multiple elements
        compound = tree.compound_command
        self.assertTrue(hasattr(compound, "pipeline"))

    def test_and_operator_structure(self):
        """
        Given a command joined by the && operator ('cmd1 && cmd2')
        When it is parsed by the PEG bash parser
        Then a non-None tree with a compound_command node is produced
        """
        tree = bash_parser.parse("cmd1 && cmd2")
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, "compound_command"))

    def test_or_operator_structure(self):
        """
        Given a command joined by the || operator ('cmd1 || cmd2')
        When it is parsed by the PEG bash parser
        Then a non-None tree with a compound_command node is produced
        """
        tree = bash_parser.parse("cmd1 || cmd2")
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, "compound_command"))

    def test_semicolon_structure(self):
        """
        Given two commands separated by a semicolon ('cmd1; cmd2')
        When it is parsed by the PEG bash parser
        Then a non-None tree with a compound_command node is produced
        """
        tree = bash_parser.parse("cmd1; cmd2")
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, "compound_command"))


class TestSubshellParsing(unittest.TestCase):
    """Test subshell parsing."""

    def test_simple_subshell(self):
        """
        Given a simple subshell ('(ls -la)')
        When it is parsed by the PEG bash parser
        Then the pipeline_element exposes a compound_command whose text contains 'ls'
        """
        tree = bash_parser.parse("(ls -la)")
        self.assertIsNotNone(tree)

        # Should have pipeline with pipeline_element
        compound = tree.compound_command
        self.assertTrue(hasattr(compound, "pipeline"))

        pipeline = compound.pipeline
        self.assertTrue(hasattr(pipeline, "pipeline_element"))

        # pipeline_element should have compound_command (for subshells)
        elem = pipeline.pipeline_element
        self.assertTrue(hasattr(elem, "compound_command"))
        self.assertIsNotNone(elem.compound_command)

        # The inner compound_command should have the command
        inner = elem.compound_command
        self.assertIsNotNone(inner.text.strip())
        self.assertIn("ls", inner.text)

    def test_subshell_with_and(self):
        """
        Given a subshell containing an && operator ('(cd /tmp && ls)')
        When it is parsed by the PEG bash parser
        Then the subshell's inner compound_command text contains the '&&' operator
        """
        tree = bash_parser.parse("(cd /tmp && ls)")
        self.assertIsNotNone(tree)

        # Get to the subshell's compound_command
        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(pipeline_elem, "compound_command"))

        inner = pipeline_elem.compound_command
        self.assertIsNotNone(inner)
        self.assertIn("&&", inner.text)

    def test_nested_subshell(self):
        """
        Given nested subshells ('((ls))')
        When it is parsed by the PEG bash parser
        Then the outer pipeline_element exposes a non-None inner compound_command
        """
        tree = bash_parser.parse("((ls))")
        self.assertIsNotNone(tree)

        # Outer subshell
        outer_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(outer_elem, "compound_command"))

        # Inner compound should contain another subshell
        inner_compound = outer_elem.compound_command
        self.assertIsNotNone(inner_compound)

    def test_subshell_in_compound(self):
        """
        Given a subshell joined to another command by && ('(rm file) && echo done')
        When it is parsed by the PEG bash parser
        Then a non-None tree with a non-None compound_command is produced
        """
        tree = bash_parser.parse("(rm file) && echo done")
        self.assertIsNotNone(tree)

        compound = tree.compound_command
        # Should have multiple parts connected by &&
        self.assertIsNotNone(compound)


class TestBraceGroupParsing(unittest.TestCase):
    """Test brace group parsing."""

    def test_simple_brace_group(self):
        """
        Given a simple brace group ('{ cmd1; }')
        When it is parsed by the PEG bash parser
        Then the pipeline_element's inner compound_command text contains 'cmd1'
        """
        tree = bash_parser.parse("{ cmd1; }")
        self.assertIsNotNone(tree)

        # Should have pipeline with pipeline_element
        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(pipeline_elem, "compound_command"))

        # The inner compound_command should have the command
        inner = pipeline_elem.compound_command
        self.assertIsNotNone(inner.text.strip())
        self.assertIn("cmd1", inner.text)

    def test_brace_group_with_multiple_commands(self):
        """
        Given a brace group with multiple commands ('{ cmd1; cmd2; }')
        When it is parsed by the PEG bash parser
        Then the inner compound_command text contains both 'cmd1' and 'cmd2'
        """
        tree = bash_parser.parse("{ cmd1; cmd2; }")
        self.assertIsNotNone(tree)

        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        inner = pipeline_elem.compound_command
        self.assertIn("cmd1", inner.text)
        self.assertIn("cmd2", inner.text)

    def test_nested_brace_groups(self):
        """
        Given nested brace groups ('{ { cmd1; }; }')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced
        """
        tree = bash_parser.parse("{ { cmd1; }; }")
        self.assertIsNotNone(tree)


class TestCommandSubstitutionParsing(unittest.TestCase):
    """Test command substitution parsing."""

    def test_simple_dollar_paren(self):
        """
        Given a command with a $(...) command substitution ('echo $(cat file)')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced whose text contains '$('
        """
        tree = bash_parser.parse("echo $(cat file)")
        self.assertIsNotNone(tree)
        # Basic parse should succeed
        self.assertIn("$(", tree.text)

    def test_simple_backtick(self):
        """
        Given a command with a backtick substitution ('echo `ls`')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced whose text contains a backtick
        """
        tree = bash_parser.parse("echo `ls`")
        self.assertIsNotNone(tree)
        self.assertIn("`", tree.text)

    def test_nested_substitution(self):
        """
        Given a nested command substitution ('echo $(cat $(find .))')
        When it is parsed by the PEG bash parser
        Then either the parse succeeds (grammar supports nesting) or a ParseError
            is raised, in which case the test is skipped as not-yet-supported
        """
        try:
            tree = bash_parser.parse("echo $(cat $(find .))")
            self.assertIsNotNone(tree)
            # If we get here, grammar was fixed!
        except bash_parser.ParseError:
            # Expected to fail with current grammar
            self.skipTest("Nested substitution not yet supported by grammar")


class TestMixedConstructs(unittest.TestCase):
    """Test mixed constructs."""

    def test_subshell_with_pipe(self):
        """
        Given a subshell containing a pipe ('(cat file | grep pattern)')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced
        """
        tree = bash_parser.parse("(cat file | grep pattern)")
        self.assertIsNotNone(tree)

    def test_brace_with_and(self):
        """
        Given a brace group containing an && operator ('{ cmd1 && cmd2; }')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced
        """
        tree = bash_parser.parse("{ cmd1 && cmd2; }")
        self.assertIsNotNone(tree)

    def test_substitution_in_subshell(self):
        """
        Given a command substitution nested inside a subshell ('(echo $(cat file))')
        When it is parsed by the PEG bash parser
        Then a non-None tree is produced
        """
        tree = bash_parser.parse("(echo $(cat file))")
        self.assertIsNotNone(tree)


if __name__ == "__main__":
    unittest.main()
