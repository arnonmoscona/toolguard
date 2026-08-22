"""
Unit tests for the Canopy PEG bash parser: the AST structure it produces for
operators, subshells, brace groups and command substitutions.

The assertions navigate the tree and compare what came out, because every
successful parse -- correct or not -- has a `compound_command`, a `pipeline`
and a `pipeline_element`, and `tree.text` is always the input string.
"""

import unittest

from toolguard.parser import bash_parser

SUBSHELL = "subshell"
BRACE_GROUP = "brace_group"
SIMPLE_COMMAND = "simple_command"


def statement(tree):
    """The program's first statement (the grammar labels it `compound_command`)."""
    return tree.compound_command


def operators(compound):
    """Texts of the control operators joining a compound_command's pipelines, in order."""
    return [rep.control_op.text.strip() for rep in compound.elements[1].elements]


def pipelines(compound):
    """Every pipeline of a compound_command, in order."""
    return [compound.pipeline] + [rep.pipeline for rep in compound.elements[1].elements]


def elements(pipeline):
    """Every pipeline_element of a pipeline, in order."""
    return [pipeline.pipeline_element] + [
        rep.pipeline_element for rep in pipeline.elements[1].elements
    ]


def kind(element):
    """Which pipeline_element alternative produced this node."""
    opener = element.elements[0].text if element.elements else ""
    if opener == "(":
        return SUBSHELL
    if opener == "{":
        return BRACE_GROUP
    return SIMPLE_COMMAND


def name(element):
    """The command name of a simple_command element."""
    return element.command_name.text.strip()


def tokens(element):
    """Texts of a simple command's tokens after the command name."""
    return [token.text.strip() for token in element.elements[1].elements]


def nested_commands(element):
    """A simple command's tokens that carry a parsed inner command -- $(...), `...`, <(...)."""
    return [
        token
        for token in element.elements[1].elements
        if hasattr(token, "compound_command")
    ]


def sole_element(pipeline):
    """The single pipeline_element of a one-element pipeline."""
    return elements(pipeline)[0]


def sole_command(compound):
    """The single pipeline_element of a compound_command with one pipeline."""
    return sole_element(compound.pipeline)


class TestBashParserAST(unittest.TestCase):
    """Test that the PEG parser produces correct AST structure."""

    def test_simple_command_structure(self):
        """
        Given a simple command with no operators ('ls -la')
        When it is parsed by the PEG bash parser
        Then it is one pipeline holding one simple command named 'ls', with '-la'
            as its only further token and no control operator
        """
        compound = statement(bash_parser.parse("ls -la"))
        self.assertEqual(operators(compound), [])
        self.assertEqual(len(elements(compound.pipeline)), 1)

        element = sole_command(compound)
        self.assertEqual(kind(element), SIMPLE_COMMAND)
        self.assertEqual(name(element), "ls")
        self.assertEqual(tokens(element), ["-la"])

    def test_pipe_structure(self):
        """
        Given a piped command ('cmd1 | cmd2')
        When it is parsed by the PEG bash parser
        Then the two commands are two pipeline_elements of one pipeline, and the
            pipe is not recorded as a control operator
        """
        compound = statement(bash_parser.parse("cmd1 | cmd2"))
        self.assertEqual(operators(compound), [])
        self.assertEqual(
            [name(element) for element in elements(compound.pipeline)],
            ["cmd1", "cmd2"],
        )

    def test_and_operator_structure(self):
        """
        Given a command joined by the && operator ('cmd1 && cmd2')
        When it is parsed by the PEG bash parser
        Then the compound holds two pipelines joined by one '&&' control operator
        """
        compound = statement(bash_parser.parse("cmd1 && cmd2"))
        self.assertEqual(operators(compound), ["&&"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(compound)],
            ["cmd1", "cmd2"],
        )

    def test_or_operator_structure(self):
        """
        Given a command joined by the || operator ('cmd1 || cmd2')
        When it is parsed by the PEG bash parser
        Then the compound holds two pipelines joined by one '||' control operator
        """
        compound = statement(bash_parser.parse("cmd1 || cmd2"))
        self.assertEqual(operators(compound), ["||"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(compound)],
            ["cmd1", "cmd2"],
        )

    def test_semicolon_structure(self):
        """
        Given two commands separated by a semicolon ('cmd1; cmd2')
        When it is parsed by the PEG bash parser
        Then the compound holds two pipelines joined by one ';' control operator
        """
        compound = statement(bash_parser.parse("cmd1; cmd2"))
        self.assertEqual(operators(compound), [";"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(compound)],
            ["cmd1", "cmd2"],
        )

    def test_unparseable_input_raises_parse_error(self):
        """
        Given an unterminated subshell ('(ls')
        When it is parsed by the PEG bash parser
        Then ParseError is raised rather than a partial tree being returned
        """
        # parse() has no None or partial-tree path; extract_commands' fail-open
        # depends on the raise, so it is pinned here.
        with self.assertRaises(bash_parser.ParseError):
            bash_parser.parse("(ls")


class TestSubshellParsing(unittest.TestCase):
    """Test subshell parsing."""

    def test_simple_subshell(self):
        """
        Given a simple subshell ('(ls -la)')
        When it is parsed by the PEG bash parser
        Then the pipeline_element is a subshell whose inner compound_command is
            'ls -la' without the parentheses
        """
        element = sole_command(statement(bash_parser.parse("(ls -la)")))
        self.assertEqual(kind(element), SUBSHELL)

        inner = element.compound_command
        self.assertEqual(inner.text, "ls -la")
        self.assertEqual(name(sole_command(inner)), "ls")

    def test_subshell_with_and(self):
        """
        Given a subshell containing an && operator ('(cd /tmp && ls)')
        When it is parsed by the PEG bash parser
        Then the subshell's inner compound holds 'cd' and 'ls' joined by one '&&'
        """
        element = sole_command(statement(bash_parser.parse("(cd /tmp && ls)")))
        self.assertEqual(kind(element), SUBSHELL)

        inner = element.compound_command
        self.assertEqual(inner.text, "cd /tmp && ls")
        self.assertEqual(operators(inner), ["&&"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(inner)],
            ["cd", "ls"],
        )

    def test_nested_subshell(self):
        """
        Given nested subshells ('((ls))')
        When it is parsed by the PEG bash parser
        Then the outer subshell's only element is itself a subshell '(ls)',
            whose own only element is the command 'ls'
        """
        outer = sole_command(statement(bash_parser.parse("((ls))")))
        self.assertEqual(kind(outer), SUBSHELL)
        self.assertEqual(outer.compound_command.text, "(ls)")

        inner = sole_command(outer.compound_command)
        self.assertEqual(kind(inner), SUBSHELL)
        self.assertEqual(inner.compound_command.text, "ls")
        self.assertEqual(name(sole_command(inner.compound_command)), "ls")

    def test_subshell_in_compound(self):
        """
        Given a subshell joined to another command by && ('(rm file) && echo done')
        When it is parsed by the PEG bash parser
        Then one '&&' joins a subshell containing 'rm file' to the simple command
            'echo done'
        """
        compound = statement(bash_parser.parse("(rm file) && echo done"))
        self.assertEqual(operators(compound), ["&&"])

        left, right = (sole_element(pipeline) for pipeline in pipelines(compound))
        self.assertEqual(kind(left), SUBSHELL)
        self.assertEqual(left.compound_command.text, "rm file")
        self.assertEqual(kind(right), SIMPLE_COMMAND)
        self.assertEqual(name(right), "echo")
        self.assertEqual(tokens(right), ["done"])


class TestBraceGroupParsing(unittest.TestCase):
    """Test brace group parsing."""

    def test_simple_brace_group(self):
        """
        Given a simple brace group ('{ cmd1; }')
        When it is parsed by the PEG bash parser
        Then the pipeline_element is a brace group whose inner compound is the
            single command 'cmd1'
        """
        element = sole_command(statement(bash_parser.parse("{ cmd1; }")))
        self.assertEqual(kind(element), BRACE_GROUP)

        inner = element.compound_command
        self.assertEqual(inner.text.strip(), "cmd1;")
        self.assertEqual(operators(inner), [])
        self.assertEqual(name(sole_command(inner)), "cmd1")

    def test_brace_group_with_multiple_commands(self):
        """
        Given a brace group with multiple commands ('{ cmd1; cmd2; }')
        When it is parsed by the PEG bash parser
        Then its inner compound holds 'cmd1' and 'cmd2' joined by one ';'
        """
        element = sole_command(statement(bash_parser.parse("{ cmd1; cmd2; }")))
        self.assertEqual(kind(element), BRACE_GROUP)

        inner = element.compound_command
        self.assertEqual(inner.text.strip(), "cmd1; cmd2;")
        self.assertEqual(operators(inner), [";"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(inner)],
            ["cmd1", "cmd2"],
        )

    def test_nested_brace_groups(self):
        """
        Given nested brace groups ('{ { cmd1; }; }')
        When it is parsed by the PEG bash parser
        Then the outer brace group's only element is the brace group '{ cmd1; }',
            whose own only element is the command 'cmd1'
        """
        outer = sole_command(statement(bash_parser.parse("{ { cmd1; }; }")))
        self.assertEqual(kind(outer), BRACE_GROUP)
        self.assertEqual(outer.compound_command.text.strip(), "{ cmd1; };")

        inner = sole_command(outer.compound_command)
        self.assertEqual(kind(inner), BRACE_GROUP)
        self.assertEqual(inner.compound_command.text.strip(), "cmd1;")
        self.assertEqual(name(sole_command(inner.compound_command)), "cmd1")


class TestCommandSubstitutionParsing(unittest.TestCase):
    """Test command substitution parsing."""

    def test_simple_dollar_paren(self):
        """
        Given a command with a $(...) command substitution ('echo $(cat file)')
        When it is parsed by the PEG bash parser
        Then 'echo' carries one substitution token whose body is parsed as the
            command 'cat file', not kept as an opaque word
        """
        element = sole_command(statement(bash_parser.parse("echo $(cat file)")))
        self.assertEqual(name(element), "echo")

        substitutions = nested_commands(element)
        self.assertEqual([token.text for token in substitutions], ["$(cat file)"])
        inner = substitutions[0].compound_command
        self.assertEqual(inner.text, "cat file")
        self.assertEqual(name(sole_command(inner)), "cat")

    def test_simple_backtick(self):
        """
        Given a command with a backtick substitution ('echo `ls`')
        When it is parsed by the PEG bash parser
        Then 'echo' carries one substitution token whose body is parsed as the
            command 'ls'
        """
        element = sole_command(statement(bash_parser.parse("echo `ls`")))
        self.assertEqual(name(element), "echo")

        substitutions = nested_commands(element)
        self.assertEqual([token.text for token in substitutions], ["`ls`"])
        inner = substitutions[0].compound_command
        self.assertEqual(inner.text, "ls")
        self.assertEqual(name(sole_command(inner)), "ls")

    def test_nested_substitution(self):
        """
        Given a nested command substitution ('echo $(cat $(find .))')
        When it is parsed by the PEG bash parser
        Then the outer substitution's body is the command 'cat $(find .)', which
            itself carries a substitution whose body is the command 'find .'
        """
        element = sole_command(statement(bash_parser.parse("echo $(cat $(find .))")))

        outer = nested_commands(element)[0].compound_command
        self.assertEqual(outer.text, "cat $(find .)")

        cat = sole_command(outer)
        self.assertEqual(name(cat), "cat")
        inner = nested_commands(cat)[0].compound_command
        self.assertEqual(inner.text, "find .")
        self.assertEqual(name(sole_command(inner)), "find")


class TestControlStructureParsing(unittest.TestCase):
    """Test that control structures keep their parts in the tree."""

    def test_while_condition_is_in_the_tree(self):
        """
        Given a while loop whose condition is a command
            ('while rm -rf /tmp/x; do :; done')
        When it is parsed by the PEG bash parser
        Then the statement is a while_loop whose ctrl_condition is the command
            'rm -rf /tmp/x', separate from the ':' body
        """
        # The condition survives parsing; dropping it is a defect of the
        # extractor rather than of the grammar (TOO-45 proposed ticket 19, P1).
        loop = statement(bash_parser.parse("while rm -rf /tmp/x; do :; done"))
        self.assertTrue(hasattr(loop, "ctrl_condition"))
        self.assertEqual(loop.ctrl_condition.text.strip(), "rm -rf /tmp/x;")

        condition = sole_command(loop.ctrl_condition)
        self.assertEqual(name(condition), "rm")
        self.assertEqual(tokens(condition), ["-rf", "/tmp/x"])
        self.assertEqual(loop.do_clause.ctrl_body.text.strip(), ":;")


class TestMixedConstructs(unittest.TestCase):
    """Test mixed constructs."""

    def test_subshell_with_pipe(self):
        """
        Given a subshell containing a pipe ('(cat file | grep pattern)')
        When it is parsed by the PEG bash parser
        Then the subshell's inner pipeline holds 'cat' and 'grep' as two elements
        """
        element = sole_command(
            statement(bash_parser.parse("(cat file | grep pattern)"))
        )
        self.assertEqual(kind(element), SUBSHELL)

        inner = element.compound_command
        self.assertEqual(operators(inner), [])
        self.assertEqual(
            [name(part) for part in elements(inner.pipeline)], ["cat", "grep"]
        )

    def test_brace_with_and(self):
        """
        Given a brace group containing an && operator ('{ cmd1 && cmd2; }')
        When it is parsed by the PEG bash parser
        Then its inner compound holds 'cmd1' and 'cmd2' joined by one '&&'
        """
        element = sole_command(statement(bash_parser.parse("{ cmd1 && cmd2; }")))
        self.assertEqual(kind(element), BRACE_GROUP)

        inner = element.compound_command
        self.assertEqual(inner.text.strip(), "cmd1 && cmd2;")
        self.assertEqual(operators(inner), ["&&"])
        self.assertEqual(
            [name(sole_element(pipeline)) for pipeline in pipelines(inner)],
            ["cmd1", "cmd2"],
        )

    def test_substitution_in_subshell(self):
        """
        Given a command substitution nested inside a subshell ('(echo $(cat file))')
        When it is parsed by the PEG bash parser
        Then the subshell contains the command 'echo' carrying a substitution
            whose body is the command 'cat file'
        """
        element = sole_command(statement(bash_parser.parse("(echo $(cat file))")))
        self.assertEqual(kind(element), SUBSHELL)

        echo = sole_command(element.compound_command)
        self.assertEqual(name(echo), "echo")
        inner = nested_commands(echo)[0].compound_command
        self.assertEqual(inner.text, "cat file")
        self.assertEqual(name(sole_command(inner)), "cat")


def _is_comment(node):
    """A comment node's only identity: the `hash`/`body` labels the grammar gives it."""
    return hasattr(node, "hash") and hasattr(node, "body")


class TestCommentParsing(unittest.TestCase):
    """The grammar's own `comment` rule (TOO-45 item 105) -- not a lexical pre-pass."""

    def test_trailing_comment_is_its_own_labelled_node(self):
        """
        Given a command followed by a trailing comment ('echo hi # note')
        When it is parsed by the PEG bash parser
        Then the argument list's last token is a comment node carrying the
            full '# note' text, and it is the only comment-labelled token
        """
        element = sole_command(statement(bash_parser.parse("echo hi # note")))
        arg_tokens = element.elements[1].elements
        comments = [t for t in arg_tokens if _is_comment(t)]
        self.assertEqual([c.text for c in comments], ["# note"])

    def test_comment_only_input_parses(self):
        """
        Given an input consisting only of a comment ('# only a comment')
        When it is parsed by the PEG bash parser
        Then parsing succeeds (comment_only_program) instead of raising ParseError
        """
        bash_parser.parse("# only a comment")

    def test_quoted_hash_is_not_a_comment_node(self):
        """
        Given a '#' inside a single-quoted argument ("echo '# quoted'")
        When it is parsed by the PEG bash parser
        Then no comment-labelled node appears anywhere in the tree
        """
        tree = bash_parser.parse("echo '# quoted'")

        def has_comment(node):
            if node is None:
                return False
            if _is_comment(node):
                return True
            return any(has_comment(c) for c in getattr(node, "elements", None) or [])

        self.assertFalse(has_comment(tree))

    def test_mid_word_hash_is_not_a_comment_node(self):
        """
        Given a '#' embedded mid-word, not at a word boundary ('echo a#b')
        When it is parsed by the PEG bash parser
        Then the argument is a single token 'a#b' and carries no comment node
        """
        element = sole_command(statement(bash_parser.parse("echo a#b")))
        arg_tokens = element.elements[1].elements
        self.assertEqual([t.text.strip() for t in arg_tokens], ["a#b"])
        self.assertFalse(any(_is_comment(t) for t in arg_tokens))


if __name__ == "__main__":
    unittest.main()
