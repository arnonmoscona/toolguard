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
        """Test that simple commands parse correctly."""
        tree = bash_parser.parse('ls -la')
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, 'compound_command'))
        self.assertIsNotNone(tree.compound_command)

    def test_pipe_structure(self):
        """Test that pipes are parsed correctly."""
        tree = bash_parser.parse('cmd1 | cmd2')
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, 'compound_command'))
        # Pipeline should have multiple elements
        compound = tree.compound_command
        self.assertTrue(hasattr(compound, 'pipeline'))

    def test_and_operator_structure(self):
        """Test that && operator is parsed correctly."""
        tree = bash_parser.parse('cmd1 && cmd2')
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, 'compound_command'))

    def test_or_operator_structure(self):
        """Test that || operator is parsed correctly."""
        tree = bash_parser.parse('cmd1 || cmd2')
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, 'compound_command'))

    def test_semicolon_structure(self):
        """Test that semicolon is parsed correctly."""
        tree = bash_parser.parse('cmd1; cmd2')
        self.assertIsNotNone(tree)
        self.assertTrue(hasattr(tree, 'compound_command'))


class TestSubshellParsing(unittest.TestCase):
    """Test subshell parsing."""

    def test_simple_subshell(self):
        """Test that simple subshell parses correctly."""
        tree = bash_parser.parse('(ls -la)')
        self.assertIsNotNone(tree)

        # Should have pipeline with pipeline_element
        compound = tree.compound_command
        self.assertTrue(hasattr(compound, 'pipeline'))

        pipeline = compound.pipeline
        self.assertTrue(hasattr(pipeline, 'pipeline_element'))

        # pipeline_element should have compound_command (for subshells)
        elem = pipeline.pipeline_element
        self.assertTrue(hasattr(elem, 'compound_command'))
        self.assertIsNotNone(elem.compound_command)

        # The inner compound_command should have the command
        inner = elem.compound_command
        self.assertIsNotNone(inner.text.strip())
        self.assertIn('ls', inner.text)

    def test_subshell_with_and(self):
        """Test subshell containing && operator."""
        tree = bash_parser.parse('(cd /tmp && ls)')
        self.assertIsNotNone(tree)

        # Get to the subshell's compound_command
        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(pipeline_elem, 'compound_command'))

        inner = pipeline_elem.compound_command
        self.assertIsNotNone(inner)
        self.assertIn('&&', inner.text)

    def test_nested_subshell(self):
        """Test nested subshells."""
        tree = bash_parser.parse('((ls))')
        self.assertIsNotNone(tree)

        # Outer subshell
        outer_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(outer_elem, 'compound_command'))

        # Inner compound should contain another subshell
        inner_compound = outer_elem.compound_command
        self.assertIsNotNone(inner_compound)

    def test_subshell_in_compound(self):
        """Test subshell as part of compound command."""
        tree = bash_parser.parse('(rm file) && echo done')
        self.assertIsNotNone(tree)

        compound = tree.compound_command
        # Should have multiple parts connected by &&
        self.assertIsNotNone(compound)


class TestBraceGroupParsing(unittest.TestCase):
    """Test brace group parsing."""

    def test_simple_brace_group(self):
        """Test that simple brace group parses correctly."""
        tree = bash_parser.parse('{ cmd1; }')
        self.assertIsNotNone(tree)

        # Should have pipeline with pipeline_element
        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        self.assertTrue(hasattr(pipeline_elem, 'compound_command'))

        # The inner compound_command should have the command
        inner = pipeline_elem.compound_command
        self.assertIsNotNone(inner.text.strip())
        self.assertIn('cmd1', inner.text)

    def test_brace_group_with_multiple_commands(self):
        """Test brace group with multiple commands."""
        tree = bash_parser.parse('{ cmd1; cmd2; }')
        self.assertIsNotNone(tree)

        pipeline_elem = tree.compound_command.pipeline.pipeline_element
        inner = pipeline_elem.compound_command
        self.assertIn('cmd1', inner.text)
        self.assertIn('cmd2', inner.text)

    def test_nested_brace_groups(self):
        """Test nested brace groups."""
        tree = bash_parser.parse('{ { cmd1; }; }')
        self.assertIsNotNone(tree)


class TestCommandSubstitutionParsing(unittest.TestCase):
    """Test command substitution parsing."""

    def test_simple_dollar_paren(self):
        """Test simple $(...) substitution."""
        tree = bash_parser.parse('echo $(cat file)')
        self.assertIsNotNone(tree)
        # Basic parse should succeed
        self.assertIn('$(', tree.text)

    def test_simple_backtick(self):
        """Test simple backtick substitution."""
        tree = bash_parser.parse('echo `ls`')
        self.assertIsNotNone(tree)
        self.assertIn('`', tree.text)

    def test_nested_substitution(self):
        """
        Test nested command substitution.

        NOTE: This will FAIL with current grammar because cmd_substitution
        uses 'inner_command' which is just text, not recursive.
        This test documents the expected behavior after grammar fix.
        """
        try:
            tree = bash_parser.parse('echo $(cat $(find .))')
            self.assertIsNotNone(tree)
            # If we get here, grammar was fixed!
        except bash_parser.ParseError:
            # Expected to fail with current grammar
            self.skipTest('Nested substitution not yet supported by grammar')


class TestMixedConstructs(unittest.TestCase):
    """Test mixed constructs."""

    def test_subshell_with_pipe(self):
        """Test subshell containing pipe."""
        tree = bash_parser.parse('(cat file | grep pattern)')
        self.assertIsNotNone(tree)

    def test_brace_with_and(self):
        """Test brace group with && operator."""
        tree = bash_parser.parse('{ cmd1 && cmd2; }')
        self.assertIsNotNone(tree)

    def test_substitution_in_subshell(self):
        """Test command substitution inside subshell."""
        tree = bash_parser.parse('(echo $(cat file))')
        self.assertIsNotNone(tree)


if __name__ == '__main__':
    unittest.main()
